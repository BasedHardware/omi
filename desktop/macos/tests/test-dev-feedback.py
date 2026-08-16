#!/usr/bin/env python3
"""Hermetic behavior checks for the explicit desktop fast-feedback loop."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

MACOS_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = MACOS_DIR / "scripts" / "dev-feedback.py"
SPEC = importlib.util.spec_from_file_location("dev_feedback", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to import {SCRIPT_PATH}")
dev_feedback = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dev_feedback
SPEC.loader.exec_module(dev_feedback)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.delays: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.now += seconds


class DevFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.desktop_root = Path(self.temporary_directory.name) / "desktop" / "macos"
        (self.desktop_root / "Desktop" / "Sources").mkdir(parents=True)
        (self.desktop_root / "Desktop" / "Tests").mkdir()
        (self.desktop_root / "Desktop" / "Package.swift").write_text("// package\n")
        backend_root = self.desktop_root.parent.parent / "backend"
        (backend_root / "routers").mkdir(parents=True)
        (backend_root / "database").mkdir()
        (backend_root / "utils").mkdir()
        (backend_root / "desktop_backend.py").write_text("app = None\n")
        (backend_root / "requirements.txt").write_text("\n")
        (backend_root / "pylock.toml").write_text("\n")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_constructs_the_required_focused_commands(self) -> None:
        swift = dev_feedback.test_command_for(self.desktop_root, "swift", "ChatTests/testSendsMessage")
        python = dev_feedback.test_command_for(self.desktop_root, "python", "tests/unit/test_desktop_chat.py")

        self.assertEqual(
            swift.command,
            (
                "xcrun",
                "swift",
                "test",
                "--package-path",
                "Desktop",
                "--filter",
                "ChatTests/testSendsMessage",
            ),
        )
        self.assertEqual(swift.cwd, self.desktop_root.resolve())
        self.assertEqual(python.command, (".venv/bin/python", "-m", "pytest", "tests/unit/test_desktop_chat.py"))
        self.assertEqual(python.cwd, self.desktop_root.resolve().parent.parent / "backend")

    def test_watch_roots_are_limited_to_the_selected_component_inputs(self) -> None:
        resolved_root = self.desktop_root.resolve()
        swift_roots = {
            path.relative_to(resolved_root).as_posix() for path in dev_feedback.watch_paths(self.desktop_root, "swift")
        }
        python_roots = {
            path.relative_to(resolved_root).as_posix() for path in dev_feedback.watch_paths(self.desktop_root, "python")
        }

        self.assertEqual(swift_roots, set(dev_feedback.SWIFT_WATCH_INPUTS))
        self.assertEqual(python_roots, set(dev_feedback.PYTHON_WATCH_INPUTS))
        self.assertNotIn("Desktop/.build", swift_roots)
        self.assertNotIn("../../backend/.venv", python_roots)
        self.assertNotIn("run.sh", swift_roots | python_roots)
        self.assertIn("../../backend/routers", python_roots)
        self.assertIn("../../backend/database", python_roots)

    def test_watch_continues_after_a_failed_test_and_coalesces_saves(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "python", "tests/unit/test_desktop_chat.py")
        calls: list[tuple[tuple[str, ...], Path]] = []
        output: list[str] = []
        exit_codes = iter((1, 0))
        snapshots = iter(("before-save", "first-save", "second-save", "second-save", "second-save"))
        clock = FakeClock()

        def runner(command_line: tuple[str, ...], *, cwd: Path) -> SimpleNamespace:
            calls.append((command_line, cwd))
            return SimpleNamespace(returncode=next(exit_codes), stdout="Executed 2 tests, with 0 failures\n")

        def snapshotter(_paths: object) -> str:
            return next(snapshots)

        result = dev_feedback.run_watch(
            command,
            self.desktop_root,
            poll_interval=0.1,
            debounce=0.2,
            runner=runner,
            snapshotter=snapshotter,
            sleep=clock.sleep,
            clock=clock,
            emit=output.append,
            should_stop=lambda: len(calls) >= 2,
        )

        self.assertEqual(result, 0)
        self.assertEqual(calls, [(command.command, command.cwd), (command.command, command.cwd)])
        self.assertTrue(any("FAIL (exit 1)" in line for line in output))
        self.assertTrue(any("Iteration 2: PASS" in line for line in output))
        self.assertEqual(sum("Change detected" in line for line in output), 1)
        self.assertEqual(clock.delays, [0.1, 0.1, 0.1, 0.1])

    def test_a_filter_matching_no_tests_fails_despite_a_zero_exit(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "swift", "ThisClassDoesNotExistAnywhere_XYZ")
        output: list[str] = []

        def runner(_command_line: tuple[str, ...], *, cwd: Path) -> SimpleNamespace:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "\t Executed 0 tests, with 0 failures (0 unexpected) in 0.000 seconds\n"
                    "✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.\n"
                ),
            )

        status = dev_feedback.emit_iteration_result(command, 1, runner=runner, clock=FakeClock(), emit=output.append)

        self.assertEqual(status, 1)
        self.assertTrue(any("matched 0 tests" in line for line in output))
        self.assertFalse(any("PASS" in line for line in output))

    def test_an_executed_test_still_passes_when_swift_testing_reports_no_suites(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "swift", "TasksStoreDeletedLaneRetirementTests")
        output: list[str] = []

        def runner(_command_line: tuple[str, ...], *, cwd: Path) -> SimpleNamespace:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "\t Executed 2 tests, with 0 failures (0 unexpected) in 0.046 seconds\n"
                    "✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.\n"
                ),
            )

        status = dev_feedback.emit_iteration_result(command, 1, runner=runner, clock=FakeClock(), emit=output.append)

        self.assertEqual(status, 0)
        self.assertTrue(any("PASS" in line for line in output))

    def test_a_swift_run_that_reports_no_test_count_fails_instead_of_passing(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "swift", "WidgetTests")
        output: list[str] = []

        def runner(_command_line: tuple[str, ...], *, cwd: Path) -> SimpleNamespace:
            return SimpleNamespace(returncode=0, stdout="Build complete!\n")

        status = dev_feedback.emit_iteration_result(command, 1, runner=runner, clock=FakeClock(), emit=output.append)

        self.assertEqual(status, 1)
        self.assertTrue(any("no executed-test count reported" in line for line in output))

    def test_a_pytest_run_passes_on_its_exit_code_without_a_swift_test_count(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "python", "tests/unit/test_desktop_chat.py")
        output: list[str] = []

        def runner(_command_line: tuple[str, ...], *, cwd: Path) -> SimpleNamespace:
            return SimpleNamespace(returncode=0, stdout="1 passed in 0.02s\n")

        status = dev_feedback.emit_iteration_result(command, 1, runner=runner, clock=FakeClock(), emit=output.append)

        self.assertEqual(status, 0)
        self.assertTrue(any("PASS" in line for line in output))

    def test_streaming_runner_echoes_and_captures_the_test_output(self) -> None:
        stream = io.StringIO()

        result = dev_feedback.run_streaming(
            (sys.executable, "-c", "print('Executed 0 tests, with 0 failures'); raise SystemExit(0)"),
            cwd=self.desktop_root,
            stream=stream,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Executed 0 tests", stream.getvalue())
        self.assertEqual(dev_feedback.executed_test_count(result.stdout), 0)

    def test_rejects_an_empty_filter(self) -> None:
        with self.assertRaisesRegex(ValueError, "test filter must not be empty"):
            dev_feedback.test_command_for(self.desktop_root, "swift", "   ")

    def test_cli_rejects_an_empty_filter_before_running_any_test(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            dev_feedback.main(["--once", "--root", str(self.desktop_root), "swift", "   "])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("test filter must not be empty", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
