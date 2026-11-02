import copy
import json
from pathlib import Path
import tempfile
import unittest
import telemetry_replay as tr

ROOT = Path(__file__).parent / 'telemetry-fixtures'

class TelemetryTests(unittest.TestCase):
 def setUp(self):
  self.fixture=tr.load_verified(ROOT/'sanitized-telemetry.json',ROOT/'manifest.json')
  self.policy=json.loads((ROOT/'proposed-policy.json').read_text())
  self.scenarios={x['id']:x for x in self.fixture['scenarios']}
 def monitor(self):return tr.ProposedMonitor(tr.Policy(60000,1000,30000,3))
 def record(self,name,index=0):return copy.deepcopy(self.scenarios[name]['evidence'][index]['record'])
 def test_five_real_excerpt_scenarios_not_full_exports(self):
  r=tr.report(self.fixture,self.policy)
  self.assertEqual(len(r['scenarios']),5);self.assertEqual(r['unique_excerpt_records'],16)
  self.assertEqual(r['externally_verified_full_export_counts_not_recomputed_from_excerpt']['disconnect_history_total'],67)
  self.assertEqual(r['root_cause'],'unresolved');self.assertFalse(r['instruction_level_simulation'])
 def test_snapshot_interval_and_connection_age_not_outage(self):
  r=tr.report(self.fixture,self.policy)['scenarios']['connected_zero_progress_backlog']
  self.assertEqual(r['snapshot_delta_ms_rounded'],345625)
  self.assertEqual(r['reported_connection_age_at_second_export_ms'],11416803)
  self.assertFalse(r['proposed_policy_evaluation']['continuous_outage_proven'])
 def test_stalled_backlog_preserved_with_zero_counters(self):
  m=self.monitor();m.event({'event':'connected'},0)
  a=self.record('connected_zero_progress_backlog',0);b=self.record('connected_zero_progress_backlog',1)
  self.assertFalse(m.snapshot(a,0));self.assertFalse(m.snapshot(b,345625))
  s=m.status(345625);self.assertTrue(s['policy_progress_timeout_concern']);self.assertEqual(s['backlog']['value'],68376);self.assertEqual(s['unread_packets']['value'],154);self.assertEqual(s['audio'],'unknown')
 def test_policy_timeout_is_configurable_virtual_time(self):
  m=tr.ProposedMonitor(tr.Policy(1000,1000,30000,3));m.snapshot(self.record('connected_zero_progress_backlog'),0)
  self.assertFalse(m.status(999)['policy_progress_timeout_concern']);self.assertTrue(m.status(1000)['policy_progress_timeout_concern'])
 def test_cross_export_cumulative_duplicate_has_two_refs_one_record(self):
  f=copy.deepcopy(self.fixture);entry=copy.deepcopy(self.scenarios['foreground_code19_reconnect']['evidence'][0]);entry['source']='diag1840';f['scenarios'][1]['evidence'].append(entry)
  rows=tr.merge_records(f);self.assertEqual(len(rows),16)
  row=next(x for x in rows if x['identity'][-1]=='/disconnect_history/65')
  self.assertEqual(len(row['references']),2);self.assertFalse(row['identity_conflict'])
 def test_conflicting_same_pointer_not_silently_discarded(self):
  f=copy.deepcopy(self.fixture);entry=copy.deepcopy(f['scenarios'][1]['evidence'][0]);entry['source']='diag1840';entry['record']['audio_packets_received']=999;f['scenarios'][1]['evidence'].append(entry)
  rows=tr.merge_records(f);self.assertEqual(len(rows),17);self.assertEqual(sum(x['identity_conflict'] for x in rows),2)
 def test_identical_payload_at_different_indexes_retained(self):
  f=copy.deepcopy(self.fixture);entry=copy.deepcopy(f['scenarios'][1]['evidence'][0]);entry['json_pointer']='/disconnect_history/64';f['scenarios'][1]['evidence'].append(entry)
  self.assertEqual(len(tr.merge_records(f)),17)
 def test_lowlevel_and_history_records_not_physical_event_dedup(self):
  rows=tr.merge_records(self.fixture)
  self.assertTrue(any(x['collection']=='ble_log' for x in rows));self.assertTrue(any(x['collection']=='disconnect_history' for x in rows))
 def test_remote_reason_rssi_age_lost_audio_preserved(self):
  raw=self.record('foreground_code19_reconnect');m=self.monitor();m.event(raw,0)
  self.assertEqual(m.disconnects[0],raw);self.assertEqual(raw['reason'],'remote_device_terminated');self.assertEqual(raw['code'],19);self.assertEqual(raw['last_rssi_age_ms'],8775)
  r=tr.report(self.fixture,self.policy)['scenarios']['foreground_code19_reconnect']
  self.assertEqual(r['lost_audio_seconds_recorded']['value'],20.865);self.assertEqual(r['received_recorded']['value'],714);self.assertEqual(r['expected_recorded']['value'],714);self.assertFalse(r['packet_loss_or_root_cause_derived'])
 def test_weak_signal_burst_offsets_and_nulls(self):
  r=tr.report(self.fixture,self.policy)['scenarios']['weak_signal_timeout_burst']
  self.assertEqual(r['relative_event_ms'],[0,28069,50683]);self.assertFalse(r['rssi_threshold_inferred'])
  self.assertEqual([x['last_rssi_age_ms'] for x in r['events']],[639,5780,1298]);self.assertTrue(all(x['lost_audio_seconds'] is None for x in r['events']))
 def test_bounded_retry_coalescing_no_storm(self):
  m=self.monitor();raw=self.record('weak_signal_timeout_burst');m.event(raw,0);m.event(raw,100)
  self.assertEqual(m.next_retry_at,1000);self.assertFalse(m.take_retry_due(999));self.assertTrue(m.take_retry_due(1000));self.assertFalse(m.take_retry_due(1000))
  m.event(raw,1000);self.assertEqual(m.next_retry_at,3000);self.assertTrue(m.take_retry_due(3000))
  m.event(raw,3000);self.assertEqual(m.next_retry_at,7000);self.assertTrue(m.take_retry_due(7000));m.event(raw,7000);self.assertIsNone(m.next_retry_at);self.assertEqual(m.retry_attempts,3)
 def test_link_reconnect_keeps_backlog_and_unknown_audio(self):
  m=self.monitor();m.snapshot(self.record('connected_zero_progress_backlog'),0);m.event(self.record('low_level_connected_vs_recovery_gap'),1);m.event(self.record('low_level_connected_vs_recovery_gap',2),2)
  s=m.status(2);self.assertEqual(s['link'],'connected');self.assertEqual(s['audio'],'unknown');self.assertEqual(s['subscriptions'],'unknown');self.assertEqual(s['backlog']['value'],68376)
  self.assertEqual(m.disconnects[-1]['time_to_reconnect_ms'],23725530)
 def test_lifecycle_not_battery_kill_or_manual_relaunch_proof(self):
  m=self.monitor();m.event(self.record('low_level_connected_vs_recovery_gap',3),0);m.event(self.record('low_level_connected_vs_recovery_gap',4),1)
  self.assertEqual(m.service,'started');self.assertEqual(m.subscriptions,'unknown');self.assertEqual(m.audio,'unknown')
  r=tr.report(self.fixture,self.policy)['scenarios']['low_level_connected_vs_recovery_gap'];self.assertEqual(r['low_level_connected_delay_ms'],6045);self.assertEqual(r['recorded_reconnect_delay_ms'],23725530);self.assertFalse(r['continuous_outage_proven']);self.assertFalse(r['manual_relaunch_or_battery_kill_proven'])
 def test_marker_timestamp_and_ingestion_order_separate(self):
  r=tr.report(self.fixture,self.policy)['scenarios']['recovery_marker_ordering_and_schema']
  self.assertEqual(r['ingestion_order'],['disconnect','audio_recovered']);self.assertEqual(r['audio_recovered_timestamp_minus_disconnect_ms'],-35);self.assertFalse(r['negative_outage_duration_inferred'])
 def test_null_marker_does_not_measure_audio_recovery(self):
  m=self.monitor();raw=self.record('recovery_marker_ordering_and_schema',1);m.event(raw,0)
  self.assertEqual(m.status(0)['audio'],'unknown');self.assertIsNone(m.recovery_markers[0]['audio_packets_received'])
 def test_missing_null_zero_unknown_distinct(self):
  self.assertEqual(tr.field({},'x'),{'presence':'absent'});self.assertEqual(tr.field({'x':None},'x'),{'presence':'null','value':None});self.assertEqual(tr.field({'x':0},'x'),{'presence':'value','value':0})
  m=self.monitor();m.snapshot({'connected_at':1,'audio_packets_received_current':None},0);self.assertTrue(m.status(999999)['telemetry_insufficient']);self.assertFalse(m.status(999999)['policy_progress_timeout_concern'])
 def test_positive_counter_delta_only_same_session(self):
  m=self.monitor();a=self.record('connected_zero_progress_backlog');m.snapshot(a,0);b=copy.deepcopy(a);b['audio_packets_received_current']=1;b['audio_packets_expected_current']=1
  self.assertTrue(m.snapshot(b,1));self.assertEqual(m.audio,'sampled_counter_progress')
  b['connected_at']+=1;self.assertFalse(m.snapshot(b,2));self.assertEqual(m.audio,'unknown')
 def test_counter_reset_not_progress(self):
  m=self.monitor();a=self.record('connected_zero_progress_backlog');a['audio_packets_received_current']=100;a['audio_packets_expected_current']=100;m.snapshot(a,0)
  self.assertFalse(m.snapshot(self.record('connected_zero_progress_backlog'),1));self.assertEqual(m.audio,'unknown')
 def test_future_schema_rejected(self):
  f=copy.deepcopy(self.fixture);f['metadata']['schema_version']=3
  with self.assertRaises(tr.UnsupportedTelemetrySchema):tr.merge_records(f)
  f=copy.deepcopy(self.fixture);f['scenarios'][0]['evidence'][0]['record']['schema_version']=99
  with self.assertRaises(tr.UnsupportedTelemetrySchema):tr.validate_fixture(f)
 def test_monotonic_policy_clock_not_event_timestamp(self):
  m=self.monitor();m.event(self.record('recovery_marker_ordering_and_schema',0),0);m.event(self.record('recovery_marker_ordering_and_schema',1),1)
  with self.assertRaises(ValueError):m.status(0)
 def test_firmware_not_assigned_to_history_and_missing_keys_uninvented(self):
  raw=self.record('foreground_code19_reconnect');self.assertNotIn('firmware',raw)
  snap=self.record('connected_zero_progress_backlog');self.assertNotIn('offline_sync_events',snap);self.assertNotIn('offline_storage_total_bytes',snap)
  self.assertIn('unknown',tr.report(self.fixture,self.policy)['historical_firmware_assignment'])
 def test_fixture_hash_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'sanitized-telemetry.json';p.write_bytes((ROOT/p.name).read_bytes()+b' ')
   with self.assertRaises(ValueError):tr.load_verified(p,ROOT/'manifest.json')
 def test_policy_is_explicit_proposal(self):
  r=tr.report(self.fixture,self.policy);self.assertEqual(r['proposed_policy']['provenance'],'engineering_proposal_not_observed_device_behavior');self.assertEqual(r['hardware_acceptance'],'not_measured')
if __name__=='__main__':unittest.main()
