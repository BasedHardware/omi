import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('virtual_admission', Path(__file__).with_name('virtual_admission.py'))
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)


class VirtualAdmissionTests(unittest.TestCase):
    def run_shell_with_stubbed_devices(self, warmups, device):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / 'calls'
            for tool in ('adb', 'flutter', 'xcrun'):
                stub = root / tool
                stub.write_text('#!/bin/sh\necho called >> "$PERF_STUB_CALLS"\nexit 1\n')
                stub.chmod(0o755)
            script = Path(__file__).resolve().parents[1] / 'perf_sim_profile.sh'
            result = subprocess.run(['bash', str(script), '--platform', 'android', '--device', device,
                                     '--emulator-qualification', '--runtime-build', 'pin',
                                     '--warmup-runs', warmups, '--out', str(root / 'output')],
                                    env={**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                                         'PERF_STUB_CALLS': str(calls)}, capture_output=True, text=True, timeout=10)
            return result, calls.exists()

    def test_shell_rejects_physical_serial_before_any_device_command(self):
        result, contacted = self.run_shell_with_stubbed_devices('1', 'physical-serial')
        self.assertEqual(result.returncode, 65)
        self.assertFalse(contacted, result.stderr)

    def test_shell_rejects_noncanonical_warmup_count_before_any_device_command(self):
        result, contacted = self.run_shell_with_stubbed_devices('01', 'emulator-5580')
        self.assertEqual(result.returncode, 64)
        self.assertFalse(contacted, result.stderr)

    def test_physical_android_serial_refused_without_adb(self):
        with patch.object(admission, 'read') as read:
            with self.assertRaisesRegex(ValueError, 'explicit emulator'):
                admission.attest('android', 'physical-serial', 'pinned')
            read.assert_not_called()

    def test_emulator_serial_alone_does_not_prove_virtual_target(self):
        with patch.object(admission, 'read', return_value='0'):
            with self.assertRaisesRegex(ValueError, 'not an Android emulator'):
                admission.attest('android', 'emulator-5580', 'pinned')

    def test_runtime_change_blocks_before_installation(self):
        with patch.object(admission, 'read', side_effect=['1', 'new', '1080x2400', '420', 'pixel']):
            with self.assertRaisesRegex(ValueError, 'differs from pin'):
                admission.attest('android', 'emulator-5580', 'old')

    def test_pin_records_rendering_dimensions(self):
        with patch.object(admission, 'read', side_effect=['1', 'pinned', '1080x2400', '420', 'pixel']):
            result = admission.attest('android', 'emulator-5580', 'pinned')
        self.assertEqual(result['runtime_build'], 'pinned')
        self.assertEqual(result['size'], '1080x2400')

    def test_no_runtime_pin_fails_closed(self):
        with patch.object(admission, 'read') as read:
            with self.assertRaises(ValueError):
                admission.attest('android', 'emulator-5580', '')
            read.assert_not_called()

    def test_same_emulator_serial_and_image_on_different_hosts_have_different_identity(self):
        with patch.object(admission, 'read', side_effect=['1', 'pin', '1080x2400', '420', 'pixel'] * 2), \
                patch.object(admission.platform, 'node', side_effect=['first-host', 'second-host']):
            first = admission.attest('android', 'emulator-5580', 'pin')
            second = admission.attest('android', 'emulator-5580', 'pin')
        self.assertNotEqual(first['host']['node_sha256'], second['host']['node_sha256'])
        self.assertNotIn('first-host', json.dumps(first['host']))
        self.assertNotIn('second-host', json.dumps(second['host']))

    def test_ios_pin_comes_from_native_booted_simulator_inventory(self):
        devices = {'devices': {'runtime-ios': [{'udid': 'sim-id', 'state': 'Booted',
                                               'deviceTypeIdentifier': 'iPhone-test'}]}}
        runtimes = {'runtimes': [{'identifier': 'runtime-ios', 'buildversion': '23F77'}]}
        with patch.object(admission, 'read', side_effect=[json.dumps(devices), json.dumps(runtimes)]):
            result = admission.attest('ios', 'sim-id', '23F77')
        self.assertEqual(result['kind'], 'ios-simulator')
        self.assertEqual(result['runtime_build'], '23F77')
        with patch.object(admission, 'read', return_value=json.dumps(devices)):
            with self.assertRaisesRegex(ValueError, 'booted iOS simulator'):
                admission.attest('ios', 'physical-udid', '23F77')


if __name__ == '__main__':
    unittest.main()
