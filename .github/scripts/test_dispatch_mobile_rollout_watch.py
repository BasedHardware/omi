#!/usr/bin/env python3
"""Offline tests for the intraday rollout-advance dispatcher."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dispatch_mobile_rollout_watch as dispatcher  # noqa: E402


class AdvanceDispatchTests(unittest.TestCase):
    def test_payload_targets_the_advance_workflow_with_its_mode_flag_set(self):
        payload = dispatcher.build_payload("app-1", dry_run=False)
        self.assertEqual(payload["workflowId"], "mobile-rollout-advance")
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(
            payload["environment"]["variables"],
            {"TRAIN_ADVANCE_ROLLOUTS": "true", "TRAIN_DRY_RUN": "false"},
        )
        self.assertEqual(
            dispatcher.build_payload("app-1", dry_run=True)["environment"]["variables"]["TRAIN_DRY_RUN"],
            "true",
        )
        with self.assertRaises(dispatcher.DispatchError):
            dispatcher.build_payload("", dry_run=False)

    def test_dispatch_requires_a_build_id(self):
        with patch.object(dispatcher, "_api_post", return_value={"buildId": "b-9"}) as post:
            self.assertEqual(dispatcher.dispatch("app-1", "token", dry_run=False), "b-9")
        self.assertEqual(post.call_args.args[0], dispatcher.BUILDS_API)
        self.assertEqual(post.call_args.args[2]["workflowId"], "mobile-rollout-advance")
        with patch.object(dispatcher, "_api_post", return_value={}):
            with self.assertRaisesRegex(dispatcher.DispatchError, "buildId"):
                dispatcher.dispatch("app-1", "token", dry_run=False)

    def test_a_capture_health_override_travels_only_when_given(self):
        self.assertNotIn(
            "TRAIN_CAPTURE_HEALTH_OVERRIDE",
            dispatcher.build_payload("app-1", dry_run=False, capture_health_override="  ")["environment"]["variables"],
        )
        variables = dispatcher.build_payload("app-1", dry_run=False, capture_health_override=" noise, DZ ")[
            "environment"
        ]["variables"]
        self.assertEqual(variables["TRAIN_CAPTURE_HEALTH_OVERRIDE"], "noise, DZ")
        with patch.dict(os.environ, {"CODEMAGIC_API_TOKEN": "t"}), patch.object(
            dispatcher, "latest_gate_receipt", return_value=datetime.now(timezone.utc)
        ), patch.object(dispatcher, "_api_post", return_value={"buildId": "b-1"}) as post:
            self.assertEqual(dispatcher.main(["--app-id", "app-1", "--capture-health-override", "why"]), 0)
        self.assertEqual(post.call_args.args[2]["environment"]["variables"]["TRAIN_CAPTURE_HEALTH_OVERRIDE"], "why")

    def test_main_fails_without_a_token_and_before_any_codemagic_request(self):
        with patch.dict(os.environ, {"CODEMAGIC_API_TOKEN": ""}), patch.object(
            dispatcher, "latest_gate_receipt", return_value=datetime.now(timezone.utc)
        ), patch.object(dispatcher, "_api_post") as post:
            self.assertEqual(dispatcher.main(["--app-id", "app-1"]), 1)
        post.assert_not_called()


class GateFreshnessTests(unittest.TestCase):
    NOW = datetime(2026, 10, 20, 17, tzinfo=timezone.utc)
    SUCCESS_QUERY = [
        "gh",
        "api",
        "--method",
        "GET",
        "repos/BasedHardware/omi/actions/workflows/mobile_daily_train.yml/runs",
        "-f",
        "branch=main",
        "-f",
        "status=success",
        "-f",
        "per_page=1",
    ]
    LATEST_QUERY = [
        "gh",
        "api",
        "--method",
        "GET",
        "repos/BasedHardware/omi/actions/workflows/mobile_daily_train.yml/runs",
        "-f",
        "branch=main",
        "-f",
        "per_page=1",
    ]

    def run_main(self, receipt_age, *, github_token="t", latest_run=None, extra_argv=()):
        """Run main with the success lookup and the freeze diagnostic lookup stubbed."""

        def gh_call(command, **_kwargs):
            runs = (
                []
                if receipt_age is None
                else [
                    {
                        "head_branch": "main",
                        "conclusion": "success",
                        "created_at": (self.NOW - receipt_age).isoformat(),
                    }
                ]
            )
            if "status=success" in command:
                return subprocess.CompletedProcess([], 0, stdout=json.dumps({"workflow_runs": runs}))
            return subprocess.CompletedProcess(
                [], 0, stdout=json.dumps({"workflow_runs": [] if latest_run is None else [latest_run]})
            )

        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            summary.write_text("Existing summary\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "CODEMAGIC_API_TOKEN": github_token,
                    "GITHUB_REPOSITORY": "BasedHardware/omi",
                    "GITHUB_STEP_SUMMARY": str(summary),
                },
            ), patch.object(dispatcher.subprocess, "run", side_effect=gh_call) as github, patch.object(
                dispatcher, "datetime", wraps=datetime
            ) as clock, patch.object(
                dispatcher, "_api_post", return_value={"buildId": "b-1"}
            ) as post, contextlib.redirect_stdout(
                stdout
            ), contextlib.redirect_stderr(
                stderr
            ):
                clock.now.return_value = self.NOW
                code = dispatcher.main(
                    ["--app-id", "app-1", "--dry-run", "true", "--capture-health-override", "why", *extra_argv]
                )
            return code, stdout.getvalue(), stderr.getvalue(), summary.read_text(encoding="utf-8"), github, post

    def test_fresh_receipt_including_exactly_26_hours_dispatches(self):
        for age in (timedelta(hours=1), timedelta(hours=26)):
            with self.subTest(age=age):
                code, stdout, stderr, summary, github, post = self.run_main(age)
                self.assertEqual(code, 0)
                post.assert_called_once()
                self.assertEqual(
                    post.call_args.args[2],
                    dispatcher.build_payload("app-1", dry_run=True, capture_health_override="why"),
                )
                self.assertNotIn("LADDER FROZEN", stdout)
                self.assertEqual(stderr, "")
                self.assertEqual(summary, "Existing summary\n")
                github.assert_called_once_with(
                    self.SUCCESS_QUERY, capture_output=True, text=True, check=True, timeout=30
                )

    def test_stale_receipt_fails_the_run_and_reports_why(self):
        latest = {
            "head_branch": "main",
            "status": "completed",
            "conclusion": "failure",
            "created_at": (self.NOW - timedelta(hours=3)).isoformat(),
        }
        code, stdout, stderr, summary, _github, post = self.run_main(
            timedelta(hours=30), latest_run=latest
        )
        post.assert_not_called()
        # A frozen ladder is a stalled release pipeline, not a quiet no-op:
        # the scheduled run fails so it cannot sit green and unnoticed.
        self.assertEqual(code, 1)
        self.assertIn("LADDER FROZEN: no successful mobile_daily_train run in the last 26h", stdout)
        self.assertIn(f"last success: {(self.NOW - timedelta(hours=30)).isoformat()}", stdout)
        # The diagnostic names the newest run even when it failed, so "the
        # dispatcher stopped" is distinguishable from "the train is failing".
        self.assertIn("latest run: failure at", stdout)
        self.assertIn("::error::LADDER FROZEN", stderr)
        self.assertIn("LADDER FROZEN", summary)

    def test_no_runs_at_all_freezes_and_says_so(self):
        code, stdout, _stderr, _summary, _github, post = self.run_main(None)
        post.assert_not_called()
        self.assertEqual(code, 1)
        self.assertIn("last success: never", stdout)
        self.assertIn("latest run: none", stdout)

    def test_a_freeze_override_dispatches_with_the_reason_recorded(self):
        code, stdout, stderr, _summary, _github, post = self.run_main(
            timedelta(hours=30), extra_argv=("--gate-freeze-override", " dispatcher paused, release owner approved ")
        )
        post.assert_called_once()
        self.assertEqual(code, 0)
        self.assertIn("LADDER FROZEN OVERRIDDEN: dispatcher paused, release owner approved", stdout)
        self.assertIn("::warning::LADDER FROZEN OVERRIDDEN", stderr)

    def test_a_blank_freeze_override_still_freezes(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                code, _stdout, _stderr, _summary, _github, post = self.run_main(
                    timedelta(hours=30), extra_argv=("--gate-freeze-override", value)
                )
                post.assert_not_called()
                self.assertEqual(code, 1)

    def test_lookup_failure_blocks_codemagic_dispatch(self):
        with patch.dict(os.environ, {"CODEMAGIC_API_TOKEN": "t"}), patch.object(
            dispatcher.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["gh", "api"])
        ), patch.object(dispatcher, "_api_post") as post:
            self.assertEqual(dispatcher.main(["--app-id", "app-1"]), 1)
        post.assert_not_called()

    def test_malformed_receipts_are_rejected(self):
        for run in (
            {"head_branch": "other", "conclusion": "success", "created_at": self.NOW.isoformat()},
            {"head_branch": "main", "conclusion": "failure", "created_at": self.NOW.isoformat()},
            {"head_branch": "main", "conclusion": "success", "created_at": "invalid"},
            {"head_branch": "main", "conclusion": "success", "created_at": "2026-10-20T17:00:00"},
        ):
            with self.subTest(run=run), patch.object(dispatcher.subprocess, "run") as github:
                github.return_value.stdout = json.dumps({"workflow_runs": [run]})
                with self.assertRaises(dispatcher.DispatchError):
                    dispatcher.latest_gate_receipt()


if __name__ == "__main__":
    unittest.main()
