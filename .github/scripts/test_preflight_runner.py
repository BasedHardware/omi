from __future__ import annotations

import importlib.util
import signal
import unittest
import unittest.mock
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("preflight_runner", Path(__file__).with_name("preflight_runner.py"))
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


class ForwardableSignalsTests(unittest.TestCase):
    def test_includes_available_signals(self) -> None:
        selected = runner.forwardable_signals()
        self.assertIn(signal.SIGINT, selected)
        self.assertIn(signal.SIGTERM, selected)

    def test_skips_signals_absent_on_host(self) -> None:
        fake_signal = unittest.mock.Mock(spec=["SIGINT", "SIGTERM"])
        fake_signal.SIGINT = signal.SIGINT
        fake_signal.SIGTERM = signal.SIGTERM
        with unittest.mock.patch.object(runner, "signal", fake_signal):
            selected = runner.forwardable_signals()
        self.assertEqual(selected, [signal.SIGINT, signal.SIGTERM])


if __name__ == "__main__":
    unittest.main()
