#!/usr/bin/env python3
"""Verify full boot partition twice via READ-ONLY UMS. Never writes the frame.

Run in the owner's Terminal (raw disk access):
  sudo /opt/homebrew/bin/python3 -I scripts/a33-uboot/verify-ms33-boot-macos.py diskN 31268536320 patched
Or use "original" after a restore/check operation. Re-identify diskN each time.
Reports exact SHA-256, verifies Android image ID, and only marks applied after
independent reads both equal the approved complete patched boot image.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PATCH=ROOT/'diagnostics/ms33-adb-patch'
CHUNK=4194304
OFFSET=88080384
SIZE=16777216
ORIGINAL_SHA='437f65ffb4b80ea6db3a4642bbc91a38210e21bee4a2a9c202856b72132ea560'
PATCHED_SHA='0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'


def require(condition,message):
    if not condition:raise ValueError(message)


def import_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(fd,offset,size):
    data=os.pread(fd,size,offset)
    require(len(data)==size,f'Short read at {offset}: {len(data)} != {size}')
    return data


def report_file(path,report):
    os.umask(0o077)
    path.write_text(json.dumps(report,indent=2)+'\n')
    if 'SUDO_UID' in os.environ:
        os.chown(path,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disk');parser.add_argument('device_bytes',type=int)
    parser.add_argument('expected',choices=['patched','original'])
    args=parser.parse_args()
    require(os.geteuid()==0,'Run with sudo in your Terminal')
    require(args.device_bytes==31268536320,'Wrong expected device size')
    prefix=(ROOT/'backups/ms33-emmc-prefix.bin').read_bytes()
    probe=json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    require(len(prefix)==CHUNK and sha(prefix)==probe['prefix_sha256'],'Saved prefix is invalid')
    original=(ROOT/'backups/ms33-firmware/boot.img').read_bytes()
    patched=(PATCH/'patched-boot.img').read_bytes()
    require(sha(original)==ORIGINAL_SHA and sha(patched)==PATCHED_SHA,'Reference image hash mismatch')
    emmc=import_file('emmc',HERE/'emmc-macos.py')
    guard=import_file('guard',HERE/'backup-firmware-macos.py')
    guard.partition_info(args.disk,'s6',OFFSET,SIZE)
    raw=emmc.open_disk(args.disk,args.device_bytes)
    fd=os.open(raw,os.O_RDONLY)
    started=time.monotonic()
    try:
        require(read(fd,0,CHUNK)==prefix,'Live device does not match saved identity prefix')
        passes=[]
        for index in range(2):
            pieces=[]
            for position in range(0,SIZE,CHUNK):
                pieces.append(read(fd,OFFSET+position,CHUNK))
                print(f'Boot verification read {index+1}: {(position+CHUNK)*100//SIZE}%',flush=True)
            passes.append(b''.join(pieces))
    finally:os.close(fd)
    require(passes[0]==passes[1],'Independent boot reads differ; do not normal-boot')
    actual=sha(passes[0])
    matches='patched' if passes[0]==patched else 'original' if passes[0]==original else 'unknown'
    report={'device_bytes':args.device_bytes,'disk':args.disk,'expected':args.expected,
            'actual_sha256':actual,'matches':matches,'independent_read_passes':2,
            'elapsed_seconds':time.monotonic()-started}
    report_file(PATCH/'write-verification.json',report)
    if matches=='unknown':
        raise ValueError('Boot differs from both approved images. Keep FEL card and power; restore required')
    if matches!=args.expected:
        raise ValueError(f'Boot is {matches}, not {args.expected}; patch may have been refused or automatically rolled back')
    image=import_file('image',HERE/'make-ms33-adb-patch.py')
    image.parse_boot(passes[0])
    plan=json.loads((PATCH/'plan.json').read_text())
    plan['applied']=matches=='patched'
    plan['last_verified_sha256']=actual
    report_file(PATCH/'plan.json',plan)
    print(f'VERIFIED: full {matches} boot partition matches byte-for-byte twice.')
    print(f'SHA-256: {actual}')
    print('Android image ID verified. No writes to the frame by this verifier.')
    print('Ready for normal boot after safely disconnecting USB/DC and removing the FEL card.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError) as error:
        sys.exit(f'STOP: {error}')
