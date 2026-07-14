#!/usr/bin/env python3
"""Regression tests for PR metadata, check selection, and single-flight execution."""

from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

import preflight_runner
from pr_metadata import load_from_api
from pr_preflight import select_checks

SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER = SCRIPT_DIR / "preflight_runner.py"
REPO_ROOT = SCRIPT_DIR.parents[1]
PRE_PUSH_SINGLEFLIGHT = REPO_ROOT / "scripts" / "pre-push-singleflight"
PRE_PUSH = REPO_ROOT / "scripts" / "pre-push"


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


class SelectionTests(unittest.TestCase):
    def test_pre_push_wrapper_reuses_current_bash_interpreter(self) -> None:
        wrapper = PRE_PUSH_SINGLEFLIGHT.read_text(encoding="utf-8")
        self.assertIn(' -- "$BASH" scripts/pre-push "$@"', wrapper)

    def test_pre_push_accepts_and_propagates_windows_backend_python(self) -> None:
        pre_push = PRE_PUSH.read_text(encoding="utf-8")
        setup_prefix = pre_push[: pre_push.index("require_backend_python()")]

        self.assertIn('BACKEND_PYTHON="${BACKEND_PYTHON:-}"', setup_prefix)
        self.assertIn('"$PWD/backend/.venv/bin/python"', setup_prefix)
        self.assertIn('"$PWD/backend/.venv/Scripts/python.exe"', setup_prefix)
        self.assertIn('PYRIGHT_PYTHON="$BACKEND_PYTHON" bash scripts/typecheck.sh', pre_push)

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
            ]
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

    def test_suggest_flag_prints_paste_ready_invariants(self) -> None:
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


class SignalCompatibilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows-specific process probe")
    def test_windows_process_probe_finds_current_process(self) -> None:
        self.assertTrue(preflight_runner.windows_process_exists(os.getpid()))

    @unittest.skipUnless(os.name == "nt", "Windows-specific process probe")
    def test_windows_process_probe_rejects_exited_process(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(timeout=5)

        self.assertFalse(preflight_runner.windows_process_exists(child.pid))

    def test_process_exists_uses_windows_probe_without_os_kill(self) -> None:
        with (
            mock.patch.object(preflight_runner.os, "name", "nt"),
            mock.patch.object(preflight_runner, "windows_process_exists", return_value=True) as windows_probe,
            mock.patch.object(preflight_runner.os, "kill") as kill,
        ):
            self.assertTrue(preflight_runner.process_exists(4321))

        windows_probe.assert_called_once_with(4321)
        kill.assert_not_called()

    def test_supported_forward_signals_skip_unavailable_members(self) -> None:
        with mock.patch.object(preflight_runner.signal, "SIGHUP", None, create=True):
            self.assertEqual(
                preflight_runner.supported_forward_signals(),
                (signal.SIGINT, signal.SIGTERM),
            )

    def test_forward_signal_uses_child_api_without_killpg(self) -> None:
        child = mock.Mock(pid=4321)
        child.poll.return_value = None

        with mock.patch.object(preflight_runner.os, "killpg", None, create=True):
            preflight_runner.forward_signal_to_child(child, signal.SIGTERM)

        child.send_signal.assert_called_once_with(signal.SIGTERM)

    @unittest.skipUnless(os.name == "nt", "Windows-specific signal forwarding")
    def test_forward_signal_terminates_windows_child(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            preflight_runner.forward_signal_to_child(child, signal.SIGTERM)
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_forward_signal_keeps_posix_process_group_behavior(self) -> None:
        child = mock.Mock(pid=4321)
        child.poll.return_value = None
        killpg = mock.Mock()

        with mock.patch.object(preflight_runner.os, "killpg", killpg, create=True):
            preflight_runner.forward_signal_to_child(child, signal.SIGTERM)

        killpg.assert_called_once_with(4321, signal.SIGTERM)
        child.send_signal.assert_not_called()


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


if __name__ == "__main__":
    unittest.main()
