#!/usr/bin/env python3
"""Run one explicitly selected desktop regression test, once or after saves.

This deliberately complements rather than replaces the component's full test
suite. Pick the test filter yourself so a fast inner loop never guesses which
coverage is relevant to a change.
"""

from __future__ import annotations

import argparse
import math
import os
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DESKTOP_ROOT = SCRIPT_DIR.parent

SWIFT_WATCH_INPUTS = (
    "Desktop/Package.swift",
    "Desktop/Package.resolved",
    "Desktop/Sources",
    "Desktop/Tests",
    "Desktop/ObjCExceptionCatcher",
    "Desktop/CWebP",
)
RUST_WATCH_INPUTS = (
    "Backend-Rust/Cargo.toml",
    "Backend-Rust/Cargo.lock",
    "Backend-Rust/rust-toolchain.toml",
    "Backend-Rust/build.rs",
    "Backend-Rust/.cargo",
    "Backend-Rust/src",
    "Backend-Rust/fixtures",
    "Backend-Rust/templates",
    "Backend-Rust/tests",
)


@dataclass(frozen=True)
class TestCommand:
    """The focused command to run and the directory it must run from."""

    language: str
    test_filter: str
    command: tuple[str, ...]
    cwd: Path


Runner = Callable[..., subprocess.CompletedProcess[object]]
Snapshotter = Callable[[Iterable[Path]], object]
Emitter = Callable[[str], None]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]
StopPredicate = Callable[[], bool]


def nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from error
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError(f"expected a finite number, got {value!r}")
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"expected a non-negative number, got {value!r}")
    return parsed


def positive_float(value: str) -> float:
    parsed = nonnegative_float(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("expected a number greater than zero")
    return parsed


def normalized_filter(test_filter: str) -> str:
    normalized = test_filter.strip()
    if not normalized:
        raise ValueError("test filter must not be empty")
    return normalized


def test_command_for(desktop_root: Path, language: str, test_filter: str) -> TestCommand:
    """Construct the exact focused command without running it."""

    desktop_root = desktop_root.resolve()
    selected_filter = normalized_filter(test_filter)

    if language == "swift":
        return TestCommand(
            language=language,
            test_filter=selected_filter,
            command=(
                "xcrun",
                "swift",
                "test",
                "--package-path",
                "Desktop",
                "--filter",
                selected_filter,
            ),
            cwd=desktop_root,
        )
    if language == "rust":
        return TestCommand(
            language=language,
            test_filter=selected_filter,
            command=("cargo", "test", "--locked", selected_filter),
            cwd=desktop_root / "Backend-Rust",
        )
    raise ValueError(f"unsupported test language: {language!r}")


def watch_paths(desktop_root: Path, language: str) -> tuple[Path, ...]:
    """Return only source, test, and package inputs for the selected language."""

    relative_inputs = SWIFT_WATCH_INPUTS if language == "swift" else RUST_WATCH_INPUTS
    if language not in {"swift", "rust"}:
        raise ValueError(f"unsupported test language: {language!r}")
    resolved_root = desktop_root.resolve()
    return tuple(resolved_root / relative_path for relative_path in relative_inputs)


def _entry_fingerprint(path: Path) -> tuple[str, str, int, int]:
    try:
        metadata = path.lstat()
    except OSError:
        return (str(path), "missing", 0, 0)

    if stat.S_ISDIR(metadata.st_mode):
        kind = "directory"
    elif stat.S_ISREG(metadata.st_mode):
        kind = "file"
    elif stat.S_ISLNK(metadata.st_mode):
        kind = "symlink"
    else:
        kind = "other"
    return (str(path), kind, metadata.st_mtime_ns, metadata.st_size)


def _path_fingerprint(path: Path) -> list[tuple[str, str, int, int]]:
    entry = _entry_fingerprint(path)
    if entry[1] != "directory":
        return [entry]

    entries = [entry]
    for current_root, directory_names, file_names in os.walk(path, topdown=True, followlinks=False):
        directory_names.sort()
        file_names.sort()
        current = Path(current_root)
        for name in directory_names:
            entries.append(_entry_fingerprint(current / name))
        for name in file_names:
            entries.append(_entry_fingerprint(current / name))
    return entries


def snapshot_paths(paths: Iterable[Path]) -> tuple[tuple[str, str, int, int], ...]:
    """Fingerprint files recursively without watching build artifacts or the repo."""

    entries: list[tuple[str, str, int, int]] = []
    for path in paths:
        entries.extend(_path_fingerprint(path))
    return tuple(entries)


def emit_iteration_result(
    test_command: TestCommand,
    iteration: int,
    *,
    runner: Runner = subprocess.run,
    clock: Clock = time.monotonic,
    emit: Emitter = print,
) -> int:
    """Run a focused test and report its unambiguous timing outcome."""

    emit(f"Iteration {iteration}: running {test_command.language} filter {test_command.test_filter!r}")
    started_at = clock()
    try:
        result = runner(test_command.command, cwd=test_command.cwd, check=False)
    except OSError as error:
        elapsed = clock() - started_at
        emit(f"Iteration {iteration}: ERROR ({error}) in {elapsed:.2f}s")
        return 127

    elapsed = clock() - started_at
    if result.returncode == 0:
        emit(f"Iteration {iteration}: PASS in {elapsed:.2f}s")
    else:
        emit(f"Iteration {iteration}: FAIL (exit {result.returncode}) in {elapsed:.2f}s")
    return result.returncode


def wait_for_change(
    previous_snapshot: object,
    paths: Iterable[Path],
    *,
    poll_interval: float,
    snapshotter: Snapshotter,
    sleep: Sleeper,
) -> object:
    while True:
        sleep(poll_interval)
        current_snapshot = snapshotter(paths)
        if current_snapshot != previous_snapshot:
            return current_snapshot


def wait_for_quiet(
    first_changed_snapshot: object,
    paths: Iterable[Path],
    *,
    poll_interval: float,
    debounce: float,
    snapshotter: Snapshotter,
    sleep: Sleeper,
    clock: Clock,
) -> object:
    """Coalesce editor temp-file writes until inputs have been quiet long enough."""

    if debounce == 0:
        return first_changed_snapshot

    latest_snapshot = first_changed_snapshot
    last_change_at = clock()
    while True:
        sleep(poll_interval)
        current_snapshot = snapshotter(paths)
        now = clock()
        if current_snapshot != latest_snapshot:
            latest_snapshot = current_snapshot
            last_change_at = now
            continue
        if now - last_change_at >= debounce:
            return latest_snapshot


def run_watch(
    test_command: TestCommand,
    desktop_root: Path,
    *,
    poll_interval: float,
    debounce: float,
    runner: Runner = subprocess.run,
    snapshotter: Snapshotter = snapshot_paths,
    sleep: Sleeper = time.sleep,
    clock: Clock = time.monotonic,
    emit: Emitter = print,
    should_stop: StopPredicate = lambda: False,
) -> int:
    """Run now, then rerun after coherent saves. Failures never end the loop."""

    desktop_root = desktop_root.resolve()
    paths = watch_paths(desktop_root, test_command.language)
    emit(f"Watching {test_command.language} test inputs only:")
    for path in paths:
        emit(f"  {path.relative_to(desktop_root)}")

    snapshot = snapshotter(paths)
    iteration = 1
    last_status = emit_iteration_result(test_command, iteration, runner=runner, clock=clock, emit=emit)

    while not should_stop():
        changed_snapshot = wait_for_change(
            snapshot,
            paths,
            poll_interval=poll_interval,
            snapshotter=snapshotter,
            sleep=sleep,
        )
        emit(f"Change detected; waiting {debounce:.2f}s for writes to settle.")
        snapshot = wait_for_quiet(
            changed_snapshot,
            paths,
            poll_interval=poll_interval,
            debounce=debounce,
            snapshotter=snapshotter,
            sleep=sleep,
            clock=clock,
        )
        iteration += 1
        last_status = emit_iteration_result(test_command, iteration, runner=runner, clock=clock, emit=emit)

    return last_status


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Run one explicit Swift or Rust desktop regression test with fast feedback.",
        epilog=(
            "Examples:\n"
            "  python3 scripts/dev-feedback.py --once swift 'ChatTests/testSendsMessage'\n"
            "  python3 scripts/dev-feedback.py --watch swift 'ChatTests/testSendsMessage'\n"
            "  python3 scripts/dev-feedback.py --watch rust 'handles_timeout'\n\n"
            "This is an opt-in inner loop. Run the existing full component suite before a PR."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = argument_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run the selected test once")
    mode.add_argument("--watch", action="store_true", help="run now and rerun after relevant saves")
    argument_parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_DESKTOP_ROOT,
        help="desktop/macos directory (defaults to this script's parent)",
    )
    argument_parser.add_argument(
        "--poll-interval",
        type=positive_float,
        default=0.10,
        help="seconds between input scans while watching (default: 0.10)",
    )
    argument_parser.add_argument(
        "--debounce",
        type=nonnegative_float,
        default=0.25,
        help="quiet time before rerunning after a save (default: 0.25)",
    )
    argument_parser.add_argument("language", choices=("swift", "rust"), help="focused test runner")
    argument_parser.add_argument("test_filter", metavar="FILTER", help="non-empty XCTest or cargo test filter")
    return argument_parser


def validate_layout(desktop_root: Path, language: str) -> None:
    expected_file = "Desktop/Package.swift" if language == "swift" else "Backend-Rust/Cargo.toml"
    if not (desktop_root / expected_file).is_file():
        raise ValueError(f"{expected_file} was not found under desktop root {desktop_root}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    argument_parser = parser()
    arguments = argument_parser.parse_args(argv)
    desktop_root = arguments.root.expanduser().resolve()

    try:
        validate_layout(desktop_root, arguments.language)
        test_command = test_command_for(desktop_root, arguments.language, arguments.test_filter)
    except ValueError as error:
        argument_parser.error(str(error))

    if arguments.once:
        return emit_iteration_result(test_command, 1)

    try:
        return run_watch(
            test_command,
            desktop_root,
            poll_interval=arguments.poll_interval,
            debounce=arguments.debounce,
        )
    except KeyboardInterrupt:
        print("Watch stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
