#!/usr/bin/env python3
"""Prepare guarded USB-ADB -> authenticated TCP-ADB scripts OFFLINE."""
import hashlib,json,os
from pathlib import Path
import struct,zlib

ROOT=Path(__file__).resolve().parents[2]
PATCH=ROOT/'diagnostics/ms33-tcp-adb-patch'
BUILD=ROOT/'diagnostics/ms33-writer-out'
OUT=PATCH/'writer'
BASE=0x41000000;TARGET=0x43000000;READ=0x45000000;PREFIX=0x46000000;SCRIPT=0x47000000
BOOT=172032;OFFSET=10168320;SLOT=4743168;SIZE=16777216
BASE_SHA='0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
TARGET_SHA='b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe'
WRITER_SHA='9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a'
SID='0461872a:a0088204:acf77697:00000000'

def crc(data):return f'{zlib.crc32(data):08x}'
def sha(data):return hashlib.sha256(data).hexdigest()

def script_image(text):
    body=struct.pack('>II',len(text),0)+text
    header=bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(body),0,0,zlib.crc32(body),5,2,6,0,b'MS33 guarded TCP ADB'))
    struct.pack_into('>I',header,4,zlib.crc32(header))
    return bytes(header)+body

def read_boot():return f'mmc read {READ:#x} {BOOT:#x} {SIZE//512:#x}'
def compare(address):return f'cmp.b {address:#x} {READ:#x} {SIZE:#x}'

def write_and_verify(address):
    return ' && '.join([f'mmc write {address+OFFSET:#x} {BOOT+OFFSET//512:#x} {SLOT//512:#x}',
      f'mmc read {READ+OFFSET:#x} {BOOT+OFFSET//512:#x} {SLOT//512:#x}',
      f'cmp.b {address+OFFSET:#x} {READ+OFFSET:#x} {SLOT:#x}',
      f'mmc write {address:#x} {BOOT:#x} 0x2',read_boot(),compare(address)])

def commands(mode,base,target,prefix):
    guards=' && '.join([f'crc32 -v {BASE:#x} {SIZE:#x} {crc(base)}',
      f'crc32 -v {TARGET:#x} {SIZE:#x} {crc(target)}','mmc dev 1 0',
      f'mmc read {PREFIX:#x} 0x0 {len(prefix)//512:#x}',
      f'crc32 -v {PREFIX:#x} {len(prefix):#x} {crc(prefix)}',read_boot()])
    lines=[f'# MS33 TCP-ADB {mode}; source is verified USB-ADB boot.',
      '# Only approved boot ramdisk/header ranges; UMS remains read-only.',f'if {guards}; then']
    if mode in ('apply','check'):
        lines += [f'  if {compare(BASE)}; then']
        if mode=='check':lines += ['    echo MS33_TCP_CHECK_PASSED_NO_WRITES']
        else:lines += [f'    if {write_and_verify(TARGET)}; then','      echo MS33_TCP_APPLY_VERIFIED','    else',
          '      echo MS33_TCP_APPLY_FAILED_ROLLING_BACK',f'      if {write_and_verify(BASE)}; then',
          '        echo MS33_USB_ADB_BASE_RESTORED','      else',
          '        echo MS33_ROLLBACK_FAILED_KEEP_FEL_CARD_AND_FILES','      fi','    fi']
        lines += ['  else','    echo MS33_USB_ADB_BASE_MISMATCH_NO_WRITES','  fi']
    else:
        middle=f'cmp.b {BASE+1024:#x} {READ+1024:#x} {OFFSET-1024:#x}'
        tail=f'cmp.b {BASE+OFFSET+SLOT:#x} {READ+OFFSET+SLOT:#x} {SIZE-OFFSET-SLOT:#x}'
        lines += [f'  if {middle} && {tail}; then',f'    if {write_and_verify(BASE)}; then',
          '      echo MS33_USB_ADB_BASE_RESTORED','    else',
          '      echo MS33_ROLLBACK_FAILED_KEEP_FEL_CARD_AND_FILES','    fi','  else',
          '    echo MS33_UNRELATED_BOOT_CHANGES_ROLLBACK_REFUSED','  fi']
    lines += ['else','  echo MS33_TCP_PAYLOAD_OR_DISK_GUARD_FAILED_NO_WRITES','fi','']
    return '\n'.join(lines)

def main():
    if not __debug__:raise ValueError('Optimized Python disables safety checks')
    if OUT.exists():raise ValueError('Writer directory exists; refusing overwrite')
    plan=json.loads((PATCH/'plan.json').read_text())
    base=(ROOT/'diagnostics/ms33-adb-patch/patched-boot.img').read_bytes()
    target=(PATCH/'tcp-adb-boot.img').read_bytes()
    prefix=(ROOT/'backups/ms33-emmc-prefix.bin').read_bytes()
    probe=json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    helper=(BUILD/'u-boot-sunxi-with-spl.bin').read_bytes()
    assert len(base)==len(target)==SIZE and sha(base)==BASE_SHA==plan['base_boot_sha256']
    assert sha(target)==TARGET_SHA==plan['target_boot_sha256']
    assert len(prefix)==4194304 and sha(prefix)==probe['prefix_sha256']
    assert probe['total_bytes']==plan['device_bytes']==31268536320 and sha(helper)==WRITER_SHA
    assert plan['writes_in_order']==[
      {'sector':191892,'sectors':9264,'target':'target-ramdisk.bin','rollback':'base-ramdisk.bin'},
      {'sector':172032,'sectors':2,'target':'target-header.bin','rollback':'base-header.bin'}]
    assert base[1024:OFFSET]==target[1024:OFFSET] and base[OFFSET+SLOT:]==target[OFFSET+SLOT:]
    header=helper[32768:32832];magic,hcrc,_,main_size,load,entry,dcrc=struct.unpack_from('>7I',header)
    h=bytearray(header);struct.pack_into('>I',h,4,0);main_image=helper[32832:32832+main_size]
    assert magic==0x27051956 and zlib.crc32(h)==hcrc and zlib.crc32(main_image)==dcrc
    assert load==entry==0x4a000000 and main_image==(BUILD/'u-boot.bin').read_bytes()
    os.umask(0o077);OUT.mkdir(mode=0o700)
    manifest={'sid':SID,'helper_sha256':WRITER_SHA,'entry_address':entry,
      'base':{'address':BASE,'bytes':SIZE,'sha256':sha(base),'crc32':crc(base)},
      'target':{'address':TARGET,'bytes':SIZE,'sha256':sha(target),'crc32':crc(target)},
      'prefix_crc32':crc(prefix),'script_address':SCRIPT,
      'main_uboot':{'address':load,'bytes':main_size,'sha256':sha(main_image)},'scripts':{}}
    for mode in ('apply','restore','check'):
        text=commands(mode,base,target,prefix);image=script_image(text.encode())
        (OUT/f'{mode}.cmd').write_text(text);(OUT/f'{mode}.scr').write_bytes(image)
        manifest['scripts'][mode]={'bytes':len(image),'sha256':sha(image),'crc32':crc(image)}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Prepared guarded TCP-ADB transition OFFLINE:',OUT)

if __name__=='__main__':main()
