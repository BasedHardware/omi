import base64,json,tempfile,unittest
from pathlib import Path
import bench,evidence
class EvidenceTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
 def tearDown(self):self.t.cleanup()
 def uart(self,raw=b'',closed=True,count=None):
  p=self.root/'metadata.json';p.write_text(json.dumps({'start':'synthetic-test-start','end':'synthetic-test-end','bytes':len(raw) if count is None else count,'status':'duration_complete','errors':[],'port_closed':closed,'transmitted_bytes':0}));r=self.root/'raw.bin';r.write_bytes(raw);return p,r
 def test_empty_actual_capture_remains_empty(self):
  m,r=self.uart();p=evidence.import_capture(self.root/'import','uart_capture',m,r)
  self.assertEqual(list(evidence.replay_uart(p)),[])
  self.assertEqual(evidence.validate_capture(p)['metadata']['bytes'],0)
 def test_uart_replay_preserves_nonutf8(self):
  raw=b'\x00\xff\xfehello\r\n';m,r=self.uart(raw);p=evidence.import_capture(self.root/'import','uart_capture',m,r)
  chunks=list(evidence.replay_uart(p,chunk_size=2));self.assertEqual(b''.join(base64.b64decode(x['data_base64']) for x in chunks),raw)
  self.assertTrue(all('synthetic' in x['timing'] for x in chunks))
 def test_active_capture_refused(self):
  m,r=self.uart(closed=False)
  with self.assertRaises(ValueError):evidence.import_capture(self.root/'import','uart_capture',m,r)
 def test_size_mismatch_refused(self):
  m,r=self.uart(b'abc',count=4)
  with self.assertRaises(ValueError):evidence.import_capture(self.root/'import','uart_capture',m,r)
 def test_future_debug_receipt(self):
  m=self.root/'debug.json';m.write_text(json.dumps({'started_at':'synthetic-test','completed_at':'synthetic-test-end','target':{'id':'synthetic-target'},'operations':['synthetic-reset-observation'],'status':'completed','cleanup_verified':True}))
  p=evidence.import_capture(self.root/'debug','debug_capture',m);self.assertEqual(evidence.validate_capture(p)['evidence_type'],'debug_capture')
 def test_capture_tamper_refused(self):
  m,r=self.uart(b'abc');p=evidence.import_capture(self.root/'import','uart_capture',m,r);(p.parent/'raw.bin').write_bytes(b'xxx')
  with self.assertRaises(ValueError):evidence.validate_capture(p)
 def test_comparison_detects_config_change_without_approval(self):
  a=self.root/'omi.conf';a.write_text('CONFIG_LOG=n\nCONFIG_BT_DIS_FW_REV_STR="1"\n')
  b=bench.manifest(self.root/'runs','baseline',[a],'test')
  a.write_text('CONFIG_LOG=y\nCONFIG_BT_DIS_FW_REV_STR="2"\n');c=bench.manifest(self.root/'runs','candidate',[a],'test2',b)
  report=evidence.compare(b,c);self.assertEqual(report['artifact_changes'][0]['state'],'changed');self.assertEqual(report['config_changes']['omi.conf']['CONFIG_LOG']['candidate'],'y');self.assertFalse(report['release_approved'])
 def test_wrong_baseline_refused(self):
  a=self.root/'a.bin';a.write_bytes(b'a');b=bench.manifest(self.root/'runs','baseline',[a],'test');other=bench.manifest(self.root/'runs','baseline',[a],'test');c=bench.manifest(self.root/'runs','candidate',[a],'test',b)
  with self.assertRaises(ValueError):evidence.compare(other,c)
 def test_ble_replay_excludes_synthetic(self):
  p=self.root/'receipt.json';p.write_text(json.dumps({'state':'completed','error':None,'run_id':'synthetic-test-receipt','results':[],'match_count':0}));index=bench.corpus(self.root/'corpus',[p]);report=evidence.replay_ble(index)
  self.assertEqual(len(report['observations']),1);self.assertFalse(report['device_emulation'])
  self.assertEqual(report['observations'][0]['provenance'],'operator_supplied');self.assertIn('cannot prove',report['limitations'][0])
 def test_string_false_cannot_finalize_capture(self):
  m,r=self.uart(b'abc');metadata=json.loads(m.read_text());metadata['port_closed']='false';m.write_text(json.dumps(metadata))
  with self.assertRaises(ValueError):evidence.import_capture(self.root/'import','uart_capture',m,r)
 def test_string_true_cannot_finalize_debug_receipt(self):
  m=self.root/'debug.json';m.write_text(json.dumps({'started_at':'synthetic-test','completed_at':'synthetic-test-end','target':{'id':'synthetic-target'},'operations':['synthetic-reset-observation'],'status':'completed','cleanup_verified':'false'}))
  with self.assertRaises(ValueError):evidence.import_capture(self.root/'debug','debug_capture',m)
 def test_unlisted_metadata_source_refused(self):
  m,r=self.uart(b'abc');p=evidence.import_capture(self.root/'import','uart_capture',m,r)
  record=json.loads(p.read_text());record['sources']=[s for s in record['sources'] if s['snapshot']!='metadata.json'];p.write_text(json.dumps(record))
  with self.assertRaises(ValueError):evidence.validate_capture(p)
 def test_validate_capture_enforces_raw_size_relationship(self):
  m,r=self.uart(b'abc');p=evidence.import_capture(self.root/'import','uart_capture',m,r)
  record=json.loads(p.read_text());record['metadata']['bytes']=99;m.write_text(json.dumps(record['metadata']))
  for s in record['sources']:
   if s['snapshot']=='metadata.json':s.update(sha256=bench.digest(m),size_bytes=m.stat().st_size)
  (p.parent/'metadata.json').write_text(json.dumps(record['metadata']));p.write_text(json.dumps(record))
  with self.assertRaises(ValueError):evidence.validate_capture(p)
 def test_replay_ble_rejects_result_without_peripheral_id(self):
  p=self.root/'receipt.json';p.write_text(json.dumps({'state':'completed','error':None,'results':[{'rssi':-70}],'match_count':1}));index=bench.corpus(self.root/'corpus',[p])
  with self.assertRaises(ValueError):evidence.replay_ble(index)
 def test_replay_ble_rejects_inconsistent_match_count(self):
  p=self.root/'receipt.json';p.write_text(json.dumps({'state':'completed','error':None,'results':[{'peripheral_id':'aa'},{'peripheral_id':'cc'}],'match_count':1}));index=bench.corpus(self.root/'corpus',[p])
  with self.assertRaises(ValueError):evidence.replay_ble(index)
 def test_uart_byte_count_must_be_an_integer(self):
  for declared in (True,1.0,'1'):
   with self.subTest(declared=declared):
    root=self.root/('uart-'+str(declared));root.mkdir();(root/'raw.bin').write_bytes(b'x');metadata={'bytes':declared}
    (root/'metadata.json').write_text(json.dumps(metadata))
    sources=[{'snapshot':name,'sha256':evidence.bench.digest(root/name),'size_bytes':(root/name).stat().st_size} for name in ('metadata.json','raw.bin')]
    (root/'capture.json').write_text(json.dumps({'schema_version':1,'provenance':'operator_supplied','evidence_type':'uart_capture','sources':sources,'metadata':metadata}))
    with self.assertRaisesRegex(ValueError,'byte count'):evidence.validate_capture(root/'capture.json')
if __name__=='__main__':unittest.main()
