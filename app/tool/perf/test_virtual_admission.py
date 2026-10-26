import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('virtual_admission', Path(__file__).with_name('virtual_admission.py'))
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)


class VirtualAdmissionTests(unittest.TestCase):
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
