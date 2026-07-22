#!/usr/bin/env python3
"""Deterministic fault tests for desktop Beta qualification admission."""

from __future__ import annotations

import unittest

import desktop_beta_qualification_admission as admission


TAG = "v1.2.3+1234-macos"
OTHER_TAG = "v9.9.9+9999-macos"
SHA = "a" * 40


def _ref() -> dict:
    return {"ref": f"refs/tags/{TAG}", "object": {"type": "commit", "sha": SHA}}


def _run(
    *,
    run_id: int,
    run_attempt: int = 1,
    status: str = "completed",
    conclusion: str | None = "failure",
    tag: str = TAG,
    sha: str = SHA,
) -> dict:
    return {
        "id": run_id,
        "run_attempt": run_attempt,
        "path": admission.QUALIFICATION_WORKFLOW,
        "event": "workflow_dispatch",
        "head_branch": tag,
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
    }


def _response(runs: list[dict]) -> dict:
    return {"total_count": len(runs), "workflow_runs": runs}


def _qualification_jobs(*, conclusion: str = "failure", started: bool = True) -> dict:
    qualify = {"id": 2, "name": "qualify", "status": "completed", "conclusion": conclusion}
    if started:
        qualify["started_at"] = "2026-07-22T00:00:00Z"
    return {
        "total_count": 2,
        "jobs": [
            {"id": 1, "name": "admit", "status": "completed", "conclusion": "success"},
            qualify,
        ],
    }


def _decide(runs: list[dict], *, jobs_by_run: dict[int, dict[int, dict]] | None = None, **kwargs: object) -> dict:
    if jobs_by_run is None:
        jobs_by_run = {
            run["id"]: {attempt: _qualification_jobs() for attempt in range(1, run["run_attempt"] + 1)}
            for run in runs
            if run["head_branch"] == TAG and run["head_sha"] == SHA
        }
    return admission.decide(_ref(), _response(runs), release_tag=TAG, jobs_by_run=jobs_by_run, **kwargs)


class AdmissionTests(unittest.TestCase):
    def test_older_active_exact_tag_denies(self) -> None:
        decision = _decide([_run(run_id=1, status="queued", conclusion=None)])
        self.assertFalse(decision["admitted"])
        self.assertIn("active", decision["reason"])

    def test_older_success_denies(self) -> None:
        decision = _decide([_run(run_id=1, conclusion="success")])
        self.assertFalse(decision["admitted"])
        self.assertIn("succeeded", decision["reason"])

    def test_older_failure_allows_bounded_retry(self) -> None:
        decision = _decide([_run(run_id=1, conclusion="failure")])
        self.assertTrue(decision["admitted"])

    def test_current_run_is_excluded_by_id(self) -> None:
        # The exact current record is structurally bound before it is excluded,
        # so it needs no prior-run job authority and cannot self-block.
        decision = _decide([_run(run_id=42, conclusion="success")], jobs_by_run={}, current_run_id=42)
        self.assertTrue(decision["admitted"])

    def test_current_run_on_main_is_denied_before_exclusion(self) -> None:
        main_run = _run(run_id=42, tag="main", sha="b" * 40, conclusion="success")
        with self.assertRaisesRegex(ValueError, "does not bind"):
            _decide([main_run], current_run_id=42)

    def test_current_run_missing_or_duplicated_is_denied(self) -> None:
        with self.subTest("missing"):
            with self.assertRaisesRegex(ValueError, "appear exactly once"):
                _decide([], current_run_id=42)
        with self.subTest("duplicated"):
            duplicate = _run(run_id=42, conclusion="failure")
            with self.assertRaisesRegex(ValueError, "duplicate run id"):
                _decide([duplicate, dict(duplicate)], current_run_id=42)

    def test_other_tag_does_not_block_exact_candidate(self) -> None:
        decision = _decide([_run(run_id=1, status="queued", conclusion=None, tag=OTHER_TAG)])
        self.assertTrue(decision["admitted"])

    def test_annotated_tag_peels_to_exact_commit(self) -> None:
        ref = {"ref": f"refs/tags/{TAG}", "object": {"type": "tag", "sha": "b" * 40}}
        tag = {"sha": "b" * 40, "object": {"type": "commit", "sha": SHA}}
        decision = admission.decide(ref, _response([]), release_tag=TAG, jobs_by_run={}, annotated_tag=tag)
        self.assertEqual(decision["source_sha"], SHA)

    def test_malformed_api_response_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed"):
            admission.decide(_ref(), {"total_count": 0, "workflow_runs": {}}, release_tag=TAG, jobs_by_run={})
        with self.assertRaisesRegex(ValueError, "non-object"):
            admission.decide(_ref(), {"total_count": 1, "workflow_runs": [None]}, release_tag=TAG, jobs_by_run={})

    def test_malformed_exact_tag_ref_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not bind"):
            admission.decide({}, _response([]), release_tag=TAG, jobs_by_run={})

    def test_success_on_second_page_beyond_first_hundred_denies(self) -> None:
        first_page = [_run(run_id=index, tag=OTHER_TAG) for index in range(1, 101)]
        second_page = [_run(run_id=101, conclusion="success")]
        pages = [
            {"total_count": 101, "workflow_runs": first_page},
            {"total_count": 101, "workflow_runs": second_page},
        ]
        decision = admission.decide(_ref(), pages, release_tag=TAG, jobs_by_run={101: {1: _qualification_jobs()}})
        self.assertFalse(decision["admitted"])
        self.assertIn("succeeded", decision["reason"])

    def test_incomplete_paginated_response_fails_closed(self) -> None:
        partial = {"total_count": 101, "workflow_runs": [_run(run_id=index) for index in range(1, 101)]}
        with self.assertRaisesRegex(ValueError, "pagination is incomplete"):
            admission.decide(_ref(), partial, release_tag=TAG, jobs_by_run={})

    def test_three_failed_attempts_reach_the_bound(self) -> None:
        decision = _decide([_run(run_id=index, conclusion="failure") for index in range(1, 4)])
        self.assertFalse(decision["admitted"])
        self.assertIn("3-attempt", decision["reason"])

    def test_workflow_run_state_machine_accepts_representative_valid_states(self) -> None:
        cases = (
            ("queued", None, False),
            ("in_progress", None, False),
            ("completed", "success", False),
            ("completed", "failure", True),
            ("completed", "cancelled", True),
        )
        for status, conclusion, admitted in cases:
            with self.subTest(status=status, conclusion=conclusion):
                decision = _decide([_run(run_id=1, status=status, conclusion=conclusion)])
                self.assertEqual(decision["admitted"], admitted)

    def test_workflow_run_state_machine_rejects_mutated_invalid_states(self) -> None:
        mutations = (
            ("completed", None, "completed status has invalid conclusion"),
            ("completed", "unknown", "completed status has invalid conclusion"),
            ("queued", "failure", "nonterminal status must have null conclusion"),
            ("unknown", None, "unknown status"),
        )
        for status, conclusion, message in mutations:
            with self.subTest(status=status, conclusion=conclusion):
                with self.assertRaisesRegex(ValueError, message):
                    _decide([_run(run_id=1, status=status, conclusion=conclusion)])

    def test_malformed_current_run_is_validated_before_exclusion(self) -> None:
        with self.assertRaisesRegex(ValueError, "completed status has invalid conclusion"):
            _decide([_run(run_id=42, status="completed", conclusion=None)], current_run_id=42)

    def test_two_pre_admission_placeholders_do_not_consume_one_real_attempt(self) -> None:
        runs = [
            _run(run_id=1, conclusion="cancelled"),
            _run(run_id=2, conclusion="cancelled"),
            _run(run_id=3, conclusion="failure"),
        ]
        # A globally-concurrent duplicate can get as far as the lightweight
        # admission job, then be cancelled before `qualify` starts.  Its
        # explicit skipped qualify record is not an attempted qualification.
        admission_only = {
            "total_count": 2,
            "jobs": [
                {"id": 1, "name": "admit", "status": "completed", "conclusion": "success"},
                {"id": 2, "name": "qualify", "status": "completed", "conclusion": "skipped"},
            ],
        }
        decision = _decide(
            runs,
            jobs_by_run={1: {1: admission_only}, 2: {1: admission_only}, 3: {1: _qualification_jobs()}},
        )
        self.assertTrue(decision["admitted"])

    def test_admission_without_started_qualification_is_not_an_attempt(self) -> None:
        run = _run(run_id=1, conclusion="failure")
        admission_only = {
            "total_count": 1,
            "jobs": [{"id": 1, "name": "admit", "status": "completed", "conclusion": "success"}],
        }
        self.assertTrue(_decide([run], jobs_by_run={1: {1: admission_only}})["admitted"])

    def test_three_started_qualification_attempts_reach_the_bound(self) -> None:
        runs = [_run(run_id=index, conclusion="failure") for index in range(1, 4)]
        decision = _decide(runs, jobs_by_run={run["id"]: {1: _qualification_jobs()} for run in runs})
        self.assertFalse(decision["admitted"])

    def test_rerun_attempts_across_two_run_ids_reach_the_bound(self) -> None:
        # Mirrors the live shape: one run was retried, so its two trusted
        # starts plus another run's start must consume all three attempts.
        runs = [_run(run_id=29949128798, run_attempt=2), _run(run_id=29946139071)]
        decision = _decide(
            runs,
            jobs_by_run={
                29949128798: {
                    1: _qualification_jobs(conclusion="failure"),
                    2: _qualification_jobs(conclusion="cancelled"),
                },
                29946139071: {1: _qualification_jobs(conclusion="failure")},
            },
        )
        self.assertFalse(decision["admitted"])
        self.assertIn("3-attempt", decision["reason"])

    def test_one_run_with_three_started_attempts_reaches_the_bound(self) -> None:
        run = _run(run_id=1, run_attempt=3)
        decision = _decide(
            [run],
            jobs_by_run={1: {attempt: _qualification_jobs() for attempt in range(1, 4)}},
        )
        self.assertFalse(decision["admitted"])

    def test_earlier_started_rerun_is_counted_when_latest_never_started(self) -> None:
        run = _run(run_id=1, run_attempt=2, conclusion="cancelled")
        pre_start_cancelled = _qualification_jobs(conclusion="cancelled", started=False)
        decision = _decide(
            [run],
            jobs_by_run={1: {1: _qualification_jobs(conclusion="failure"), 2: pre_start_cancelled}},
        )
        self.assertTrue(decision["admitted"])

    def test_missing_or_extra_historical_attempt_authority_fails_closed(self) -> None:
        run = _run(run_id=1, run_attempt=2)
        with self.subTest("missing"):
            with self.assertRaisesRegex(ValueError, "attempt job authority is incomplete"):
                _decide([run], jobs_by_run={1: {2: _qualification_jobs()}})
        with self.subTest("extra"):
            with self.assertRaisesRegex(ValueError, "attempt job authority is incomplete"):
                _decide([run], jobs_by_run={1: {1: _qualification_jobs(), 2: _qualification_jobs(), 3: _qualification_jobs()}})

    def test_attempt_specific_pagination_malformed_and_duplicate_fail_closed(self) -> None:
        run = _run(run_id=1)
        incomplete = {"total_count": 1, "jobs": []}
        duplicate = {
            "total_count": 2,
            "jobs": [
                {"id": 2, "name": "qualify", "status": "completed", "conclusion": "failure", "started_at": "x"},
                {"id": 2, "name": "other", "status": "completed", "conclusion": "failure"},
            ],
        }
        with self.subTest("incomplete"):
            with self.assertRaisesRegex(ValueError, "attempt 1 jobs pagination is incomplete"):
                _decide([run], jobs_by_run={1: {1: incomplete}})
        with self.subTest("duplicate"):
            with self.assertRaisesRegex(ValueError, "attempt 1 jobs response contains duplicate"):
                _decide([run], jobs_by_run={1: {1: duplicate}})

    def test_skipped_or_pre_start_cancelled_attempts_do_not_count(self) -> None:
        runs = [_run(run_id=1, conclusion="cancelled"), _run(run_id=2, conclusion="cancelled")]
        self.assertTrue(
            _decide(
                runs,
                jobs_by_run={
                    1: {1: _qualification_jobs(conclusion="skipped")},
                    2: {1: _qualification_jobs(conclusion="cancelled", started=False)},
                },
            )["admitted"]
        )

    def test_started_cancelled_attempts_count(self) -> None:
        run = _run(run_id=1, run_attempt=3, conclusion="cancelled")
        decision = _decide(
            [run],
            jobs_by_run={1: {attempt: _qualification_jobs(conclusion="cancelled") for attempt in range(1, 4)}},
        )
        self.assertFalse(decision["admitted"])

    def test_current_workflow_rerun_is_rejected_before_exclusion(self) -> None:
        current = _run(run_id=42, run_attempt=2)
        with self.assertRaisesRegex(ValueError, "workflow reruns are not admitted"):
            _decide([current], jobs_by_run={}, current_run_id=42)

    def test_fresh_dispatch_remains_admitted_below_real_start_bound(self) -> None:
        prior = _run(run_id=1, run_attempt=2, conclusion="cancelled")
        current = _run(run_id=42)
        decision = _decide(
            [prior, current],
            jobs_by_run={
                1: {
                    1: _qualification_jobs(conclusion="failure"),
                    2: _qualification_jobs(conclusion="cancelled", started=False),
                }
            },
            current_run_id=42,
        )
        self.assertTrue(decision["admitted"])

    def test_run_attempt_schema_and_bounded_authority_fail_closed(self) -> None:
        with self.subTest("bool"):
            with self.assertRaisesRegex(ValueError, "run_attempt must be a positive integer"):
                _decide([_run(run_id=1, run_attempt=True)])
        with self.subTest("excessive"):
            with self.assertRaisesRegex(ValueError, "bounded admission limit"):
                _decide([_run(run_id=1, run_attempt=admission.MAX_RUN_ATTEMPTS_TO_INSPECT + 1)])

    def test_missing_job_authority_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "attempt job authority is incomplete"):
            _decide([_run(run_id=1, conclusion="failure")], jobs_by_run={})


if __name__ == "__main__":
    unittest.main()
