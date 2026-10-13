#!/usr/bin/env python3
"""Prepare an OFFLINE, unit-specific USB ADB patch. Never accesses a device.

Usage: python3 -I scripts/a33-uboot/make-ms33-adb-patch.py ~/.android/adbkey.pub
Requires this unit's independently verified boot/recovery backup. Leaves kernel,
recovery, SELinux, default properties and adbd executable unchanged. Enables ADB
at boot-completion and alongside the stock photo-transfer USB mode. Adds ONLY the
host's public key; private keys are never read. Does not enable network ADB/root.

Outputs a private patched boot image plus exact original/new write ranges and an
undo plan. A separately reviewed, approved writer is required to apply it.
Legacy Android/newc parsing is adapted from wesbos/photo-frame-dashboard's
boot-patch.py at fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03, with bounds checks.
"""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backups/ms33-firmware'
OUT = ROOT / 'diagnostics/ms33-adb-patch'
EXPECTED = {'boot': '437f65ffb4b80ea6db3a4642bbc91a38210e21bee4a2a9c202856b72132ea560',
            'recovery': '98eace612f4ff5793d91a29a52989bb591bcd628095aa349d96b1d08db154e6b'}
BOOT_SECTOR = 172032
OLD_ACTION = (b'on property:sys.usb.config=mass_storage\n'
              b'    write /sys/class/android_usb/android0/enable\t0\n'
              b'    write /sys/class/android_usb/android0/idVendor\t1f3a\n'
              b'    write /sys/class/android_usb/android0/idProduct\t1000\n'
              b'    write /sys/class/android_usb/android0/functions\t${sys.usb.config}\n'
              b'    write /sys/class/android_usb/android0/enable \t1\n'
              b'    setprop sys.usb.state ${sys.usb.config}\n')
NEW_ACTION = (b'on property:sys.usb.config=mass_storage\n'
              b'    write /sys/class/android_usb/android0/enable 0\n'
              b'    write /sys/class/android_usb/android0/idVendor 1f3a\n'
              b'    write /sys/class/android_usb/android0/idProduct 1002\n'
              b'    write /sys/class/android_usb/android0/functions mass_storage,adb\n'
              b'    write /sys/class/android_usb/android0/enable 1\n'
              b'    setprop service.adb.tcp.port -1\n'
              b'    start adbd\n'
              b'    setprop sys.usb.state ${sys.usb.config}\n')
BOOT_ACTION = (b'\n# Local dashboard setup: authenticated USB debugging; no TCP listener.\n'
               b'on property:sys.boot_completed=1\n'
               b'    stop adbd\n'
               b'    setprop service.adb.tcp.port -1\n'
               b'    setprop sys.usb.config adb\n'
               b'    start adbd\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_boot(image):
    require(len(image) >= 2048 and image[:8] == b'ANDROID!', 'Not an Android image')
    kernel_size, ramdisk_size, second_size, page = (struct.unpack_from('<I', image, n)[0]
                                                   for n in (8, 16, 24, 36))
    require(page == 2048 and second_size == 0 and image[40:44] == bytes(4),
            'Unexpected legacy Android image geometry')
    pad = lambda n: (n + page - 1)//page*page
    offset = page + pad(kernel_size)
    slot = pad(ramdisk_size)
    require(kernel_size > 0 and ramdisk_size > 0 and offset + slot <= len(image),
            'Image exceeds partition')
    kernel = image[page:page+kernel_size]
    ramdisk = image[offset:offset+ramdisk_size]
    digest = hashlib.sha1()
    for data in (kernel, ramdisk, b''):
        digest.update(data)
        digest.update(struct.pack('<I', len(data)))
    require(image[576:608] == digest.digest()+bytes(12), 'Android image ID mismatch')
    require(ramdisk[:2] == b'\x1f\x8b', 'Ramdisk is not gzip')
    return kernel, offset, slot, gzip.decompress(ramdisk)


def records(archive):
    position, result, seen = 0, [], set()
    while position < len(archive):
        header = archive[position:position+110]
        require(len(header) == 110 and header[:6] == b'070701', 'Invalid newc header')
        fields = [int(header[n:n+8], 16) for n in range(6, 110, 8)]
        size, namesize = fields[6], fields[11]
        name_end = position+110+namesize
        require(0 < namesize < 4096 and name_end <= len(archive), 'Invalid newc name')
        require(archive[name_end-1] == 0, 'Missing name terminator')
        name = archive[position+110:name_end-1]
        require(name not in seen and b'\0' not in name, 'Duplicate or invalid newc name')
        seen.add(name)
        start = (name_end+3) & ~3
        end = (start+size+3) & ~3
        require(end <= len(archive), 'Truncated newc record')
        data = archive[start:start+size]
        result.append((name, header, archive[position+110:start], data))
        position = end
        if name == b'TRAILER!!!':
            require(size == 0 and not any(archive[end:]), 'Unexpected newc trailer')
            return result, archive[end:]
    raise ValueError('Missing newc trailer')


def encode(record):
    _, header, namepart, data = record
    out = header+namepart+data
    return out+bytes(-len(out) % 4)


def key_record(public, inode):
    name = b'adb_keys\0'
    fields = [inode, 0o100644, 0, 0, 1, 0, len(public), 0, 0, 0, 0, len(name), 0]
    header = b'070701'+b''.join(b'%08x' % n for n in fields)
    namepart = name+bytes(-(110+len(name)) % 4)
    return (name[:-1], header, namepart, public)


def read_public_key(path):
    require(path.name.endswith('.pub'), 'Only a .pub public-key file may be read')
    require(0 < path.stat().st_size < 8192, 'Unexpected public-key file size')
    lines = path.read_bytes().splitlines()
    require(len(lines) == 1 and len(lines[0].split()) >= 1, 'Expected one ADB public key')
    token = lines[0].split()[0]
    key = base64.b64decode(token, validate=True)
    require(len(key) == 524 and struct.unpack_from('<I', key)[0] == 64,
            'Not an Android RSA-2048 public key')
    require(struct.unpack_from('<I', key, 520)[0] == 65537, 'Unexpected RSA exponent')
    return token+b' frame-dashboard-admin\n'


def build(image, public):
    kernel, offset, slot, archive = parse_boot(image)
    original, tail = records(archive)
    files = {r[0]:r[3] for r in original}
    require(b'adb_keys' not in files, 'Existing ramdisk key; refusing to replace')
    require(b'/adb_keys' in files.get(b'file_contexts', b''), 'No adb_keys SELinux label')
    require(b'restorecon /adb_keys' in files.get(b'init.rc', b''), 'No adb_keys restorecon')
    require(files.get(b'init.sun8i.usb.rc', b'').count(OLD_ACTION) == 1,
            'Expected stock USB action not found exactly once')
    require(b'sys.boot_completed' not in files[b'init.sun8i.usb.rc'], 'Boot action already exists')
    updated = []
    next_inode = max(int(r[1][6:14], 16) for r in original)+1
    for name, header, namepart, data in original:
        if name == b'init.sun8i.usb.rc':
            data = data.replace(OLD_ACTION, NEW_ACTION)+BOOT_ACTION
            header = header[:54]+b'%08x' % len(data)+header[62:]
        if name == b'TRAILER!!!':
            updated.append(key_record(public, next_inode))
        updated.append((name, header, namepart, data))
    new_archive = b''.join(encode(r) for r in updated)+tail
    ramdisk = min((gzip.compress(new_archive, compresslevel=n, mtime=0) for n in range(1,10)), key=len)
    require(len(ramdisk) <= slot, 'Patched ramdisk does not fit original slot')
    digest = hashlib.sha1()
    for data in (kernel, ramdisk, b''):
        digest.update(data); digest.update(struct.pack('<I', len(data)))
    patched = bytearray(image)
    struct.pack_into('<I', patched, 16, len(ramdisk))
    patched[576:608] = digest.digest()+bytes(12)
    patched[offset:offset+slot] = ramdisk+bytes(slot-len(ramdisk))
    patched = bytes(patched)
    # Reparse and verify all archive records and untouched image ranges.
    k2, o2, s2, a2 = parse_boot(patched)
    require(k2 == kernel and o2 == offset and s2 <= slot,
            'Kernel changed or new ramdisk exceeds original slot')
    r2, t2 = records(a2)
    require(r2 == updated and t2 == tail, 'Archive verification failed')
    old_map = {r[0]:r for r in original}
    new_map = {r[0]:r for r in r2}
    require(set(new_map)-set(old_map) == {b'adb_keys'} and set(old_map) <= set(new_map),
            'Unexpected ramdisk file list changes')
    require([name for name in old_map if old_map[name] != new_map[name]] == [b'init.sun8i.usb.rc'],
            'Unexpected changes to existing ramdisk files')
    allowed_header = [(16,20),(576,596)]
    require(all(image[n] == patched[n] or any(lo <= n < hi for lo,hi in allowed_header)
                for n in range(offset)), 'Unexpected header or kernel changes')
    require(image[offset+slot:] == patched[offset+slot:], 'Partition tail changed')
    return patched, offset, slot


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    require(not OUT.exists(), 'Output directory already exists; refusing to overwrite')
    manifest = json.loads((SOURCE/'manifest.json').read_text())
    require(manifest['complete'], 'Backup not complete')
    images = {}
    for kind, sha in EXPECTED.items():
        data = (SOURCE/f'{kind}.img').read_bytes()
        info = manifest['partitions'][kind]
        require(info['read_passes'] == 2 and info['gzip_readback_verified'], 'Unverified backup')
        require(hashlib.sha256(data).hexdigest() == sha == info['sha256'], 'Backup hash mismatch')
        require(len(data) == info['partition_bytes'], 'Backup length mismatch')
        require(gzip.decompress((SOURCE/f'{kind}.img.gz').read_bytes()) == data, 'Gzip backup mismatch')
        parse_boot(data)
        images[kind] = data
    require(manifest['total_device_bytes'] == 31268536320, 'Wrong device size')
    require(manifest['partitions']['boot']['offset_bytes'] == BOOT_SECTOR*512,
            'Wrong boot partition offset')
    public = read_public_key(Path(sys.argv[1]).expanduser())
    old = images['boot']
    new, offset, slot = build(old, public)
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'patched-boot.img').write_bytes(new)
    payloads = {'orig-header':old[:1024], 'new-header':new[:1024],
                'orig-ramdisk':old[offset:offset+slot], 'new-ramdisk':new[offset:offset+slot]}
    for name,data in payloads.items():
        (OUT/f'{name}.bin').write_bytes(data)
    plan = {'applied':False, 'device_bytes':31268536320, 'boot_sector':BOOT_SECTOR,
            'original_boot_sha256':hashlib.sha256(old).hexdigest(),
            'patched_boot_sha256':hashlib.sha256(new).hexdigest(),
            'public_key_sha256':hashlib.sha256(public.split()[0]).hexdigest(),
            'changes':['init.sun8i.usb.rc: boot-completion ADB plus ADB in photo-transfer mode',
                       'adb_keys: authorize this Mac public key'],
            'unchanged':['kernel','recovery','default.prop','sbin/adbd','SELinux policy'],
            'root_enabled':False,'network_adb_enabled':False,
            'payloads':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                              'crc32':f'{zlib.crc32(data):08x}'} for name,data in payloads.items()},
            'writes_in_order':[{'sector':BOOT_SECTOR+offset//512,'sectors':slot//512,
                                'new':'new-ramdisk.bin','original':'orig-ramdisk.bin'},
                               {'sector':BOOT_SECTOR,'sectors':2,
                                'new':'new-header.bin','original':'orig-header.bin'}],
            'undo':'Restore original ramdisk range then original header range; reread and compare with original image.',
            'requires':'A separately reviewed write-capable RAM-only U-Boot method and explicit owner approval.'}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2))
    print(f'OFFLINE ONLY. No frame writes. Prepared {OUT}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(f'STOP: {error}')
