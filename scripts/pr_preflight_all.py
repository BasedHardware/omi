#!/usr/bin/env python3
"""Keep-going PR preflight: run every selected gate, then report every failure.

Selected by ``scripts/pr-preflight --all``, ``OMI_PREFLIGHT_ALL=1`` for direct
calls, or ``PRE_PUSH_PREFLIGHT_ALL=1`` for hook calls. The hook variable is
included in the pre-push single-flight fingerprint.
The default preflight stays fail-fast on purpose: the push is already blocked
by the first failing gate. Keep-going is opt-in because it runs selected gates
after failures. Each failed gate is reported with its name, first error line,
log path, and a repro command; gates that no longer fit the wall budget are
reported as skipped for time instead of silently passing.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))

from pr_preflight import (  # noqa: E402
    _resolve_repo_root,
    changed_files,
    configure_output_streams,
    current_branch,
    resolve_pr_metadata,
    run_git,
)
from run_checks import (  # noqa: E402
    MANIFEST_RELATIVE_PATH,
    Check,
    command_for_check,
    command_for_host,
    detect_platform,
    load_manifest,
    manifest_changed_check_ids,
    resolve_check_selections,
    trigger_matches,
    validate_manifest,
)

RATCHET_GATE_ID = "backend-ratchet-preflight"
# Runs the backend ratchet guard tests through backend/test.sh under background
# priority. Selected only when backend files change.
RATCHET_GATE_TRIGGERS = ("backend/**",)
RATCHET_CHECK = Check(
    id=RATCHET_GATE_ID,
    command=("make", "backend-ratchet-preflight"),
    triggers=RATCHET_GATE_TRIGGERS,
    lanes=("local", "ci"),
    reason="run every backend ratchet guard test (test_*ratchet*.py plus the reason-label enums) "
    "through backend/test.sh before pushing a backend change",
)

DEFAULT_BUDGET_SECONDS = 300.0
KEPT_RUN_DIRECTORIES = 5
_ERROR_LINE = re.compile(
    r"^\s*(?:FAIL(?:ED)?\b|ERROR\b|FATAL\b|::error\b|E\s|Traceback \(most recent call last\)|AssertionError\b)",
    re.IGNORECASE,
)


@dataclass
class GateResult:
    check: Check
    status: str  # "PASS", "FAIL", or "skipped-for-time"
    seconds: float
    first_error: str
    repro: str
    log_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Present when the wrapper selects this keep-going mode.")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--lane", choices=("local", "ci"), default="ci")
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument("--repository", help="GitHub repository as owner/name; requires --pr-number")
    parser.add_argument("--pr-number", type=int, help="Load current PR metadata through the GitHub API")
    parser.add_argument(
        "--event-payload-file",
        type=Path,
        help="Use the triggering pull_request event only after transient GitHub API metadata failures",
    )
    parser.add_argument("--head-branch", help="PR head branch, used for release-changelog policy")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Delegated to the shared preflight, which already reports all metadata errors in one pass.",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Delegated to the shared preflight; suggest output is unaffected by keep-going.",
    )
    parser.add_argument("--list", action="store_true", help="Print selected gates without running them")
    parser.add_argument("--root", type=Path)
    return parser.parse_args()


def _new_run_dir() -> Path:
    """Create the persistent run directory holding logs and repro inputs.

    The changed-files and PR-body files the gate commands consume are written
    here (not a vanishing temp dir) so the printed repro commands rerun as-is.
    """
    base = Path(os.getenv("OMI_PREFLIGHT_ALL_LOG_DIR", str(Path(tempfile.gettempdir()) / "omi-pr-preflight-all")))
    run_dir = base / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    if base.is_dir():
        # Lexicographic stamp order is chronological; keep the newest runs only.
        for stale in sorted(path for path in base.iterdir() if path.is_dir())[:-KEPT_RUN_DIRECTORIES]:
            shutil.rmtree(stale, ignore_errors=True)
    return run_dir


_SLOT_FD: int | None = None


def _acquire_local_slot(lane: str) -> int | None:
    """Hold one local admission slot for the whole keep-going run.

    Mirrors ``pr_preflight.run_local_checks``: same ``OMI_PREFLIGHT_LOCAL_SLOTS``
    and ``OMI_PREFLIGHT_LOCAL_WAIT`` knobs and the same slot directory, so every
    caller sharing that directory agrees on the slot count. Returns an exit
    code when admission fails, None when admitted (or admission is off).
    """
    global _SLOT_FD
    slots_env = os.getenv("OMI_PREFLIGHT_LOCAL_SLOTS")
    if lane != "local" or slots_env is None or os.getenv("GITHUB_ACTIONS") == "true":
        return None
    try:
        slots = int(slots_env)
        wait = float(os.getenv("OMI_PREFLIGHT_LOCAL_WAIT", "900"))
        if slots <= 0 or not math.isfinite(wait) or wait < 0:
            raise ValueError("slots must be positive and wait finite and nonnegative")
        import fcntl
    except (ImportError, ValueError) as exc:
        print(f"FAIL: OMI_PREFLIGHT_LOCAL_SLOTS/OMI_PREFLIGHT_LOCAL_WAIT admission failed: {exc}", file=sys.stderr)
        return 2
    directory = Path(os.getenv("OMI_PREFLIGHT_LOCAL_DIR", str(Path(tempfile.gettempdir()) / "omi-preflight-local")))
    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    while _SLOT_FD is None:
        for slot in range(slots):
            candidate = os.open(str(directory / str(slot)), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(candidate)
                continue
            except BaseException:
                os.close(candidate)
                raise
            os.ftruncate(candidate, 0)
            os.write(candidate, str(os.getpid()).encode("ascii"))
            _SLOT_FD = candidate
            break
        if _SLOT_FD is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                f"FAIL: OMI_PREFLIGHT_LOCAL_SLOTS={slots} busy in {directory}; "
                f"OMI_PREFLIGHT_LOCAL_WAIT={wait:g}s exhausted",
                file=sys.stderr,
            )
            return 75
        time.sleep(min(2, remaining))
    return None


def _release_local_slot() -> None:
    global _SLOT_FD
    if _SLOT_FD is not None:
        os.close(_SLOT_FD)
        _SLOT_FD = None


def _background_command(command: list[str]) -> list[str]:
    """Wrap a gate with the same background-priority knob run_local_checks uses."""
    if os.getenv("OMI_PREFLIGHT_BACKGROUND", "1").lower() not in ("1", "true"):
        return command
    if sys.platform == "darwin":
        if os.access("/usr/bin/taskpolicy", os.X_OK):
            return ["/usr/bin/taskpolicy", "-b", *command]
    else:
        nice = shutil.which("nice")
        if nice:
            return [nice, "-n", "19", *command]
    return command


def _run_gate(command: list[str], root: Path, log_path: Path, timeout: float) -> tuple[int, str, bool]:
    """Run one gate within its remaining wall budget; return exit, error line, timed out."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    first_error: str | None = None
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="backslashreplace") as log:
        try:
            process = subprocess.Popen(
                _background_command(command),
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except OSError as exc:
            message = f"FAIL: could not start gate command: {exc}"
            print(message, flush=True)
            log.write(message + "\n")
            return 127, message, False

        def stop_gate() -> None:
            nonlocal timed_out
            timed_out = True
            try:
                if os.name != "nt":
                    os.killpg(process.pid, 15)
                else:
                    process.terminate()
            except (ProcessLookupError, OSError):
                return

            # Give a cooperative runner time to flush, then ensure descendants
            # cannot outlive a gate that exceeded the wall budget.
            time.sleep(1)
            if process.poll() is None:
                try:
                    if os.name != "nt":
                        os.killpg(process.pid, 9)
                    else:
                        process.kill()
                except (ProcessLookupError, OSError):
                    pass

        timer = threading.Timer(timeout, stop_gate)
        timer.daemon = True
        timer.start()
        assert process.stdout is not None
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
                if first_error is None and _ERROR_LINE.match(line):
                    first_error = line.strip()
            returncode = process.wait()
        finally:
            timer.cancel()
    if returncode and first_error is None:
        first_error = next(
            (
                line.strip()
                for line in log_path.read_text(encoding="utf-8", errors="backslashreplace").splitlines()
                if line.strip()
            ),
            "",
        )
    if timed_out and first_error is None:
        first_error = f"time budget expired while running {shlex.join(command)}"
    return returncode, first_error or "", timed_out


def _select_gates(
    files: list[str], lane: str, root: Path, merge_base: str, head: str
) -> tuple[list[tuple[Check, tuple[str, ...]]], list[str]]:
    manifest = load_manifest(root / MANIFEST_RELATIVE_PATH)
    manifest_errors = validate_manifest(manifest, root)
    changed_ids = (
        manifest_changed_check_ids(root, merge_base, head, include_worktree=lane == "local")
        if MANIFEST_RELATIVE_PATH in files
        else None
    )
    selections = resolve_check_selections(
        manifest, files, lane, platform=detect_platform(), manifest_changed_ids=changed_ids
    )
    gates = [(selection.check, selection.matched_paths) for selection in selections]
    ratchet_paths = tuple(
        path for path in files if any(trigger_matches(pattern, path) for pattern in RATCHET_GATE_TRIGGERS)
    )
    if ratchet_paths:
        gates.append((RATCHET_CHECK, ratchet_paths))
    return gates, manifest_errors


def _summary(results: list[GateResult], run_dir: Path, budget: float) -> None:
    failed = [result for result in results if result.status == "FAIL"]
    skipped = [result for result in results if result.status == "skipped-for-time"]
    print()
    print(
        f"PR preflight --all summary: {len(results)} gate result(s), "
        f"{len(failed)} failed, {len(skipped)} skipped for time",
        flush=True,
    )
    print(f"Run inputs and logs: {run_dir}", flush=True)
    for result in failed:
        print(f"FAILED {result.check.id}", flush=True)
        print(f"  error: {result.first_error or '(no output captured)'}", flush=True)
        print(f"  log:   {result.log_path}", flush=True)
        print(f"  repro: {result.repro}", flush=True)
    if skipped:
        print(
            f"SKIPPED FOR TIME (wall budget {budget:g}s exhausted; "
            f"OMI_PREFLIGHT_ALL_BUDGET_SECONDS overrides): " + ", ".join(result.check.id for result in skipped),
            flush=True,
        )
        print("A skipped gate means this pass did not certify the whole selection; rerun with a larger budget.", flush=True)


def main() -> int:
    configure_output_streams()
    args = parse_args()
    if bool(args.repository) != bool(args.pr_number):
        print("FAIL: --repository and --pr-number must be supplied together", file=sys.stderr)
        return 2
    if args.suggest or args.metadata_only:
        # Both modes are already single-pass in the shared preflight:
        # --metadata-only reports every metadata error in one run.
        os.execv(
            sys.executable,
            [
                sys.executable,
                str(REPO_ROOT / ".github" / "scripts" / "pr_preflight.py"),
                *(arg for arg in sys.argv[1:] if arg != "--all"),
            ],
        )
    raw_budget = os.getenv("OMI_PREFLIGHT_ALL_BUDGET_SECONDS", str(DEFAULT_BUDGET_SECONDS))
    try:
        budget = float(raw_budget)
        if not math.isfinite(budget) or budget < 0:
            raise ValueError("budget must be finite and nonnegative")
    except ValueError:
        print(
            f"FAIL: OMI_PREFLIGHT_ALL_BUDGET_SECONDS must be a nonnegative number, got {raw_budget!r}", file=sys.stderr
        )
        return 2

    root = (args.root or _resolve_repo_root()).resolve()
    started = time.monotonic()
    try:
        merge_base = run_git(root, "merge-base", args.base, args.head)
        files = changed_files(root, args.base, args.head, include_worktree=args.lane == "local")
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: could not resolve preflight diff: {exc.stderr.strip()}", file=sys.stderr)
        return 1
    try:
        gates, manifest_errors = _select_gates(files, args.lane, root, merge_base, args.head)
    except (OSError, ValueError) as exc:
        gates, manifest_errors = [], [f"could not load checks manifest: {exc}"]

    print(
        f"PR preflight --all (keep-going): lane={args.lane} base={args.base} ({merge_base[:12]}) "
        f"head={args.head} files={len(files)}"
    )
    for check, _ in gates:
        print(f"  SELECTED {check.id}: {check.reason}")
    if args.list:
        if manifest_errors:
            for error in manifest_errors:
                print(f"FAIL: {error}", file=sys.stderr)
            return 1
        return 0

    run_dir = _new_run_dir()
    files_path = run_dir / "changed-files.txt"
    files_path.write_text("".join(f"{path}\n" for path in files), encoding="utf-8")
    try:
        metadata = resolve_pr_metadata(
            root, args.pr_body_file, args.repository, args.pr_number, args.event_payload_file
        )
    except RuntimeError as exc:
        metadata = None
        metadata_error = str(exc)
    else:
        metadata_error = ""
    head_branch = args.head_branch or os.getenv("GITHUB_HEAD_REF", "")
    if not head_branch:
        head_branch = current_branch(root)
    skip_changelog = head_branch.startswith("changelog/v") or os.getenv("PRE_PUSH_SKIP_DESKTOP_CHANGELOG") == "1"
    if metadata:
        print(f"PR metadata: {metadata.source}, updated_at={metadata.updated_at}")
    body_path = run_dir / "pr-body.txt"
    body_path.write_text(metadata.body if metadata else "", encoding="utf-8")

    admission = _acquire_local_slot(args.lane)
    if admission is not None:
        return admission
    try:
        results: list[GateResult] = []
        if manifest_errors:
            log_path = run_dir / "manifest-validation.log"
            message = "FAIL: " + "; ".join(manifest_errors)
            log_path.write_text(message + "\n", encoding="utf-8")
            repro_args = [
                str(REPO_ROOT / "scripts" / "pr-preflight"),
                "--all",
                "--lane",
                args.lane,
                "--base",
                args.base,
                "--head",
                args.head,
            ]
            results.append(
                GateResult(
                    Check(
                        id="manifest-validation",
                        command=(".github/scripts/run_checks.py", "--list"),
                        triggers=(),
                        lanes=("local", "ci"),
                        reason="validate the shared gate manifest before selecting checks",
                    ),
                    "FAIL",
                    0.0,
                    message,
                    f"cd {shlex.quote(str(root))} && {shlex.join(repro_args)}",
                    log_path,
                )
            )
        if metadata_error:
            log_path = run_dir / "pr-metadata.log"
            message = f"FAIL: {metadata_error}"
            log_path.write_text(message + "\n", encoding="utf-8")
            repro_args = [
                str(REPO_ROOT / "scripts" / "pr-preflight"),
                "--all",
                *(arg for arg in sys.argv[1:] if arg != "--all"),
            ]
            results.append(
                GateResult(
                    Check(
                        id="pr-metadata",
                        command=("scripts/pr-preflight", "--all"),
                        triggers=(),
                        lanes=("local", "ci"),
                        reason="resolve PR metadata before metadata-dependent checks",
                    ),
                    "FAIL",
                    0.0,
                    message.splitlines()[0],
                    f"cd {shlex.quote(str(root))} && {shlex.join(repro_args)}",
                    log_path,
                )
            )
        for check, _ in gates:
            log_path = run_dir / f"{check.id}.log"
            remaining = budget - (time.monotonic() - started)
            if remaining <= 0:
                print(f"==> {check.id}", flush=True)
                print(
                    f"SKIPPED-FOR-TIME {check.id}: wall budget {budget:g}s exhausted before this gate started",
                    flush=True,
                )
                results.append(GateResult(check, "skipped-for-time", 0.0, "", "", log_path))
                continue
            command = command_for_host(
                command_for_check(
                    check,
                    changed_files_path=files_path,
                    base=merge_base,
                    target_base=args.base,
                    head=args.head,
                    pr_body_file=body_path,
                    skip_changelog=skip_changelog,
                ),
                python_executable=sys.executable,
            )
            print(f"==> {check.id}", flush=True)
            gate_started = time.monotonic()
            returncode, first_error, timed_out = _run_gate(command, root, log_path, remaining)
            seconds = time.monotonic() - gate_started
            status = "skipped-for-time" if timed_out else ("PASS" if returncode == 0 else "FAIL")
            if timed_out:
                print(f"<== SKIPPED-FOR-TIME {check.id} ({seconds:.2f}s)", flush=True)
            else:
                print(f"<== {status} {check.id} ({seconds:.2f}s)", flush=True)
            results.append(
                GateResult(
                    check,
                    status,
                    seconds,
                    first_error,
                    f"cd {shlex.quote(str(root))} && {shlex.join(command)}",
                    log_path,
                )
            )
    finally:
        _release_local_slot()

    elapsed = time.monotonic() - started
    _summary(results, run_dir, budget)
    failed = any(result.status == "FAIL" for result in results)
    skipped = any(result.status == "skipped-for-time" for result in results)
    if failed or skipped:
        print(f"PR preflight --all failed in {elapsed:.2f}s.", file=sys.stderr)
        return 1
    print(f"PR preflight --all passed: {len(results)} gate(s) in {elapsed:.2f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
