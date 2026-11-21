"""Acceptance assertions over the C demo's report, not a Python OTA model."""
import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent.parent
class HostWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ncs=os.environ.get('CV1_DEMO_NCS_ROOT');cls.archive=os.environ.get('CV1_DEMO_MBEDCRYPTO');cls.arm=os.environ.get('CV1_DEMO_ARM_CC')
        if not all((cls.ncs,cls.archive,cls.arm)):raise unittest.SkipTest('set CV1_DEMO_NCS_ROOT/MBEDCRYPTO/ARM_CC for real host acceptance; no installer')
        cls.tmp=tempfile.TemporaryDirectory();cls.parent=Path(cls.tmp.name)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def args(self,out,archive=None):return [sys.executable,str(ROOT/'host/run.py'),'--output',str(out),'--ncs',self.ncs,'--mbedcrypto',archive or self.archive,'--arm-cc',self.arm]
    def test_end_to_end_shared_c_pipeline_and_guards(self):
        out=self.parent/'successful';p=subprocess.run(self.args(out),capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stderr)
        report=json.loads((out/'report.json').read_text());fixtures=json.loads((out/'fixtures.json').read_text())
        stages=[x['stage'] for x in report['events']]
        required={'chunked_upload_and_verified_trial','explicit_healthy_confirmation','invalid_confirmation_rejected','pending_trial_upload_rejected','confirmation_storage_fault_rejected','wrong_owner_rejected','modified_image_rejected','wrong_ABI_rejected','return_to_known_good','interrupted_upload_restart','interrupted_copy_restart','completed_copy_before_trial_restart','unconfirmed_trial_restart','user_data_bounds_preserved','PASS'}
        self.assertTrue(required.issubset(stages),required-set(stages));self.assertEqual(stages[-1],'PASS')
        self.assertEqual(report['events'][-1]['artifact_sha256'],fixtures['artifacts']['B']['sha256'])
        self.assertEqual(stages.count('explicit_healthy_confirmation'),2)
        guard=next(x for x in report['events'] if x['stage']=='user_data_bounds_preserved')
        self.assertEqual(guard['artifact_sha256'],hashlib.sha256(bytes([0x5a])*(0x100000-0xf4000)).hexdigest())
        self.assertFalse(report['target_operations']);self.assertFalse(report['artifact_admission']);self.assertFalse(report['release_authorized'])
        self.assertTrue(all('HOST SIMULATION' in x['layer'] for x in report['events']))
        self.assertTrue(json.loads((out/'03-host-demo.json').read_text())['returncode']==0)
    def test_missing_archive_fails_without_creating_output(self):
        out=self.parent/'missing';p=subprocess.run(self.args(out,str(self.parent/'absent.a')),capture_output=True,text=True,timeout=15)
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists());self.assertIn('no installation attempted',p.stderr)
    def test_in_source_output_is_rejected(self):
        out=ROOT/'forbidden-output';self.assertFalse(out.exists())
        p=subprocess.run(self.args(out),capture_output=True,text=True,timeout=15)
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists());self.assertIn('outside source tree',p.stderr)
if __name__=='__main__':unittest.main()
