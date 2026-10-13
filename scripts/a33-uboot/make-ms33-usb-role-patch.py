#!/usr/bin/env python3
"""Build the OFFLINE permanent local USB-ADB boot transition.

Input is the applied, independently verified temporary TCP-ADB image. Output:
  * removes every temporary TCP-ADB recovery action and sets port -1;
  * forces the broken Allwinner OTG manager to DEVICE role after boot;
  * writes DEVICE twice, two seconds apart, to outlast its final scan iteration;
  * preserves the kernel, system, vendor adbd, SELinux policy and embedded key.
Runtime testing proves this vendor adbd accepts unknown keys despite its secure
properties; this transition removes network exposure but does not claim auth.
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
BASE_DIR=ROOT/'diagnostics/ms33-tcp-adb-patch'
OUT=ROOT/'diagnostics/ms33-usb-role-patch'
BASE_SHA='b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe'
KEY_SHA='5f469650ffc98fd630939160c81a3f0e707900731250cf59c5490715b31a76cd'
BOOT_SECTOR=172032
OFFSET=10168320
SLOT=4743168
SIZE=16777216
SCRIPT_NAME=b'sbin/ms33-usb-device.sh'
ROLE_PATH=b'/sys/devices/platform/sunxi_usb_udc/otg_role'
ROLE_SCRIPT=(b'#!/system/bin/sh\n'
             b'# Writing otg_role stops the faulty VBUS/ID scanner. Its loop can finish\n'
             b'# one stale iteration after the stop request, so select DEVICE again.\n'
             b'echo 2 > /sys/devices/platform/sunxi_usb_udc/otg_role\n'
             b'sleep 2\n'
             b'echo 2 > /sys/devices/platform/sunxi_usb_udc/otg_role\n')
OLD_ACTION=(b'# Temporary diagnostic access: RSA-authenticated ADB over trusted Wi-Fi.\n'
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
NEW_ACTION=(b'# Permanent local USB ADB; vendor adbd does not enforce RSA; no network listener.\n'
            b'service ms33_usb_device /system/bin/sh /sbin/ms33-usb-device.sh\n'
            b'    class main\n'
            b'    user root\n'
            b'    group root\n'
            b'    disabled\n'
            b'    oneshot\n'
            b'\n'
            b'on property:sys.boot_completed=1\n'
            b'    stop adbd\n'
            b'    setprop service.adb.tcp.port -1\n'
            b'    setprop sys.usb.config adb\n'
            b'    start ms33_usb_device\n'
            b'    start adbd\n')

spec=importlib.util.spec_from_file_location('bootpatch',ROOT/'scripts/a33-uboot/make-ms33-adb-patch.py')
bp=importlib.util.module_from_spec(spec);spec.loader.exec_module(bp)

def require(condition,message):
    if not condition:raise ValueError(message)

def sha(data):return hashlib.sha256(data).hexdigest()

def file_record(name,data,inode,mode=0o100755):
    cpio_name=name+b'\0'
    fields=[inode,mode,0,0,1,0,len(data),0,0,0,0,len(cpio_name),0]
    header=b'070701'+b''.join(b'%08x'%n for n in fields)
    namepart=cpio_name+bytes(-(110+len(cpio_name))%4)
    return name,header,namepart,data

def build(base):
    kernel,offset,used_slot,archive=bp.parse_boot(base)
    require(offset==OFFSET and used_slot<=SLOT and OFFSET+SLOT<=len(base),'Unexpected ramdisk geometry')
    old_records,tail=bp.records(archive);old={r[0]:r for r in old_records}
    require(SCRIPT_NAME not in old,'Role helper already exists')
    require(old[b'init.sun8i.usb.rc'][3].count(OLD_ACTION)==1,'Expected TCP action not found once')
    require(b'ro.adb.secure=1\n' in old[b'default.prop'][3],'Secure ADB property absent')
    require(sha(old[b'adb_keys'][3].split()[0])==KEY_SHA,'Embedded host public key changed')
    updated=[];next_inode=max(int(r[1][6:14],16) for r in old_records)+1
    for name,header,namepart,data in old_records:
        if name==b'init.sun8i.usb.rc':
            data=data.replace(OLD_ACTION,NEW_ACTION)
            header=header[:54]+b'%08x'%len(data)+header[62:]
        if name==b'TRAILER!!!':updated.append(file_record(SCRIPT_NAME,ROLE_SCRIPT,next_inode))
        updated.append((name,header,namepart,data))
    new_archive=b''.join(bp.encode(r) for r in updated)+tail
    ramdisk=min((gzip.compress(new_archive,compresslevel=n,mtime=0) for n in range(1,10)),key=len)
    require(len(ramdisk)<=SLOT,'USB-role ramdisk does not fit original allocation')
    digest=hashlib.sha1()
    for data in (kernel,ramdisk,b''):
        digest.update(data);digest.update(struct.pack('<I',len(data)))
    target=bytearray(base);struct.pack_into('<I',target,16,len(ramdisk))
    target[576:608]=digest.digest()+bytes(12)
    target[OFFSET:OFFSET+SLOT]=ramdisk+bytes(SLOT-len(ramdisk));target=bytes(target)
    k2,o2,s2,a2=bp.parse_boot(target);new_records,t2=bp.records(a2);new={r[0]:r for r in new_records}
    require(k2==kernel and o2==OFFSET and s2<=SLOT and t2==tail,'Patched image reparse failed')
    require(set(new)-set(old)=={SCRIPT_NAME} and set(old)<=set(new),'Unexpected ramdisk file list')
    require([n for n in old if old[n]!=new[n]]==[b'init.sun8i.usb.rc'],'Unexpected existing file changes')
    require(new[b'adb_keys']==old[b'adb_keys'] and new[b'default.prop']==old[b'default.prop'],
            'ADB key or secure properties changed')
    require(new[SCRIPT_NAME][3]==ROLE_SCRIPT and int(new[SCRIPT_NAME][1][14:22],16)==0o100755,
            'Role helper differs or is not executable')
    init=new[b'init.sun8i.usb.rc'][3]
    require(b'5555' not in init and init.count(b'setprop service.adb.tcp.port -1')==2,
            'Unexpected network-ADB configuration remains in init')
    require(init.count(b'start ms33_usb_device')==1 and ROLE_SCRIPT.count(b'echo 2 > '+ROLE_PATH)==2,
            'Device-role sequence missing')
    allowed=[(16,20),(576,596)]
    require(all(base[n]==target[n] or any(lo<=n<hi for lo,hi in allowed) for n in range(OFFSET)),
            'Unexpected header/kernel change')
    require(base[OFFSET+SLOT:]==target[OFFSET+SLOT:],'Partition tail changed')
    return target,old,new

def main():
    require(__debug__,'Optimized Python disables checks');require(not OUT.exists(),'Output exists; refusing overwrite')
    base=(BASE_DIR/'tcp-adb-boot.img').read_bytes();plan0=json.loads((BASE_DIR/'plan.json').read_text())
    verify=json.loads((BASE_DIR/'write-verification.json').read_text())
    require(len(base)==SIZE and sha(base)==BASE_SHA,'Wrong TCP-ADB base image')
    require(plan0['applied'] and plan0['last_verified_sha256']==BASE_SHA,'TCP base not verified applied')
    require(verify['matches']=='target' and verify['independent_read_passes']==2 and
            verify['actual_sha256']==BASE_SHA,'TCP base lacks independent verification')
    target,old,new=build(base)
    os.umask(0o077);OUT.mkdir(mode=0o700)
    (OUT/'usb-role-boot.img').write_bytes(target)
    payloads={'base-header':base[:1024],'target-header':target[:1024],
              'base-ramdisk':base[OFFSET:OFFSET+SLOT],'target-ramdisk':target[OFFSET:OFFSET+SLOT]}
    for name,data in payloads.items():(OUT/f'{name}.bin').write_bytes(data)
    plan={'applied':False,'temporary':False,'device_bytes':31268536320,'boot_sector':BOOT_SECTOR,
          'base_boot_sha256':BASE_SHA,'target_boot_sha256':sha(target),
          'public_key_token_sha256':KEY_SHA,'embedded_key_preserved':True,
          'authentication_enforced':False,'network_adb_enabled':False,'root_enabled':False,
          'changes':['init.sun8i.usb.rc: remove TCP ADB and launch one-shot USB-role helper',
                     'sbin/ms33-usb-device.sh: stop faulty OTG scan and select DEVICE twice'],
          'unchanged':['kernel','recovery','system','sbin/adbd','SELinux policy','adb_keys','default.prop'],
          'payloads':{name:{'bytes':len(data),'sha256':sha(data),'crc32':f'{zlib.crc32(data):08x}'}
                      for name,data in payloads.items()},
          'writes_in_order':[{'sector':BOOT_SECTOR+OFFSET//512,'sectors':SLOT//512,
                              'target':'target-ramdisk.bin','rollback':'base-ramdisk.bin'},
                             {'sector':BOOT_SECTOR,'sectors':2,
                              'target':'target-header.bin','rollback':'base-header.bin'}],
          'rollback':'Restore the independently verified temporary TCP-ADB base with the guarded transition.'}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2));print(f'OFFLINE ONLY. No frame writes. Prepared {OUT}')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError) as error:sys.exit(f'STOP: {error}')
