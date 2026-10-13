#!/usr/bin/env python3
"""Load/execute the approved authenticated TCP-ADB transition through FEL.

Without --execute, validates host artifacts only. With --execute, apply/restore
may write only the two allowlisted boot ranges. The full result must afterward
be verified twice through read-only UMS before normal boot.
"""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import struct,subprocess,tempfile,time,zlib

ROOT=Path(__file__).resolve().parents[2]
FEL=ROOT/'diagnostics/sunxi-tools-src/sunxi-fel'
PATCH=ROOT/'diagnostics/ms33-tcp-adb-patch';BUILD=ROOT/'diagnostics/ms33-writer-out'
SID='0461872a:a0088204:acf77697:00000000'
HELPER_SHA='9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a'
BASE_SHA='0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
TARGET_SHA='b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe'
RAM_READ_CHUNK=512*1024

def require(condition,message):
    if not condition:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()

def validate(mode):
    base_path=ROOT/'diagnostics/ms33-adb-patch/patched-boot.img'
    target_path=PATCH/'tcp-adb-boot.img';helper_path=BUILD/'u-boot-sunxi-with-spl.bin'
    script_path=PATCH/f'writer/{mode}.scr'
    base,target,helper,script=(p.read_bytes() for p in (base_path,target_path,helper_path,script_path))
    require(len(base)==len(target)==16777216 and sha(base)==BASE_SHA and sha(target)==TARGET_SHA,
            'Wrong transition images')
    require(sha(helper)==HELPER_SHA,'Wrong guarded helper')
    require(base[1024:10168320]==target[1024:10168320] and base[14911488:]==target[14911488:],
            'Changes outside approved boot ranges')
    base_plan=json.loads((ROOT/'diagnostics/ms33-adb-patch/plan.json').read_text())
    base_verify=json.loads((ROOT/'diagnostics/ms33-adb-patch/write-verification.json').read_text())
    require(base_plan['applied'] and base_plan['last_verified_sha256']==BASE_SHA and
            base_verify['matches']=='patched' and base_verify['independent_read_passes']==2,
            'Transition base was not independently verified applied')
    manifest=json.loads((PATCH/'writer/manifest.json').read_text())
    require(manifest['sid']==SID and manifest['helper_sha256']==HELPER_SHA and
            manifest['entry_address']==0x4a000000 and manifest['script_address']==0x47000000,
            'Wrong writer manifest identity')
    require(sha(script)==manifest['scripts'][mode]['sha256'] and len(script)==manifest['scripts'][mode]['bytes'],
            'Script hash/length mismatch')
    spec=importlib.util.spec_from_file_location('prepare',Path(__file__).with_name('prepare-ms33-tcp-writer.py'))
    prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    prefix=(ROOT/'backups/ms33-emmc-prefix.bin').read_bytes()
    probe=json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    require(len(prefix)==4194304 and sha(prefix)==probe['prefix_sha256'],'Wrong identity prefix')
    expected=prepare.script_image(prepare.commands(mode,base,target,prefix).encode())
    require(script==expected,'Script differs from reviewed generator')
    header=bytearray(helper[32768:32832]);magic,hcrc,_,size,load,entry,dcrc=struct.unpack_from('>7I',header)
    struct.pack_into('>I',header,4,0);main=helper[32832:32832+size]
    require(magic==0x27051956 and zlib.crc32(header)==hcrc and zlib.crc32(main)==dcrc and
            load==entry==0x4a000000 and main==(BUILD/'u-boot.bin').read_bytes(),'Invalid helper payload')
    return helper_path,[(0x4a000000,BUILD/'u-boot.bin',sha(main)),(0x41000000,base_path,BASE_SHA),
                        (0x43000000,target_path,TARGET_SHA),(0x47000000,script_path,sha(script))]

def fel(*args,timeout=120):
    result=subprocess.run([str(FEL),'--sid',SID,*map(str,args)],capture_output=True,text=True,timeout=timeout)
    require(result.returncode==0,f'FEL failed: {result.stdout} {result.stderr}')
    if result.stdout.strip():print(result.stdout.strip(),flush=True)
    return result.stdout

def ram_sha256(address,length,session,read_function=None):
    reader=fel if read_function is None else read_function
    fd,name=tempfile.mkstemp(prefix='readback-',dir=session);os.close(fd);path=Path(name)
    digest=hashlib.sha256()
    try:
        for offset in range(0,length,RAM_READ_CHUNK):
            size=min(RAM_READ_CHUNK,length-offset)
            reader('read',hex(address+offset),hex(size),path)
            data=path.read_bytes();require(len(data)==size,f'Short RAM read at {address+offset:#x}')
            digest.update(data)
            if (offset//RAM_READ_CHUNK+1)%4==0 or offset+size==length:
                print(f'  RAM readback {(offset+size)*100//length}%',flush=True)
    finally:path.unlink(missing_ok=True)
    return digest.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['apply','restore','check'])
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    helper,payloads=validate(args.mode)
    print(f'Host checks passed for TCP-ADB {args.mode}.',flush=True)
    if not args.execute:
        print('Host validation ONLY. No device access.');return
    require('soc=00001667(A33)' in fel('version',timeout=10),'Unexpected SoC')
    os.umask(0o077);session=PATCH/'writer'/f'fel-{args.mode}-{time.time_ns()}';session.mkdir(mode=0o700)
    report={'mode':args.mode,'sid':SID,'helper_sha256':HELPER_SHA,'ram_verified':[],
            'execution_requested':False,'flash_result':'NOT_EXECUTED'}
    (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Loading SPL/main U-Boot without executing main U-Boot.',flush=True);fel('spl',helper)
    for index,(address,path,expected) in enumerate(payloads):
        if index:
            print(f'Loading {path.name} at {address:#x}',flush=True);fel('write',hex(address),path)
        print(f'Verifying RAM {path.name}: {path.stat().st_size} bytes',flush=True)
        require(ram_sha256(address,path.stat().st_size,session)==expected,f'RAM differs: {path.name}')
        report['ram_verified'].append({'file':path.name,'address':address,'bytes':path.stat().st_size,'sha256':expected})
        (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'All RAM verified. Executing guarded TCP-ADB {args.mode}. Do not disconnect.',flush=True)
    report['execution_requested']=True;report['flash_result']='PENDING_TERMINAL_VERIFICATION'
    (session/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    fel('exec','0x4a000000',timeout=30)
    print('Execution requested; wait for read-only UMS and run the TCP boot verifier.')
    print('Report:',session/'report.json')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as error:
        raise SystemExit(f'STOP: {error}. Keep FEL card/recovery files; do not boot an unverified image.')
