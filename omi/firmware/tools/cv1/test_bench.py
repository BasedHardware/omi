import copy,json,tempfile,unittest
from pathlib import Path
import bench
class BenchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self): self.temp.cleanup()
 def test_exclusive_and_clean_reacquire(self):
  with bench.Lease(self.root,'one') as one:
   with self.assertRaises(bench.Busy):
    with bench.Lease(self.root,'two'): pass
   one.clean=True
  with bench.Lease(self.root,'three') as three: three.clean=True
 def test_unclean_quarantine(self):
  with bench.Lease(self.root,'one'): pass
  with self.assertRaises(bench.Busy):
   with bench.Lease(self.root,'two'): pass
 def test_crashed_owner_not_stolen(self):
  lease=bench.Lease(self.root,'crash').__enter__();lease.fd.close()
  with self.assertRaises(bench.Busy):
   with bench.Lease(self.root,'later'): pass
 def test_manifest_snapshot_candidate_link(self):
  artifact=self.root/'app.bin';artifact.write_bytes(b'baseline')
  base=bench.manifest(self.root/'runs','baseline',[artifact],'test')
  artifact.write_bytes(b'candidate')
  cand=bench.manifest(self.root/'runs','candidate',[artifact],'next',base)
  b=json.loads(base.read_text());c=json.loads(cand.read_text())
  self.assertEqual((base.parent/b['artifacts'][0]['snapshot']).read_bytes(),b'baseline')
  self.assertEqual(c['baseline']['sha256'],bench.digest(base))
  self.assertFalse(c['installed_on_device_verified'])
  self.assertNotEqual(b['artifacts'][0]['sha256'],c['artifacts'][0]['sha256'])
 def test_candidate_requires_baseline(self):
  with self.assertRaises(ValueError): bench.manifest(self.root,'candidate',[],'test')
 def test_tampered_baseline_refused(self):
  p=self.root/'image.bin';p.write_bytes(b'known')
  base=bench.manifest(self.root/'runs','baseline',[p],'test')
  b=json.loads(base.read_text());(base.parent/b['artifacts'][0]['snapshot']).write_bytes(b'tampered')
  with self.assertRaises(ValueError):bench.manifest(self.root/'runs','candidate',[p],'next',base)
 def test_hex_ranges_checksums(self):
  p=self.root/'image.hex';p.write_text(':020000040000FA\n:0400000001020304F2\n:00000001FF\n')
  self.assertEqual(bench.hex_ranges(p),[{'start':'0x0','end_exclusive':'0x4'}])
  p.write_text(':0400000001020304F3\n:00000001FF\n')
  with self.assertRaises(ValueError):bench.hex_ranges(p)
 def test_hex_ranges_rejects_overlap(self):
  p=self.root/'image.hex';p.write_text(':020000040000FA\n:0400000001020304F2\n:020000000102FB\n:00000001FF\n')
  with self.assertRaises(ValueError):bench.hex_ranges(p)
 def test_hex_ranges_adjacent_records_merge_without_overlap(self):
  p=self.root/'image.hex';p.write_text(':0400000001020304F2\n:020004000507EE\n:00000001FF\n')
  self.assertEqual(bench.hex_ranges(p),[{'start':'0x0','end_exclusive':'0x6'}])
 def test_actual_payload_and_hash(self):
  receipt=self.root/'receipt.json';receipt.write_text(json.dumps({'state':'completed','error':None,'results':[]}))
  index=bench.corpus(self.root/'corpus',[receipt]);record=json.loads(index.read_text())[0]
  self.assertTrue(bench.validate_corpus(record,index.parent))
  bad=copy.deepcopy(record);bad['observation']['results']=[{'invented':True}]
  with self.assertRaises(ValueError):bench.validate_corpus(bad,index.parent)
  (index.parent/record['source']['snapshot']).write_text('{}')
  with self.assertRaises(ValueError):bench.validate_corpus(record,index.parent)
 def test_provenance_separation(self):
  for value in [{'schema_version':1,'scenario':'x'},{'schema_version':1,'provenance':'synthetic','scenario':'x','source':{}},{'schema_version':1,'provenance':'operator_supplied','expected':True}]:
   with self.assertRaises(ValueError):bench.validate_corpus(value,self.root)
 def test_success_cleanup(self):
  r=json.loads(bench.synthetic_run(self.root).read_text());self.assertEqual(r['state'],'completed');self.assertTrue(r['cleanup_verified']);self.assertFalse(r['hardware_access'])
 def test_timeout_cleanup(self):
  r=json.loads(bench.synthetic_run(self.root,delay=5,timeout=.3).read_text());self.assertEqual(r['state'],'timeout');self.assertTrue(r['direct_child_reaped']);self.assertTrue(r['process_group_absent'])
 def test_term_resistant_cleanup(self):
  r=json.loads(bench.synthetic_run(self.root,delay=5,timeout=.3,ignore_term=True).read_text());self.assertEqual(r['state'],'timeout');self.assertTrue(r['kill_required']);self.assertTrue(r['cleanup_verified'])
 def test_unbounded_timeout_refused(self):
  with self.assertRaises(ValueError):bench.synthetic_run(self.root,timeout=3600)
if __name__=='__main__':unittest.main()
