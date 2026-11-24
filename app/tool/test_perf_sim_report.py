import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('perf_sim_report', Path(__file__).with_name('perf_sim_report.py'))
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def receipt(mode='profile'):
    scenarios = {name: {metric: 10 for metric in reporter.METRICS + reporter.STALL_METRICS} for name in reporter.SCENARIOS if name != "wal_sync_upload_success"}
    for metrics in scenarios.values():
        metrics.update(start_vm_us=1, end_vm_us=2, **{name: 0 for name in reporter.STALL_METRICS})
    scenarios['cold_start'].update(restored_from_cache=True, cache_ready_us=1000000)
    return {'schema': 'omi-mobile-perf-sim/v2', 'complete': True, 'frame_policy': 'framework-requested/v1',
            'idle_preflight_frames': 0,
            'pacing': 'fixed-real-time/v1', 'foreground_before_measurement': True,
            'native_foreground_before_measurement': True,
            'storage_isolated': True, 'build_mode': mode,
            'timeline_enabled': False,
            'acceptance_eligible': mode == 'profile', 'dataset': {**reporter.HEAVY_DATASET, 'semantics': 'off', 'upload': 'refuse'},
            'scenario_order': list(scenarios), 'scenarios': scenarios}


def driver_response(mode='profile', run=1):
    return {'heavy_profile': receipt(mode), 'heavy_run': {
        'source_sha': 'test-source', 'binary_sha256': 'test-binary', 'harness_sha256': 'test-harness',
        'device_id': 'test-device', 'device_os_version': 'test-os', 'platform': 'ios', 'flutter_revision': 'test-sdk'},
        'heavy_timeline_capture': {'enabled': False, 'file': None, 'events': 0, 'truncated': False}}


class ReportTests(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def batch(self, mutate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(3):
                value = driver_response('debug', i)
                mutate(value['heavy_profile'], i)
                (root / f'receipt-{i}.json').write_text(json.dumps(value))
            return reporter.summarize(root, 3)

    def test_sparse_p90_noise_does_not_gate_or_drop_runs(self):
        def mutate(value, i):
            for name in ('cold_start', 'home_idle_sync_refresh'):
                for metric in reporter.P90_METRICS:
                    value['scenarios'][name][metric] = [10, 164, 70][i]
        result = self.batch(mutate)
        self.assertTrue(result['variance_pass'])
        self.assertEqual(result['scenarios']['cold_start']['build_p90_us'], [10, 164, 70])
        self.assertEqual(result['scoring_protocol'], reporter.SCORING_PROTOCOL)

    def test_upload_window_is_scored_as_sparse(self):
        self.assertTrue(reporter.SCENARIOS['wal_sync_upload_success']['sparse'])
        self.assertFalse(reporter.SCENARIOS['wal_sync_bg_fg']['sparse'])

    def test_cold_readiness_keeps_fifteen_percent_gate(self):
        for last, passed in ((1150000, True), (1150001, False)):
            result = self.batch(lambda r, i: r['scenarios']['cold_start'].update(
                cache_ready_us=last if i == 2 else 1000000))
            self.assertEqual(result['variance_pass'], passed)
            self.assertEqual(result['scenarios']['cold_start']['cache_ready_us'][-1], last)

    def test_sparse_stall_budgets_apply_to_every_run_and_both_windows(self):
        for scenario in ('cold_start', 'home_idle_sync_refresh'):
            for metric, limit in reporter.SPARSE_STALL_LIMITS.items():
                for value, passed in ((limit, True), (limit + 1, False)):
                    result = self.batch(lambda r, i: r['scenarios'][scenario].update(
                        {metric: value if i == 1 else 0}))
                    self.assertEqual(result['variance_pass'], passed)
                    self.assertEqual(result['scenarios'][scenario][metric][1], value)

    def test_synced_history_is_diagnostic_not_standard_heavy_baseline(self):
        result = self.batch(lambda r, i: r['dataset'].update(synced_wals=66222))
        self.assertFalse(result['heavy_dataset'])
        self.assertFalse(result['accepted_baseline'])

    def test_dense_stalls_remain_diagnostic(self):
        result = self.batch(lambda r, i: r['scenarios']['scroll_conversations'].update(
            stalls_over_100ms=i * 100, stall_blocked_over_100ms_us=i * 999999))
        self.assertTrue(result['variance_pass'])

    def test_readiness_and_dataset_modes_required(self):
        for bad in (None, 0, -1, True, float('inf')):
            value = receipt()
            value['scenarios']['cold_start']['cache_ready_us'] = bad
            with self.assertRaises(ValueError):
                reporter.validate(value)
        for key in ('semantics', 'upload'):
            value = receipt()
            del value['dataset'][key]
            with self.assertRaises(ValueError):
                reporter.validate(value)

    def test_semantics_cannot_mix_within_batch(self):
        with self.assertRaisesRegex(ValueError, 'dataset'):
            self.batch(lambda r, i: r['dataset'].update(semantics='on' if i == 1 else 'off'))

    def test_upload_window_is_required_only_when_accepting(self):
        value = receipt()
        value['dataset'].update(upload='accept', upload_wals=12)
        with self.assertRaises(ValueError):
            reporter.validate(value)
        window = dict(value['scenarios']['scroll_conversations'], uploaded_wals=12, completed_jobs=12)
        value['scenarios']['wal_sync_upload_success'] = window
        value['scenario_order'].append('wal_sync_upload_success')
        self.assertIs(reporter.validate(value), value)
        window['uploaded_wals'] = 11
        with self.assertRaisesRegex(ValueError, 'upload/reconcile'):
            reporter.validate(value)
        window['uploaded_wals'] = 12
        value['dataset']['upload'] = 'refuse'
        with self.assertRaises(ValueError):
            reporter.validate(value)

    def test_empty_or_incomplete_evidence_rejected(self):
        for change in ({'complete': False}, {'scenarios': {}}, {'storage_isolated': False},
                       {'idle_preflight_frames': 240}, {'native_foreground_before_measurement': False}):
            value = receipt()
            value.update(change)
            with self.assertRaises(ValueError):
                reporter.validate(value)

    def test_missing_nonfinite_and_zero_frames_rejected(self):
        for bad in (None, -1, float('nan'), float('inf'), True):
            value = receipt()
            value['scenarios']['cold_start']['build_p90_us'] = bad
            with self.assertRaises(ValueError):
                reporter.validate(value)
        value = receipt()
        value['scenarios']['cold_start']['frame_count'] = 0
        with self.assertRaises(ValueError):
            reporter.validate(value)

    def test_spread_uses_fastest_run(self):
        self.assertAlmostEqual(reporter.spread([100, 115, 110]), .15)
        self.assertGreater(reporter.spread([100, 116, 110]), .15)

    def test_variance_failure_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(3):
                value = driver_response(run=i)
                if i == 2:
                    value['heavy_profile']['scenarios']['scroll_conversations']['build_p90_us'] = 12
                (root / f'receipt-{i}.json').write_text(json.dumps(value))
                (root / f'receipt-{i}-preservation.json').write_text(json.dumps({
                    'verified': True, 'bundle_id': 'com.friend-app-with-wearable.ios12.development'}))
            summary = reporter.summarize(root, 3)
            self.assertTrue(summary['acceptance_eligible'])
            self.assertFalse(summary['variance_pass'])
            self.assertFalse(summary['accepted_baseline'])

    def test_truncated_or_partial_timeline_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = driver_response()
            value['heavy_profile'].update(timeline_enabled=True, acceptance_eligible=False)
            value['heavy_timeline_capture'].update(enabled=True, file='receipt-1-timeline.json',
                                                    events=1, truncated=True)
            (root / 'receipt-1.json').write_text(json.dumps(value))
            (root / 'receipt-1-preservation.json').write_text(json.dumps({
                'verified': True, 'bundle_id': 'com.friend-app-with-wearable.ios12.development'}))
            (root / 'receipt-1-timeline.json').write_text('{"traceEvents":[]}')
            with self.assertRaises(ValueError):
                reporter.summarize(root, 1)
            value['heavy_timeline_capture']['truncated'] = False
            (root / 'receipt-1.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                reporter.summarize(root, 1)

    def test_three_runs_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'receipt-1.json').write_text(json.dumps(driver_response()))
            with self.assertRaises(ValueError):
                reporter.summarize(root, 3)

    def test_missing_physical_ios_retention_proof_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(3):
                (root / f'receipt-{i}.json').write_text(json.dumps(driver_response(run=i)))
            with self.assertRaisesRegex(ValueError, 'missing DEV sandbox preservation proof'):
                reporter.summarize(root, 3)

    def test_debug_never_eligible_and_mode_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(3):
                (root / f'receipt-{i}.json').write_text(json.dumps(driver_response('debug', i)))
                (root / f'receipt-{i}-timeline.json').write_text('{"traceEvents":[]}')
            self.assertFalse(reporter.summarize(root, 3)['acceptance_eligible'])
            (root / 'receipt-1.json').write_text(json.dumps(driver_response()))
            (root / 'receipt-1-preservation.json').write_text(json.dumps({
                'verified': True, 'bundle_id': 'com.friend-app-with-wearable.ios12.development'}))
            with self.assertRaises(ValueError):
                reporter.summarize(root, 3)

    def test_virtual_baseline_requires_retained_identical_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = driver_response()
            value['heavy_profile'].update(virtual_qualification=True, acceptance_eligible=False)
            value['heavy_run'].update(platform='android',
                                     native_harness={'package': 'com.friend.ios.dev', 'firebase_auto_initializer_absent': True},
                                     virtual_runtime={'kind': 'android-emulator', 'runtime_build': 'pinned',
                                                      'host': {'node_sha256': 'a' * 64, 'platform': 'fixture-os',
                                                               'architecture': 'arm64', 'logical_cpus': 10}},
                                     launch_protocol={'warmup_runs': 1, 'measured_runs': 3, 'outlier_policy': 'retain-all',
                                                      'host_load_policy': 'load1-per-logical-cpu<=1/v1'})
            for prefix, count in (('warmup', 1), ('receipt', 3)):
                for index in range(1, count + 1):
                    (root / f'{prefix}-{index}-host-load.json').write_text(json.dumps({
                        'policy': 'load1-per-logical-cpu<=1/v1', 'passed': True, 'command_exit_code': 0,
                        'samples': [{'phase': phase, 'logical_cpus': 10, 'load_1_5_15m': [10, 9, 8]}
                                    for phase in ('before', 'after')]}))
            for i in range(1, 4):
                (root / f'receipt-{i}.json').write_text(json.dumps(value))
            with self.assertRaises(FileNotFoundError):
                reporter.summarize(root, 3)
            (root / 'warmup-1.json').write_text(json.dumps(value))
            summary = reporter.summarize(root, 3)
            self.assertTrue(summary['qualified_virtual_baseline'])
            self.assertFalse(summary['accepted_baseline'])
            host_path = root / 'receipt-2-host-load.json'
            host = json.loads(host_path.read_text())
            host['samples'][1]['load_1_5_15m'][0] = 10.01
            host_path.write_text(json.dumps(host))
            with self.assertRaisesRegex(ValueError, 'host overload'):
                reporter.summarize(root, 3)
            host['samples'][1]['load_1_5_15m'][0] = 10
            host_path.write_text(json.dumps(host))
            value['heavy_run']['binary_sha256'] = 'different'
            (root / 'warmup-1.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'warmup differs'):
                reporter.summarize(root, 3)
            del value['heavy_run']['virtual_runtime']['host']
            for path in [root / f'receipt-{i}.json' for i in range(1, 4)] + [root / 'warmup-1.json']:
                path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'requires host identity'):
                reporter.summarize(root, 3)

    def test_ios_profile_cannot_masquerade_as_virtual_profile_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = driver_response()
            value['heavy_profile'].update(virtual_qualification=True, acceptance_eligible=False)
            value['heavy_run'].update(virtual_runtime={'kind': 'ios-simulator', 'runtime_build': 'pin'},
                                     launch_protocol={'warmup_runs': 1, 'measured_runs': 3, 'outlier_policy': 'retain-all'})
            for i in range(1, 4):
                (root / f'receipt-{i}.json').write_text(json.dumps(value))
                (root / f'receipt-{i}-preservation.json').write_text(json.dumps({
                    'verified': True, 'bundle_id': 'com.friend-app-with-wearable.ios12.development'}))
            with self.assertRaisesRegex(ValueError, 'platform/build mode'):
                reporter.summarize(root, 3)


if __name__ == '__main__':
    unittest.main()
