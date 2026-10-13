#!/usr/bin/env python3
"""Build the OFFLINE, authenticated temporary TCP-ADB transition.

Input is the already-applied and independently verified USB-ADB boot image.
Output changes only default.prop and init.sun8i.usb.rc inside its ramdisk:
  * ro.adb.secure=1 (require Android ADB RSA authentication)
  * service.adb.tcp.port=5555 after boot, including recovery from USB "none"
It preserves the existing /adb_keys entry byte-for-byte and does not enable root.
This script never accesses the frame.
"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[2]
BASE_DIR=ROOT/'diagnostics/ms33-adb-patch'
OUT=ROOT/'diagnostics/ms33-tcp-adb-patch'
BASE_SHA='0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
KEY_SHA='5f469650ffc98fd630939160c81a3f0e707900731250cf59c5490715b31a76cd'
BOOT_SECTOR=172032
OFFSET=10168320
SLOT=4743168
SIZE=16777216
OLD_DEFAULT=b'ro.secure=1\nro.allow.mock.location=0\n'
NEW_DEFAULT=b'ro.secure=1\nro.adb.secure=1\nro.allow.mock.location=0\n'
OLD_ACTION=(b'# Local dashboard setup: authenticated USB debugging; no TCP listener.\n'
            b'on property:sys.boot_completed=1\n'
            b'    stop adbd\n'
            b'    setprop service.adb.tcp.port -1\n'
            b'    setprop sys.usb.config adb\n'
            b'    start adbd\n')
NEW_ACTION=(b'# Temporary diagnostic access: RSA-authenticated ADB over trusted Wi-Fi.\n'
            b'on property:sys.boot_completed=1\n'
            b'    stop adbd\n'
            b'    setprop service.adb.tcp.port 5555\n'
            b'    setprop sys.usb.config adb\n'
            b'    start adbd\n'
            b'\n'
            b'# Keep TCP ADB available if Android disables its broken USB gadget mode.\n'
            b'on property:sys.usb.config=none && property:sys.boot_completed=1\n'
            b'    stop adbd\n'
            b'    setprop service.adb.tcp.port 5555\n'
            b'    start adbd\n'
            b'\n'
            b'# Frameo/UsbDeviceManager may explicitly reset the TCP property.\n'
            b'on property:service.adb.tcp.port=-1 && property:sys.boot_completed=1\n'
            b'    stop adbd\n'
            b'    setprop service.adb.tcp.port 5555\n'
            b'    start adbd\n')

spec=importlib.util.spec_from_file_location('bootpatch',ROOT/'scripts/a33-uboot/make-ms33-adb-patch.py')
bp=importlib.util.module_from_spec(spec);spec.loader.exec_module(bp)


def require(condition,message):
    if not condition:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def build(base):
    kernel,offset,used_slot,archive=bp.parse_boot(base)
    require(offset==OFFSET and used_slot<=SLOT and OFFSET+SLOT<=len(base),'Unexpected ramdisk geometry')
    old_records,tail=bp.records(archive)
    old={r[0]:r for r in old_records}
    require(old[b'default.prop'][3].count(OLD_DEFAULT)==1,'Expected secure property location not found once')
    require(b'ro.adb.secure=' not in old[b'default.prop'][3],'ADB authentication property already exists')
    require(old[b'init.sun8i.usb.rc'][3].count(OLD_ACTION)==1,'Expected USB-only boot action not found once')
    require(sha(old[b'adb_keys'][3].split()[0])==KEY_SHA,'Embedded host public key changed')
    updated=[]
    for name,header,namepart,data in old_records:
        if name==b'default.prop':data=data.replace(OLD_DEFAULT,NEW_DEFAULT)
        elif name==b'init.sun8i.usb.rc':data=data.replace(OLD_ACTION,NEW_ACTION)
        if name in (b'default.prop',b'init.sun8i.usb.rc'):
            header=header[:54]+b'%08x'%len(data)+header[62:]
        updated.append((name,header,namepart,data))
    new_archive=b''.join(bp.encode(r) for r in updated)+tail
    ramdisk=min((gzip.compress(new_archive,compresslevel=n,mtime=0) for n in range(1,10)),key=len)
    require(len(ramdisk)<=SLOT,'TCP ramdisk does not fit original allocation')
    digest=hashlib.sha1()
    for data in (kernel,ramdisk,b''):
        digest.update(data);digest.update(struct.pack('<I',len(data)))
    target=bytearray(base)
    struct.pack_into('<I',target,16,len(ramdisk))
    target[576:608]=digest.digest()+bytes(12)
    target[OFFSET:OFFSET+SLOT]=ramdisk+bytes(SLOT-len(ramdisk))
    target=bytes(target)
    k2,o2,s2,a2=bp.parse_boot(target);new_records,t2=bp.records(a2)
    require(k2==kernel and o2==OFFSET and s2<=SLOT and t2==tail,'Patched image reparse failed')
    new={r[0]:r for r in new_records}
    require(set(old)==set(new),'Ramdisk file list changed')
    require([n for n in old if old[n]!=new[n]]==[b'default.prop',b'init.sun8i.usb.rc'],
            'Unexpected ramdisk file changes')
    require(new[b'adb_keys']==old[b'adb_keys'],'ADB key record changed')
    require(b'ro.adb.secure=1\n' in new[b'default.prop'][3],'Authentication property absent')
    require(new[b'init.sun8i.usb.rc'][3].count(b'setprop service.adb.tcp.port 5555')==3,
            'Expected TCP property actions absent')
    require(b'service.adb.tcp.port 0' not in new[b'init.sun8i.usb.rc'][3] and
            b'service.adb.tcp.port -1' in new[b'init.sun8i.usb.rc'][3],
            'Unexpected TCP configuration')
    allowed=[(16,20),(576,596)]
    require(all(base[n]==target[n] or any(lo<=n<hi for lo,hi in allowed) for n in range(OFFSET)),
            'Unexpected header/kernel change')
    require(base[OFFSET+SLOT:]==target[OFFSET+SLOT:],'Partition tail changed')
    return target,old,new


def main():
    require(__debug__,'Optimized Python disables checks')
    require(not OUT.exists(),'Output directory exists; refusing to overwrite')
    base=(BASE_DIR/'patched-boot.img').read_bytes()
    plan1=json.loads((BASE_DIR/'plan.json').read_text())
    verify=json.loads((BASE_DIR/'write-verification.json').read_text())
    require(len(base)==SIZE and sha(base)==BASE_SHA,'Wrong USB-ADB base image')
    require(plan1['applied'] and plan1['last_verified_sha256']==BASE_SHA,'Base plan not verified applied')
    require(verify['matches']=='patched' and verify['independent_read_passes']==2 and
            verify['actual_sha256']==BASE_SHA,'Base image lacks independent verification')
    target,old,new=build(base)
    os.umask(0o077);OUT.mkdir(mode=0o700)
    (OUT/'tcp-adb-boot.img').write_bytes(target)
    payloads={'base-header':base[:1024],'target-header':target[:1024],
              'base-ramdisk':base[OFFSET:OFFSET+SLOT],
              'target-ramdisk':target[OFFSET:OFFSET+SLOT]}
    for name,data in payloads.items():(OUT/f'{name}.bin').write_bytes(data)
    plan={'applied':False,'temporary':True,'device_bytes':31268536320,'boot_sector':BOOT_SECTOR,
          'base_boot_sha256':BASE_SHA,'target_boot_sha256':sha(target),
          'public_key_token_sha256':KEY_SHA,'authentication_required':True,
          'tcp_port':5555,'root_enabled':False,
          'changes':['default.prop: add ro.adb.secure=1',
                     'init.sun8i.usb.rc: start/restart adbd on TCP 5555 after boot'],
          'unchanged':['kernel','recovery','system','sbin/adbd','SELinux policy','adb_keys','USB patch'],
          'payloads':{name:{'bytes':len(data),'sha256':sha(data),'crc32':f'{zlib.crc32(data):08x}'}
                      for name,data in payloads.items()},
          'writes_in_order':[{'sector':BOOT_SECTOR+OFFSET//512,'sectors':SLOT//512,
                              'target':'target-ramdisk.bin','rollback':'base-ramdisk.bin'},
                             {'sector':BOOT_SECTOR,'sectors':2,
                              'target':'target-header.bin','rollback':'base-header.bin'}],
          'rollback':'Restore the independently verified USB-ADB base image using the guarded transition.'}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2))
    print(f'OFFLINE ONLY. No frame writes. Prepared {OUT}')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError) as error:sys.exit(f'STOP: {error}')
