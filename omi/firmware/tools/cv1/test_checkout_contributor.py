"""No-jig entrypoint regressions. SDK and hardware operations are never executed."""
import json,subprocess,tempfile,unittest
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
  with patch.object(entry,'metadata_git',side_effect=[(0,'b'*40),(1,''),(0,'false')]):self.assertEqual(entry.source_check(self.root/'checkout')['state'],'failed')
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
  with patch.object(entry,'kit_integrity',return_value=dict(state='passed')),patch.object(entry,'sdk_check',return_value=dict(state='passed')),patch.object(entry,'toolchain_check',return_value=dict(state='passed')),patch('contributor.verify') as verify,\
   patch.object(entry.subprocess,'run',side_effect=AssertionError('no signing/build subprocess allowed')),patch.object(entry.subprocess,'Popen',side_effect=AssertionError('no signing/build subprocess allowed')),patch.object(entry.subprocess,'check_call',side_effect=AssertionError('no signing/build subprocess allowed')),patch.object(entry.subprocess,'check_output',side_effect=AssertionError('no signing/build subprocess allowed')):
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
 def test_shallow_clone_reported_distinctly(self):
  self.source.stop()
  with patch.object(entry,'metadata_git',side_effect=[(0,'b'*40),(1,''),(0,'true')]):
   result=entry.source_check(self.root/'checkout');self.assertEqual(result['state'],'failed');self.assertIn('unshallow',result['reason']);self.assertIn('shallow',result['reason'])
 def test_real_shallow_clone_reported_distinctly(self):
  self.source.stop()
  origin=self.root/'origin';origin.mkdir()
  def git(cwd,*args):return subprocess.run(['git','-c','user.name=t','-c','user.email=t@example.com','-C',str(cwd)]+list(args),check=True,capture_output=True,text=True).stdout.strip()
  git(origin,'init','-q');(origin/'a').write_text('1');git(origin,'add','a');git(origin,'commit','-qm','1');base=git(origin,'rev-parse','HEAD')
  (origin/'a').write_text('2');git(origin,'commit','-qam','2')
  git(self.root,'clone','-q','--depth','1','file://'+str(origin),'shallow')
  result=entry.source_check(self.root/'shallow',base);self.assertEqual(result['state'],'failed');self.assertIn('unshallow',result['reason'])
  git(self.root,'clone','-q','file://'+str(origin),'full')
  self.assertEqual(entry.source_check(self.root/'full',base)['state'],'passed')
 def test_real_sdk_tree_states(self):
  sdk=self.root/'sdk';project=sdk/'nrf';project.mkdir(parents=True)
  def git(*args):return subprocess.run(['git','-c','user.name=t','-c','user.email=t@example.com','-C',str(project)]+list(args),check=True,capture_output=True,text=True).stdout.strip()
  git('init','-q');(project/'.gitignore').write_text('*.o\n*.pyc\n');(project/'a.c').write_text('1');git('add','.');git('commit','-qm','1')
  lock={'sdk_projects':[{'name':'nrf','path':'nrf','commit':git('rev-parse','HEAD')}],'not_cloned_in_reference':[]}
  state=lambda:entry.sdk_check(sdk,lock)['state']
  self.assertEqual(state(),'passed')
  (project/'__pycache__').mkdir();(project/'__pycache__'/'a.cpython-312.pyc').write_text('x');self.assertEqual(state(),'passed')
  (project/'b.o').write_text('x');self.assertEqual(state(),'failed');(project/'b.o').unlink()
  (project/'new.c').write_text('x');self.assertEqual(state(),'failed');(project/'new.c').unlink()
  (project/'a.c').write_text('2');self.assertEqual(state(),'failed')
 def test_real_toolchain_executables_launch(self):
  toolchain={'toolchain_environment_sha256':'e'*64,'toolchain_files':[{'public_path':'environment.json','sha256':'e'*64}],'toolchain_id':'synthetic'}
  (self.root/'bin').mkdir()
  def tool(name,code):
   path=self.root/'bin'/name;path.write_text('#!/bin/sh\nexit '+str(code)+'\n');path.chmod(0o755)
  with patch.object(entry,'digest',return_value='e'*64):
   tool('cmake',0);self.assertEqual(entry.toolchain_check(self.root,toolchain)['state'],'failed')
   tool('ninja',1);self.assertEqual(entry.toolchain_check(self.root,toolchain)['state'],'failed')
   tool('ninja',0);self.assertEqual(entry.toolchain_check(self.root,toolchain)['state'],'passed')
 def lock(self):
  return {'sdk_projects':[{'name':'nrf','path':'nrf','commit':'c'*40}],'not_cloned_in_reference':[]}
 def test_sdk_untracked_files_rejected(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(0,''),(0,'edited.c\0'),(0,'')]):
   result=entry.sdk_check(self.root,self.lock());self.assertEqual(result['state'],'failed');self.assertIn('untracked',result['projects'][0]['reason'])
 def test_sdk_tracked_modification_still_rejected(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(1,'')]):
   result=entry.sdk_check(self.root,self.lock());self.assertEqual(result['state'],'failed');self.assertIn('tracked',result['projects'][0]['reason'])
 def test_sdk_ignored_files_rejected(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(0,''),(0,''),(0,'build/app.o\0')]):
   result=entry.sdk_check(self.root,self.lock());self.assertEqual(result['state'],'failed');self.assertIn('ignored',result['projects'][0]['reason'])
 def test_sdk_ignored_python_bytecode_allowed(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(0,''),(0,''),(0,'scripts/__pycache__/a.cpython-312.pyc\0')]):
   self.assertEqual(entry.sdk_check(self.root,self.lock())['state'],'passed')
 def test_sdk_ignored_pyc_outside_pycache_rejected(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(0,''),(0,''),(0,'scripts/a.pyc\0')]):
   self.assertEqual(entry.sdk_check(self.root,self.lock())['state'],'failed')
 def test_sdk_exact_project_passes_all_tree_states(self):
  with patch.object(entry,'metadata_git',side_effect=[(0,'c'*40),(0,''),(0,''),(0,'')]) as git:
   self.assertEqual(entry.sdk_check(self.root,self.lock())['state'],'passed');self.assertEqual(git.call_count,4)
 def test_toolchain_executables_must_launch(self):
  toolchain={'toolchain_environment_sha256':'e'*64,'toolchain_files':[{'public_path':'environment.json','sha256':'e'*64}],'toolchain_id':'synthetic'}
  with patch.object(entry,'digest',return_value='e'*64),patch.object(entry.subprocess,'run',return_value=entry.subprocess.CompletedProcess([],1)) as launch:
   result=entry.toolchain_check(self.root,toolchain);self.assertEqual(result['state'],'failed');launch.assert_called_once_with([str(self.root/'bin/cmake'),'--version'],capture_output=True,text=True,timeout=10)
 def test_toolchain_launch_verified_for_pinned_cmake_and_ninja(self):
  toolchain={'toolchain_environment_sha256':'e'*64,'toolchain_files':[{'public_path':'environment.json','sha256':'e'*64}],'toolchain_id':'synthetic'}
  with patch.object(entry,'digest',return_value='e'*64),patch.object(entry.subprocess,'run',return_value=entry.subprocess.CompletedProcess([],0)) as launch:
   result=entry.toolchain_check(self.root,toolchain);self.assertEqual(result['state'],'passed');self.assertEqual([c.args[0][0] for c in launch.call_args_list],[str(self.root/'bin/cmake'),str(self.root/'bin/ninja')])
if __name__=='__main__':unittest.main()
