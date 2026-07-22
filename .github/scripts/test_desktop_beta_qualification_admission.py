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


def _decide(runs: list[dict], **kwargs: object) -> dict:
    return admission.decide(_ref(), {"workflow_runs": runs}, release_tag=TAG, **kwargs)


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
        decision = admission.decide(ref, {"workflow_runs": []}, release_tag=TAG, annotated_tag=tag)
        self.assertEqual(decision["source_sha"], SHA)

    def test_malformed_api_response_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed"):
            admission.decide(_ref(), {"workflow_runs": {}}, release_tag=TAG)
        with self.assertRaisesRegex(ValueError, "non-object"):
            admission.decide(_ref(), {"workflow_runs": [None]}, release_tag=TAG)

    def test_malformed_exact_tag_ref_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not bind"):
            admission.decide({}, {"workflow_runs": []}, release_tag=TAG)


if __name__ == "__main__":
    unittest.main()
