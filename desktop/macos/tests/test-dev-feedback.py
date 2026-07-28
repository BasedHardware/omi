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
        (self.desktop_root / "Backend-Rust" / "src").mkdir(parents=True)
        (self.desktop_root / "Backend-Rust" / "tests").mkdir()
        (self.desktop_root / "Backend-Rust" / "Cargo.toml").write_text("[package]\n")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_constructs_the_required_focused_commands(self) -> None:
        swift = dev_feedback.test_command_for(self.desktop_root, "swift", "ChatTests/testSendsMessage")
        rust = dev_feedback.test_command_for(self.desktop_root, "rust", "handles_timeout")

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
        self.assertEqual(rust.command, ("cargo", "test", "--locked", "handles_timeout"))
        self.assertEqual(rust.cwd, self.desktop_root.resolve() / "Backend-Rust")

    def test_watch_roots_are_limited_to_the_selected_component_inputs(self) -> None:
        resolved_root = self.desktop_root.resolve()
        swift_roots = {
            path.relative_to(resolved_root).as_posix() for path in dev_feedback.watch_paths(self.desktop_root, "swift")
        }
        rust_roots = {
            path.relative_to(resolved_root).as_posix() for path in dev_feedback.watch_paths(self.desktop_root, "rust")
        }

        self.assertEqual(swift_roots, set(dev_feedback.SWIFT_WATCH_INPUTS))
        self.assertEqual(rust_roots, set(dev_feedback.RUST_WATCH_INPUTS))
        self.assertNotIn("Desktop/.build", swift_roots)
        self.assertNotIn("Backend-Rust/target", rust_roots)
        self.assertNotIn("run.sh", swift_roots | rust_roots)
        self.assertIn("Backend-Rust/fixtures", rust_roots)
        self.assertIn("Backend-Rust/templates", rust_roots)

    def test_watch_continues_after_a_failed_test_and_coalesces_saves(self) -> None:
        command = dev_feedback.test_command_for(self.desktop_root, "rust", "handles_timeout")
        calls: list[tuple[tuple[str, ...], Path, bool]] = []
        output: list[str] = []
        exit_codes = iter((1, 0))
        snapshots = iter(("before-save", "first-save", "second-save", "second-save", "second-save"))
        clock = FakeClock()

        def runner(command_line: tuple[str, ...], *, cwd: Path, check: bool) -> SimpleNamespace:
            calls.append((command_line, cwd, check))
            return SimpleNamespace(returncode=next(exit_codes))

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
        self.assertEqual(calls, [(command.command, command.cwd, False), (command.command, command.cwd, False)])
        self.assertTrue(any("FAIL (exit 1)" in line for line in output))
        self.assertTrue(any("Iteration 2: PASS" in line for line in output))
        self.assertEqual(sum("Change detected" in line for line in output), 1)
        self.assertEqual(clock.delays, [0.1, 0.1, 0.1, 0.1])

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
