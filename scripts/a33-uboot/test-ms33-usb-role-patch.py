#!/usr/bin/env python3
"""Independent offline validation of the permanent local USB-role image."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'diagnostics/ms33-usb-role-patch'
TARGET_SHA='1cb468440e18ee7a914376ed890215bdf54a7c31ac5fcce797850291c7f0c1db'
BASE_SHA='b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe'
SCRIPT=b'sbin/ms33-usb-device.sh'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
bp=load('bp',ROOT/'scripts/a33-uboot/make-ms33-adb-patch.py')
ref=load('ref',ROOT/'diagnostics/upstream-boot-patch.py')
class Tests(unittest.TestCase):
 def test_independent_parse_exact_changes_and_undo(self):
  base=(ROOT/'diagnostics/ms33-tcp-adb-patch/tcp-adb-boot.img').read_bytes();target=(P/'usb-role-boot.img').read_bytes()
  plan=json.loads((P/'plan.json').read_text())
  self.assertEqual(hashlib.sha256(base).hexdigest(),BASE_SHA);self.assertEqual(plan['base_boot_sha256'],BASE_SHA)
  self.assertEqual(hashlib.sha256(target).hexdigest(),TARGET_SHA);self.assertEqual(plan['target_boot_sha256'],TARGET_SHA)
  _,offset,_,ba=ref.parse_boot(base);_,offset2,_,ta=ref.parse_boot(target);self.assertEqual(offset,offset2)
  br,_=ref.cpio_records(ba);tr,_=ref.cpio_records(ta);b={r[0]:r for r in br};t={r[0]:r for r in tr}
  self.assertEqual(set(t)-set(b),{SCRIPT});self.assertLessEqual(set(b),set(t))
  self.assertEqual([n for n in b if b[n]!=t[n]],[b'init.sun8i.usb.rc'])
  self.assertEqual(b[b'adb_keys'],t[b'adb_keys']);self.assertEqual(b[b'default.prop'],t[b'default.prop'])
  self.assertIn(b'ro.adb.secure=1\n',t[b'default.prop'][3]);self.assertNotIn(b'ro.secure=0',t[b'default.prop'][3])
  init=t[b'init.sun8i.usb.rc'][3];helper=t[SCRIPT][3]
  self.assertNotIn(b'5555',init);self.assertEqual(init.count(b'service.adb.tcp.port -1'),2)
  self.assertEqual(init.count(b'service ms33_usb_device '),1);self.assertEqual(init.count(b'start ms33_usb_device'),1)
  self.assertEqual(helper.count(b'echo 2 > /sys/devices/platform/sunxi_usb_udc/otg_role'),2)
  self.assertEqual(helper.count(b'sleep 2'),1);self.assertTrue(helper.startswith(b'#!/system/bin/sh\n'))
  self.assertEqual(int(t[SCRIPT][1][14:22],16),0o100755)
  check=subprocess.run(['/usr/bin/cpio','-it'],input=ta,capture_output=True);self.assertEqual(check.returncode,0,check.stderr)
  applied=bytearray(base);undone=bytearray(target)
  for item in plan['writes_in_order']:
   start=(item['sector']-plan['boot_sector'])*512;end=start+item['sectors']*512
   new=(P/item['target']).read_bytes();old=(P/item['rollback']).read_bytes()
   self.assertEqual(target[start:end],new);self.assertEqual(base[start:end],old)
   applied[start:end]=new;undone[start:end]=old
  self.assertEqual(bytes(applied),target);self.assertEqual(bytes(undone),base);bp.parse_boot(target)
 def test_base_is_verified_current_transition_source(self):
  state=json.loads((ROOT/'diagnostics/ms33-tcp-adb-patch/write-verification.json').read_text())
  plan=json.loads((ROOT/'diagnostics/ms33-tcp-adb-patch/plan.json').read_text())
  self.assertEqual(state['matches'],'target');self.assertEqual(state['independent_read_passes'],2)
  self.assertEqual(state['actual_sha256'],BASE_SHA);self.assertTrue(plan['applied'])
  self.assertEqual(plan['last_verified_sha256'],BASE_SHA)
 def test_plan_security_claims(self):
  plan=json.loads((P/'plan.json').read_text())
  self.assertFalse(plan['authentication_enforced']);self.assertTrue(plan['embedded_key_preserved'])
  self.assertFalse(plan['network_adb_enabled']);self.assertFalse(plan['root_enabled']);self.assertFalse(plan['temporary'])
if __name__=='__main__':unittest.main(verbosity=2)
