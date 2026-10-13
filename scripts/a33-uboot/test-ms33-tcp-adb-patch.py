#!/usr/bin/env python3
"""Independent offline validation of the temporary authenticated TCP-ADB image."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'diagnostics/ms33-tcp-adb-patch'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
bp=load('bp',ROOT/'scripts/a33-uboot/make-ms33-adb-patch.py')
ref=load('ref',ROOT/'diagnostics/upstream-boot-patch.py')
class Tests(unittest.TestCase):
 def test_independent_parse_exact_changes_and_undo(self):
  base=(ROOT/'diagnostics/ms33-adb-patch/patched-boot.img').read_bytes();target=(P/'tcp-adb-boot.img').read_bytes()
  plan=json.loads((P/'plan.json').read_text())
  self.assertEqual(hashlib.sha256(base).hexdigest(),plan['base_boot_sha256'])
  self.assertEqual(hashlib.sha256(target).hexdigest(),plan['target_boot_sha256'])
  _,offset,_,ba=ref.parse_boot(base);_,offset2,_,ta=ref.parse_boot(target);self.assertEqual(offset,offset2)
  br,_=ref.cpio_records(ba);tr,_=ref.cpio_records(ta);b={r[0]:r for r in br};t={r[0]:r for r in tr}
  self.assertEqual(set(b),set(t));self.assertEqual([n for n in b if b[n]!=t[n]],[b'default.prop',b'init.sun8i.usb.rc'])
  self.assertEqual(b[b'adb_keys'],t[b'adb_keys']);self.assertIn(b'ro.adb.secure=1\n',t[b'default.prop'][3])
  self.assertEqual(t[b'init.sun8i.usb.rc'][3].count(b'setprop service.adb.tcp.port 5555'),3)
  self.assertNotIn(b'ro.secure=0',t[b'default.prop'][3]);self.assertNotIn(b'ro.debuggable=1',t[b'default.prop'][3])
  check=subprocess.run(['/usr/bin/cpio','-it'],input=ta,capture_output=True);self.assertEqual(check.returncode,0,check.stderr)
  applied=bytearray(base);undone=bytearray(target)
  for item in plan['writes_in_order']:
   start=(item['sector']-plan['boot_sector'])*512;end=start+item['sectors']*512
   new=(P/item['target']).read_bytes();old=(P/item['rollback']).read_bytes()
   self.assertEqual(target[start:end],new);self.assertEqual(base[start:end],old)
   applied[start:end]=new;undone[start:end]=old
  self.assertEqual(bytes(applied),target);self.assertEqual(bytes(undone),base)
  bp.parse_boot(target)
 def test_base_is_verified_current_transition_source(self):
  state=json.loads((ROOT/'diagnostics/ms33-adb-patch/write-verification.json').read_text())
  plan=json.loads((P/'plan.json').read_text())
  self.assertEqual(state['matches'],'patched');self.assertEqual(state['independent_read_passes'],2)
  self.assertEqual(state['actual_sha256'],plan['base_boot_sha256'])
if __name__=='__main__':unittest.main(verbosity=2)
