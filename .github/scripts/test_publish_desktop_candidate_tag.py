#!/usr/bin/env python3
"""Behavioral contract tests for fail-closed macOS candidate-tag publication."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

SCRIPT = Path(__file__).with_name("publish-desktop-candidate-tag.py")
SPEC = importlib.util.spec_from_file_location("publish_desktop_candidate_tag", SCRIPT)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)

REPOSITORY = "BasedHardware/omi"
CANDIDATE_SHA = "a" * 40
RELEASE_TAG = "v1.2.3+10203-macos"


class PublishDesktopCandidateTagTests(unittest.TestCase):
    def test_native_git_transport_preserves_annotated_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            remote = root / "remote.git"
            source.mkdir()
            git_environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

            def git(*args: str, cwd: Path = source) -> str:
                result = subprocess.run(
                    ["git", *args],
                    cwd=cwd,
                    env=git_environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "--quiet")
            git("config", "user.name", "Candidate contract")
            git("config", "user.email", "candidate-contract@example.com")
            (source / "candidate.txt").write_text("candidate source\n", encoding="utf-8")
            git("add", "candidate.txt")
            git("commit", "--quiet", "-m", "candidate")
            candidate_sha = git("rev-parse", "HEAD")
            git("init", "--bare", "--quiet", str(remote), cwd=root)
            git("remote", "add", "origin", str(remote))
            git("push", "--quiet", "origin", "HEAD:refs/heads/main")

            original_directory = Path.cwd()
            try:
                os.chdir(source)
                publisher.create_local_annotated_tag(
                    release_tag=RELEASE_TAG,
                    candidate_sha=candidate_sha,
                    evidence="immutable planner evidence\n",
                    timestamp="2026-07-25T00:00:00Z",
                )
                publisher.publish_immutable_tag_ref(RELEASE_TAG)
            finally:
                os.chdir(original_directory)

            self.assertEqual(git("cat-file", "-t", f"refs/tags/{RELEASE_TAG}", cwd=remote), "tag")
            evidence = git("cat-file", "-p", f"refs/tags/{RELEASE_TAG}", cwd=remote)
            self.assertIn(f"object {candidate_sha}", evidence)
            self.assertIn("immutable planner evidence", evidence)

    def test_publishes_only_after_refetching_exact_live_main_via_native_tag_push(self) -> None:
        with (
            patch.object(publisher, "run_gh_json", return_value={"object": {"sha": CANDIDATE_SHA}}) as run_gh,
            patch.object(publisher, "run_git") as run_git,
        ):
            publisher.publish_candidate_tag(
                repository=REPOSITORY,
                release_tag=RELEASE_TAG,
                candidate_sha=CANDIDATE_SHA,
                evidence="immutable planner evidence\n",
                timestamp="2026-07-25T00:00:00Z",
            )

        self.assertEqual(
            run_gh.call_args_list,
            [call(["api", "--method", "GET", f"repos/{REPOSITORY}/git/ref/heads/main"])],
        )
        self.assertEqual(
            run_git.call_args_list[0].args,
            (["tag", "--annotate", "--file=-", RELEASE_TAG, CANDIDATE_SHA],),
        )
        self.assertEqual(run_git.call_args_list[0].kwargs["stdin"], "immutable planner evidence\n")
        self.assertEqual(
            run_git.call_args_list[0].kwargs["environment"]["GIT_COMMITTER_NAME"], publisher.TAGGER_NAME
        )
        self.assertEqual(
            run_git.call_args_list[0].kwargs["environment"]["GIT_COMMITTER_DATE"], "2026-07-25T00:00:00Z"
        )
        self.assertEqual(
            run_git.call_args_list[1],
            call(["push", "origin", f"refs/tags/{RELEASE_TAG}:refs/tags/{RELEASE_TAG}"]),
        )

    def test_main_advance_rejection_never_pushes_the_tag(self) -> None:
        with (
            patch.object(publisher, "run_gh_json", return_value={"object": {"sha": "c" * 40}}) as run_gh,
            patch.object(publisher, "run_git") as run_git,
        ):
            with self.assertRaisesRegex(ValueError, "GitHub main moved before candidate publication"):
                publisher.publish_candidate_tag(
                    repository=REPOSITORY,
                    release_tag=RELEASE_TAG,
                    candidate_sha=CANDIDATE_SHA,
                    evidence="immutable planner evidence\n",
                    timestamp="2026-07-25T00:00:00Z",
                )
        self.assertEqual(
            run_gh.call_args_list,
            [call(["api", "--method", "GET", f"repos/{REPOSITORY}/git/ref/heads/main"])],
        )
        self.assertEqual(run_git.call_count, 1)
        self.assertEqual(
            run_git.call_args_list[0].args,
            (["tag", "--annotate", "--file=-", RELEASE_TAG, CANDIDATE_SHA],),
        )

    def test_transport_failure_is_actionable_and_credential_safe(self) -> None:
        result = subprocess.CompletedProcess(
            ["git", "push"],
            1,
            stdout="",
            stderr=(
                "remote: cannot lock ref 'refs/tags/v1.2.3+10203-macos': reference already exists "
                "https://x-access-token:ghp_supersecret@github.com/BasedHardware/omi.git"
            ),
        )
        with patch.object(publisher.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(
                publisher.GitTransportError,
                r"cannot lock ref 'refs/tags/v1.2.3\+10203-macos': reference already exists",
            ) as raised:
                publisher.run_git(["push", "origin", f"refs/tags/{RELEASE_TAG}:refs/tags/{RELEASE_TAG}"])

        self.assertNotIn("ghp_supersecret", str(raised.exception))
        self.assertIn("<redacted>", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
