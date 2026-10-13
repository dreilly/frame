#!/usr/bin/env python3
"""Offline tests; real-image test uses private local backups when available."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('patch', Path(__file__).with_name('make-ms33-adb-patch.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def record(name, data, inode):
    name = name+b'\0'
    fields = [inode,0o100644,0,0,1,0,len(data),0,0,0,0,len(name),0]
    header = b'070701'+b''.join(b'%08x' % n for n in fields)
    return (name[:-1],header,name+bytes(-(110+len(name))%4),data)


def synthetic_image():
    files = [(b'file_contexts',b'/adb_keys u:object_r:adb_keys_file:s0\n'),
             (b'init.rc',b'on early-init\n    restorecon /adb_keys\n'),
             (b'init.sun8i.usb.rc',p.OLD_ACTION),
             (b'default.prop',b'ro.secure=1\nro.debuggable=0\n'),
             (b'sbin/adbd',b'unchanged executable sentinel'),
             (b'TRAILER!!!',b'')]
    archive = b''.join(p.encode(record(name,data,n+1)) for n,(name,data) in enumerate(files))+bytes(64)
    ramdisk = gzip.compress(archive,mtime=0)
    kernel = b'kernel sentinel'*16
    image = bytearray(8192)
    image[:8] = b'ANDROID!'
    for offset,value in [(8,len(kernel)),(16,len(ramdisk)),(36,2048)]:
        struct.pack_into('<I',image,offset,value)
    image[2048:2048+len(kernel)] = kernel
    image[4096:4096+len(ramdisk)] = ramdisk
    digest = hashlib.sha1()
    for data in (kernel,ramdisk,b''):
        digest.update(data);digest.update(struct.pack('<I',len(data)))
    image[576:608] = digest.digest()+bytes(12)
    return bytes(image)


class OfflinePatchTests(unittest.TestCase):
    def test_synthetic_patch(self):
        old=synthetic_image()
        new,offset,slot=p.build(old,b'public-key sentinel\n')
        self.assertEqual((offset,slot),(4096,2048))
        records,_=p.records(p.parse_boot(new)[3])
        files={r[0]:r[3] for r in records}
        self.assertEqual(files[b'default.prop'],b'ro.secure=1\nro.debuggable=0\n')
        self.assertEqual(files[b'sbin/adbd'],b'unchanged executable sentinel')
        self.assertEqual(files[b'adb_keys'],b'public-key sentinel\n')
        self.assertIn(p.BOOT_ACTION,files[b'init.sun8i.usb.rc'])
        self.assertIn(p.NEW_ACTION,files[b'init.sun8i.usb.rc'])

    def test_invalid_image_id(self):
        image=bytearray(synthetic_image());image[2048]^=1
        with self.assertRaises(ValueError):p.parse_boot(image)

    def test_truncated_image(self):
        with self.assertRaises(ValueError):p.parse_boot(synthetic_image()[:4096])

    def test_truncated_archive(self):
        archive=p.parse_boot(synthetic_image())[3]
        with self.assertRaises(ValueError):p.records(archive[:120])

    def test_duplicate_archive_name(self):
        r=record(b'duplicate',b'',1)
        with self.assertRaises(ValueError):p.records(p.encode(r)*2)

    def test_missing_usb_action(self):
        # A cryptographically valid image without the expected stock USB stanza
        # must still be rejected.
        image=synthetic_image()
        with patch.object(p,'OLD_ACTION',b'action that is not present'):
            with self.assertRaises(ValueError):p.build(image,b'key')

    def test_private_key_path_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'adbkey';path.write_bytes(b'not a public key')
            with self.assertRaises(ValueError):p.read_public_key(path)

    def test_invalid_public_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'adbkey.pub';path.write_bytes(b'invalid')
            with self.assertRaises(ValueError):p.read_public_key(path)

    @unittest.skipUnless((p.OUT/'plan.json').exists(),'Private patch not prepared')
    def test_actual_image_independent_reparse_and_undo(self):
        original=(p.SOURCE/'boot.img').read_bytes()
        patched=(p.OUT/'patched-boot.img').read_bytes()
        plan=json.loads((p.OUT/'plan.json').read_text())
        refspec=importlib.util.spec_from_file_location('reference',p.ROOT/'diagnostics/upstream-boot-patch.py')
        ref=importlib.util.module_from_spec(refspec);refspec.loader.exec_module(ref)
        _,offset,_,archive=ref.parse_boot(patched)
        original_records,_=ref.cpio_records(ref.parse_boot(original)[3])
        new_records,_=ref.cpio_records(archive)
        old={r[0]:r for r in original_records};new={r[0]:r for r in new_records}
        self.assertEqual(set(new)-set(old),{b'adb_keys'})
        self.assertEqual([n for n in old if old[n]!=new[n]],[b'init.sun8i.usb.rc'])
        check=subprocess.run(['/usr/bin/cpio','-it'],input=archive,capture_output=True)
        self.assertEqual(check.returncode,0,check.stderr.decode())
        self.assertIn(b'adb_keys\n',check.stdout)
        apply=bytearray(original);undo=bytearray(patched)
        for item in plan['writes_in_order']:
            start=(item['sector']-plan['boot_sector'])*512
            end=start+item['sectors']*512
            self.assertTrue(0<=start<end<=len(original))
            after=(p.OUT/item['new']).read_bytes();before=(p.OUT/item['original']).read_bytes()
            self.assertEqual((len(after),len(before)),(end-start,end-start))
            self.assertEqual(original[start:end],before)
            apply[start:end]=after;undo[start:end]=before
        self.assertEqual(bytes(apply),patched)
        self.assertEqual(bytes(undo),original)
        self.assertEqual(hashlib.sha256(patched).hexdigest(),plan['patched_boot_sha256'])
        self.assertFalse(plan['root_enabled'])
        self.assertFalse(plan['network_adb_enabled'])


if __name__=='__main__':
    unittest.main(verbosity=2)
