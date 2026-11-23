#!/usr/bin/env python3
"""Tests for the self-healing Play internal publish (no network)."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import play_internal_publish as pub  # noqa: E402

HELD_ERROR = (
    "Setting release for Google Play track internal failed.\n"
    "Changes cannot be sent for review automatically. Please set the query parameter "
    "changesNotSentForReview to true. Once committed, the changes in this edit can be sent "
    "for review from the Google Play Console UI.\n"
)
AUTO_ERROR = (
    "Setting release for Google Play track internal failed. Changes are sent for review "
    "automatically. The query parameter changesNotSentForReview must not be set.\n"
)


class FakeRunner:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return self.results.pop(0)


class PublishTests(unittest.TestCase):
    command = pub.publish_command(Path("app.aab"), "internal")

    def test_command_matches_the_built_in_block(self):
        self.assertEqual(
            self.command,
            [
                "google-play", "bundles", "publish",
                "--credentials", "@env:GCLOUD_SERVICE_ACCOUNT_CREDENTIALS",
                "--bundle", "app.aab", "--track", "internal",
            ],
        )

    def test_normal_mode_publishes_once_without_the_flag(self):
        runner = FakeRunner((0, "ok"))
        self.assertEqual(pub.publish(self.command, runner), "normal")
        self.assertEqual(runner.calls, [self.command])

    def test_held_instruction_retries_once_with_the_flag(self):
        runner = FakeRunner((1, HELD_ERROR), (0, "ok"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(pub.publish(self.command, runner), "held")
        self.assertEqual(runner.calls, [self.command, [*self.command, "--changes-not-sent-for-review"]])

    def test_other_failures_do_not_retry(self):
        for output in (AUTO_ERROR, "Version code 1608 has already been used.", ""):
            with self.subTest(output=output):
                runner = FakeRunner((1, output))
                with self.assertRaises(pub.PublishError):
                    pub.publish(self.command, runner)
                self.assertEqual(len(runner.calls), 1)

    def test_failed_held_retry_fails(self):
        runner = FakeRunner((1, HELD_ERROR), (1, "boom"))
        with redirect_stdout(io.StringIO()), self.assertRaises(pub.PublishError):
            pub.publish(self.command, runner)


class MainTests(unittest.TestCase):
    def run_main(self, runner, bundles=("app-prod-release.aab",)):
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp, "bundle")
            bundle_dir.mkdir()
            for name in bundles:
                (bundle_dir / name).write_bytes(b"aab")
            out_dir = Path(tmp, "out")
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                rc = pub.main(["--bundle-dir", str(bundle_dir), "--out-dir", str(out_dir)], runner)
            files = {p.name: json.loads(p.read_text()) for p in out_dir.glob("*.json")}
            names = sorted(p.name for p in out_dir.glob("*.json"))
            return rc, stdout.getvalue(), files, names

    def test_held_publish_writes_only_held_evidence(self):
        rc, out, files, names = self.run_main(FakeRunner((1, HELD_ERROR), (0, "ok")))
        self.assertEqual(rc, 0)
        self.assertEqual(names, ["play-internal-publish-held.json"])
        self.assertEqual(files["play-internal-publish-held.json"]["mode"], "held")
        self.assertIn("PLAY_INTERNAL_PUBLISH_MODE=held", out)
        self.assertIn("Send changes for review", out)

    def test_normal_publish_writes_normal_evidence(self):
        rc, out, files, names = self.run_main(FakeRunner((0, "ok")))
        self.assertEqual((rc, names), (0, ["play-internal-publish-normal.json"]))
        self.assertIn("PLAY_INTERNAL_PUBLISH_MODE=normal", out)

    def test_failure_writes_no_evidence(self):
        rc, _, _, names = self.run_main(FakeRunner((1, "boom")))
        self.assertEqual(rc, 1)
        self.assertEqual(names, [])

    def test_evidence_replaces_a_stale_mode_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "play-internal-publish-normal.json").write_text("{}")
            pub.write_evidence(Path(tmp), "held", "internal")
            self.assertEqual(sorted(p.name for p in Path(tmp).glob("*.json")), ["play-internal-publish-held.json"])

    def test_requires_exactly_one_bundle(self):
        for bundles in ((), ("a.aab", "b.aab")):
            with self.subTest(bundles=bundles):
                runner = FakeRunner()
                rc, _, _, _ = self.run_main(runner, bundles)
                self.assertEqual(rc, 1)
                self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
