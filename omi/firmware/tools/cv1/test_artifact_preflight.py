import copy,json,tempfile,unittest,subprocess,sys
from pathlib import Path
from artifact_preflight import evaluate,digest,hex_bytes

def record(address,kind,data):
 b=bytes([len(data)])+address.to_bytes(2,'big')+bytes([kind])+data
 return ':'+(b+bytes([-sum(b)%256])).hex().upper()+'\n'
def ihex(address,data):return (record(0,4,(address>>16).to_bytes(2,'big'))+record(address&65535,0,data)+record(0,1,b'')).encode()
class PreflightTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.c=json.loads((Path(__file__).parent/'preflight-evidence/baseline-contract.json').read_text());self.app=ihex(0x10000,b'fake application fixture');self.c['reviewed_app_only_sha256']=[digest(self.app)];self.c['baseline_images']['application_full']=digest(self.app)
  self.m=dict(schema=1,operation='reviewed_swd_app_only',board=self.c['board'],layout_sha256=self.c['layout_sha256'],images=[self.image('application',self.app,'app.hex')])
 def image(self,role,data,name):
  (self.root/name).write_bytes(data);return dict(role=role,file=name,sha256=digest(data))
 def runcheck(self):
  (self.root/'contract.json').write_text(json.dumps(self.c));self.m['baseline_contract_sha256']=digest((self.root/'contract.json').read_bytes());(self.root/'input.json').write_text(json.dumps(self.m));return evaluate(self.root/'input.json',self.root/'contract.json')
 def codes(self):return [e['code'] for e in self.runcheck()['errors']]
 def network(self,keyname='baseline'):
  key=(Path(__file__).parent/('preflight-evidence/'+keyname+'-public.raw')).read_bytes();data=b'network fixture'+key;im=self.image('network_full',data,'net.bin');im['public_key']=self.image('public',key,'public.raw');self.c['baseline_images']['network_full']=digest(data);self.m['operation']='reviewed_swd_baseline_restore';self.m['images']=[self.image('application_full',self.app,'full.hex'),im];return im
 def test_reviewed_app_eligible_but_no_hardware_authority(self):
  r=self.runcheck();self.assertTrue(r['eligible_for_live_identity_gate']);self.assertFalse(r['hardware_authorized'])
 def test_exact_baseline_restore_eligible(self):self.network();self.assertEqual(self.codes(),[])
 def test_hash_only_metadata_mismatch_is_not_signature_rejection(self):
  self.network('later-candidate');r=self.runcheck();self.assertEqual(r['errors'],[])
  self.assertFalse(r['network_metadata_observations'][0]['matches_installed_provision_metadata']);self.assertFalse(r['network_metadata_observations'][0]['signature_rejection_proven'])
  self.assertEqual(r['validation_capabilities']['network']['enforcement'],'integrity_only');self.assertFalse(r['hardware_authorized'])
 def test_real_later_candidate_stays_blocked_without_false_key_rejection(self):
  self.network('later-candidate');self.c['baseline_images']['network_full']='0'*64;r=self.runcheck();codes=[e['code'] for e in r['errors']]
  self.assertIn('network_review',codes);self.assertIn('restore_hash',codes);self.assertNotIn('network_signature_trust_mismatch',codes)
 def test_authenticated_network_mode_checks_metadata_but_does_not_verify_signature(self):
  self.network('later-candidate');self.c['validation_policy']['network']['mode']='ecdsa_p256_sha256_signature';r=self.runcheck()
  self.assertIn('network_signature_trust_mismatch',[e['code'] for e in r['errors']]);self.assertFalse(r['validation_capabilities']['image_signature_verification_performed'])
 def test_authenticated_network_matching_metadata_is_not_signature_proof(self):
  self.network();self.c['validation_policy']['network']['mode']='ecdsa_p256_sha256_signature';r=self.runcheck()
  self.assertEqual(r['errors'],[]);self.assertEqual(r['validation_capabilities']['network']['enforcement'],'signature');self.assertFalse(r['network_metadata_observations'][0]['signature_rejection_proven'])
 def test_unknown_network_mode_fails_closed(self):
  self.c['validation_policy']['network']['mode']='unknown';self.assertIn('network_validation_unknown',self.codes())
 def test_missing_validation_policy_fails_closed(self):
  del self.c['validation_policy'];codes=self.codes();self.assertIn('network_validation_unknown',codes);self.assertIn('application_validation_unknown',codes)
 def test_missing_installed_image_provenance_fails_closed(self):
  del self.c['validation_policy']['network']['installed_image_evidence_sha256'];self.assertIn('network_validation_unknown',self.codes())
 def test_application_rsa_verification_reported_separately(self):
  r=self.runcheck();self.assertEqual(r['validation_capabilities']['application']['mode'],'rsa_pss_2048_sha256');self.assertEqual(r['validation_capabilities']['application']['enforcement'],'signature');self.assertFalse(r['validation_capabilities']['image_signature_verification_performed'])
 def test_application_unknown_mode_not_satisfied_by_network_hash_mode(self):
  self.c['validation_policy']['application']['mode']='sha256_hash_only';self.assertIn('application_validation_unknown',self.codes())
 def test_boolean_mode_cannot_select_validation_branch(self):
  self.c['validation_policy']['network']['mode']=True;self.assertIn('network_validation_unknown',self.codes())
 def test_wrong_board(self):self.m['board']='other';self.assertIn('board',self.codes())
 def test_wrong_layout(self):self.m['layout_sha256']='wrong';self.assertIn('layout',self.codes())
 def test_missing_installed_evidence(self):self.c['installed_provision']={};self.assertIn('trust_unknown',self.codes())
 def test_non_object_installed_provision_structured_rejection(self):
  for value in [[],'false',3,True]:self.c['installed_provision']=value;self.assertIn('trust_unknown',self.codes())
 def test_missing_key_evidence(self):im=self.network();del im['public_key'];self.assertIn('network_trust_unknown',self.codes())
 def test_ambiguous_roles(self):self.m['images'].append(copy.deepcopy(self.m['images'][0]));self.assertIn('roles',self.codes())
 def test_unknown_operation(self):self.m['operation']='flash';self.assertIn('roles',self.codes())
 def test_unreviewed_app(self):self.c['reviewed_app_only_sha256']=[];self.assertIn('app_review',self.codes())
 def test_stale_hash(self):(self.root/'app.hex').write_bytes(b'changed');self.assertIn('artifact',self.codes())
 def test_persistence_overlap(self):b=ihex(0xf6000,b'x');self.m['images']=[self.image('application',b,'bad.hex')];self.assertIn('app_range',self.codes())
 def test_bootloader_overlap(self):b=ihex(0,b'x');self.m['images']=[self.image('application',b,'bad.hex')];self.assertIn('app_range',self.codes())
 def test_new_full_bytes_blocked(self):self.network();self.c['baseline_images']['network_full']='unknown';self.assertIn('network_review',self.codes());self.assertIn('restore_hash',self.codes())
 def test_ota_missing_version_dependency_and_confirmation(self):
  self.network();self.m['operation']='proposed_ota_pair';self.m['images'][0]['role']='application';self.m['images'][1]['role']='network';codes=self.codes()
  for c in ['version_policy','dependency_evidence','pinned_client_confirmation_evidence','ota_not_qualified']:self.assertIn(c,codes)
 def test_claimed_ota_policy_does_not_enable_execution(self):
  self.m['operation']='proposed_ota_pair'
  for f in ['version_policy','dependency_evidence','signature_verification_evidence','pinned_client_confirmation_evidence','overwrite_recovery_plan']:self.m[f]='synthetic declared evidence; not verified'
  self.assertIn('ota_not_qualified',self.codes())
 def test_bad_hex_checksum(self):
  with self.assertRaises(ValueError):hex_bytes(b':010000000000\n:00000001FF\n')
 def test_missing_eof(self):
  with self.assertRaises(ValueError):hex_bytes(record(0,0,b'x').encode())
 def test_path_escape(self):self.m['images'][0]['file']='../outside';self.assertIn('artifact',self.codes())
 def deep_cli(self,which):
  self.runcheck();(self.root/which).write_text('['*10000+'0'+']'*10000)
  q=subprocess.run([sys.executable,str(Path(__file__).parent/'artifact_preflight.py'),str(self.root/'input.json'),'--contract',str(self.root/'contract.json')],capture_output=True,text=True,timeout=10)
  self.assertEqual(q.returncode,2);self.assertNotIn('Traceback',q.stderr);r=json.loads(q.stdout);self.assertFalse(r['eligible_for_live_identity_gate']);self.assertIn('nesting',r['errors'][0]['reason'])
 def test_deep_manifest_structured_rejection(self):self.deep_cli('input.json')
 def test_deep_contract_structured_rejection(self):self.deep_cli('contract.json')
 def test_duplicate_json_rejected(self):
  from artifact_preflight import strict_json
  with self.assertRaises(ValueError):strict_json(b'{"schema":1,"schema":true}')
if __name__=='__main__':unittest.main()
