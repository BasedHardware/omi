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
from pr_metadata import TransientPRMetadataError, load_from_api, load_from_event_file
from pr_preflight import changed_files, format_failure_class_suggest, resolve_pr_metadata, select_checks

SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER = SCRIPT_DIR / "preflight_runner.py"
REPO_ROOT = SCRIPT_DIR.parents[1]


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class MetadataTests(unittest.TestCase):
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
            urllib.error.HTTPError("url", 502, "bad gateway", None, None),  # type: ignore[arg-type]
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
            raise urllib.error.HTTPError("url", 404, "not found", None, None)  # type: ignore[arg-type]

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
            with patch(
                "pr_preflight.load_from_api", side_effect=TransientPRMetadataError("GitHub API unavailable")
            ), redirect_stderr(warnings):
                metadata = resolve_pr_metadata(REPO_ROOT, None, "BasedHardware/omi", 9847, event_path)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.body, "current")
        self.assertIn("using the PR snapshot", warnings.getvalue())

    def test_pr_metadata_does_not_use_event_payload_after_permanent_api_failure(self) -> None:
        with patch("pr_preflight.load_from_api", side_effect=RuntimeError("GitHub API returned HTTP 403")):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                resolve_pr_metadata(REPO_ROOT, None, "BasedHardware/omi", 9847, Path("event.json"))


class SelectionTests(unittest.TestCase):
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

    def test_make_preflight_resolves_pr_metadata_before_running_checks(self) -> None:
        result = subprocess.run(
            ["make", "-n", "preflight"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "python3 .github/scripts/pr_preflight.py --lane local --base origin/main",
            result.stdout,
        )

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
                "architecture-guardrails",
                "product-invariants",
                "failure-class-protocol",
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
            )
            self.assertEqual(invariant.returncode, 1, invariant.stdout)
            self.assertIn("INV-AUTH-1", invariant.stdout)
            self.assertIn("INV-CHAT-1", invariant.stdout)
            self.assertIn("INV-AGENT-*", invariant.stdout)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn(str(body.resolve()), result.stdout)

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
        self.assertIn("github.event.pull_request.base.sha", metadata_job)
        self.assertIn("astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84", metadata_job)
        self.assertLess(metadata_job.index("Set up uv"), metadata_job.index("Run current PR metadata preflight"))
        self.assertIn("github.event_name != 'pull_request'", changes_job)
        self.assertIn("github.event_name != 'pull_request'", hygiene_job)

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
    ) -> subprocess.Popen[str]:
        env = {**os.environ, "OMI_PREFLIGHT_STATE_DIR": str(state_root)}
        return subprocess.Popen(
            [sys.executable, str(RUNNER), "--name", "test", "--", *command],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def wait_for_lock(self, state_root: Path) -> None:
        lock = state_root / "test" / "lock" / "owner.json"
        deadline = time.monotonic() + 5
        while not lock.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(lock.exists(), "runner did not acquire its lock")

    def test_identical_processes_join_and_execute_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            counter = temp / "counter"
            code = (
                "from pathlib import Path; import time; "
                f"p=Path({str(counter)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x'); "
                "print('==> focused-tests', flush=True); time.sleep(.5)"
            )
            command = [sys.executable, "-c", code]
            first = self.run_runner(temp, command)
            assert first.stdin is not None
            first.stdin.write("same\n")
            first.stdin.close()
            self.wait_for_lock(temp)
            second = self.run_runner(temp, command)
            assert second.stdin is not None
            second.stdin.write("same\n")
            second.stdin.close()
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

    def test_different_input_is_rejected_while_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            command = [sys.executable, "-c", "import time; print('==> slow', flush=True); time.sleep(.5)"]
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

    def test_forwarding_swallows_dead_child(self) -> None:
        child = Mock(pid=4321)
        with patch.object(os, "killpg", side_effect=ProcessLookupError):
            preflight_runner.signal_child(child, signal.SIGTERM)  # must not raise


if __name__ == "__main__":
    unittest.main()
