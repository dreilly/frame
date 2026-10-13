#!/usr/bin/env python3
"""Load the approved, guarded MS33 boot patch into RAM via FEL, then execute.

Without --execute: host validation ONLY, no device access.
With --execute: apply/restore may WRITE THE FRAME'S BOOT PARTITION.
Example: python3 -I scripts/a33-uboot/load-ms33-writer.py apply --execute
Device must already be back in FEL (power cycle with the trigger card inserted).
After execution UMS is still read-only. Run the separate Terminal verifier before
returning to normal boot. User approval is required for apply or restore.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
FEL = ROOT/'diagnostics/sunxi-tools-src/sunxi-fel'
PATCH = ROOT/'diagnostics/ms33-adb-patch'
BUILD = ROOT/'diagnostics/ms33-writer-out'
SID = '0461872a:a0088204:acf77697:00000000'
HELPER_SHA = '9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a'
OLD_SHA = '437f65ffb4b80ea6db3a4642bbc91a38210e21bee4a2a9c202856b72132ea560'
NEW_SHA = '0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
RAM_READ_CHUNK = 512 * 1024  # sunxi-tools receives have a per-transfer 10s timeout.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate(mode):
    original_path = ROOT/'backups/ms33-firmware/boot.img'
    patched_path = PATCH/'patched-boot.img'
    helper_path = BUILD/'u-boot-sunxi-with-spl.bin'
    script_path = PATCH/f'writer/{mode}.scr'
    original,patched,helper,script = (x.read_bytes() for x in
                                     (original_path,patched_path,helper_path,script_path))
    require(sha(original)==OLD_SHA and len(original)==16777216, 'Wrong original boot image')
    require(sha(patched)==NEW_SHA and len(patched)==16777216, 'Wrong approved patched boot image')
    require(sha(helper)==HELPER_SHA, 'Wrong guarded helper binary')
    require(original[1024:10168320]==patched[1024:10168320] and
            original[14911488:]==patched[14911488:], 'Changes outside approved boot ranges')
    manifest = json.loads((PATCH/'writer/manifest.json').read_text())
    require(manifest['sid']==SID and manifest['helper_sha256']==HELPER_SHA, 'Wrong manifest identity')
    require(manifest['entry_address']==0x4a000000 and manifest['script_address']==0x47000000,
            'Wrong execution/script address')
    require(sha(script)==manifest['scripts'][mode]['sha256'] and
            len(script)==manifest['scripts'][mode]['bytes'], 'Script checksum/length mismatch')
    # Independently reconstruct the reviewed script, not merely its editable manifest.
    spec=importlib.util.spec_from_file_location('prepare',Path(__file__).with_name('prepare-ms33-writer.py'))
    prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    prefix=(ROOT/'backups/ms33-emmc-prefix.bin').read_bytes()
    probe=json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    require(len(prefix)==4194304 and sha(prefix)==probe['prefix_sha256'], 'Wrong identity prefix')
    expected=prepare.script_image(prepare.commands(mode,original,patched,prefix).encode())
    require(script==expected, 'Script is not exactly the reviewed guard sequence')
    # Validate the legacy firmware payload placed in RAM by sunxi-fel spl.
    header=bytearray(helper[32768:32832])
    magic,hcrc,_,size,load,entry,dcrc=struct.unpack_from('>7I',header)
    struct.pack_into('>I',header,4,0)
    main=helper[32832:32832+size]
    require(magic==0x27051956 and zlib.crc32(header)==hcrc and zlib.crc32(main)==dcrc,
            'Helper legacy image checksum mismatch')
    require(load==entry==0x4a000000 and main==(BUILD/'u-boot.bin').read_bytes(),
            'Wrong main U-Boot address/content')
    return helper_path, [(0x4a000000,BUILD/'u-boot.bin',sha(main)),
                         (0x41000000,original_path,OLD_SHA),
                         (0x43000000,patched_path,NEW_SHA),
                         (0x47000000,script_path,sha(script))]


def fel(*args, timeout=120):
    result=subprocess.run([str(FEL),'--sid',SID,*map(str,args)],capture_output=True,text=True,timeout=timeout)
    require(result.returncode==0, f'FEL command failed: {result.stdout} {result.stderr}')
    if result.stdout.strip():
        print(result.stdout.strip(),flush=True)
    return result.stdout


def ram_sha256(address, length, session, read_function=None):
    """Read bounded chunks; verify exact lengths and hash the complete RAM range."""
    reader = fel if read_function is None else read_function
    fd,name=tempfile.mkstemp(prefix='readback-',dir=session);os.close(fd)
    readback=Path(name)
    digest=hashlib.sha256()
    try:
        for offset in range(0,length,RAM_READ_CHUNK):
            size=min(RAM_READ_CHUNK,length-offset)
            reader('read',hex(address+offset),hex(size),readback)
            data=readback.read_bytes()
            require(len(data)==size,f'Short RAM readback at {address+offset:#x}')
            digest.update(data)
            if (offset//RAM_READ_CHUNK+1)%4==0 or offset+size==length:
                print(f'  RAM readback {(offset+size)*100//length}%',flush=True)
    finally:
        readback.unlink(missing_ok=True)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['apply','restore','check'])
    parser.add_argument('--execute',action='store_true',help='Execute in device RAM; apply/restore write boot flash')
    args=parser.parse_args()
    helper,payloads=validate(args.mode)
    print(f'Host checks passed for {args.mode}; helper and approved boot hashes match.',flush=True)
    if not args.execute:
        print('Host validation ONLY. No device access. --execute is required.')
        return
    version=fel('version',timeout=10)
    require('soc=00001667(A33)' in version, 'Unexpected SoC')
    os.umask(0o077)
    session=PATCH/'writer'/f'fel-{args.mode}-{time.time_ns()}'
    session.mkdir(mode=0o700)
    report={'mode':args.mode,'sid':SID,'helper_sha256':HELPER_SHA,'ram_verified':[],
            'execution_requested':False,'flash_result':'NOT_EXECUTED'}
    (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Loading SPL/main U-Boot without executing main U-Boot yet.',flush=True)
    fel('spl',helper)
    for index,(address,path,expected_sha) in enumerate(payloads):
        if index:
            print(f'Loading RAM payload {path.name} at {address:#x}',flush=True)
            fel('write',hex(address),path)
        length=path.stat().st_size
        print(f'Verifying RAM readback {path.name}: {length} bytes',flush=True)
        require(ram_sha256(address,length,session)==expected_sha,
                f'RAM readback differs: {path.name}; NOT executing')
        report['ram_verified'].append({'file':path.name,'address':address,'bytes':length,'sha256':expected_sha})
        (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    # Nothing can write flash before this final execution request. U-Boot is
    # loaded but has not run; SPL has only initialized hardware and returned FEL.
    print(f'All RAM payloads verified. Executing guarded {args.mode}. Do not disconnect power.',flush=True)
    report['execution_requested']=True
    report['flash_result']='PENDING_TERMINAL_VERIFICATION'
    (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    fel('exec','0x4a000000',timeout=30)
    print('Execution requested. Wait for read-only UMS, then run the Terminal verifier.')
    print(f'Report: {session}/report.json')


if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as error:
        raise SystemExit(f'STOP: {error}. Keep recovery files and FEL card; do not normal-boot an unverified image.')
