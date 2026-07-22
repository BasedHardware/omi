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


def _run(*, run_id: int, status: str = "completed", conclusion: str | None = "failure", tag: str = TAG, sha: str = SHA) -> dict:
    return {
        "id": run_id,
        "path": admission.QUALIFICATION_WORKFLOW,
        "event": "workflow_dispatch",
        "head_branch": tag,
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
    }


def _response(runs: list[dict]) -> dict:
    return {"total_count": len(runs), "workflow_runs": runs}


def _decide(runs: list[dict], **kwargs: object) -> dict:
    return admission.decide(_ref(), _response(runs), release_tag=TAG, **kwargs)


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
        decision = _decide([_run(run_id=42, conclusion="success")], current_run_id=42)
        self.assertTrue(decision["admitted"])

    def test_other_tag_does_not_block_exact_candidate(self) -> None:
        decision = _decide([_run(run_id=1, status="queued", conclusion=None, tag=OTHER_TAG)])
        self.assertTrue(decision["admitted"])

    def test_annotated_tag_peels_to_exact_commit(self) -> None:
        ref = {"ref": f"refs/tags/{TAG}", "object": {"type": "tag", "sha": "b" * 40}}
        tag = {"sha": "b" * 40, "object": {"type": "commit", "sha": SHA}}
        decision = admission.decide(ref, _response([]), release_tag=TAG, annotated_tag=tag)
        self.assertEqual(decision["source_sha"], SHA)

    def test_malformed_api_response_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed"):
            admission.decide(_ref(), {"total_count": 0, "workflow_runs": {}}, release_tag=TAG)
        with self.assertRaisesRegex(ValueError, "non-object"):
            admission.decide(_ref(), {"total_count": 1, "workflow_runs": [None]}, release_tag=TAG)

    def test_malformed_exact_tag_ref_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not bind"):
            admission.decide({}, _response([]), release_tag=TAG)

    def test_success_on_second_page_beyond_first_hundred_denies(self) -> None:
        first_page = [_run(run_id=index, tag=OTHER_TAG) for index in range(1, 101)]
        second_page = [_run(run_id=101, conclusion="success")]
        pages = [
            {"total_count": 101, "workflow_runs": first_page},
            {"total_count": 101, "workflow_runs": second_page},
        ]
        decision = admission.decide(_ref(), pages, release_tag=TAG)
        self.assertFalse(decision["admitted"])
        self.assertIn("succeeded", decision["reason"])

    def test_incomplete_paginated_response_fails_closed(self) -> None:
        partial = {"total_count": 101, "workflow_runs": [_run(run_id=index) for index in range(1, 101)]}
        with self.assertRaisesRegex(ValueError, "pagination is incomplete"):
            admission.decide(_ref(), partial, release_tag=TAG)

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


if __name__ == "__main__":
    unittest.main()
