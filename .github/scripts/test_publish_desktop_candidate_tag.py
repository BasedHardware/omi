#!/usr/bin/env python3
"""Behavioral contract tests for atomic macOS candidate-tag publication."""

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
REPOSITORY_ID = "R_kgDOGHExample"
CANDIDATE_SHA = "a" * 40
TAG_OBJECT_SHA = "b" * 40
RELEASE_TAG = "v1.2.3+10203-macos"


class PublishDesktopCandidateTagTests(unittest.TestCase):
    def test_ref_transaction_requires_live_main_and_an_unused_tag(self) -> None:
        with patch.object(publisher, "run_gh_json", return_value={"data": {"updateRefs": {}}}) as run_gh:
            publisher.atomic_publish_tag_ref(
                repository_id_value=REPOSITORY_ID,
                release_tag=RELEASE_TAG,
                candidate_sha=CANDIDATE_SHA,
                tag_object_sha=TAG_OBJECT_SHA,
            )

        args, payload = run_gh.call_args.args
        self.assertEqual(args, ["api", "graphql"])
        self.assertIn("updateRefs", payload["query"])
        self.assertEqual(
            payload["variables"],
            {
                "repositoryId": REPOSITORY_ID,
                "mainBefore": CANDIDATE_SHA,
                "mainAfter": CANDIDATE_SHA,
                "tagName": f"refs/tags/{RELEASE_TAG}",
                "tagObject": TAG_OBJECT_SHA,
                "zeroOid": publisher.ZERO_OID,
            },
        )

    def test_main_advance_rejection_cannot_report_a_published_candidate(self) -> None:
        responses = [
            {"data": {"repository": {"id": REPOSITORY_ID}}},
            {"sha": TAG_OBJECT_SHA},
            subprocess.CalledProcessError(1, ["gh", "api", "graphql"], stderr="main beforeOid mismatch"),
        ]
        with patch.object(publisher, "run_gh_json", side_effect=responses):
            with self.assertRaises(subprocess.CalledProcessError):
                publisher.publish_candidate_tag(
                    repository=REPOSITORY,
                    release_tag=RELEASE_TAG,
                    candidate_sha=CANDIDATE_SHA,
                    evidence="immutable planner evidence\n",
                    timestamp="2026-07-25T00:00:00Z",
                )

    def test_annotated_tag_carries_the_identity_evidence_before_the_ref_transaction(self) -> None:
        responses = [
            {"data": {"repository": {"id": REPOSITORY_ID}}},
            {"sha": TAG_OBJECT_SHA},
            {"data": {"updateRefs": {}}},
        ]
        with patch.object(publisher, "run_gh_json", side_effect=responses) as run_gh:
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                release_tag=RELEASE_TAG,
                candidate_sha=CANDIDATE_SHA,
                evidence="immutable planner evidence\n",
                timestamp="2026-07-25T00:00:00Z",
            )

        tag_args, tag_payload = run_gh.call_args_list[1].args
        self.assertEqual(tag_args, ["api", "--method", "POST", f"repos/{REPOSITORY}/git/tags"])
        self.assertEqual(tag_payload["object"], CANDIDATE_SHA)
        self.assertEqual(tag_payload["message"], "immutable planner evidence\n")
        self.assertEqual(tag_payload["tagger"]["name"], publisher.TAGGER_NAME)
        self.assertEqual(tag_payload["tagger"]["date"], "2026-07-25T00:00:00Z")
        self.assertEqual(run_gh.call_args_list[2].args[1]["variables"]["mainBefore"], CANDIDATE_SHA)


if __name__ == "__main__":
    unittest.main()
