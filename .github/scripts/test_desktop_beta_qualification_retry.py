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
         updated=NOW_ISO, run_id=1, run_attempt=1) -> dict:
    return {
        "id": run_id,
        "run_attempt": run_attempt,
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


def _jobs(*, conclusion="failure", started=True):
    qualify = {"id": 2, "name": "qualify", "status": "completed", "conclusion": conclusion}
    if started:
        qualify["started_at"] = NOW_ISO
    return {"total_count": 2, "jobs": [{"id": 1, "name": "admit", "status": "completed", "conclusion": "success"}, qualify]}


def _response(runs):
    return {"total_count": len(runs), "workflow_runs": runs}


def _decide(release, runs, *, jobs_by_run=None, **overrides):
    if jobs_by_run is None:
        jobs_by_run = {
            run["id"]: {attempt: _jobs() for attempt in range(1, run["run_attempt"] + 1)}
            for run in runs if run.get("head_branch") == TAG and run.get("head_sha") == SHA
        }
    kwargs = dict(release_tag=TAG, tag_sha=SHA, max_attempts=3, max_age_hours=24)
    kwargs.update(overrides)
    return retry.decide(release, _response(runs), jobs_by_run=jobs_by_run, **kwargs)


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

    def test_candidate_24_hours_30_minutes_old_denies(self):
        old = _utc_iso(_NOW - timedelta(hours=24, minutes=30))
        d = _decide(_release(published=old), [_run(conclusion="failure")], max_age_hours=24)
        self.assertFalse(d["should_retry"])
        self.assertIn("exceeds", d["reason"])

    def test_malformed_publication_timestamp_denies(self):
        d = _decide(_release(published="not-a-timestamp"), [_run(conclusion="failure")])
        self.assertFalse(d["should_retry"])
        self.assertIn("malformed", d["reason"])

    def test_future_publication_timestamp_denies(self):
        future = _utc_iso(_NOW + timedelta(minutes=30))
        d = _decide(_release(published=future), [_run(conclusion="failure")])
        self.assertFalse(d["should_retry"])
        self.assertIn("future", d["reason"])

    # --- run state (never retry in-progress / successful / unattempted) ---

    def test_no_prior_attempt_denies(self):
        # The retry never owns the initial dispatch; Codemagic does.
        d = _decide(_release(), [])
        self.assertFalse(d["should_retry"])
        self.assertIn("unattempted", d["reason"])

    def test_in_progress_denies(self):
        for status in ("in_progress", "queued"):
            with self.subTest(status=status):
                d = _decide(_release(), [_run(status=status, conclusion=None)])
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

    def test_neutral_plus_two_failures_reaches_total_attempt_bound(self):
        runs = [
            _run(conclusion="neutral", run_id=1, updated=_utc_iso(_NOW - timedelta(minutes=2))),
            _run(conclusion="failure", run_id=2, updated=_utc_iso(_NOW - timedelta(minutes=1))),
            _run(conclusion="failure", run_id=3, updated=NOW_ISO),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 3)
        self.assertIn("bound", d["reason"])

    def test_duplicate_run_records_fail_closed(self):
        run = _run(conclusion="failure", run_id=7)
        d = _decide(_release(), [run, copy.deepcopy(run)])
        self.assertFalse(d["should_retry"])
        self.assertIn("authority", d["reason"])

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

    def test_older_success_with_newer_failure_denies(self):
        runs = [
            _run(conclusion="success", run_id=1, updated=_utc_iso(_NOW - timedelta(hours=1))),
            _run(conclusion="failure", run_id=2, updated=NOW_ISO),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertIn("already succeeded", d["reason"])

    def test_older_in_progress_with_newer_cancelled_denies(self):
        runs = [
            _run(status="in_progress", conclusion=None, run_id=1,
                 updated=_utc_iso(_NOW - timedelta(hours=1))),
            _run(conclusion="cancelled", run_id=2, updated=NOW_ISO),
        ]
        d = _decide(_release(), runs)
        self.assertFalse(d["should_retry"])
        self.assertIn("in-progress", d["reason"])

    # --- shared attempt-authority accounting ---

    def test_admission_only_cancellations_do_not_consume_retry_bound(self):
        runs = [_run(run_id=1, conclusion="cancelled"), _run(run_id=2, conclusion="cancelled"), _run(run_id=3)]
        skipped = _jobs(conclusion="skipped")
        d = _decide(
            _release(), runs,
            jobs_by_run={1: {1: skipped}, 2: {1: skipped}, 3: {1: _jobs(conclusion="failure")}},
        )
        self.assertTrue(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 1)

    def test_rerun_attempts_two_plus_one_reach_the_shared_bound(self):
        runs = [_run(run_id=29949128798, run_attempt=2), _run(run_id=29946139071)]
        d = _decide(
            _release(), runs,
            jobs_by_run={
                29949128798: {1: _jobs(conclusion="failure"), 2: _jobs(conclusion="cancelled")},
                29946139071: {1: _jobs(conclusion="failure")},
            },
        )
        self.assertFalse(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 3)

    def test_earlier_started_rerun_counts_when_latest_prestart_cancelled(self):
        run = _run(run_id=1, run_attempt=2, conclusion="cancelled")
        d = _decide(
            _release(), [run],
            jobs_by_run={1: {1: _jobs(conclusion="failure"), 2: _jobs(conclusion="cancelled", started=False)}},
        )
        self.assertTrue(d["should_retry"])
        self.assertEqual(d["attempts_so_far"], 1)

    def test_missing_malformed_or_incomplete_attempt_authority_denies(self):
        run = _run(run_id=1, run_attempt=2)
        cases = (
            {1: {1: _jobs()}},
            {1: {1: {"total_count": 1, "jobs": []}, 2: _jobs()}},
            {1: None},
        )
        for authority in cases:
            with self.subTest(authority=authority):
                d = _decide(_release(), [run], jobs_by_run=authority)
                self.assertFalse(d["should_retry"])
                self.assertIn("authority", d["reason"])

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
        jobs_dir = root / "_tmp_retry_jobs"
        out_path = root / "_tmp_retry_decision.json"
        try:
            release_path.write_text(json.dumps(_release()), encoding="utf-8")
            runs_path.write_text(json.dumps(_response([_run(conclusion="failure")])), encoding="utf-8")
            (jobs_dir / "1").mkdir(parents=True)
            (jobs_dir / "1" / "1.json").write_text(json.dumps(_jobs()), encoding="utf-8")
            import subprocess

            result = subprocess.run(
                ["python3", str(script), "decide",
                 "--release-json", str(release_path),
                 "--runs-json", str(runs_path),
                 "--jobs-dir", str(jobs_dir),
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
            import shutil
            shutil.rmtree(jobs_dir, ignore_errors=True)


class WorkflowContractTests(unittest.TestCase):
    def test_app_token_requests_only_required_permissions(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows" /
                    "desktop_retry_beta_qualification.yml").read_text(encoding="utf-8")
        self.assertIn("          permission-actions: write\n", workflow)
        self.assertIn("          permission-contents: read\n", workflow)

    def test_retry_gathers_bounded_exact_attempt_authority(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows" /
                    "desktop_retry_beta_qualification.yml").read_text(encoding="utf-8")
        self.assertIn("gh api --paginate --slurp --method GET", workflow)
        self.assertIn('branch="$LATEST_TAG"', workflow)
        self.assertIn("actions/runs/$run_id/attempts/$attempt/jobs", workflow)
        self.assertIn("run_attempt > 10", workflow)
        self.assertIn("attempt_authorities > 30", workflow)
        self.assertIn("--jobs-dir /tmp/desktop-beta-retry/jobs", workflow)
        self.assertNotIn("runs?event=workflow_dispatch&per_page=100", workflow)


if __name__ == "__main__":
    unittest.main()
