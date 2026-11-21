import json,subprocess,sys,unittest
from pathlib import Path
import test_artifact_preflight as fixtures
from artifact_preflight import hex_bytes
from bench import Busy,Lease
from unittest import mock
import bench_loop
from bench_loop import SimulatedBench,StageFailed,erase_list,run
PROTECTED=dict(mcuboot_sha256='a'*64,network_sha256='b'*64)
IDENTITY='1'*64
class LoopTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.PreflightTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root;self.restore=fixtures.ihex(0x10000,b'baseline fixture');self.candidate=fixtures.ihex(0x11000,b'candidate fixture')
  self.bind([fixtures.digest(self.restore),fixtures.digest(self.candidate)]);self.pins=dict(protected_sha256=PROTECTED,restore_image_sha256=fixtures.digest(self.restore))
  (self.root/'profile.json').write_text(json.dumps(dict(probe_serial='synthetic-probe',external_target_identity_sha256=IDENTITY)));self.n=0
 def bind(self,reviewed):
  self.f.c['reviewed_app_only_sha256']=reviewed;(self.root/'contract.json').write_text(json.dumps(self.f.c));contract=fixtures.digest((self.root/'contract.json').read_bytes())
  for role,data in [('candidate',self.candidate),('restore',self.restore)]:
   m=dict(schema=1,operation='reviewed_swd_app_only',board=self.f.c['board'],layout_sha256=self.f.c['layout_sha256'],baseline_contract_sha256=contract,images=[self.f.image('application',data,role+'.hex')]);(self.root/(role+'-manifest.json')).write_text(json.dumps(m))
   (self.root/(role+'-job.json')).write_text(json.dumps(self.job(role)))
 def job(self,role):return dict(schema=1,operation='reviewed_swd_app_only',probe_serial='synthetic-probe',external_target_identity_sha256=IDENTITY,deadline_seconds=60,on_failure='stop_preserve_receipts',retries=0,power_cycle=False,reset_after_verify=False,lease_scope='whole_cv1_bench',evidence_policy='local_unique_no_truncate',artifact_manifest=role+'-manifest.json')
 def sim(self,fail=(),identity=IDENTITY,protected=PROTECTED,app=None):return SimulatedBench(identity,protected,hex_bytes(self.restore) if app is None else app,fail)
 def go(self,adapter,checks=()):
  self.n+=1;return run(adapter,{'candidate':self.root/'candidate-job.json','restore':self.root/'restore-job.json'},self.root/'profile.json',self.root/'contract.json',self.pins,self.root/'bench',self.root/f'out{self.n}',checks=checks)
 def lease(self):return json.loads((self.root/'bench/lease.json').read_text())['state']
 def stages(self,summary):return [s['stage'] for s in summary['stages']]
 def restored(self,sim):self.assertEqual(sim.memory,hex_bytes(self.restore))
 def test_pass_restores_and_releases(self):
  sim=self.sim();r=self.go(sim);self.assertEqual(r['result'],'candidate_passed_restored');self.assertTrue(r['lease_clean']);self.assertEqual(self.lease(),'idle');self.restored(sim)
  self.assertEqual(self.stages(r),['admit','identity','baseline_check','flash_candidate','verify_candidate','boot_check','restore_write','restore_verify','restore_boot_check'])
  self.assertFalse(r['hardware_exercised']);self.assertFalse(r['release_authorized']);self.assertEqual(sim.programs,2)
 def test_admit_rejects_before_any_device_step(self):
  (self.root/'candidate.hex').write_text('changed');sim=self.sim();r=self.go(sim);self.assertEqual(r['result'],'rejected_device_untouched');self.assertEqual(sim.calls,[]);self.assertEqual(self.lease(),'idle')
 def test_unreviewed_candidate_rejected(self):
  self.bind([fixtures.digest(self.restore)]);sim=self.sim();r=self.go(sim);self.assertEqual(r['result'],'rejected_device_untouched');self.assertIn('app_review',r['stages'][0]['detail']);self.assertEqual(sim.calls,[])
 def test_reviewed_but_unpinned_restore_rejected(self):
  self.pins['restore_image_sha256']=fixtures.digest(self.candidate);sim=self.sim(app=hex_bytes(self.candidate));r=self.go(sim);self.assertEqual(r['stages'][0]['code'],'restore_image_not_pinned');self.assertEqual(sim.calls,[])
 def test_wrong_identity_never_writes(self):
  sim=self.sim(identity='2'*64);r=self.go(sim);self.assertEqual(r['result'],'rejected_device_untouched');self.assertNotIn('erase',sim.calls)
 def test_unexpected_app_quarantines_without_writing(self):
  sim=self.sim(app=hex_bytes(self.candidate));r=self.go(sim);self.assertEqual(r['result'],'unexpected_device_state');self.assertNotIn('erase',sim.calls);self.assertEqual(self.lease(),'quarantined')
 def test_changed_bootloader_quarantines_without_writing(self):
  sim=self.sim(protected=dict(PROTECTED,mcuboot_sha256='c'*64));self.assertEqual(self.go(sim)['result'],'unexpected_device_state');self.assertNotIn('erase',sim.calls)
 def test_flash_failure_restores_then_quarantines(self):
  sim=self.sim(fail=['program1']);r=self.go(sim);self.assertEqual(r['result'],'candidate_failed_restored');self.restored(sim);self.assertEqual(self.lease(),'quarantined');self.assertEqual(sim.programs,2)
 def test_partial_program_restores_then_quarantines(self):
  sim=self.sim(fail=['partial1']);r=self.go(sim);self.assertEqual(r['result'],'candidate_failed_restored');self.restored(sim);self.assertEqual(self.lease(),'quarantined')
 def test_failed_erase_cannot_pass_as_restored(self):
  sim=self.sim(fail=['erase_noop']);r=self.go(sim);self.assertEqual(r['result'],'restore_failed_needs_owner');self.assertEqual(self.lease(),'quarantined')
 def test_target_swapped_before_restore_is_not_written(self):
  sim=self.sim();real=sim.identity
  def identity():
   return dict(external_target_identity_sha256='2'*64) if sim.programs else real()
  sim.identity=identity;r=self.go(sim);self.assertEqual(r['result'],'restore_failed_needs_owner');self.assertEqual(sim.programs,1);self.assertEqual(sim.calls.count('erase'),1);self.assertEqual(self.lease(),'quarantined')
 def test_target_swapped_after_erase_is_not_programmed(self):
  sim=self.sim();real=sim.identity
  def identity():
   return dict(external_target_identity_sha256='2'*64) if 'erase' in sim.calls else real()
  sim.identity=identity;r=self.go(sim);self.assertEqual(r['result'],'restore_failed_needs_owner');self.assertEqual(sim.programs,0);self.assertEqual(sim.calls.count('erase'),1)
 def test_stale_bytes_on_a_candidate_page_quarantine_before_writing(self):
  app=hex_bytes(self.restore);app[0x11800]=0;sim=self.sim(app=app);self.assertEqual(self.go(sim)['result'],'unexpected_device_state');self.assertNotIn('erase',sim.calls)
 def test_manifest_replaced_after_plan_is_refused(self):
  real=bench_loop.plan
  def replacing(job,profile,contract):
   result=real(job,profile,contract);m=json.loads((self.root/'candidate-manifest.json').read_text());m['images'][0]['file']='other.hex';(self.root/'candidate-manifest.json').write_text(json.dumps(m));return result
  sim=self.sim()
  with mock.patch('bench_loop.plan',replacing):r=self.go(sim)
  self.assertEqual(r['stages'][0]['code'],'manifest_changed');self.assertEqual(sim.calls,[])
 def test_unsaved_proof_leaves_lease_quarantined(self):
  with mock.patch('bench_loop.save',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.go(self.sim())
  self.assertEqual(self.lease(),'quarantined')
 def test_stuck_candidate_restore_fails_closed(self):
  sim=self.sim(fail=['stuck']);r=self.go(sim);self.assertEqual(r['result'],'restore_failed_needs_owner');self.assertEqual(self.lease(),'quarantined')
 def test_restore_failure_is_never_retried(self):
  sim=self.sim(fail=['program2']);r=self.go(sim);self.assertEqual(r['result'],'restore_failed_needs_owner');self.assertEqual(sim.programs,2);self.assertEqual(self.lease(),'quarantined')
 def test_quarantine_blocks_the_next_run(self):
  self.go(self.sim(fail=['program1']))
  with self.assertRaises(Busy):self.go(self.sim())
 def test_crash_leaves_bench_blocked(self):
  sim=self.sim();sim.erase=lambda selected:(_ for _ in ()).throw(KeyboardInterrupt())
  with self.assertRaises(KeyboardInterrupt):self.go(sim)
  self.assertEqual(self.lease(),'quarantined')
 def test_second_holder_refused(self):
  with Lease(self.root/'bench','other'):
   with self.assertRaises(Busy):self.go(self.sim())
 def test_pages_outside_app_range_refused(self):
  for address in (0xf000,0xf6000,0xfc000,0xff8000,0x1000000):
   with self.assertRaises(StageFailed):erase_list({address:0},{0x10000:0})
  with self.assertRaises(StageFailed):erase_list({},{})
 def test_erase_list_covers_both_images(self):self.assertEqual(erase_list({0x10010:0},{0x11fff:0}),[0x10000,0x11000])
 def test_swapped_input_cannot_reach_device(self):
  sim=self.sim();real=sim.erase;seen=[];program=sim.program
  def swap(selected):
   for path in self.root.rglob('candidate.hex'):path.write_text('swapped')
   real(selected)
  def record(data):seen.append(data);program(data)
  sim.erase=swap;sim.program=record;self.assertEqual(self.go(sim)['result'],'candidate_passed_restored');self.assertEqual(seen[0],self.candidate)
 def test_checks_pass_in_order_before_restore(self):
  sim=self.sim();seen=[]
  def check():
   self.assertEqual(sim.programs,1);seen.append('checked');return dict(result='passed')
  r=self.go(sim,[('gatt',check),('audio',check)])
  self.assertEqual(r['result'],'candidate_passed_restored');self.assertEqual(r['checks_ran'],['gatt','audio']);self.assertEqual(seen,['checked','checked']);self.restored(sim)
  self.assertEqual(self.stages(r)[6:9],['gatt','audio','restore_write'])
 def test_check_failures_and_exceptions_always_restore(self):
  for action in (lambda:dict(result='failed',reason='gatt_failed'),lambda:(_ for _ in ()).throw(OSError('oops')),lambda:(_ for _ in ()).throw(SystemExit()),lambda:(_ for _ in ()).throw(KeyboardInterrupt()),lambda:dict(result='skipped'),lambda:None):
   with self.subTest(action=action):
    # A failed candidate quarantines this lease; use an independent bench fixture.
    self.setUp();sim=self.sim();r=self.go(sim,[('gatt',action),('audio',lambda:dict(result='passed'))])
    self.assertEqual(r['result'],'candidate_failed_restored');self.restored(sim);self.assertEqual(sim.programs,2)
    self.assertEqual(r['checks_ran'],['gatt']);self.assertEqual(r['checks'][1]['result'],'not_run');self.assertIn('restore_boot_check',self.stages(r))
 def test_skipped_check_is_incomplete_and_restores(self):
  sim=self.sim();r=self.go(sim,[('ble',lambda:dict(result='skipped',reason='no_advertisement'))])
  self.assertEqual(r['result'],'candidate_incomplete_restored');self.assertEqual(r['checks'][0]['reason'],'no_advertisement');self.assertEqual(r['stages'][6]['result'],'skipped');self.assertTrue(r['lease_clean']);self.restored(sim)
 def test_unreachable_ble_central_skips_and_restores_with_clean_lease(self):
  from ble_check import BLECheck
  serial='synthetic-private-serial'
  runner=mock.Mock(side_effect=subprocess.CalledProcessError(1,['ssh',serial],output=serial,stderr=serial))
  check=BLECheck(dict(ssh_host='synthetic-receiver',app='/tmp/Helper.app',receipt_dir='/tmp',expected_serial=serial),self.root/'ble.json',runner)
  sim=self.sim();r=self.go(sim,[('ble',check)])
  self.assertEqual(r['result'],'candidate_incomplete_restored');self.assertTrue(r['lease_clean']);self.assertEqual(self.lease(),'idle');self.restored(sim)
  self.assertEqual(r['checks_ran'],['ble']);self.assertEqual(r['checks'][0]['result'],'skipped');self.assertEqual(r['checks'][0]['reason'],'central_unreachable: BLE was not tested')
  self.assertEqual(self.stages(r)[-3:],['restore_write','restore_verify','restore_boot_check']);self.assertNotIn(serial,json.dumps(r))
 def test_boot_failure_never_runs_checks_and_still_restores(self):
  sim=self.sim();original=sim.tick;count=0
  def tick():
   nonlocal count
   count+=1
   if count==1:raise OSError('candidate boot failed')
   return original()
  sim.tick=tick;check=mock.Mock();r=self.go(sim,[('ble',check)])
  check.assert_not_called();self.assertEqual(r['checks_ran'],[]);self.assertEqual(r['result'],'candidate_failed_restored');self.restored(sim)
 def test_bad_check_names_rejected_before_device_access(self):
  for checks in ([('boot_check',lambda:None)],[('ble',lambda:None),('ble',lambda:None)]):
   sim=self.sim()
   with self.assertRaises(ValueError):self.go(sim,checks)
   self.assertEqual(sim.calls,[])
 def test_cli_dry_run(self):
  (self.root/'pins.json').write_text(json.dumps(self.pins))
  q=subprocess.run([sys.executable,str(Path(__file__).parent/'bench_loop.py'),'dry-run','--candidate-job',str(self.root/'candidate-job.json'),'--restore-job',str(self.root/'restore-job.json'),'--profile',str(self.root/'profile.json'),'--contract',str(self.root/'contract.json'),'--pins',str(self.root/'pins.json'),'--bench-dir',str(self.root/'bench'),'--output',str(self.root/'cli')],capture_output=True,text=True,timeout=30)
  self.assertEqual(q.returncode,0,q.stderr);self.assertEqual(json.loads(q.stdout)['result'],'candidate_passed_restored');self.assertTrue((self.root/'cli/summary.json').exists())
if __name__=='__main__':unittest.main()
