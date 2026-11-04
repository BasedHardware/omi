import json,subprocess,sys,unittest
from pathlib import Path
import test_artifact_preflight as fixtures
from artifact_preflight import digest
from job_dry_run import plan
class JobTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.PreflightTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.f=self.fixture;self.f.runcheck();self.root=self.f.root
  self.profile=dict(probe_serial='synthetic-probe',external_target_identity_sha256='1'*64)
  self.job=dict(schema=1,operation='reviewed_swd_app_only',probe_serial='synthetic-probe',external_target_identity_sha256='1'*64,deadline_seconds=60,on_failure='stop_preserve_receipts',retries=0,power_cycle=False,reset_after_verify=False,lease_scope='whole_cv1_bench',evidence_policy='local_unique_no_truncate',artifact_manifest='input.json')
 def check(self):
  (self.root/'job.json').write_text(json.dumps(self.job));(self.root/'profile.json').write_text(json.dumps(self.profile));return plan(self.root/'job.json',self.root/'profile.json',self.root/'contract.json')
 def test_valid_plan_never_executes(self):r=self.check();self.assertTrue(r['plan_valid']);self.assertFalse(r['execution_enabled']);self.assertFalse(r['hardware_authorized']);self.assertFalse(r['release_authorized'])
 def test_wrong_probe(self):self.job['probe_serial']='wrong';self.assertIn('probe_mismatch',self.check()['errors'])
 def test_probe_alone_is_not_target_identity(self):del self.job['external_target_identity_sha256'];self.assertIn('external_identity_missing_or_mismatch',self.check()['errors'])
 def test_timeout_unbounded(self):
  for x in [None,0,301,True]:self.job['deadline_seconds']=x;self.assertIn('unbounded_deadline',self.check()['errors'])
  for x in [float('inf'),float('nan')]:
   self.job['deadline_seconds']=x
   with self.assertRaises(ValueError):self.check()
 def test_no_automatic_retry(self):self.job['retries']=1;self.assertIn('automatic_retries_forbidden',self.check()['errors'])
 def test_no_power_cycle(self):self.job['power_cycle']=True;self.assertIn('power_cycle_not_qualified',self.check()['errors'])
 def test_no_arbitrary_commands(self):self.job['shell']='echo forbidden';self.assertIn('arbitrary_or_irreversible_action',self.check()['errors'])
 def test_role_mismatch(self):self.job['operation']='reviewed_swd_baseline_restore';self.assertIn('operation_role_mismatch',self.check()['errors'])
 def test_stale_artifact(self):(self.root/'app.hex').write_text('changed');self.assertIn('offline_preflight_failed',self.check()['errors'])
 def test_whole_bench_exclusivity(self):self.job['lease_scope']='uart_only';self.assertIn('exclusive_scope_required',self.check()['errors'])
 def test_no_hidden_reset(self):self.job['reset_after_verify']=True;self.assertIn('reset_requires_separate_reviewed_step',self.check()['errors'])
 def test_manifest_escape(self):self.job['artifact_manifest']='../outside';self.assertIn('artifact_manifest_path_escape',self.check()['errors'])
 def test_duplicate_policy_fields_rejected(self):
  (self.root/'profile.json').write_text(json.dumps(self.profile))
  (self.root/'job.json').write_text('{"schema":1,"schema":1}')
  with self.assertRaises(ValueError):plan(self.root/'job.json',self.root/'profile.json',self.root/'contract.json')
 def test_deep_policy_json_fails_closed_without_traceback(self):
  self.check();(self.root/'job.json').write_text('['*10000+'0'+']'*10000)
  q=subprocess.run([sys.executable,str(Path(__file__).parent/'job_dry_run.py'),str(self.root/'job.json'),'--profile',str(self.root/'profile.json'),'--contract',str(self.root/'contract.json')],capture_output=True,text=True,timeout=10)
  self.assertEqual(q.returncode,2);self.assertNotIn('Traceback',q.stderr);self.assertFalse(json.loads(q.stdout)['plan_valid'])
if __name__=='__main__':unittest.main()
