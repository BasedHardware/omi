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
    return {'scoring_protocol': 'sparse-readiness-stalls/v1',
            'sparse_stall_limits': {'stalls_over_100ms': 2, 'stall_blocked_over_100ms_us': 500000},
            'sparse_scenarios': ['cold_start', 'home_idle_sync_refresh'],
            'accepted_baseline': True, 'variance_pass': True, 'build_mode': 'profile', 'runs': 3,
            'dataset': {'wals': 6500, 'semantics': 'off', 'upload': 'refuse'}, 'frame_policy': 'framework-requested/v1',
            'pacing': 'fixed-real-time/v1', 'timeline_enabled': False,
            'identity': {'device_id': 'fixture-device', 'platform': 'ios',
                         'device_os_version': 'fixture-os',
                         'flutter_revision': 'fixture-sdk', 'harness_sha256': 'fixture-harness'},
            'scenarios': {'cold_start': {'build_p90_us': [10, 11, 10], 'raster_p90_us': [20, 21, 20],
                          'total_p90_us': [30, 31, 30], 'frames_over_16ms': [1, 2, 3],
                          'frames_over_100ms': [1, 0, 0], 'worst_total_us': [100001, 20, 30],
                          'stalls_over_100ms': [0, 1, 0], 'stall_blocked_over_100ms_us': [0, 150000, 0],
                          'cache_ready_us': [1000000, 1100000, 1050000]}}}


class DeviceToolsTests(unittest.TestCase):
    def test_semantics_and_scoring_protocol_must_match(self):
        for setting in ('on', None):
            after = summary()
            after['dataset']['semantics'] = setting
            with self.assertRaisesRegex(ValueError, 'semantics'):
                comparison.compare(summary(), after)
        after = summary()
        after['scoring_protocol'] = 'other'
        with self.assertRaisesRegex(ValueError, 'scoring_protocol'):
            comparison.compare(summary(), after)

    def test_comparison_exposes_sparse_readiness_and_stalls(self):
        before, after = summary(), summary()
        after['scenarios']['cold_start']['stalls_over_100ms'] = [0, 3, 0]
        result = comparison.compare(before, after)['scenarios']['cold_start']
        self.assertEqual(result['cache_ready_us']['before'], [1000000, 1100000, 1050000])
        self.assertEqual(result['stalls_over_100ms']['after'], [0, 3, 0])

    def test_worker_command_forwards_modes_and_history(self):
        spec = dict(heavy='/synthetic/omi-heavy', platform='ios', runs=3, out='/synthetic/out',
                    timeline=True, synced_wals=66222, upload='accept', semantics='on', upload_wals=6)
        command = runner.profile_command(spec, 'synthetic-phone')
        for flag, value in (('--upload', 'accept'), ('--upload-wals', '6'),
                            ('--semantics', 'on'), ('--synced-wals', '66222')):
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn('--timeline', command)

    def test_new_cli_modes_are_retained_in_dry_run(self):
        # An explicit root keeps the test independent of the host's scratch mounts.
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(Path(runner.__file__)), '--dry-run',
                                     '--artifact-root', directory,
                                     '--upload', 'accept', '--upload-wals', '6', '--semantics', 'on'],
                                    capture_output=True, text=True, check=True)
        value = json.loads(result.stdout)
        self.assertEqual((value['upload'], value['upload_wals'], value['semantics']), ('accept', 6, 'on'))

    def test_invalid_modes_are_rejected_before_launch(self):
        for option, value in (('--upload', 'real'), ('--semantics', 'auto'), ('--upload-wals', '19')):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, str(Path(runner.__file__)), '--dry-run',
                                         '--artifact-root', directory, option, value],
                                        capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn(option, result.stderr)

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



class IosTransportTest(unittest.TestCase):
    LISTING = json.dumps({'result': {'devices': [
        {'hardwareProperties': {'udid': 'PHONE-USB'}, 'connectionProperties': {'transportType': 'wired'}},
        {'hardwareProperties': {'udid': 'PHONE-WIFI'}, 'connectionProperties': {'transportType': 'localNetwork'}},
    ]}})

    def test_reports_transport_per_device(self):
        self.assertEqual(runner.ios_transport('PHONE-USB', self.LISTING), 'wired')
        self.assertEqual(runner.ios_transport('PHONE-WIFI', self.LISTING), 'localNetwork')
        self.assertIsNone(runner.ios_transport('MISSING', self.LISTING))

if __name__ == '__main__':
    unittest.main()
