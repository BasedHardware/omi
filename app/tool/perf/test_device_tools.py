import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runner = module('device_run')
comparison = module('compare')


def summary():
    return {'accepted_baseline': True, 'variance_pass': True, 'build_mode': 'profile',
            'dataset': {'wals': 6500}, 'frame_policy': 'benchmarkLive',
            'pacing': 'fixed-real-time/v1', 'timeline_enabled': False,
            'identity': {'device_id': 'fixture-device', 'platform': 'ios',
                         'flutter_revision': 'fixture-sdk', 'harness_sha256': 'fixture-harness'},
            'scenarios': {'cold_start': {'build_p90_us': [10, 11, 10], 'raster_p90_us': [20, 21, 20],
                          'total_p90_us': [30, 31, 30], 'frames_over_16ms': [1, 2, 3],
                          'frames_over_100ms': [1, 0, 0], 'worst_total_us': [100001, 20, 30]}}}


class DeviceToolsTests(unittest.TestCase):
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
        for key in ('device_id', 'platform', 'flutter_revision', 'harness_sha256'):
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
