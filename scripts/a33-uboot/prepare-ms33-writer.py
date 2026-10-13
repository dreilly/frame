#!/usr/bin/env python3
"""Prepare guarded apply/check/restore RAM scripts OFFLINE. No device access."""
import hashlib
import json
import os
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT/'diagnostics/ms33-adb-patch'
BUILD = ROOT/'diagnostics/ms33-writer-out'
OUT = PATCH/'writer'
ORIG = 0x41000000
NEW = 0x43000000
READ = 0x45000000
PREFIX = 0x46000000
SCRIPT = 0x47000000
BOOT = 172032
OFFSET = 10168320
SLOT = 4743168
SIZE = 16777216
ORIGINAL_SHA = '437f65ffb4b80ea6db3a4642bbc91a38210e21bee4a2a9c202856b72132ea560'
PATCHED_SHA = '0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33'
WRITER_SHA = '9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a'
SID = '0461872a:a0088204:acf77697:00000000'


def crc(data):
    return f'{zlib.crc32(data):08x}'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def script_image(text):
    body = struct.pack('>II',len(text),0)+text
    header = bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(body),0,0,
                                  zlib.crc32(body),5,2,6,0,b'MS33 guarded boot patch'))
    struct.pack_into('>I',header,4,zlib.crc32(header))
    return bytes(header)+body


def read_boot():
    return f'mmc read {READ:#x} {BOOT:#x} {SIZE//512:#x}'


def compare(address):
    return f'cmp.b {address:#x} {READ:#x} {SIZE:#x}'


def write_and_verify(address):
    """Ramdisk first, header last, full image comparison last. All && chained."""
    return ' && '.join([
        f'mmc write {address+OFFSET:#x} {BOOT+OFFSET//512:#x} {SLOT//512:#x}',
        f'mmc read {READ+OFFSET:#x} {BOOT+OFFSET//512:#x} {SLOT//512:#x}',
        f'cmp.b {address+OFFSET:#x} {READ+OFFSET:#x} {SLOT:#x}',
        f'mmc write {address:#x} {BOOT:#x} 0x2',
        read_boot(), compare(address)])


def commands(mode, original, patched, prefix):
    guards = ' && '.join([
        f'crc32 -v {ORIG:#x} {SIZE:#x} {crc(original)}',
        f'crc32 -v {NEW:#x} {SIZE:#x} {crc(patched)}',
        'mmc dev 1 0',
        f'mmc read {PREFIX:#x} 0x0 {len(prefix)//512:#x}',
        f'crc32 -v {PREFIX:#x} {len(prefix):#x} {crc(prefix)}',
        read_boot()])
    lines = [f'# MS33 {mode}: host loads originals, patched boot and this script into RAM.',
             '# Never writes bootloader/recovery/system/userdata. UMS remains read-only.',
             f'if {guards}; then']
    if mode in ('apply','check'):
        lines += [f'  if {compare(ORIG)}; then']
        if mode == 'check':
            lines += ['    echo MS33_CHECK_PASSED_NO_WRITES']
        else:
            lines += [f'    if {write_and_verify(NEW)}; then',
                      '      echo MS33_APPLY_VERIFIED',
                      '    else',
                      '      echo MS33_APPLY_FAILED_ATTEMPTING_ORIGINAL_RESTORE',
                      f'      if {write_and_verify(ORIG)}; then',
                      '        echo MS33_ORIGINAL_RESTORED',
                      '      else',
                      '        echo MS33_RESTORE_FAILED_KEEP_FEL_CARD_AND_RECOVERY_FILES',
                      '      fi', '    fi']
        lines += ['  else','    echo MS33_ORIGINAL_MISMATCH_NO_WRITES','  fi']
    else:
        # Allow undo after a partial write, not only after an intact patched image.
        # Refuse to undo if ANY byte outside the approved write ranges differs.
        middle = f'cmp.b {ORIG+1024:#x} {READ+1024:#x} {OFFSET-1024:#x}'
        tail = f'cmp.b {ORIG+OFFSET+SLOT:#x} {READ+OFFSET+SLOT:#x} {SIZE-OFFSET-SLOT:#x}'
        lines += [f'  if {middle} && {tail}; then',
                  f'    if {write_and_verify(ORIG)}; then',
                  '      echo MS33_ORIGINAL_RESTORED',
                  '    else','      echo MS33_RESTORE_FAILED_KEEP_FEL_CARD_AND_RECOVERY_FILES','    fi',
                  '  else','    echo MS33_UNRELATED_BOOT_CHANGES_UNDO_REFUSED','  fi']
    lines += ['else','  echo MS33_PAYLOAD_OR_DISK_READ_GUARD_FAILED_NO_WRITES','fi','']
    return '\n'.join(lines)


def main():
    if not __debug__:
        raise ValueError('Optimized Python disables safety checks; use python3 -I without -O')
    if OUT.exists():
        raise ValueError('Writer directory exists; refusing to overwrite')
    plan = json.loads((PATCH/'plan.json').read_text())
    original = (ROOT/'backups/ms33-firmware/boot.img').read_bytes()
    patched = (PATCH/'patched-boot.img').read_bytes()
    prefix = (ROOT/'backups/ms33-emmc-prefix.bin').read_bytes()
    probe = json.loads((ROOT/'diagnostics/ms33-emmc-probe.json').read_text())
    helper = (BUILD/'u-boot-sunxi-with-spl.bin').read_bytes()
    assert sha(original)==ORIGINAL_SHA==plan['original_boot_sha256']
    assert sha(patched)==PATCHED_SHA==plan['patched_boot_sha256']
    assert len(original)==len(patched)==SIZE
    assert len(prefix)==4*1024*1024 and sha(prefix)==probe['prefix_sha256']
    assert probe['total_bytes']==plan['device_bytes']==31268536320
    assert sha(helper)==WRITER_SHA
    assert plan['writes_in_order']==[
        {'sector':191892,'sectors':9264,'new':'new-ramdisk.bin','original':'orig-ramdisk.bin'},
        {'sector':172032,'sectors':2,'new':'new-header.bin','original':'orig-header.bin'}]
    assert original[1024:OFFSET]==patched[1024:OFFSET]
    assert original[OFFSET+SLOT:]==patched[OFFSET+SLOT:]
    header = helper[32768:32832]
    magic,hcrc,_,main_size,load,entry,dcrc = struct.unpack_from('>7I',header)
    h=bytearray(header);struct.pack_into('>I',h,4,0)
    main_image=helper[32832:32832+main_size]
    assert magic==0x27051956 and zlib.crc32(h)==hcrc
    assert load==entry==0x4a000000 and len(main_image)==main_size
    assert zlib.crc32(main_image)==dcrc
    assert main_image==(BUILD/'u-boot.bin').read_bytes()
    os.umask(0o077);OUT.mkdir(mode=0o700)
    manifest={'sid':SID,'helper_sha256':WRITER_SHA,'entry_address':entry,
              'original':{'address':ORIG,'bytes':SIZE,'sha256':sha(original),'crc32':crc(original)},
              'patched':{'address':NEW,'bytes':SIZE,'sha256':sha(patched),'crc32':crc(patched)},
              'prefix_crc32':crc(prefix),'script_address':SCRIPT,
              'main_uboot':{'address':load,'bytes':main_size,'sha256':sha(main_image)},
              'scripts':{}}
    for mode in ('apply','restore','check'):
        text=commands(mode,original,patched,prefix)
        image=script_image(text.encode())
        (OUT/f'{mode}.cmd').write_text(text)
        (OUT/f'{mode}.scr').write_bytes(image)
        manifest['scripts'][mode]={'bytes':len(image),'sha256':sha(image),'crc32':crc(image)}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Prepared guarded apply/check/partial-failure restore scripts OFFLINE.')
    print(f'Output: {OUT}')


if __name__=='__main__':
    main()
