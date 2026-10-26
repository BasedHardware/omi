import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('perf_drive', Path(__file__).with_name('perf_drive.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class DriverSafetyTests(unittest.TestCase):
    def test_default_cleanup_and_conflicting_flags_rejected(self):
        for flags in ([], ['--no-keep-app-running'], ['--keep-app-running=false'],
                      ['--keep-app-running', '--no-keep-app-running'],
                      ['--keep-app-running', '--uninstall-first'],
                      ['--keep-app-running', '--uninstall'],
                      ['--keep-app-running', '--no-keep-app-running=true'],
                      ['--keep-app-running', '--disable-service-auth-codes']):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                driver.validate_command(['flutter', 'drive', '--flavor', 'dev', *flags])

    def test_non_dev_and_duplicate_flavors_rejected(self):
        for flags in ([], ['--flavor', 'prod'], ['--flavor=prod'],
                      ['--flavor', 'dev', '--flavor=prod']):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                driver.validate_command(['flutter', 'drive', '--keep-app-running', *flags])
        with self.assertRaises(ValueError):
            driver.validate_command(['xcrun', 'devicectl', 'device', 'uninstall', 'app'])

    def test_unsafe_command_never_starts_a_child(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv', ['perf_drive.py', str(Path(directory) / 'log'),
                                    'flutter', 'drive', '--flavor', 'dev']), patch.object(driver.subprocess, 'Popen') as spawn:
                self.assertEqual(driver.main(), 64)
                spawn.assert_not_called()

    def test_explicit_preserved_dev_command_accepted(self):
        command = ['flutter', 'drive', '--flavor', 'dev', '--keep-app-running']
        self.assertEqual(driver.validate_command(command), command)


if __name__ == '__main__':
    unittest.main()
