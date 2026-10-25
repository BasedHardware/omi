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
    scenarios = {name: {metric: 10 for metric in reporter.METRICS} for name in reporter.SCENARIOS}
    for metrics in scenarios.values():
        metrics.update(start_vm_us=1, end_vm_us=2)
    scenarios['cold_start']['restored_from_cache'] = True
    return {'schema': 'omi-mobile-perf-sim/v2', 'complete': True, 'frame_policy': 'framework-requested/v1',
            'idle_preflight_frames': 0,
            'pacing': 'fixed-real-time/v1', 'foreground_before_measurement': True,
            'native_foreground_before_measurement': True,
            'storage_isolated': True, 'build_mode': mode,
            'timeline_enabled': False,
            'acceptance_eligible': mode == 'profile', 'dataset': dict(reporter.HEAVY_DATASET),
            'scenario_order': list(reporter.SCENARIOS), 'scenarios': scenarios}


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
                    value['heavy_profile']['scenarios']['cold_start']['build_p90_us'] = 12
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


if __name__ == '__main__':
    unittest.main()
