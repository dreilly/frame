#!/usr/bin/env python3
"""Verify the complete TCP-ADB target (or USB-ADB base) twice via read-only UMS.

Usage:
 sudo python3 -I scripts/a33-uboot/verify-ms33-tcp-boot-macos.py diskN 31268536320 target
Use "base" after rollback. This verifier never writes the frame.
"""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PATCH=ROOT/'diagnostics/ms33-tcp-adb-patch';CHUNK=4194304;OFFSET=88080384;SIZE=16777216
BASE_SHA='0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
TARGET_SHA='b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe'
def require(c,m):
    if not c:raise ValueError(m)
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(data):return hashlib.sha256(data).hexdigest()
def read(fd,offset,size):
    data=os.pread(fd,size,offset);require(len(data)==size,f'Short read at {offset}');return data
def save(path,data):
    os.umask(0o077);path.write_text(json.dumps(data,indent=2)+'\n')
    if 'SUDO_UID' in os.environ:os.chown(path,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('disk');p.add_argument('device_bytes',type=int)
    p.add_argument('expected',choices=['target','base']);args=p.parse_args()
    require(os.geteuid()==0,'Run with sudo in your Terminal');require(args.device_bytes==31268536320,'Wrong size')
    prefix=(ROOT/'backups/ms33-emmc-prefix.bin').read_bytes();probe=json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    require(len(prefix)==CHUNK and sha(prefix)==probe['prefix_sha256'],'Invalid identity prefix')
    base=(ROOT/'diagnostics/ms33-adb-patch/patched-boot.img').read_bytes();target=(PATCH/'tcp-adb-boot.img').read_bytes()
    require(sha(base)==BASE_SHA and sha(target)==TARGET_SHA and len(base)==len(target)==SIZE,'Reference mismatch')
    emmc=load('emmc',HERE/'emmc-macos.py');guard=load('guard',HERE/'backup-firmware-macos.py')
    guard.partition_info(args.disk,'s6',OFFSET,SIZE);raw=emmc.open_disk(args.disk,args.device_bytes)
    fd=os.open(raw,os.O_RDONLY);started=time.monotonic()
    try:
        require(read(fd,0,CHUNK)==prefix,'Live device identity mismatch');passes=[]
        for index in range(2):
            pieces=[]
            for pos in range(0,SIZE,CHUNK):
                pieces.append(read(fd,OFFSET+pos,CHUNK));print(f'TCP boot verification {index+1}: {(pos+CHUNK)*100//SIZE}%',flush=True)
            passes.append(b''.join(pieces))
    finally:os.close(fd)
    require(passes[0]==passes[1],'Independent reads differ; do not normal-boot')
    actual=sha(passes[0]);matches='target' if passes[0]==target else 'base' if passes[0]==base else 'unknown'
    report={'device_bytes':args.device_bytes,'disk':args.disk,'expected':args.expected,'actual_sha256':actual,
            'matches':matches,'independent_read_passes':2,'elapsed_seconds':time.monotonic()-started}
    save(PATCH/'write-verification.json',report)
    require(matches!='unknown','Boot differs from both transition images; restore required')
    require(matches==args.expected,f'Boot is {matches}, not {args.expected}; apply may have rolled back')
    boot=load('boot',HERE/'make-ms33-adb-patch.py');boot.parse_boot(passes[0])
    plan=json.loads((PATCH/'plan.json').read_text());plan['applied']=matches=='target';plan['last_verified_sha256']=actual
    save(PATCH/'plan.json',plan)
    print(f'VERIFIED: full TCP-ADB {matches} image matches twice.')
    print('SHA-256:',actual);print('Android image ID valid. Verifier made no frame writes.')
    print('Ready to disconnect USB/DC, remove FEL card, and normal boot.')
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError) as error:sys.exit(f'STOP: {error}')
