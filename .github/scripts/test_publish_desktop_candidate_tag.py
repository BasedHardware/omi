#!/usr/bin/env python3
"""Behavioral contract tests for fail-closed macOS candidate-tag publication."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("publish-desktop-candidate-tag.py")
SPEC = importlib.util.spec_from_file_location("publish_desktop_candidate_tag", SCRIPT)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)

REPOSITORY = "BasedHardware/omi"
CANDIDATE_SHA = "a" * 40
TAG_OBJECT_SHA = "b" * 40
RELEASE_TAG = "v1.2.3+10203-macos"


class PublishDesktopCandidateTagTests(unittest.TestCase):
    def test_publishes_only_after_refetching_exact_live_main(self) -> None:
        responses = [
            {"sha": TAG_OBJECT_SHA},
            {"object": {"sha": CANDIDATE_SHA}},
            {
                "ref": f"refs/tags/{RELEASE_TAG}",
                "object": {"sha": TAG_OBJECT_SHA},
            },
        ]
        with patch.object(publisher, "run_gh_json", side_effect=responses) as run_gh:
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                release_tag=RELEASE_TAG,
                candidate_sha=CANDIDATE_SHA,
                evidence="immutable planner evidence\n",
                timestamp="2026-07-25T00:00:00Z",
            )

        main_args = run_gh.call_args_list[1].args
        self.assertEqual(
            main_args,
            (
                [
                    "api",
                    "--method",
                    "GET",
                    f"repos/{REPOSITORY}/git/ref/heads/main",
                ],
            ),
        )
        ref_args, ref_payload = run_gh.call_args_list[2].args
        self.assertEqual(
            ref_args,
            ["api", "--method", "POST", f"repos/{REPOSITORY}/git/refs"],
        )
        self.assertEqual(
            ref_payload,
            {
                "ref": f"refs/tags/{RELEASE_TAG}",
                "sha": TAG_OBJECT_SHA,
            },
        )

    def test_main_advance_rejection_never_creates_the_tag_ref(self) -> None:
        responses = [
            {"sha": TAG_OBJECT_SHA},
            {"object": {"sha": "c" * 40}},
        ]
        with patch.object(publisher, "run_gh_json", side_effect=responses) as run_gh:
            with self.assertRaisesRegex(ValueError, "GitHub main moved before candidate publication"):
                publisher.publish_candidate_tag(
                    repository=REPOSITORY,
                    release_tag=RELEASE_TAG,
                    candidate_sha=CANDIDATE_SHA,
                    evidence="immutable planner evidence\n",
                    timestamp="2026-07-25T00:00:00Z",
                )
        self.assertEqual(run_gh.call_count, 2)

    def test_annotated_tag_carries_identity_evidence_before_ref_creation(self) -> None:
        responses = [
            {"sha": TAG_OBJECT_SHA},
            {"object": {"sha": CANDIDATE_SHA}},
            {
                "ref": f"refs/tags/{RELEASE_TAG}",
                "object": {"sha": TAG_OBJECT_SHA},
            },
        ]
        with patch.object(publisher, "run_gh_json", side_effect=responses) as run_gh:
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                release_tag=RELEASE_TAG,
                candidate_sha=CANDIDATE_SHA,
                evidence="immutable planner evidence\n",
                timestamp="2026-07-25T00:00:00Z",
            )

        tag_args, tag_payload = run_gh.call_args_list[0].args
        self.assertEqual(tag_args, ["api", "--method", "POST", f"repos/{REPOSITORY}/git/tags"])
        self.assertEqual(tag_payload["object"], CANDIDATE_SHA)
        self.assertEqual(tag_payload["message"], "immutable planner evidence\n")
        self.assertEqual(tag_payload["tagger"]["name"], publisher.TAGGER_NAME)
        self.assertEqual(tag_payload["tagger"]["date"], "2026-07-25T00:00:00Z")

    def test_existing_tag_api_failure_is_actionable_and_credential_safe(self) -> None:
        result = subprocess.CompletedProcess(
            ["gh", "api"],
            1,
            stdout="",
            stderr=(
                "HTTP 422: Reference already exists " "(Request ID: A50A:19CD13) Authorization: Bearer ghp_supersecret"
            ),
        )
        with patch.object(publisher.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(
                publisher.GitHubApiError,
                r"HTTP 422: Reference already exists .*Request ID: A50A:19CD13",
            ) as raised:
                publisher.run_gh_json(
                    ["api", "--method", "POST", f"repos/{REPOSITORY}/git/refs"],
                    {"ref": f"refs/tags/{RELEASE_TAG}", "sha": TAG_OBJECT_SHA},
                )

        self.assertNotIn("ghp_supersecret", str(raised.exception))
        self.assertIn("<redacted>", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
