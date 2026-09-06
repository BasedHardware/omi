#!/usr/bin/env python3
"""Regression tests for PR metadata, check selection, and single-flight execution."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import preflight_runner
from pr_metadata import (
    TransientPRMetadataError,
    extract_merged_pr_number,
    load_from_api,
    load_from_event_file,
    load_from_gh,
    resolve_main_push_body,
)
from pr_preflight import (
    changed_files,
    current_branch,
    format_failure_class_suggest,
    resolve_pr_metadata,
    run_git,
    run_python_capture,
    select_checks,
)

SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER = SCRIPT_DIR / "preflight_runner.py"
REPO_ROOT = SCRIPT_DIR.parents[1]


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class MetadataTests(unittest.TestCase):
    def test_gh_loader_decodes_current_metadata_as_utf8(self) -> None:
        payload = json.dumps(
            {
                "number": 10823,
                "body": "packaged entry → debug → ms",
                "updatedAt": "2026-08-28T07:45:46Z",
                "labels": [{"name": "workflow-review"}],
            },
            ensure_ascii=False,
        )
        completed = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=payload, stderr="")

        with patch("pr_metadata.subprocess.run", return_value=completed) as run:
            metadata = load_from_gh(REPO_ROOT)

        self.assertEqual(metadata.body, "packaged entry → debug → ms")
        self.assertEqual(metadata.labels, ("workflow-review",))
        _, kwargs = run.call_args
        self.assertEqual(kwargs.get("encoding"), "utf-8")

    def test_api_loader_uses_current_body_and_records_provenance(self) -> None:
        captured = {}

        def opener(request: object, timeout: int) -> FakeResponse:
            captured["url"] = request.full_url  # type: ignore[attr-defined]
            captured["authorization"] = request.headers["Authorization"]  # type: ignore[attr-defined]
            captured["timeout"] = timeout
            return FakeResponse(
                json.dumps(
                    {
                        "number": 9402,
                        "body": "INV-AUTH-1\nINV-CHAT-1\nINV-AGENT-*",
                        "updated_at": "2026-07-10T21:17:00Z",
                        "labels": [{"name": "no-changelog-needed"}],
                    }
                ).encode()
            )

        metadata = load_from_api("BasedHardware/omi", 9402, "test-token", opener=opener)
        self.assertEqual(metadata.number, 9402)
        self.assertIn("INV-CHAT-1", metadata.body)
        self.assertEqual(metadata.updated_at, "2026-07-10T21:17:00Z")
        self.assertEqual(metadata.labels, ("no-changelog-needed",))
        self.assertEqual(captured["url"], "https://api.github.com/repos/BasedHardware/omi/pulls/9402")
        self.assertEqual(captured["authorization"], "Bearer test-token")
        self.assertEqual(captured["timeout"], 15)

    def test_api_loader_retries_transient_failures_then_succeeds(self) -> None:
        payload = json.dumps({"number": 9847, "body": "ok", "updated_at": "u", "labels": []}).encode()
        outcomes: list[object] = [
            urllib.error.HTTPError("url", 502, "bad gateway", None, io.BytesIO()),  # type: ignore[arg-type]
            TimeoutError("timed out"),
            FakeResponse(payload),
        ]
        sleeps: list[float] = []

        def opener(request: object, timeout: int) -> FakeResponse:
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome  # type: ignore[return-value]

        metadata = load_from_api("BasedHardware/omi", 9847, "test-token", opener=opener, sleeper=sleeps.append)
        self.assertEqual(metadata.number, 9847)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_api_loader_does_not_retry_permanent_http_errors(self) -> None:
        calls = {"count": 0}

        def opener(request: object, timeout: int) -> FakeResponse:
            calls["count"] += 1
            raise urllib.error.HTTPError("url", 404, "not found", None, io.BytesIO())  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "HTTP 404") as raised:
            load_from_api("BasedHardware/omi", 9847, "test-token", opener=opener, sleeper=lambda _: None)
        self.assertEqual(calls["count"], 1)
        cause = raised.exception.__cause__
        self.assertIsInstance(cause, urllib.error.HTTPError)
        cause.close()  # type: ignore[union-attr]

    def test_api_loader_raises_after_exhausting_transient_retries(self) -> None:
        calls = {"count": 0}

        def opener(request: object, timeout: int) -> FakeResponse:
            calls["count"] += 1
            raise TimeoutError("timed out")

        with self.assertRaisesRegex(TransientPRMetadataError, "request failed"):
            load_from_api("BasedHardware/omi", 9847, "test-token", opener=opener, sleeper=lambda _: None)
        self.assertEqual(calls["count"], 3)

    def test_extract_merged_pr_number_from_squash_and_merge_subjects(self) -> None:
        self.assertEqual(
            extract_merged_pr_number(
                "Cut the Windows app's idle request volume (#11835)\n\n* Run the retention sweep\n"
            ),
            11835,
        )
        self.assertEqual(extract_merged_pr_number('Merge pull request #10965 from aryanorastar/fix'), 10965)
        self.assertEqual(extract_merged_pr_number('Revert "foo (#12)" (#99)'), 99)
        self.assertIsNone(extract_merged_pr_number("security(backend): gate Anthropic web search"))
        self.assertIsNone(extract_merged_pr_number(""))

    def test_main_push_body_uses_live_pr_body_for_squash_head(self) -> None:
        """#12003: wrapped merge text must not remain beside line-sensitive metadata."""
        commit = (
            "Cut the Windows app's idle and focus-driven backend request volume (#11835)\n\n"
            "Line-Count-Exception: backend/utils/conversations/process_conversation.py | 2403 ->\n"
            "  2424 | extracted helper keeps the production owner readable\n"
        )
        live_body = (
            "## Product invariants affected\n\n"
            "- INV-CHAT-1\n\n"
            "Line-Count-Exception: backend/utils/conversations/process_conversation.py | "
            "2403 -> 2424 | extracted helper keeps the production owner readable\n"
        )
        metadata = type("M", (), {"body": live_body, "number": 11835})()
        resolved = resolve_main_push_body(
            commit,
            repository="BasedHardware/omi",
            token="test-token",
            loader=lambda *args, **kwargs: metadata,
        )
        self.assertEqual(resolved, live_body)
        self.assertNotIn("2403 ->\n", resolved)

    def test_main_push_body_keeps_commit_message_when_live_pr_body_is_empty(self) -> None:
        commit = "Cut the Windows app's idle volume (#11835)\n\nFailure-Class: FC-example\n"
        metadata = type("M", (), {"body": "  \n", "number": 11835})()

        self.assertEqual(
            resolve_main_push_body(
                commit,
                repository="BasedHardware/omi",
                token="test-token",
                loader=lambda *args, **kwargs: metadata,
            ),
            commit,
        )

    def test_main_push_body_keeps_commit_message_without_pr_number_or_token(self) -> None:
        commit = "direct push that forgot INV-CHAT-1\n"
        self.assertEqual(
            resolve_main_push_body(commit, repository="BasedHardware/omi", token=""),
            commit,
        )
        self.assertEqual(
            resolve_main_push_body(commit, repository="BasedHardware/omi", token="tok"),
            commit,
        )

    def test_main_push_body_falls_back_when_api_fails(self) -> None:
        commit = "Cut the Windows app's idle volume (#11835)\n"

        def loader(*args: object, **kwargs: object):
            raise RuntimeError("GitHub API returned HTTP 502 while reading PR #11835")

        self.assertEqual(
            resolve_main_push_body(
                commit,
                repository="BasedHardware/omi",
                token="test-token",
                loader=loader,
            ),
            commit,
        )

    def test_event_payload_loader_uses_top_level_pr_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "number": 9847,
                        "pull_request": {
                            "body": "INV-MEM-1",
                            "updated_at": "2026-07-16T23:30:00Z",
                            "labels": [{"name": "no-changelog-needed"}],
                        },
                    }
                ),
                encoding="utf-8",
            )

            metadata = load_from_event_file(event_path, 9847)

        self.assertEqual(metadata.number, 9847)
        self.assertEqual(metadata.body, "INV-MEM-1")
        self.assertEqual(metadata.labels, ("no-changelog-needed",))

    def test_event_payload_loader_rejects_missing_pull_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(json.dumps({"number": 9847}), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "pull_request"):
                load_from_event_file(event_path, 9847)

    def test_pr_metadata_uses_event_payload_only_after_transient_api_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text(
                json.dumps({"number": 9847, "pull_request": {"body": "current", "labels": []}}),
                encoding="utf-8",
            )
            warnings = io.StringIO()
            with patch.dict(os.environ, {"OMI_PR_BODY_FILE": ""}), patch(
                "pr_preflight.load_from_api", side_effect=TransientPRMetadataError("GitHub API unavailable")
            ), redirect_stderr(warnings):
                metadata = resolve_pr_metadata(REPO_ROOT, None, "BasedHardware/omi", 9847, event_path)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.body, "current")
        self.assertIn("using the PR snapshot", warnings.getvalue())

    def test_pr_metadata_does_not_use_event_payload_after_permanent_api_failure(self) -> None:
        with patch.dict(os.environ, {"OMI_PR_BODY_FILE": ""}), patch(
            "pr_preflight.load_from_api", side_effect=RuntimeError("GitHub API returned HTTP 403")
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                resolve_pr_metadata(REPO_ROOT, None, "BasedHardware/omi", 9847, Path("event.json"))


class SelectionTests(unittest.TestCase):
    def test_captured_python_output_is_utf8_when_host_utf8_mode_is_disabled(self) -> None:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "0"
        env.pop("PYTHONIOENCODING", None)

        with patch.dict(os.environ, env, clear=True):
            completed = run_python_capture(
                REPO_ROOT,
                "-c",
                "print('\\u8def\\u5f84\\U0001f680')",
            )

        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(completed.stdout, "路径🚀\n")

    def test_current_branch_decodes_utf8_when_host_utf8_mode_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = os.environ.copy()
            env["PYTHONUTF8"] = "0"
            env.pop("PYTHONIOENCODING", None)
            for key in tuple(env):
                if key.startswith("GIT_"):
                    del env[key]
            subprocess.run(["git", "init", "-q", "-b", "分支-🚀", str(root)], check=True, env=env)

            with patch.dict(os.environ, env, clear=True):
                branch = current_branch(root)

        self.assertEqual(branch, "分支-🚀")

    def test_run_git_decodes_unicode_checkout_path_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "路径 checkout"
            root.mkdir()
            env = os.environ.copy()
            for key in tuple(env):
                if key.startswith("GIT_"):
                    del env[key]
            subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)

            with patch.dict(os.environ, env, clear=True):
                resolved = run_git(root, "rev-parse", "--show-toplevel")

        self.assertEqual(Path(resolved).resolve(), root.resolve())

    def test_changed_files_disables_rename_detection_to_preserve_both_move_paths(self) -> None:
        root = Path("/repo")
        source = "desktop/macos/Desktop/Sources/FloatingControlBar/VoiceTurnStateMachine.swift"
        destination = "desktop/macos/Desktop/Sources/VoiceTurnDomain/VoiceTurnStateMachine.swift"
        with patch("pr_preflight.run_git", return_value=f"{source}\n{destination}\n") as run_git:
            self.assertEqual(changed_files(root, "base", "head"), [source, destination])

        run_git.assert_called_once_with(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACMRTD",
            "base...head",
        )

    def test_stale_event_payload_base_widens_diff_scope_past_the_live_base(self) -> None:
        """Behavioral regression for FC-stale-event-payload-diff-base (#10758).

        Exercises the real changed_files() git seam end to end: a base SHA
        captured once (standing in for github.event.pull_request.base.sha) and
        never refreshed goes stale as the target branch keeps advancing, so a
        downstream merge-ref diff against it silently picks up unrelated
        commits. A live-resolved base ref does not.
        """
        # Disposable repo must not inherit the caller's git context: under a
        # pre-commit/pre-push hook, GIT_DIR points at the real checkout and its
        # commit-msg hook would reject these throwaway messages.
        git_isolation = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]

        def run(*args: str, cwd: Path) -> None:
            subprocess.run(
                ["git", *git_isolation, *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        def rev_parse(cwd: Path, ref: str = "HEAD") -> str:
            result = subprocess.run(
                ["git", *git_isolation, "rev-parse", ref],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            return result.stdout.strip()

        def commit(cwd: Path, path: str, content: str, message: str) -> str:
            (cwd / path).write_text(content, encoding="utf-8")
            run("add", path, cwd=cwd)
            run("commit", "-q", "-m", message, cwd=cwd)
            return rev_parse(cwd)

        with patch.dict(os.environ):
            for key in list(os.environ):
                if key.startswith("GIT_"):
                    del os.environ[key]

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run("init", "-q", "-b", "main", cwd=root)
                run("config", "user.email", "test@example.com", cwd=root)
                run("config", "user.name", "Test", cwd=root)

                # The SHA a PR event payload would have captured at PR-open time.
                stale_base_sha = commit(root, "root.txt", "root", "root commit")

                run("checkout", "-q", "-b", "pr", cwd=root)
                commit(root, "pr_file.txt", "pr change", "touch pr_file.txt")
                run("checkout", "-q", "main", cwd=root)

                # main keeps moving after the PR branched. This is what makes
                # stale_base_sha stale: no event ever refreshes it past here.
                commit(root, "unrelated_file.txt", "v1", "unrelated main commit 1")
                commit(root, "unrelated_file.txt", "v2", "unrelated main commit 2")

                # GitHub's refs/pull/N/merge: the PR branch merged onto main's
                # *current* tip, on its own ref — main itself does not move.
                run("checkout", "-q", "-b", "merge_ref", "main", cwd=root)
                run("merge", "--no-ff", "-q", "-m", "merge pr into main", "pr", cwd=root)
                merge_sha = rev_parse(root)

                stale_diff = changed_files(root, stale_base_sha, merge_sha)
                # "main" stands in for a freshly fetched origin/<base_ref>: a
                # live ref, not a value captured once and carried across events.
                live_diff = changed_files(root, "main", merge_sha)

                self.assertEqual(sorted(live_diff), ["pr_file.txt"])
                self.assertEqual(sorted(stale_diff), ["pr_file.txt", "unrelated_file.txt"])

    def test_make_preflight_resolves_pr_metadata_before_running_checks(self) -> None:
        result = subprocess.run(
            ["make", "-n", "preflight"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("scripts/dev-harness/run-python.sh", result.stdout)
        self.assertIn(".github/scripts/pr_preflight.py --lane local --base origin/main", result.stdout)
        if os.name == "nt":
            self.assertIn("Git/mingw64/libexec/git-core/../../../bin/bash.exe", result.stdout.replace("\\", "/"))

    def test_9402_equivalent_diff_selects_invariants_changelog_and_e2e(self) -> None:
        checks = select_checks(
            [
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
                "desktop/macos/agent/src/runtime/control-tools.ts",
            ],
            platform="macos",
        )
        names = {check.name for check in checks}
        self.assertIn("product-invariants", names)
        self.assertIn("desktop-changelog-entry", names)
        self.assertIn("desktop-e2e-flow-coverage", names)

    def test_docs_diff_keeps_contract_small(self) -> None:
        names = {check.name for check in select_checks(["docs/doc/developer/Contribution.mdx"])}
        self.assertEqual(
            names,
            {
                "check-manifest-contract",
                "diff-hygiene",
                "git-author-identity",
                "architecture-guardrails",
                "product-invariants",
                "failure-class-protocol",
                "failure-class-guard-artifact-ratchet",
                "desktop-changelog-data",
                "deferred-work-markers",
                "lifecycle-headers",
                "version-prefixed-filenames",
            },
        )

    def test_9402_equivalent_fixture_fails_missing_invariants_and_flow_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            changed = temp / "changed.txt"
            body = temp / "body.md"
            changed.write_text(
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift\n"
                "desktop/macos/Desktop/Sources/Providers/UncoveredRoutingSurface.swift\n"
                "desktop/macos/agent/src/runtime/control-tools.ts\n",
                encoding="utf-8",
            )
            body.write_text("## Product invariants affected\n\nnone\n", encoding="utf-8")
            invariant = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/check_product_invariants.py",
                    "--changed-files",
                    str(changed),
                    "--pr-body-file",
                    str(body),
                ],
                cwd=REPO_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            coverage = subprocess.run(
                [
                    sys.executable,
                    "desktop/macos/scripts/check-e2e-flow-coverage.py",
                    "--strict",
                    "desktop/macos/Desktop/Sources/Providers/UncoveredRoutingSurface.swift",
                ],
                cwd=REPO_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(invariant.returncode, 1, invariant.stdout)
            self.assertIn("INV-AUTH-1", invariant.stdout)
            self.assertIn("INV-CHAT-1", invariant.stdout)
            self.assertIn("INV-AGENT-*", invariant.stdout)
            self.assertEqual(coverage.returncode, 1, coverage.stdout)
            self.assertIn("UNCOVERED", coverage.stdout)

    def test_flow_coverage_discovers_unicode_checkout_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "路径 checkout"
            source = root / "desktop/macos/Desktop/Sources/Fixture.swift"
            source.parent.mkdir(parents=True)
            source.write_text("struct Fixture {}\n", encoding="utf-8")
            env = os.environ.copy()
            for key in tuple(env):
                if key.startswith("GIT_"):
                    del env[key]
            subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, env=env)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Omi Test",
                    "-c",
                    "user.email=omi-test@example.com",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
                env=env,
            )
            source.write_text("struct Fixture { let value = 1 }\n", encoding="utf-8")

            coverage = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "desktop/macos/scripts/check-e2e-flow-coverage.py"),
                    "--formatter-binary",
                    "none",
                    "--base",
                    "HEAD",
                    "--strict",
                ],
                cwd=root,
                env=env,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(coverage.returncode, 1, coverage.stdout)
        self.assertIn("UNCOVERED", coverage.stdout)

    def test_suggest_flag_prints_paste_ready_pr_metadata(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                ".github/scripts/pr_preflight.py",
                "--base",
                "HEAD",
                "--head",
                "HEAD",
                "--suggest",
            ],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("## Product invariants affected", result.stdout)
        self.assertIn("## Failure class (fixes)", result.stdout)
        self.assertIn("No `fix:` commits were detected", result.stdout)

    def test_failure_class_suggestion_keeps_classification_manual(self) -> None:
        output = format_failure_class_suggest(
            {
                "requires_declaration": True,
                "pr_body_patch": {"text": "Failure-Class: none\n"},
                "advisory_candidates": [
                    {
                        "id": "FC-malformed-doc-read",
                        "violated_contract": "Stored documents must be validated at the read boundary.",
                    }
                ],
            }
        )
        self.assertIn("Failure-Class: none", output)
        self.assertIn("does not infer a class from paths or diffs", output)
        self.assertIn("scripts/failure-class explain FC-<slug> --format json", output)
        self.assertIn("FC-malformed-doc-read", output)

    def test_pr_body_file_env_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            body = temp / "body.md"
            body.write_text("## Product invariants affected\n\nnone\n", encoding="utf-8")
            env = {**os.environ, "OMI_PR_BODY_FILE": str(body)}
            # Empty diff vs itself: product-invariants should pass with any body.
            result = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/pr_preflight.py",
                    "--base",
                    "HEAD",
                    "--head",
                    "HEAD",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            # This test isolates metadata-file selection. Other manifest-selected
            # repository guardrails may legitimately fail as global state evolves;
            # requiring a zero exit here made the metadata contract time-dependent.
            self.assertIn(str(body.resolve()), result.stdout)
            self.assertNotIn("No PR metadata file is available", result.stdout)

    def test_repo_checks_routes_metadata_events_to_the_narrow_preflight(self) -> None:
        """Metadata-only PR updates must not restart the full hygiene suite."""
        workflow = (REPO_ROOT / ".github/workflows/repo-checks.yml").read_text(encoding="utf-8")
        metadata_job = workflow.split("  metadata-preflight:\n", 1)[1].split("\n  changes:\n", 1)[0]
        changes_job = workflow.split("  changes:\n", 1)[1].split("\n  hygiene:\n", 1)[0]
        hygiene_job = workflow.split("  hygiene:\n", 1)[1].split("\n  formatting:\n", 1)[0]

        for event in ("edited", "labeled", "unlabeled"):
            self.assertIn(event, metadata_job)
            self.assertIn(event, changes_job)
            self.assertIn(event, hygiene_job)
        self.assertIn("scripts/pr-preflight", metadata_job)
        # Static tripwire only: confirms the workflow text wires --base to the
        # live ref rather than the stale event-payload SHA. It does not exercise
        # changed_files() itself — see
        # test_stale_event_payload_base_widens_diff_scope_past_the_live_base for
        # the behavioral regression backing FC-stale-event-payload-diff-base.
        self.assertNotIn("github.event.pull_request.base.sha", metadata_job)
        self.assertIn('--base "origin/${{ github.base_ref }}"', metadata_job)
        self.assertIn("astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84", metadata_job)
        self.assertLess(metadata_job.index("Set up uv"), metadata_job.index("Run current PR metadata preflight"))
        self.assertIn("github.event_name != 'pull_request'", changes_job)
        self.assertIn("github.event_name != 'pull_request'", hygiene_job)

        # The manifest can select the Firestore admission proof for either PR
        # preflight path. Java must be present before the selected check runs.
        for job, gate in (
            (metadata_job, "Run current PR metadata preflight"),
            (hygiene_job, "Run shared PR contract preflight"),
        ):
            self.assertIn("actions/setup-java@v5", job)
            self.assertIn("java-version: '21'", job)
            self.assertLess(job.index("Set up Java for manifest-selected Firestore checks"), job.index(gate))

    def test_issue_sync_action_is_pinned(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/main.yml").read_text(encoding="utf-8")

        self.assertIn("paritytech/github-issue-sync@34a24348bf2f2a73924e322f43d6132e0c276b5f", workflow)
        self.assertNotIn("paritytech/github-issue-sync@master", workflow)

    def test_standard_actions_no_longer_use_node_20_majors(self) -> None:
        deprecated_references = (
            "actions/checkout@v3",
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v3",
            "actions/setup-node@v4",
            "actions/cache@v4",
            "actions/cache/restore@v4",
            "actions/cache/save@v4",
            "actions/upload-artifact@v4",
            "actions/download-artifact@v4",
            "actions/github-script@v6",
            "actions/github-script@v7",
            "actions/create-github-app-token@v1",
            "actions/configure-pages@v3",
            "actions/deploy-pages@v4",
            "actions/upload-pages-artifact@v3",
            "actions/setup-dotnet@v4",
            "google-github-actions/auth@v2",
            "google-github-actions/setup-gcloud@v2",
            "google-github-actions/get-gke-credentials@v2",
            "google-github-actions/deploy-cloudrun@v2",
            "docker/build-push-action@v6",
            "docker/setup-buildx-action@v3",
            "azure/setup-helm@v3",
            "gradle/actions/setup-gradle@v4",
            "pnpm/action-setup@v4",
            "opentofu/setup-opentofu@v1",
            "peter-evans/create-pull-request@v5",
            "astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78",
        )
        workflow_files = (*REPO_ROOT.glob(".github/workflows/*.yml"), *REPO_ROOT.glob(".github/actions/*/action.yml"))

        for path in workflow_files:
            text = path.read_text(encoding="utf-8")
            for reference in deprecated_references:
                self.assertNotIn(reference, text, f"{path}: update {reference} to a non-Node-20 action")


class SingleFlightTests(unittest.TestCase):
    def run_runner(
        self,
        state_root: Path,
        command: list[str],
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        env = {**os.environ, "OMI_PREFLIGHT_STATE_DIR": str(state_root)}
        if extra_env:
            env.update(extra_env)
        return subprocess.Popen(
            [sys.executable, str(RUNNER), "--name", "test", "--", *command],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

    def wait_for_lock(self, state_root: Path) -> None:
        lock = state_root / "test" / "lock" / "owner.json"
        deadline = time.monotonic() + 5
        while not lock.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(lock.exists(), "runner did not acquire its lock")

    @unittest.skipUnless(os.name == "nt", "Windows-only")
    def test_process_liveness_check_does_not_send_windows_ctrl_c(self) -> None:
        with patch.object(os, "kill", side_effect=AssertionError("must not signal")):
            self.assertTrue(preflight_runner.process_exists(os.getpid()))
            self.assertFalse(preflight_runner.process_exists(0x7FFFFFFF))

    def test_pr_body_content_participates_in_singleflight_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text("first", encoding="utf-8")
            with patch.dict(os.environ, {"OMI_PR_BODY_FILE": str(body)}):
                first = preflight_runner.fingerprint(REPO_ROOT, ["check"], "")
                body.write_text("second", encoding="utf-8")
                second = preflight_runner.fingerprint(REPO_ROOT, ["check"], "")
        self.assertNotEqual(first, second)

    def test_identical_processes_join_and_execute_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            counter = temp / "counter"
            hold = temp / "hold"
            hold.write_text("1", encoding="utf-8")
            script = (
                "from pathlib import Path\n"
                "import time\n"
                f"p = Path({str(counter)!r})\n"
                f"hold = Path({str(hold)!r})\n"
                "p.write_text(p.read_text() + 'x' if p.exists() else 'x')\n"
                "print('==> focused-tests', flush=True)\n"
                "deadline = time.monotonic() + 10\n"
                "while hold.exists() and time.monotonic() < deadline:\n"
                "    time.sleep(0.02)\n"
            )
            command = [sys.executable, "-c", script]
            first = self.run_runner(temp, command)
            assert first.stdin is not None
            first.stdin.write("same\n")
            first.stdin.close()
            self.wait_for_lock(temp)
            second = self.run_runner(temp, command)
            assert second.stdin is not None
            second.stdin.write("same\n")
            second.stdin.close()
            time.sleep(0.3)
            hold.unlink(missing_ok=True)
            first_output = first.stdout.read() if first.stdout else ""
            second_output = second.stdout.read() if second.stdout else ""
            self.assertEqual(first.wait(), 0, first_output)
            self.assertEqual(second.wait(), 0, second_output)
            if first.stdout:
                first.stdout.close()
            if second.stdout:
                second.stdout.close()
            self.assertEqual(counter.read_text(), "x")
            self.assertIn("Joining identical preflight", second_output)
            status = json.loads((temp / "test" / "status.json").read_text())
            self.assertEqual(status["phase"], "passed")
            self.assertTrue((temp / "test" / "preflight.log").exists())

    def _hold_command(self, hold: Path) -> list[str]:
        # A short sleep races the second runner on a loaded host: the first
        # child can exit before the overlap is observed, so the second starts
        # cleanly and the test expects 75 but gets 0. Hold a file instead.
        script = (
            "from pathlib import Path\n"
            "import time\n"
            f"hold = Path({str(hold)!r})\n"
            "print('==> slow', flush=True)\n"
            "deadline = time.monotonic() + 10\n"
            "while hold.exists() and time.monotonic() < deadline:\n"
            "    time.sleep(0.02)\n"
        )
        return [sys.executable, "-c", script]

    def test_different_input_is_rejected_while_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            hold = temp / "hold"
            hold.write_text("1", encoding="utf-8")
            command = self._hold_command(hold)
            first = self.run_runner(temp, command)
            assert first.stdin is not None
            first.stdin.write("first\n")
            first.stdin.close()
            self.wait_for_lock(temp)
            second = self.run_runner(temp, command)
            assert second.stdin is not None
            second.stdin.write("second\n")
            second.stdin.close()
            second_output = second.stdout.read() if second.stdout else ""
            self.assertEqual(second.wait(), 75, second_output)
            if second.stdout:
                second.stdout.close()
            self.assertIn("already running different input", second_output)
            hold.unlink(missing_ok=True)
            if first.stdout:
                first.stdout.read()
                first.stdout.close()
            self.assertEqual(first.wait(), 0)

    def test_failure_reports_exit_status_and_last_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            command = [sys.executable, "-c", "print('==> deliberate-failure', flush=True); raise SystemExit(17)"]
            process = self.run_runner(temp, command)
            assert process.stdin is not None
            process.stdin.close()
            output = process.stdout.read() if process.stdout else ""
            self.assertEqual(process.wait(), 17, output)
            if process.stdout:
                process.stdout.close()
            self.assertIn("child exited with status 17", output)
            self.assertIn("phase=deliberate-failure", output)
            result = json.loads((temp / "test" / "result.json").read_text())
            self.assertEqual(result["exit_code"], 17)
            self.assertEqual(result["last_phase"], "deliberate-failure")
            self.assertIsNone(result["received_signal"])

    def test_different_pre_push_environment_is_not_joined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            hold = temp / "hold"
            hold.write_text("1", encoding="utf-8")
            command = self._hold_command(hold)
            first = self.run_runner(temp, command, extra_env={"PRE_PUSH_SKIP_ACTIONLINT": "1"})
            assert first.stdin is not None
            first.stdin.close()
            self.wait_for_lock(temp)
            second = self.run_runner(temp, command, extra_env={"PRE_PUSH_SKIP_ACTIONLINT": "0"})
            assert second.stdin is not None
            second.stdin.close()
            second_output = second.stdout.read() if second.stdout else ""
            self.assertEqual(second.wait(), 75, second_output)
            self.assertIn("already running different input", second_output)
            if second.stdout:
                second.stdout.close()
            hold.unlink(missing_ok=True)
            if first.stdout:
                first.stdout.read()
                first.stdout.close()
            self.assertEqual(first.wait(), 0)


class SignalPortabilityTests(unittest.TestCase):
    """The single-flight wrapper must start on hosts without POSIX signal APIs.

    Windows Python defines neither ``signal.SIGHUP`` nor ``os.killpg``. Building the
    handler map from a hard-coded tuple containing SIGHUP raised AttributeError inside
    ``run_owned()``, so every ``git push`` failed before the pre-push checks began.
    These exercise the selection/forwarding seams directly — no real signal is sent.
    """

    def test_forwardable_signals_omits_signals_absent_on_host(self) -> None:
        had_sighup = hasattr(signal, "SIGHUP")
        original = getattr(signal, "SIGHUP", None)
        try:
            if had_sighup:
                delattr(signal, "SIGHUP")  # simulate Windows
            selected = preflight_runner.forwardable_signals()
        finally:
            if had_sighup:
                signal.SIGHUP = original
        self.assertIn(signal.SIGINT, selected)
        self.assertIn(signal.SIGTERM, selected)
        self.assertTrue(all(signum is not None for signum in selected))

    @unittest.skipUnless(hasattr(signal, "SIGHUP"), "POSIX-only")
    def test_forwardable_signals_includes_sighup_on_posix(self) -> None:
        self.assertIn(signal.SIGHUP, preflight_runner.forwardable_signals())

    @unittest.skipUnless(hasattr(os, "killpg"), "POSIX-only")
    def test_forwards_to_process_group_when_available(self) -> None:
        child = Mock(pid=4321)
        with patch.object(os, "killpg") as killpg:
            preflight_runner.signal_child(child, signal.SIGTERM)
        killpg.assert_called_once_with(4321, signal.SIGTERM)
        child.send_signal.assert_not_called()

    def test_forwards_via_send_signal_when_process_groups_unavailable(self) -> None:
        child = Mock(pid=4321)
        had_killpg = hasattr(os, "killpg")
        original = getattr(os, "killpg", None)
        try:
            if had_killpg:
                delattr(os, "killpg")  # simulate Windows
            preflight_runner.signal_child(child, signal.SIGTERM)
        finally:
            if had_killpg:
                os.killpg = original
        child.send_signal.assert_called_once_with(signal.SIGTERM)

    def test_windows_job_terminates_child_process_tree(self) -> None:
        child = Mock(pid=4321)
        windows_job = Mock()
        windows_job.terminate.return_value = True
        preflight_runner.signal_child(child, signal.SIGINT, windows_job=windows_job)
        windows_job.terminate.assert_called_once_with()
        child.send_signal.assert_not_called()

    def test_windows_unsupported_signal_does_not_abort_runner(self) -> None:
        child = Mock(pid=4321)
        child.send_signal.side_effect = ValueError("unsupported")
        with patch.object(os, "killpg", None, create=True):
            preflight_runner.signal_child(child, signal.SIGINT)

    def test_forwarding_swallows_dead_child(self) -> None:
        child = Mock(pid=4321)
        with patch.object(os, "killpg", side_effect=ProcessLookupError, create=True):
            preflight_runner.signal_child(child, signal.SIGTERM)  # must not raise


if __name__ == "__main__":
    unittest.main()
