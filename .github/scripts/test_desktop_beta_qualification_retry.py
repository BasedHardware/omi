#!/usr/bin/env python3
"""Fault tests for the bounded desktop Beta qualification retry decision.

These exercise every safety property of the retry decision against fabricated
server JSON: invalid candidate, age bound, no prior attempt, in-progress and
successful runs, transient retry under the attempt bound, the deterministic
loop guard at the bound, exact-SHA/tag binding, and non-retryable conclusions.
"""

# omi-test-quality: source-inspection -- the decision script is pure JSON logic.
from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import desktop_beta_qualification_retry as retry

TAG = "v1.2.3+1234-macos"
SHA = "a" * 40


def _utc_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_NOW = datetime.now(timezone.utc)
NOW_ISO = _utc_iso(_NOW)
RECENT_ISO = _utc_iso(_NOW - timedelta(hours=1))


def _release(*, tag: str = TAG, channel: str = "candidate", is_live: str = "false",
             draft: bool = False, prerelease: bool = False, published: str = RECENT_ISO,
             assets=retry.CANONICAL_ASSETS) -> dict:
    body = (
        "<!-- KEY_VALUE_START\n"
        f"channel: {channel}\nisLive: {is_live}\n"
        "<!-- KEY_VALUE_END -->"
    )
    return {
        "tagName": tag,
        "body": body,
        "isDraft": draft,
        "isPrerelease": prerelease,
        "publishedAt": published,
        "assets": [{"name": name} for name in assets],
    }


def _run(*, status="completed", conclusion="failure", branch=TAG, sha=SHA,
         updated=NOW_ISO, run_id=1) -> dict:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "event": "workflow_dispatch",
        "path": retry.QUALIFICATION_WORKFLOW,
        "head_branch": branch,
        "head_sha": sha,
        "name": "Qualify Desktop Beta Candidate",
        "updated_at": updated,
        "created_at": updated,
    }


def _decide(release, runs, **overrides):
    kwargs = dict(release_tag=TAG, tag_sha=SHA, max_attempts=3, max_age_hours=24)
    kwargs.update(overrides)
    return retry.decide(release, runs, **kwargs)


class RetryDecisionTests(unittest.TestCase):
    # --- candidate validity (no retry) ---

    def test_missing_release_denies(self):
        d = _decide({}, [])
        self.assertFalse(d["should_retry"])
        self.assertIn("no published GitHub release", d["reason"])

    def test_release_tag_mismatch_denies(self):
        release = _release(tag="v9.9.9+9999-macos")
        d = _decide(release, [])
        self.assertFalse(d["should_retry"])
        self.assertIn("does not match", d["reason"])

    def test_draft_or_prerelease_denies(self):
        for kw in ({"draft": True}, {"prerelease": True}):
            with self.subTest(**kw):
                d = _decide(_release(**kw), [_run(conclusion="failure")])
                self.assertFalse(d["should_retry"])

    def test_missing_canonical_asset_denies(self):
        release = _release(assets=("Omi.zip", "omi.dmg"))  # no smoke result
        d = _decide(release, [_run(conclusion="failure")])
        self.assertFalse(d["should_retry"])
        self.assertIn("missing canonical assets", d["reason"])

    def test_promoted_candidate_denies(self):
        # isLive:true means the candidate already advanced; never re-qualify.
        d = _decide(_release(is_live="true"), [_run(conclusion="failure")])
        self.assertFalse(d["should_retry"])
        self.assertIn("isLive", d["reason"])

    def test_wrong_channel_denies(self):
        d = _decide(_release(channel="stable"), [_run(conclusion="failure")])
        self.assertFalse(d["should_retry"])
        self.assertIn("channel", d["reason"])

    # --- age bound ---

    def test_candidate_too_old_denies(self):
        old = _utc_iso(_NOW - timedelta(hours=48))
        d = _decide(_release(published=old), [_run(conclusion="failure")], max_age_hours=24)
        self.assertFalse(d["should_retry"])
        self.assertIn("exceeds", d["reason"])

    # --- run state (never retry in-progress / successful / unattempted) ---

    def test_no_prior_attempt_denies(self):
        # The retry never owns the initial dispatch; Codemagic does.
        d = _decide(_release(), [])
        self.assertFalse(d["should_retry"])
        self.assertIn("unattempted", d["reason"])

    def test_in_progress_denies(self):
        for status in ("in_progress", "queued", "waiting"):
            with self.subTest(status=status):
                d = _decide(_release(), [_run(status=status)])
                self.assertFalse(d["should_retry"])
                self.assertIn("in-progress", d["reason"])

    def test_successful_run_denies(self):
        d = _decide(_release(), [_run(conclusion="success")])
        self.assertFalse(d["should_retry"])
        self.assertIn("already succeeded", d["reason"])

    def test_non_retryable_conclusion_denies(self):
        for conclusion in ("neutral", "skipped", "action_required"):
            with self.subTest(conclusion=conclusion):
                d = _decide(_release(), [_run(conclusion=conclusion)])
                self.assertFalse(d["should_retry"])

    # --- transient retry under the bound ---

    def test_failed_run_under_bound_retries(self):
        d = _decide(_release(), [_run(conclusion="failure")])
        self.assertTrue(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 1)
        self.assertIn("attempt 2 of 3", d["reason"])

    def test_cancelled_run_retries(self):
        d = _decide(_release(), [_run(conclusion="cancelled")])
        self.assertTrue(d["should_retry"])

    def test_second_failure_still_retries(self):
        runs = [
            _run(conclusion="failure", run_id=1),
            _run(conclusion="failure", run_id=2, updated=_utc_iso(_NOW + timedelta(minutes=5))),
        ]
        d = _decide(_release(), runs)
        self.assertTrue(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 2)
        self.assertIn("attempt 3 of 3", d["reason"])

    # --- deterministic / persistent loop guard ---

    def test_at_max_attempts_denies(self):
        runs = [
            _run(conclusion="failure", run_id=i, updated=_utc_iso(_NOW + timedelta(minutes=i)))
            for i in (1, 2, 3)
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 3)
        self.assertIn("bound", d["reason"])

    def test_custom_lower_bound_caps_earlier(self):
        runs = [_run(conclusion="failure", run_id=1), _run(conclusion="failure", run_id=2)]
        d = _decide(_release(), runs, max_attempts=2)
        self.assertFalse(d["should_retry"])
        self.assertIn("bound", d["reason"])

    # --- exact tag + SHA binding (ignore other candidates' runs) ---

    def test_runs_for_other_tags_are_ignored(self):
        # A failed run for a different tag must not count toward this tag.
        runs = [
            _run(branch="v9.9.9+9999-macos", conclusion="failure", run_id=1),
            _run(branch="v8.8.8+8888-macos", sha="b" * 40, conclusion="failure", run_id=2),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertIn("unattempted", d["reason"])

    def test_newest_run_governs_in_progress_check(self):
        # Older failure present, but newest run is in_progress -> do not retry.
        runs = [
            _run(conclusion="failure", run_id=1, updated=_utc_iso(_NOW - timedelta(hours=1))),
            _run(status="in_progress", conclusion=None, run_id=2, updated=NOW_ISO),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertIn("in-progress", d["reason"])

    def test_success_after_failure_denies(self):
        # A later successful run supersedes an earlier failure.
        runs = [
            _run(conclusion="failure", run_id=1, updated=_utc_iso(_NOW - timedelta(hours=1))),
            _run(conclusion="success", run_id=2, updated=NOW_ISO),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertIn("already succeeded", d["reason"])

    def test_non_workflow_dispatch_runs_ignored(self):
        # Only workflow_dispatch qualification runs are authoritative.
        run = _run()
        run["event"] = "workflow_run"
        d = _decide(_release(), [run])
        self.assertFalse(d["should_retry"])

    # --- never reaches promotion / stable ---

    def test_decision_never_carries_promotion_authority(self):
        d = _decide(_release(), [_run(conclusion="failure")])
        self.assertTrue(d["should_retry"])
        self.assertNotIn("promote-qualified", json.dumps(d))
        self.assertNotIn("stable", json.dumps(d).lower())


class CliOutputContractTests(unittest.TestCase):
    """The CLI emits the decision file the workflow reads into GITHUB_OUTPUT."""

    def test_decide_writes_json_with_should_retry(self):
        import tempfile

        script = Path(retry.__file__).resolve()
        root = script.parent
        release_path = root / "_tmp_retry_release.json"
        runs_path = root / "_tmp_retry_runs.json"
        out_path = root / "_tmp_retry_decision.json"
        try:
            release_path.write_text(json.dumps(_release()), encoding="utf-8")
            runs_path.write_text(json.dumps([_run(conclusion="failure")]), encoding="utf-8")
            import subprocess

            result = subprocess.run(
                ["python3", str(script), "decide",
                 "--release-json", str(release_path),
                 "--runs-json", str(runs_path),
                 "--release-tag", TAG, "--tag-sha", SHA,
                 "--output", str(out_path)],
                check=True, text=True, capture_output=True,
            )
            decision = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(decision["should_retry"])
            self.assertEqual(decision["release_tag"], TAG)
            self.assertIn("retrying", result.stdout)
        finally:
            for p in (release_path, runs_path, out_path):
                p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
