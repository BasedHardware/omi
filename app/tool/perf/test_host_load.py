import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('host_load', Path(__file__).with_name('host_load.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class HostLoadTests(unittest.TestCase):
    def test_threshold_is_inclusive(self):
        with patch.object(guard.os, 'cpu_count', return_value=10):
            with patch.object(guard.os, 'getloadavg', return_value=(10, 20, 30)):
                self.assertTrue(guard.sample('before')['admitted'])
            with patch.object(guard.os, 'getloadavg', return_value=(10.01, 0, 0)):
                self.assertFalse(guard.sample('before')['admitted'])

    def test_overloaded_precondition_never_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'host.json'
            with patch.object(guard, 'sample', return_value={'admitted': False}), patch.object(guard.subprocess, 'Popen') as spawn:
                self.assertEqual(guard.run(['unused'], out), 65)
            spawn.assert_not_called()
            self.assertFalse(json.loads(out.read_text())['passed'])

    def test_during_overload_retains_completed_launch_without_termination(self):
        child = Mock()
        child.wait.side_effect = [guard.subprocess.TimeoutExpired('test', 1), 0]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'host.json'
            with patch.object(guard, 'sample', side_effect=[{'admitted': True}, {'admitted': False}, {'admitted': True}]), patch.object(guard.subprocess, 'Popen', return_value=child):
                self.assertEqual(guard.run(['unused'], out), 65)
            child.terminate.assert_not_called()
            receipt = json.loads(out.read_text())
            self.assertEqual(receipt['command_exit_code'], 0)
            self.assertEqual(len(receipt['samples']), 3)


if __name__ == '__main__':
    unittest.main()
