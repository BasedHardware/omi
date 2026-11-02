"""Pure Swift checks only; unittest discovery never initializes Bluetooth."""
import shutil
import subprocess
import unittest
from pathlib import Path


class TestBLECentral(unittest.TestCase):
    def test_pure_swift(self):
        compiler = shutil.which('swiftc')
        if compiler is None:
            self.skipTest('Swift compiler unavailable')
        try:
            probe = subprocess.run([compiler, '--version'], capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            self.skipTest('Swift toolchain unavailable')
        if probe.returncode != 0:
            self.skipTest('Swift toolchain unavailable')
        result = subprocess.run(
            ['sh', str(Path(__file__).parent / 'ble_central' / 'test.sh')],
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('pure Swift checks', result.stdout)


if __name__ == '__main__':
    unittest.main()
