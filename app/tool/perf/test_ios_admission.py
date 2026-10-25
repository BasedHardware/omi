import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('device_admission', Path(__file__).with_name('device_admission.py'))
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)

ROOT = '/private/var/containers/Bundle/Application/fixture/Runner.app'
APP = {'bundleIdentifier': admission.DEV, 'url': 'file://' + ROOT + '/'}


class AdmissionTests(unittest.TestCase):
    def test_dev_main_and_extension_are_busy_even_with_url_slash_variation(self):
        for suffix in ('/Runner', '/PlugIns/Widget.appex/Widget'):
            with self.subTest(suffix=suffix):
                state = admission.idle_state([APP], [
                    {'executable': 'file:///' + ROOT + suffix, 'processIdentifier': 42}])
                self.assertEqual(state['running_pids'], [42])

    def test_another_installed_app_and_prefix_sibling_are_not_dev(self):
        state = admission.idle_state([APP], [
            {'executable': 'file://' + ROOT + '.other/Runner', 'processIdentifier': 10},
            {'executable': 'file:///usr/libexec/fixture', 'processIdentifier': 11}])
        self.assertEqual(state['running_pids'], [])

    def test_absent_installation_is_explicit_not_a_failed_query(self):
        self.assertFalse(admission.idle_state([], [])['installed'])

    def test_unknown_or_mismatched_metadata_fails_closed(self):
        for apps, processes in ((None, []), ([APP, APP], []),
                                ([dict(APP, bundleIdentifier='prod')], []),
                                ([dict(APP, url=None)], []), ([APP], None),
                                ([APP], [{}]),
                                ([APP], [{'executable': 'file://' + ROOT + '/Runner'}])):
            with self.subTest(apps=apps, processes=processes), self.assertRaises(ValueError):
                admission.idle_state(apps, processes)

    def test_failed_native_query_cannot_be_read_as_no_processes(self):
        with patch.object(admission.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"error":"permission denied"}'
            with self.assertRaises(KeyError):
                admission.query('fixture-device', 'processes')

    def test_android_busy_absent_and_error_states_are_distinct(self):
        with patch.object(admission.subprocess, 'run') as run:
            run.return_value.stdout, run.return_value.stderr = '42 43\n', ''
            run.return_value.returncode = 0
            self.assertEqual(admission.android_state('fixture')['running_pids'], [42, 43])
            run.return_value.stdout, run.return_value.returncode = '', 1
            self.assertEqual(admission.android_state('fixture')['running_pids'], [])
            run.return_value.stderr = 'device unavailable'
            with self.assertRaises(ValueError):
                admission.android_state('fixture')


if __name__ == '__main__':
    unittest.main()
