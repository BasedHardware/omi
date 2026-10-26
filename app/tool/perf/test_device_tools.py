import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runner = module('device_run')
comparison = module('compare')


def summary():
    return {'accepted_baseline': True, 'variance_pass': True, 'build_mode': 'profile', 'runs': 3,
            'dataset': {'wals': 6500}, 'frame_policy': 'framework-requested/v1',
            'pacing': 'fixed-real-time/v1', 'timeline_enabled': False,
            'identity': {'device_id': 'fixture-device', 'platform': 'ios',
                         'device_os_version': 'fixture-os',
                         'flutter_revision': 'fixture-sdk', 'harness_sha256': 'fixture-harness'},
            'scenarios': {'cold_start': {'build_p90_us': [10, 11, 10], 'raster_p90_us': [20, 21, 20],
                          'total_p90_us': [30, 31, 30], 'frames_over_16ms': [1, 2, 3],
                          'frames_over_100ms': [1, 0, 0], 'worst_total_us': [100001, 20, 30]}}}


class DeviceToolsTests(unittest.TestCase):
    def test_stale_gui_request_cannot_start_a_device_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / 'launch.json'
            spec.write_text(json.dumps({'out': str(root), 'env': {}, 'parent_pid': os.getpid(),
                                         'parent_start': 'a different process incarnation',
                                         'platform': 'ios',
                                         'launch_expires_at': time.time() + 300}))
            self.assertEqual(runner.worker(spec), 1)
            self.assertEqual((root / 'runner-done.txt').read_text(), 'PERF_DONE exit=1\n')
            self.assertFalse((root / 'child-pgid.txt').exists())

    def test_delayed_aqua_launch_cannot_clobber_the_first_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'worker-claim').mkdir()
            (root / 'worker-pid.txt').write_text('first-worker\n')
            spec = root / 'launch.json'
            spec.write_text(json.dumps({'out': str(root)}))
            self.assertEqual(runner.worker(spec), 0)
            self.assertEqual((root / 'worker-pid.txt').read_text(), 'first-worker\n')
            self.assertFalse((root / 'runner-done.txt').exists())

    def test_autodetect_ignores_simulator_desktop_and_unsupported(self):
        devices = [{'id': 'sim', 'targetPlatform': 'ios', 'emulator': True},
                   {'id': 'mac', 'targetPlatform': 'darwin', 'emulator': False},
                   {'id': 'unsupported', 'targetPlatform': 'ios', 'emulator': False, 'isSupported': False},
                   {'id': 'phone', 'targetPlatform': 'ios', 'emulator': False, 'isSupported': True}]
        self.assertEqual(runner.choose_ios(devices), 'phone')
        with self.assertRaises(ValueError):
            runner.choose_ios(devices + [dict(devices[-1], id='second-phone')])
        with self.assertRaises(ValueError):
            runner.choose_ios(devices[:-1])

    def test_comparison_preserves_failed_variance_and_jank(self):
        before, after = summary(), summary()
        after.update(accepted_baseline=False, variance_pass=False)
        after['scenarios']['cold_start']['total_p90_us'] = [15, 16, 15]
        result = comparison.compare(before, after)
        self.assertFalse(result['current_variance_pass'])
        self.assertEqual(result['scenarios']['cold_start']['total_p90_us']['change_percent'], -50)
        self.assertEqual(result['scenarios']['cold_start']['frames_over_100ms'], {'before': 1, 'after': 1})

    def test_incomparable_or_unaccepted_reference_rejected(self):
        for key in ('device_id', 'device_os_version', 'platform', 'flutter_revision', 'harness_sha256'):
            after = summary()
            after['identity'][key] = 'different'
            with self.assertRaises(ValueError):
                comparison.compare(summary(), after)
        before = summary()
        before['accepted_baseline'] = False
        with self.assertRaises(ValueError):
            comparison.compare(before, summary())
        after = summary()
        after['timeline_enabled'] = True
        with self.assertRaises(ValueError):
            comparison.compare(summary(), after)

    def test_virtual_comparison_cannot_cross_runtime_or_physical_evidence(self):
        before, after = summary(), summary()
        for value in (before, after):
            value.update(accepted_baseline=False, qualified_virtual_baseline=True, virtual_qualification=True)
            value['identity'].update(virtual_runtime={'kind': 'android-emulator', 'runtime_build': 'pin',
                                                     'host': {'node_sha256': 'a' * 64}},
                                     launch_protocol={'warmup_runs': 1, 'measured_runs': 3, 'outlier_policy': 'retain-all'})
        self.assertTrue(comparison.compare(before, after)['current_variance_pass'])
        after['identity']['virtual_runtime']['runtime_build'] = 'new'
        with self.assertRaisesRegex(ValueError, 'virtual_runtime'):
            comparison.compare(before, after)
        after['identity']['virtual_runtime']['runtime_build'] = 'pin'
        after['identity']['virtual_runtime']['host']['node_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'virtual_runtime'):
            comparison.compare(before, after)
        del after['identity']['virtual_runtime']['host']
        with self.assertRaisesRegex(ValueError, 'requires host identity'):
            comparison.compare(before, after)
        after = summary()
        with self.assertRaisesRegex(ValueError, 'virtual and physical'):
            comparison.compare(before, after)
        with self.assertRaisesRegex(ValueError, 'physical and virtual'):
            comparison.compare(summary(), before)

    def test_cancellation_reaps_owned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'sleep.py'
            script.write_text('import time\ntime.sleep(60)\n')
            process = subprocess.Popen([sys.executable, '-I', str(script)], start_new_session=True)
            runner.stop(process)
            self.assertIsNotNone(process.poll())
            self.assertNotEqual(process.returncode, 0)
            runner.stop(process)


if __name__ == '__main__':
    unittest.main()
