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
    def test_names_android_tap_unittest_go_and_browser_failures(self):
        samples = {
            "com.example.CaptureTest > reopensAfterDrop FAILED": "com.example.CaptureTest > reopensAfterDrop",
            "not ok 3 - agent reconnects after transport close": "agent reconnects after transport close",
            "FAIL: test_restart (test_service.ServiceTests)": "test_restart (test_service.ServiceTests)",
            "--- FAIL: TestReconnect (0.01s)": "TestReconnect",
            "✘ Test reconnect() failed after 0.1 seconds": "reconnect()",
            "1) [chromium] › flows/capture.spec.ts:20:3 › resumes after drop": "[chromium] › flows/capture.spec.ts:20:3 › resumes after drop",
            "FAIL src/capture.test.ts > recorder > reconnects": "src/capture.test.ts > recorder > reconnects",
        }
        for record, expected in samples.items():
            with self.subTest(record=record):
                self.assertEqual(REPORT.failing_tests(record), [expected])

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
            self.assertIsNone(REPORT.last_green("BasedHardware/omi", 123, "a" * 40))

    def test_previous_green_uses_artifact_main_sha_and_verifies_ancestry(self):
        runs = [dict(id=120, event="schedule"), dict(id=123, event="schedule"), dict(id=119, event="push")]

        def gh(*args, **kwargs):
            if args[0] == "api":
                self.assertIn("b" * 40 + "..." + "a" * 40, args[1])
                return "ahead\n"
            self.assertEqual(args[2], "120")
            out = Path(args[args.index("--dir") + 1])
            (out / "report.json").write_text(json.dumps(dict(run_id=120, failures=[], main_sha="b" * 40)))

        with patch.object(REPORT, "api_pages", return_value=runs) as api, patch.object(REPORT, "gh", side_effect=gh):
            self.assertEqual(REPORT.last_green("BasedHardware/omi", 123, "a" * 40), "b" * 40)
        self.assertIn("status=success", api.call_args.args[0])
        self.assertNotIn("branch=", api.call_args.args[0])

    def test_non_main_green_candidate_cannot_replace_the_verified_baseline(self):
        runs = [dict(id=120, event="workflow_dispatch"), dict(id=119, event="schedule")]
        downloads = []

        def gh(*args, **kwargs):
            if args[0] == "api":
                return "diverged" if "c" * 40 in args[1] else "identical"
            run_id = int(args[2])
            downloads.append(run_id)
            out = Path(args[args.index("--dir") + 1])
            (out / "report.json").write_text(json.dumps(dict(run_id=run_id, failures=[],
                                                           main_sha=("c" if run_id == 120 else "b") * 40)))

        with patch.object(REPORT, "api_pages", return_value=runs), patch.object(REPORT, "gh", side_effect=gh):
            self.assertEqual(REPORT.last_green("BasedHardware/omi", 123, "a" * 40), "b" * 40)
        self.assertEqual(downloads, [120, 119])

    def test_expired_newest_receipt_falls_back_to_an_older_verified_green(self):
        runs = [dict(id=121, event="schedule"), dict(id=120, event="schedule")]

        def gh(*args, **kwargs):
            if args[0] == "api":
                return "ahead"
            if args[2] == "121":
                raise REPORT.subprocess.CalledProcessError(1, "gh", stderr="no artifact matches")
            out = Path(args[args.index("--dir") + 1])
            (out / "report.json").write_text(json.dumps(dict(run_id=120, failures=[], main_sha="b" * 40)))

        with patch.object(REPORT, "api_pages", return_value=runs), patch.object(REPORT, "gh", side_effect=gh):
            self.assertEqual(REPORT.last_green("BasedHardware/omi", 123, "a" * 40), "b" * 40)

    def test_unverifiable_baseline_still_writes_the_failure_receipt(self):
        jobs = [dict(id=1, name="Backend / unit", conclusion="failure", steps=[])]
        log = "FAILED tests/unit/test_x.py::test_y - AssertionError"
        with patch.object(REPORT, "gh", return_value=log), \
                patch.object(REPORT, "last_green", side_effect=ValueError("Cannot verify last-green source ancestry")):
            receipt = REPORT.collect("BasedHardware/omi", 100, "a" * 40, jobs)
        self.assertEqual(receipt["failures"], [{"job": "Backend / unit", "test": "tests/unit/test_x.py::test_y"}])
        self.assertIsNone(receipt["last_green_sha"])

    def test_older_run_rerun_on_newer_main_cannot_reverse_the_bisect_range(self):
        runs = [dict(id=120, event="workflow_dispatch")]

        def gh(*args, **kwargs):
            if args[0] == "api":
                self.assertTrue(args[1].endswith("c" * 40 + "..." + "a" * 40))
                return "behind"
            out = Path(args[args.index("--dir") + 1])
            (out / "report.json").write_text(json.dumps(dict(run_id=120, failures=[], main_sha="c" * 40)))

        with patch.object(REPORT, "api_pages", return_value=runs), patch.object(REPORT, "gh", side_effect=gh):
            self.assertIsNone(REPORT.last_green("BasedHardware/omi", 123, "a" * 40))

    def test_manifest_verdicts_suppress_passing_self_test_noise(self):
        # The Hygiene job runs manifest checks whose PASSING self-tests print
        # deliberate ❌/FAIL: strings (error-handling fixtures, promotion-policy
        # gates). The runner's own verdicts are the only failure records.
        log = "\n".join([
            "2026-11-01T03:22:16Z <== PASS desktop-prod-promotion-policy (0.4s)",
            "2026-11-01T03:46:50Z ##[error]required check failed",
            "2026-11-01T03:48:56Z ❌ Error getting customers: /srv/app/.secrets/shopify_token_store.json",
            "2026-11-01T03:48:56Z <== PASS shopify-error-handling-tests (0.47s)",
            "2026-11-01T03:46:38Z <== FAIL backend-module-isolation (8.02s)",
            "2026-11-01T03:49:20Z Manifest checks failed: backend-module-isolation",
        ])
        self.assertEqual(REPORT.failing_tests(log), ["backend-module-isolation"])

    def test_manifest_fail_lines_report_check_names_without_summary(self):
        log = "<== FAIL backend-module-isolation (8.02s)\n<== FAIL repo-hygiene (0.2s)"
        self.assertEqual(REPORT.failing_tests(log), ["backend-module-isolation", "repo-hygiene"])

    def test_passed_manifest_drops_self_test_noise_and_defers_to_failed_step(self):
        # Hygiene failing at a later step while the manifest itself passed: the
        # self-test ❌/FAIL strings must not become phantom failures; collect()
        # then names the actually-failed workflow step via its steps fallback.
        log = "\n".join([
            "2026-11-01T03:22:16Z <== PASS shopify-error-handling-tests (0.47s)",
            "2026-11-01T03:48:56Z ❌ Error getting customers: /srv/app/.secrets/shopify_token_store.json",
            "2026-11-01T03:33:37Z FAIL: PROMOTE_IOS_BUILD must be a positive integer",
            "2026-11-01T03:49:20Z Manifest checks passed: 214 check(s).",
            "2026-11-01T03:49:40Z .github/workflows/foo.yml:2: property foo is not defined",
        ])
        self.assertEqual(REPORT.failing_tests(log), [])
        jobs = [dict(id=1, name="repo-checks / Hygiene", conclusion="failure",
                     steps=[dict(name="Check GitHub Actions workflows", conclusion="failure")])]
        with patch.object(REPORT, "gh", return_value=log), patch.object(REPORT, "last_green", return_value=None):
            receipt = REPORT.collect("BasedHardware/omi", 100, "a" * 40, jobs)
        self.assertIn("Check GitHub Actions workflows", receipt["failures"][0]["test"])

    def test_summary_escapes_test_markdown_and_names_main_and_green(self):
        rendered = REPORT.summary(dict(main_sha="a" * 40, last_green_sha="b" * 40,
                                       failures=[dict(job="Dart|Linux", test="<script>alert</script>\nother")]))
        self.assertIn("a" * 40, rendered)
        self.assertIn("b" * 40, rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("Dart&#124;Linux", rendered)


if __name__ == "__main__":
    unittest.main()
