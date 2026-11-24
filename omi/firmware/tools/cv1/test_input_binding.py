"""Deterministic file replacement/coercion regressions; no timing races or hardware."""
import json,unittest
from pathlib import Path
from unittest.mock import patch
import test_artifact_preflight as artifacts
import test_job_dry_run as jobs
import artifact_preflight,job_dry_run

class InputBindingTests(unittest.TestCase):
 def setUp(self):
  self.f=artifacts.PreflightTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.runcheck();self.root=self.f.root
 def replace_after_read(self,path,replacement,action):
  original=Path.read_bytes;count=[0];old=original(path)
  def read(p):
   b=original(p)
   if p==path:
    count[0]+=1
    if count[0]==1:path.write_bytes(replacement)
   return b
  with patch.object(Path,'read_bytes',read):result=action()
  self.assertEqual(count[0],1,'validated input must be read exactly once')
  return old,result
 def test_manifest_replacement_hash_binds_parsed_bytes(self):
  p=self.root/'input.json';bad=json.loads(p.read_bytes());bad['board']='wrong-board'
  old,r=self.replace_after_read(p,json.dumps(bad).encode(),lambda:artifact_preflight.evaluate(p,self.root/'contract.json'))
  self.assertTrue(r['eligible_for_live_identity_gate']);self.assertEqual(r['manifest_sha256'],artifact_preflight.digest(old));self.assertNotEqual(r['manifest_sha256'],artifact_preflight.digest(p.read_bytes()))
 def test_contract_replacement_hash_binds_parsed_bytes(self):
  p=self.root/'contract.json';old,r=self.replace_after_read(p,b'{}',lambda:artifact_preflight.evaluate(self.root/'input.json',p))
  self.assertTrue(r['eligible_for_live_identity_gate']);self.assertEqual(r['baseline_contract_sha256'],artifact_preflight.digest(old))
 def test_manifest_bool_schema_rejected(self):self.f.m['schema']=True;self.assert_schema_reject()
 def assert_schema_reject(self):
  with self.assertRaises(ValueError):self.f.runcheck()
 def test_manifest_unknown_field_rejected(self):self.f.m['erase_all']=True;self.assert_schema_reject()
 def test_image_unknown_field_rejected(self):self.f.m['images'][0]['erase_all']=True;self.assert_schema_reject()
 def test_key_unknown_field_rejected(self):self.f.network()['public_key']['erase_all']=True;self.assert_schema_reject()
 def test_manifest_array_board_rejected(self):self.f.m['board']=['omi'];self.assert_schema_reject()
 def test_ota_bool_declaration_rejected(self):self.f.m['version_policy']=True;self.assert_schema_reject()

class JobBindingTests(unittest.TestCase):
 def setUp(self):
  self.f=jobs.JobTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.check();self.root=self.f.root
 def test_job_replacement_hash_binds_validated_bytes(self):
  p=self.root/'job.json';original=Path.read_bytes;old=original(p);bad=json.loads(old);bad['power_cycle']=True;count=[0]
  def read(path):
   b=original(path)
   if path==p:
    count[0]+=1
    if count[0]==1:p.write_text(json.dumps(bad))
   return b
  with patch.object(Path,'read_bytes',read):r=job_dry_run.plan(p,self.root/'profile.json',self.root/'contract.json')
  self.assertTrue(r['plan_valid']);self.assertEqual(r['job_sha256'],artifact_preflight.digest(old));self.assertEqual(count[0],1);self.assertNotEqual(r['job_sha256'],artifact_preflight.digest(p.read_bytes()))
 def test_operation_is_carried_from_validated_receipt(self):
  original=job_dry_run.evaluate
  def evaluate(*args):
   r=original(*args);p=Path(args[0]);bad=json.loads(p.read_bytes());bad['operation']='proposed_ota_pair';p.write_text(json.dumps(bad));return r
  with patch.object(job_dry_run,'evaluate',evaluate):r=job_dry_run.plan(self.root/'job.json',self.root/'profile.json',self.root/'contract.json')
  self.assertTrue(r['plan_valid']);self.assertEqual(r['artifact_preflight']['validated_operation'],'reviewed_swd_app_only')
 def test_job_bool_schema_rejected(self):self.f.job['schema']=True;self.assertIn('schema',self.f.check()['errors'])
 def test_job_bool_retry_rejected(self):self.f.job['retries']=False;self.assertIn('automatic_retries_forbidden',self.f.check()['errors'])
 def test_array_probe_rejected(self):self.f.job['probe_serial']=self.f.profile['probe_serial']=['same'];self.assertIn('probe_mismatch',self.f.check()['errors'])
 def test_unbounded_or_empty_serial_rejected(self):
  for s in ['', 'x'*65, 'id\n', 1, True, {}]:
   self.f.job['probe_serial']=self.f.profile['probe_serial']=s;self.assertIn('probe_mismatch',self.f.check()['errors'])
 def test_unknown_job_field_rejected(self):self.f.job['erase_all']=True;self.assertIn('unknown_job_fields',self.f.check()['errors'])
 def test_unknown_profile_field_rejected(self):self.f.profile['command']='ignored';self.assertIn('unknown_profile_fields',self.f.check()['errors'])
if __name__=='__main__':unittest.main()
