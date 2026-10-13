#!/usr/bin/env python3
"""Offline shell fault-injection tests for the generated guarded scripts.

No frame access. Each hardware command is a stub; failures simulate even partial
writes. Exercises shell chaining/rollback, not actual MMC electronics or Hush.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
WRITER=ROOT/'diagnostics/ms33-usb-role-patch/writer'
STUB=r'''import json,os,sys
from pathlib import Path
path=Path(os.environ['MS33_SIMULATION'])
s=json.loads(path.read_text())
cmd=Path(sys.argv[0]).name;a=sys.argv[1:]
index=len(s['commands']);s['commands'].append([cmd,*a])
fail=index==s['fail_index'];okay=True
if cmd=='mmc':
 if a[0]=='dev':okay=a==['dev','1','0']
 elif a[0]=='read':
  address,start,count=map(lambda n:int(n,0),a[1:])
  if (start,count)==(0,8192):s['prefix_read']=True
  elif (start,count)==(172032,32768):s['read']=s['disk'].copy()
  elif (start,count)==(191892,9264):s['read']['ramdisk']=s['disk']['ramdisk']
  else:raise Exception('Unexpected read')
 elif a[0]=='write':
  address,start,count=map(lambda n:int(n,0),a[1:])
  if (start,count)==(172032,2):
   assert address in [0x41000000,0x43000000];part='header'
  elif (start,count)==(191892,9264):
   assert address in [0x419b2800,0x439b2800];part='ramdisk'
  else:raise Exception('WRITE OUTSIDE ALLOWED RANGES')
  state='orig' if address<0x43000000 else 'new'
  s['disk'][part]='partial' if fail else state
  s['writes'].append([part,state])
 else:raise Exception('Unexpected MMC operation')
elif cmd=='crc32':okay=True
elif cmd=='cmp.b':
 source,target,count=map(lambda n:int(n,0),a)
 state='orig' if source<0x43000000 else 'new'
 if count==16777216:okay=s['read']==dict(header=state,ramdisk=state,middle='orig',tail='orig')
 elif count==4743168:okay=s['read']['ramdisk']==state
 elif count==10168320-1024:okay=s['read']['middle']=='orig'
 elif count==16777216-10168320-4743168:okay=s['read']['tail']=='orig'
 else:raise Exception('Unexpected comparison')
else:raise Exception('Unexpected command')
path.write_text(json.dumps(s))
sys.exit(0 if okay and not fail else 1)
'''


def run(mode,fail_index=-1,disk=None):
    with tempfile.TemporaryDirectory() as folder:
        temp=Path(folder)
        for name in ('mmc','crc32','cmp.b'):
            executable=temp/name
            executable.write_text(f'#!{sys.executable}\n'+STUB)
            executable.chmod(0o700)
        state={'commands':[],'writes':[],'fail_index':fail_index,
               'disk':disk or dict(header='orig',ramdisk='orig',middle='orig',tail='orig')}
        path=temp/'state.json';path.write_text(json.dumps(state))
        env=os.environ|{'PATH':str(temp)+':'+os.environ['PATH'],'MS33_SIMULATION':str(path)}
        result=subprocess.run(['/bin/sh',str(WRITER/f'{mode}.cmd')],env=env,capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr)
        return json.loads(path.read_text()),result.stdout


class WriterTests(unittest.TestCase):
    def test_success(self):
        state,text=run('apply')
        self.assertEqual(state['writes'],[['ramdisk','new'],['header','new']])
        self.assertIn('MS33_USB_ROLE_APPLY_VERIFIED',text)
        self.assertEqual(state['disk'],dict(header='new',ramdisk='new',middle='orig',tail='orig'))

    def test_each_prewrite_guard(self):
        for index in range(7):
            with self.subTest(index=index):
                state,text=run('apply',index)
                self.assertEqual(state['writes'],[])
                self.assertIn('NO_WRITES',text)

    def test_each_write_or_verification_failure_rolls_back(self):
        for index in range(7,13):
            with self.subTest(index=index):
                state,text=run('apply',index)
                self.assertIn('MS33_TCP_ADB_BASE_RESTORED',text)
                self.assertEqual(state['disk'],dict(header='orig',ramdisk='orig',middle='orig',tail='orig'))
                self.assertEqual(state['writes'][-2:],[['ramdisk','orig'],['header','orig']])

    def test_check_never_writes(self):
        state,text=run('check')
        self.assertEqual(state['writes'],[])
        self.assertIn('USB_ROLE_CHECK_PASSED_NO_WRITES',text)

    def test_partial_write_manual_restore(self):
        for header,ramdisk in [('new','new'),('orig','partial'),('partial','new'),('partial','partial')]:
            with self.subTest(header=header,ramdisk=ramdisk):
                state,text=run('restore',disk=dict(header=header,ramdisk=ramdisk,middle='orig',tail='orig'))
                self.assertIn('MS33_TCP_ADB_BASE_RESTORED',text)
                self.assertEqual(state['disk'],dict(header='orig',ramdisk='orig',middle='orig',tail='orig'))

    def test_unrelated_changes_refuse_undo(self):
        for field in ('middle','tail'):
            disk=dict(header='new',ramdisk='new',middle='orig',tail='orig');disk[field]='changed'
            state,text=run('restore',disk=disk)
            self.assertEqual(state['writes'],[])
            self.assertIn('ROLLBACK_REFUSED',text)

    def test_apply_refuses_nonoriginal_image(self):
        state,text=run('apply',disk=dict(header='new',ramdisk='new',middle='orig',tail='orig'))
        self.assertEqual(state['writes'],[])
        self.assertIn('BASE_MISMATCH_NO_WRITES',text)


if __name__=='__main__':unittest.main(verbosity=2)
