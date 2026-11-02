"""No-jig entrypoint regressions. SDK and hardware operations are never executed."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import checkout_contributor as entry
class CheckoutTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);self.path=self.root/'config.json';self.c=dict(schema=1,checkout_root=str(self.root/'checkout'),compiler='cc');self.kit=Path(entry.__file__).parent
  self.c['checkout_root']=str(self.kit.resolve().parents[3])
  self.host=patch.object(entry,'host_prerequisite',return_value=dict(state='passed'));self.host.start();self.addCleanup(self.host.stop)
  self.source=patch.object(entry,'source_check',return_value=dict(state='passed',revision=entry.BASELINE));self.source.start();self.addCleanup(self.source.stop)
 def runstage(self,action='quick-host'):
  self.path.write_text(json.dumps(self.c));return entry.run(action,self.path,self.kit)
 def stage(self,r,name):return next(x for x in r['stages'] if x['name']==name)
 def test_quick_reuses_existing_verifier(self):
  with patch('contributor.verify',return_value={'passed':True,'runs':[]}) as verify,patch.object(entry.shutil,'which',return_value='/synthetic/cc'):
   r=self.runstage();self.assertTrue(r['required_stages_passed']);verify.assert_called_once_with(self.kit,'/synthetic/cc');self.assertFalse(r['hardware_access'])
 def test_other_checkout_rejected_before_verification(self):
  self.c['checkout_root']=str(self.root/'another-checkout')
  with patch('contributor.verify') as verify:
   r=self.runstage();self.assertFalse(r['required_stages_passed']);self.assertEqual(self.stage(r,'checkout_selection')['state'],'failed');verify.assert_not_called()
 def test_absent_hardware_does_not_block_or_probe(self):
  with patch('contributor.verify',return_value={'passed':True}),patch.object(entry.shutil,'which',return_value='/synthetic/cc'),patch.object(entry,'metadata_git',side_effect=AssertionError('no device or SDK command allowed')):
   r=self.runstage();self.assertEqual(self.stage(r,'hardware')['state'],'skipped');self.assertTrue(r['required_stages_passed'])
 def test_missing_compiler_explicit_unavailable(self):
  with patch.object(entry.shutil,'which',return_value=None),patch('contributor.verify') as verify:
   r=self.runstage();self.assertFalse(r['required_stages_passed']);self.assertEqual(self.stage(r,'C11_UBSan_compiler')['state'],'unavailable');verify.assert_not_called()
 def test_wrong_baseline_stops_before_tests(self):
  with patch.object(entry,'source_check',return_value=dict(state='failed',reason='wrong baseline')),patch('contributor.verify') as verify:
   self.assertFalse(self.runstage()['required_stages_passed']);verify.assert_not_called()
 def test_active_tracked_changes_are_host_test_inputs(self):
  self.source.stop()
  with patch.object(entry,'metadata_git',side_effect=[(0,entry.BASELINE),(1,'')]):
   result=entry.source_check(self.root/'checkout');self.assertEqual(result['state'],'passed');self.assertTrue(result['tracked_firmware_changes'])
 def test_unrelated_baseline_ancestry_is_rejected(self):
  self.source.stop()
  with patch.object(entry,'metadata_git',side_effect=[(0,'b'*40),(1,'')]):self.assertEqual(entry.source_check(self.root/'checkout')['state'],'failed')
 def test_malformed_config_writes_failed_stage(self):self.path.write_text('{');r=entry.run('quick-host',self.path,self.kit);self.assertFalse(r['required_stages_passed']);self.assertEqual(self.stage(r,'configuration')['state'],'failed')
 def test_deep_config_is_bounded(self):self.path.write_text('['*10000+'0'+']'*10000);r=entry.run('quick-host',self.path,self.kit);self.assertFalse(r['required_stages_passed'])
 def test_unknown_signing_field_rejected(self):self.c['signing_key']='NEVER_OPEN';r=self.runstage();self.assertEqual(self.stage(r,'configuration')['state'],'failed');self.assertFalse(r['signing_keys_accessed'])
 def test_bool_schema_rejected(self):self.c['schema']=True;self.assertEqual(self.stage(self.runstage(),'configuration')['state'],'failed')
 def test_missing_toolchain_explicit_and_build_blocked(self):
  self.c.update(sdk_root=str(self.root/'missing-sdk'),toolchain_root=str(self.root/'missing-toolchain'))
  with patch.object(entry,'kit_integrity',return_value=dict(state='passed')):
   r=self.runstage('firmware-build');self.assertEqual(self.stage(r,'toolchain')['state'],'unavailable');self.assertEqual(self.stage(r,'Nordic_SDK')['state'],'unavailable');self.assertEqual(self.stage(r,'firmware_build')['state'],'blocked');self.assertFalse(r['build_executed'])
 def test_full_ready_prerequisites_never_sign_or_build(self):
  self.c.update(sdk_root='SDK',toolchain_root='TC')
  with patch.object(entry,'kit_integrity',return_value=dict(state='passed')),patch.object(entry,'sdk_check',return_value=dict(state='passed')),patch.object(entry,'toolchain_check',return_value=dict(state='passed')),patch('contributor.verify') as verify:
   r=self.runstage('firmware-build');self.assertFalse(r['required_stages_passed']);self.assertFalse(r['signing_keys_accessed']);self.assertFalse(r['build_executed']);verify.assert_not_called()
 def test_unavailable_host_stops_before_git(self):
  with patch.object(entry,'host_prerequisite',return_value=dict(state='unavailable')),patch.object(entry,'source_check') as source:
   self.assertFalse(self.runstage()['required_stages_passed']);source.assert_not_called()
 def test_key_filename_is_not_opened_as_config(self):
  with patch.object(entry.os,'open') as opened:
   with self.assertRaises(ValueError):entry.config(self.root/'private.pem')
   opened.assert_not_called()
 def test_shared_object_store_rejected(self):
  self.source.stop()
  with patch.object(entry,'metadata_git') as git:self.assertEqual(entry.source_check(self.root/'upstream-keep-clean')['state'],'failed');git.assert_not_called()
 def test_supported_descendant_revision_real_logic(self):
  self.source.stop()
  with patch.object(entry,'metadata_git',return_value=(0,'f'*40)):self.assertEqual(entry.source_check(self.root)['state'],'passed')
if __name__=='__main__':unittest.main()
