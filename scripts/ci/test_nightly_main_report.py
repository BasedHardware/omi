import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("nightly_main_report", Path(__file__).with_name("nightly_main_report.py"))
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class ReportTests(unittest.TestCase):
    def test_extracts_each_pytest_swift_dart_rust_and_web_failure(self):
        log = "\n".join([
            "2026-10-21T00:00:00.000Z FAILED tests/unit/test_audio.py::test_reconnect - AssertionError: private payload",
            "Test Case '-[DesktopTests.MeetingMemoryBriefRenderingTests testCitedCardRendersAtDesktopWidth]' failed (0.2 seconds).",
            "00:10 +100 -1: /home/runner/app/test/capture_live_recovery_test.dart: pendant BLE drop [E]",
            "test audio::reconnect ... FAILED", "FAIL src/audio.test.tsx", "FAIL src/audio.test.tsx",
            "2026-10-21T05:45:35.0501075Z ##[group]❌ /home/runner/app/test/capture_live_recovery_test.dart: pendant BLE drop (failed)",
        ])
        tests = REPORT.failing_tests(log)
        self.assertEqual(len(tests), 5, tests)
        self.assertIn("tests/unit/test_audio.py::test_reconnect", tests)
        self.assertTrue(any("MeetingMemoryBriefRenderingTests" in name for name in tests))
        self.assertTrue(any("capture_live_recovery_test.dart: pendant BLE drop" in name for name in tests))
        self.assertFalse(any("private payload" in name for name in tests))

    def test_infrastructure_failure_has_step_fallback(self):
        jobs = [dict(id=1, name="Backend / unit", conclusion="failure",
                     steps=[dict(name="Install dependencies", conclusion="failure")])]
        with patch.object(REPORT, "gh", return_value="no test record"), patch.object(REPORT, "last_green", return_value=None):
            receipt = REPORT.collect("BasedHardware/omi", 100, "a" * 40, jobs)
        self.assertIn("Install dependencies", receipt["failures"][0]["test"])
        self.assertIsNone(receipt["last_green_sha"])

    def test_first_run_records_none_without_guessing_head_sha(self):
        with patch.object(REPORT, "api_pages", return_value=[]):
            self.assertIsNone(REPORT.last_green("BasedHardware/omi", 123))

    def test_previous_green_uses_artifact_main_sha_and_excludes_branch_dispatch(self):
        runs = [dict(id=120, event="schedule"), dict(id=123, event="schedule"), dict(id=119, event="push")]

        def gh(*args, **kwargs):
            self.assertEqual(args[2], "120")
            out = Path(args[args.index("--dir") + 1])
            (out / "report.json").write_text(json.dumps(dict(run_id=120, failures=[], main_sha="b" * 40)))

        with patch.object(REPORT, "api_pages", return_value=runs) as api, patch.object(REPORT, "gh", side_effect=gh):
            self.assertEqual(REPORT.last_green("BasedHardware/omi", 123), "b" * 40)
        self.assertIn("branch=main&status=success", api.call_args.args[0])

    def test_summary_escapes_test_markdown_and_names_main_and_green(self):
        rendered = REPORT.summary(dict(main_sha="a" * 40, last_green_sha="b" * 40,
                                       failures=[dict(job="Dart|Linux", test="<script>alert</script>\nother")]))
        self.assertIn("a" * 40, rendered)
        self.assertIn("b" * 40, rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("Dart&#124;Linux", rendered)


if __name__ == "__main__":
    unittest.main()
