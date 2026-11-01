#!/usr/bin/env python3
"""Resolve and run deterministic checks from .github/checks-manifest.yaml."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import platform as _platform_mod
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from git_bash import bash_executable

VALID_PLATFORMS = {"all", "macos", "linux", "windows"}
MANIFEST_RELATIVE_PATH = ".github/checks-manifest.yaml"
DEFAULT_MAX_CHECK_JOBS = 4
MAX_CHECK_JOBS = 8


def detect_platform() -> str:
    """Map the host OS to a manifest platform tag."""
    system = _platform_mod.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    if system == "Windows":
        return "windows"
    return system.lower()


@dataclass(frozen=True)
class Check:
    id: str
    command: tuple[str, ...]
    triggers: tuple[str, ...]
    lanes: tuple[str, ...]
    reason: str
    requires_pr_body: bool = False
    platforms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Exemption:
    path: str
    reason: str


@dataclass(frozen=True)
class Manifest:
    checks: tuple[Check, ...]
    exempt: tuple[Exemption, ...]


@dataclass(frozen=True)
class CheckSelection:
    """A manifest check together with the paths that selected it."""

    check: Check
    matched_paths: tuple[str, ...]


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith(("[", "{", '"')) or value in {"true", "false", "null"}:
        return json.loads(value)
    return value


def _parse_yaml_subset(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Parse the intentionally small, JSON-valued YAML subset used by the manifest."""
    sections: dict[str, list[dict[str, Any]]] = {}
    section: str | None = None
    current: dict[str, Any] | None = None
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t")) and stripped.endswith(":"):
            section = stripped[:-1]
            sections.setdefault(section, [])
            current = None
            continue
        if section is None:
            raise ValueError(f"{path}:{lineno}: entry appears before a section")
        if stripped.startswith("- {"):
            current = json.loads(stripped[2:])
            if not isinstance(current, dict):
                raise ValueError(f"{path}:{lineno}: expected an object")
            sections[section].append(current)
            continue
        if stripped.startswith("- "):
            current = {}
            sections[section].append(current)
            stripped = stripped[2:]
        if current is None or ":" not in stripped:
            raise ValueError(f"{path}:{lineno}: expected key: value")
        key, raw_value = stripped.split(":", 1)
        current[key.strip()] = _parse_value(raw_value)
    return sections


def load_manifest(path: Path) -> Manifest:
    raw = _parse_yaml_subset(path)
    checks = tuple(
        Check(
            id=str(item.get("id", "")),
            command=tuple(item.get("command", ())),
            triggers=tuple(item.get("triggers", ())),
            lanes=tuple(item.get("lanes", ())),
            reason=str(item.get("reason", "")),
            requires_pr_body=item.get("requires_pr_body", False),
            platforms=tuple(item.get("platforms", ())),
        )
        for item in raw.get("checks", [])
    )
    exempt = tuple(
        Exemption(path=str(item.get("path", "")), reason=str(item.get("reason", ""))) for item in raw.get("exempt", [])
    )
    return Manifest(checks=checks, exempt=exempt)


def load_manifest_from_text(text: str) -> Manifest:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False) as handle:
        handle.write(text)
        path = Path(handle.name)
    try:
        return load_manifest(path)
    finally:
        path.unlink(missing_ok=True)


def manifest_changed_check_ids(root: Path, base: str, head: str, *, include_worktree: bool = False) -> set[str]:
    """Return check ids whose manifest entries differ between base and head."""
    manifest_path = root / MANIFEST_RELATIVE_PATH
    head_manifest = load_manifest(manifest_path)
    try:
        base_text = run_git(root, "show", f"{base}:{MANIFEST_RELATIVE_PATH}")
    except subprocess.CalledProcessError:
        return {check.id for check in head_manifest.checks}

    base_manifest = load_manifest_from_text(base_text)
    head_by_id = {check.id: check for check in head_manifest.checks}
    base_by_id = {check.id: check for check in base_manifest.checks}
    changed = {
        check_id
        for check_id in set(head_by_id) | set(base_by_id)
        if head_by_id.get(check_id) != base_by_id.get(check_id)
    }
    if include_worktree and head == "HEAD":
        try:
            committed_text = run_git(root, "show", f"HEAD:{MANIFEST_RELATIVE_PATH}")
        except subprocess.CalledProcessError:
            return changed
        committed_manifest = load_manifest_from_text(committed_text)
        committed_by_id = {check.id: check for check in committed_manifest.checks}
        changed |= {
            check_id
            for check_id in set(head_by_id) | set(committed_by_id)
            if head_by_id.get(check_id) != committed_by_id.get(check_id)
        }
    return changed


def validate_manifest(manifest: Manifest, root: Path) -> list[str]:
    errors: list[str] = []
    ids = [check.id for check in manifest.checks]
    duplicates = sorted({check_id for check_id in ids if ids.count(check_id) > 1})
    if duplicates:
        errors.append(f"duplicate check ids: {', '.join(duplicates)}")
    for check in manifest.checks:
        if not check.id:
            errors.append("check id must not be empty")
        if not check.command:
            errors.append(f"{check.id}: command must not be empty")
        elif len(check.command) > 1 and check.command[0].startswith("python"):
            script = check.command[1]
            if not script.startswith("{") and not (root / script).is_file():
                errors.append(f"{check.id}: command path does not exist: {script}")
        if not check.triggers:
            errors.append(f"{check.id}: triggers must not be empty")
        for pattern in check.triggers:
            if not pattern or pattern.count("[") != pattern.count("]"):
                errors.append(f"{check.id}: invalid trigger glob: {pattern!r}")
            elif (
                pattern not in {"all", "@firestore-index-guard"}
                and not glob.has_magic(pattern)
                and not (root / pattern).exists()
            ):
                errors.append(f"{check.id}: explicit trigger path does not exist: {pattern}")
        if not check.lanes:
            errors.append(f"{check.id}: lanes must not be empty")
        invalid_lanes = sorted(set(check.lanes) - {"local", "ci"})
        if invalid_lanes:
            errors.append(f"{check.id}: invalid lanes: {', '.join(invalid_lanes)}")
        missing_lanes = sorted({"local", "ci"} - set(check.lanes))
        if missing_lanes:
            errors.append(f"{check.id}: missing required lanes: {', '.join(missing_lanes)}")
        if not check.reason:
            errors.append(f"{check.id}: reason must not be empty")
        if not isinstance(check.requires_pr_body, bool):
            errors.append(f"{check.id}: requires_pr_body must be a boolean")
        invalid_platforms = sorted(set(check.platforms) - VALID_PLATFORMS)
        if invalid_platforms:
            errors.append(f"{check.id}: invalid platforms: {', '.join(invalid_platforms)}")
    for exemption in manifest.exempt:
        if not exemption.path or not exemption.reason:
            errors.append("exempt entries require non-empty path and reason")
    return errors


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def merge_base(root: Path, base: str, head: str) -> str:
    return run_git(root, "merge-base", base, head)


def changed_files(root: Path, base: str, head: str, include_worktree: bool = False) -> list[str]:
    """PR file list: three-dot *base*...*head*. Never first-parent or HEAD~."""
    files = set(
        run_git(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACMRTD",
            f"{base}...{head}",
        ).splitlines()
    )
    if include_worktree and head == "HEAD":
        files.update(run_git(root, "diff", "--name-only", "--no-renames", "--diff-filter=ACMRTD", "HEAD").splitlines())
        files.update(
            run_git(root, "diff", "--name-only", "--no-renames", "--diff-filter=ACMRTD", "--cached").splitlines()
        )
        files.update(run_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(path for path in files if path)


def trigger_matches(pattern: str, path: str) -> bool:
    if pattern == "@firestore-index-guard":
        # The backend selector owns both the inventory scope and guard inputs.
        # It and its inventory imports are stdlib-only; selection needs no venv.
        backend_scripts = Path(__file__).resolve().parents[2] / "backend/scripts"
        if str(backend_scripts) not in sys.path:
            sys.path.insert(0, str(backend_scripts))
        from select_backend_unit_tests import is_firestore_index_guard_path

        return is_firestore_index_guard_path(path)
    if pattern == "all":
        return True
    if pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    if fnmatch.fnmatchcase(path, pattern):
        return True
    # Path.match treats a slash-free pattern as a final-component glob, so a
    # trigger written as `package.json` also selects `web/frontend/package.json`.
    # A literal trigger names one repo path. Glob patterns still use Path.match.
    if ("/" in pattern or glob.has_magic(pattern)) and PurePath(path).match(pattern):
        return True
    if "/**/" in pattern and fnmatch.fnmatchcase(path, pattern.replace("/**/", "/")):
        return True
    # `**/x` means "x at any depth, the repository root included" -- the reading
    # git, .gitignore and Actions path filters share. fnmatch needs the literal
    # `/`, so a trigger list written only as `**/*.json` selects nothing for a
    # root-level file it is meant to cover. Collapse a leading `**/` to nothing,
    # exactly as the interior `/**/` is collapsed above.
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return False


def _platform_matches(check: Check, platform: str, *, exclusive: bool = False) -> bool:
    if exclusive:
        # A macOS-exclusive query intentionally excludes portable checks.  Those
        # remain owned by the Linux Repo Checks lane even though they could also
        # execute on a Mac.
        return set(check.platforms) == {platform}
    return not check.platforms or "all" in check.platforms or platform in check.platforms


def matching_paths(
    check: Check,
    files: list[str],
    *,
    manifest_changed_ids: set[str] | None = None,
) -> tuple[str, ...]:
    """Return changed paths that caused *check* to be selected."""
    if "all" in check.triggers:
        return tuple(files) if files else ("all",)
    matched = tuple(path for path in files if any(trigger_matches(pattern, path) for pattern in check.triggers))
    if manifest_changed_ids is None or not matched:
        return matched
    non_manifest = [path for path in matched if path != MANIFEST_RELATIVE_PATH]
    if non_manifest:
        return matched
    if MANIFEST_RELATIVE_PATH in matched and check.id in manifest_changed_ids:
        return matched
    return ()


def resolve_check_selections(
    manifest: Manifest,
    files: list[str],
    lane: str,
    *,
    include_pr_body_checks: bool = True,
    platform: str = "all",
    exclusive_platform: bool = False,
    manifest_changed_ids: set[str] | None = None,
) -> list[CheckSelection]:
    """Resolve checks with their manifest-owned path and reason evidence."""
    selections: list[CheckSelection] = []
    for check in manifest.checks:
        if lane not in check.lanes:
            continue
        if not include_pr_body_checks and check.requires_pr_body:
            continue
        if not _platform_matches(check, platform, exclusive=exclusive_platform):
            continue
        paths = matching_paths(check, files, manifest_changed_ids=manifest_changed_ids)
        if paths:
            selections.append(CheckSelection(check=check, matched_paths=paths))
    return selections


def resolve_checks(
    manifest: Manifest,
    files: list[str],
    lane: str,
    *,
    include_pr_body_checks: bool = True,
    platform: str = "all",
    exclusive_platform: bool = False,
    manifest_changed_ids: set[str] | None = None,
) -> list[Check]:
    return [
        selection.check
        for selection in resolve_check_selections(
            manifest,
            files,
            lane,
            include_pr_body_checks=include_pr_body_checks,
            platform=platform,
            exclusive_platform=exclusive_platform,
            manifest_changed_ids=manifest_changed_ids,
        )
    ]


def resolve_explicit_checks(
    manifest: Manifest,
    check_ids: list[str],
    lane: str,
    *,
    include_pr_body_checks: bool,
    platform: str,
) -> list[CheckSelection]:
    """Resolve named manifest checks without duplicating their commands in callers."""
    checks_by_id = {check.id: check for check in manifest.checks}
    selections: list[CheckSelection] = []
    for check_id in dict.fromkeys(check_ids):
        check = checks_by_id.get(check_id)
        if check is None:
            raise ValueError(f"unknown check id: {check_id}")
        if lane not in check.lanes:
            raise ValueError(f"{check_id}: check is not available in the {lane} lane")
        if not include_pr_body_checks and check.requires_pr_body:
            raise ValueError(f"{check_id}: check requires pull-request metadata")
        if not _platform_matches(check, platform):
            raise ValueError(f"{check_id}: check does not support platform {platform}")
        selections.append(CheckSelection(check=check, matched_paths=()))
    return selections


def skipped_platform_checks(manifest: Manifest, files: list[str], lane: str, platform: str) -> list[Check]:
    """Checks that match lane+triggers but are skipped due to platform."""
    return [
        check
        for check in manifest.checks
        if lane in check.lanes
        and not _platform_matches(check, platform)
        and (
            "all" in check.triggers
            or any(trigger_matches(pattern, path) for pattern in check.triggers for path in files)
        )
    ]


def command_for_check(
    check: Check,
    *,
    changed_files_path: Path,
    base: str,
    target_base: str,
    head: str,
    pr_body_file: Path,
    skip_changelog: bool,
) -> list[str]:
    replacements = {
        "{changed_files}": str(changed_files_path),
        "{base}": base,
        "{target_base}": target_base,
        "{head}": head,
        "{pr_body_file}": str(pr_body_file),
    }
    command: list[str] = []
    for token in check.command:
        if token == "{skip_changelog}":
            if skip_changelog:
                command.append("--skip")
            continue
        command.append(replacements.get(token, token))
    return command


def command_for_host(
    command: list[str],
    *,
    platform_name: str | None = None,
    python_executable: str | None = None,
) -> list[str]:
    """Resolve manifest interpreter aliases through the active toolchain.

    On Windows, `python3`/`bash` must route through Git's toolchain. On POSIX
    hosts the manifest's `python3` alias also honors an explicit
    `python_executable`, so a host whose PATH `python3` is Xcode CLT 3.9 runs
    manifest checks under the >= 3.10 interpreter the dev harness selected
    instead of crashing on PEP 604 unions at module scope.
    """
    platform = platform_name or os.name
    if not command:
        return command
    if platform != "nt":
        if command[0] == "python3" and python_executable:
            return [python_executable, *command[1:]]
        return command
    if command[0] == "bash":
        return [bash_executable(platform_name=platform), *command[1:]]
    if command[0] == "python3":
        return [python_executable or sys.executable, *command[1:]]
    return command


def check_jobs() -> int:
    """Worker count for parallel-safe checks; OMI_CHECKS_JOBS=1 restores the serial run.

    Overrides are clamped to MAX_CHECK_JOBS: the pool runs inside one omi-heavy slot on shared hosts.
    """
    raw = os.environ.get("OMI_CHECKS_JOBS", "").strip()
    if raw:
        try:
            return min(MAX_CHECK_JOBS, max(1, int(raw)))
        except ValueError:
            print(f"WARN: ignoring non-integer OMI_CHECKS_JOBS={raw!r}", file=sys.stderr)
    return min(DEFAULT_MAX_CHECK_JOBS, max(1, (os.cpu_count() or 2) // 2))


def is_parallel_safe(check: Check) -> bool:
    """Plain `python3 <script>` checks are read-only analyzers; anything else (bash, bun, swift, ruby) stays serial.

    Generators in the manifest run in their --check/validate form; their writes sit behind explicit
    --write/--update-baseline flags. execute_checks fails the run if a parallel check changes a tracked file.
    """
    return bool(check.command) and check.command[0] == "python3"


def tracked_tree_snapshot(root: Path) -> dict[str, str] | None:
    """Content hashes of tracked files that differ from HEAD, or None when git is unavailable.

    Untracked files are left out on purpose: checks keep ignored scratch state in the tree
    (`.agent-brief/`), and only some hosts ignore it.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", "surrogateescape")
    except (OSError, subprocess.CalledProcessError):
        return None
    snapshot: dict[str, str] = {}
    entries = status.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            index += 1  # the rename/copy source path follows as its own NUL-separated field
        path = entry[3:]
        try:
            snapshot[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
        except OSError:
            snapshot[path] = "missing"
    return snapshot


def duration_cache_path(root: Path) -> Path | None:
    """Per-clone record of each check's last wall time, used to start the slowest checks first."""
    try:
        common = run_git(root, "rev-parse", "--git-common-dir")
    except (OSError, subprocess.CalledProcessError):
        return None
    return (root / common).resolve() / "omi-preflight" / "check-durations.json"


def load_durations(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): float(value) for key, value in data.items() if isinstance(value, (int, float))}


def save_durations(path: Path | None, durations: dict[str, float]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(durations, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass


def _stop(process: subprocess.Popen[bytes]) -> bool:
    """Stop a running check; True only when this call ended it, False when it had already exited on its own."""
    if process.poll() is not None:
        return False
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
        process.wait()
    if os.name == "nt":
        return True  # TerminateProcess leaves no signal trace; the poll above is the best available check
    # A check that exited between the poll and the signal keeps its own exit status.
    return process.returncode in (-signal.SIGTERM, -signal.SIGKILL)


def execute_parallel_checks(
    root: Path,
    checks: list[Check],
    commands: dict[str, list[str]],
    *,
    jobs: int,
    keep_going: bool,
    durations: dict[str, float],
) -> list[str]:
    """Run checks in a bounded pool, longest-known first, printing each check's output as one block.

    Fail-fast stops scheduling and terminates the running checks at the first failure, then prints the
    failing block last so the preflight runner's last `==> ` line still names the failing check.
    Returns the failed check ids in manifest order; `durations` is updated in place.
    """
    pending = sorted(checks, key=lambda check: -durations.get(check.id, 0.0))
    running: dict[str, tuple[subprocess.Popen[bytes], Any, float]] = {}
    failures: list[str] = []
    failed_block: str | None = None

    def collect(check_id: str) -> tuple[int, str]:
        process, log, started = running.pop(check_id)
        elapsed = time.monotonic() - started
        durations[check_id] = elapsed
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
        log.close()
        status = "PASS" if process.returncode == 0 else "FAIL"
        block = f"==> {check_id}\n{output}"
        if output and not output.endswith("\n"):
            block += "\n"
        return process.returncode, block + f"<== {status} {check_id} ({elapsed:.2f}s)\n"

    try:
        while pending or running:
            while pending and len(running) < jobs:
                check = pending.pop(0)
                log = tempfile.TemporaryFile()
                process = subprocess.Popen(
                    commands[check.id],
                    cwd=root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=os.name != "nt",
                )
                running[check.id] = (process, log, time.monotonic())
            finished = [check_id for check_id, (process, _, _) in running.items() if process.poll() is not None]
            if not finished:
                time.sleep(0.05)
                continue
            for check_id in finished:
                returncode, block = collect(check_id)
                if returncode:
                    failures.append(check_id)
                    if not keep_going and failed_block is None:
                        failed_block = block
                        continue
                print(block, end="", flush=True)
            if failed_block is not None:
                pending.clear()
                # Checks that finished on their own report their real result; only live ones are cancelled.
                for check_id, (process, log, _) in list(running.items()):
                    if _stop(process):
                        log.close()
                        running.pop(check_id)
                        print(f"<== CANCELLED {check_id} (stopped after the first failure)", flush=True)
                        continue
                    returncode, block = collect(check_id)
                    if returncode:
                        failures.append(check_id)
                    print(block, end="", flush=True)
    finally:
        for process, log, _ in running.values():
            _stop(process)
            log.close()
    if failed_block is not None:
        print(failed_block, end="", flush=True)
    order = {check.id: index for index, check in enumerate(checks)}
    return sorted(failures, key=order.__getitem__)


def execute_checks(
    root: Path,
    checks: list[Check],
    *,
    changed_files_path: Path,
    base: str,
    head: str,
    pr_body_file: Path,
    target_base: str | None = None,
    skip_changelog: bool = False,
    keep_going: bool = False,
) -> int:
    failures: list[str] = []
    total = len(checks)
    jobs = check_jobs()
    parallel = [check for check in checks if is_parallel_safe(check)] if jobs > 1 else []
    if len(parallel) > 1:
        commands = {
            check.id: command_for_host(
                command_for_check(
                    check,
                    changed_files_path=changed_files_path,
                    base=base,
                    target_base=target_base or base,
                    head=head,
                    pr_body_file=pr_body_file,
                    skip_changelog=skip_changelog,
                ),
                python_executable=sys.executable,
            )
            for check in parallel
        }
        cache = duration_cache_path(root)
        durations = load_durations(cache)
        before = tracked_tree_snapshot(root)
        print(
            f"Running {len(parallel)} python check(s) with {jobs} workers (OMI_CHECKS_JOBS=1 runs serially).",
            flush=True,
        )
        failures = execute_parallel_checks(
            root, parallel, commands, jobs=jobs, keep_going=keep_going, durations=durations
        )
        save_durations(cache, durations)
        after = tracked_tree_snapshot(root)
        if before is not None and after is not None and before != after:
            changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            print(
                f"FAIL: parallel checks modified tracked files: {', '.join(changed)}. A check that writes must not "
                "run in the parallel pool; rerun with OMI_CHECKS_JOBS=1 to find it, then make it read-only or "
                "exclude it in is_parallel_safe().",
                file=sys.stderr,
            )
            return 1
        if failures and not keep_going:
            print(f"Manifest checks failed: {', '.join(failures)}", file=sys.stderr)
            return 1
        parallel_ids = {check.id for check in parallel}
        checks = [check for check in checks if check.id not in parallel_ids]
    for check in checks:
        started = time.monotonic()
        print(f"==> {check.id}", flush=True)
        command = command_for_check(
            check,
            changed_files_path=changed_files_path,
            base=base,
            target_base=target_base or base,
            head=head,
            pr_body_file=pr_body_file,
            skip_changelog=skip_changelog,
        )
        command = command_for_host(command, python_executable=sys.executable)
        returncode = subprocess.run(command, cwd=root, check=False).returncode
        status = "PASS" if returncode == 0 else "FAIL"
        print(f"<== {status} {check.id} ({time.monotonic() - started:.2f}s)", flush=True)
        if returncode:
            failures.append(check.id)
            if not keep_going:
                break
    if failures:
        print(f"Manifest checks failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"Manifest checks passed: {total} check(s).")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--lane", choices=("local", "ci"), required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument(
        "--skip-pr-body-checks",
        action="store_true",
        help="Exclude checks declared as requiring pull-request metadata.",
    )
    parser.add_argument("--skip-changelog", action="store_true")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Run only selected checks that consume PR metadata and report all their failures.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Run every selected check before exiting and report all failures (nightly full runs); "
        "fail-fast remains the default for PR and local lanes.",
    )
    parser.add_argument(
        "--check-id",
        action="append",
        default=[],
        help="Run a named manifest check regardless of path triggers; repeat for multiple checks.",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument(
        "--platform",
        choices=sorted(VALID_PLATFORMS),
        default=None,
        help="Platform filter (auto-detected if omitted). macOS-only checks are skipped on other platforms.",
    )
    parser.add_argument(
        "--exclusive-platform",
        action="store_true",
        help="Select only checks scoped exclusively to --platform (for example macOS-only, not portable, checks).",
    )
    parser.add_argument(
        "--output",
        choices=("human", "json"),
        default="human",
        help="Selection output format. JSON implies --list and includes check IDs, matching paths, and reasons.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.metadata_only and (args.skip_pr_body_checks or args.check_id):
        print("FAIL: --metadata-only cannot combine with --skip-pr-body-checks or --check-id", file=sys.stderr)
        return 2
    root = (args.root or Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel"))).resolve()
    manifest_path = (args.manifest or root / ".github/checks-manifest.yaml").resolve()
    try:
        manifest = load_manifest(manifest_path)
        manifest_errors = validate_manifest(manifest, root)
        if manifest_errors:
            raise ValueError("; ".join(manifest_errors))
        resolved_base = merge_base(root, args.base, args.head)
        files = (
            [line for line in args.changed_files.read_text(encoding="utf-8").splitlines() if line]
            if args.changed_files
            else changed_files(root, args.base, args.head, include_worktree=args.lane == "local")
        )
        manifest_changed_ids = (
            manifest_changed_check_ids(
                root,
                resolved_base,
                args.head,
                include_worktree=args.lane == "local",
            )
            if MANIFEST_RELATIVE_PATH in files
            else None
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: could not resolve manifest checks: {exc}", file=sys.stderr)
        return 2
    detected_platform = args.platform or detect_platform()
    try:
        selections = (
            resolve_explicit_checks(
                manifest,
                args.check_id,
                args.lane,
                include_pr_body_checks=not args.skip_pr_body_checks,
                platform=detected_platform,
            )
            if args.check_id
            else resolve_check_selections(
                manifest,
                files,
                args.lane,
                include_pr_body_checks=not args.skip_pr_body_checks,
                platform=detected_platform,
                exclusive_platform=args.exclusive_platform,
                manifest_changed_ids=manifest_changed_ids,
            )
        )
    except ValueError as exc:
        print(f"FAIL: could not select manifest checks: {exc}", file=sys.stderr)
        return 2
    if args.metadata_only:
        selections = [selection for selection in selections if selection.check.requires_pr_body]
    checks = [selection.check for selection in selections]
    if args.output == "json":
        print(
            json.dumps(
                {
                    "lane": args.lane,
                    "platform": detected_platform,
                    "exclusive_platform": args.exclusive_platform,
                    "checks": [
                        {
                            "id": selection.check.id,
                            "matched_paths": list(selection.matched_paths),
                            "reason": selection.check.reason,
                        }
                        for selection in selections
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    print(
        f"Check manifest: lane={args.lane} platform={detected_platform} exclusive_platform={args.exclusive_platform} "
        f"base={resolved_base[:12]} head={args.head} files={len(files)}"
    )
    for check in checks:
        print(f"  SELECTED {check.id}: {check.reason}")
    if not args.check_id:
        for skip in skipped_platform_checks(manifest, files, args.lane, detected_platform):
            print(
                f"  SKIPPED {skip.id}: platform-only (requires {', '.join(skip.platforms)}, running on {detected_platform})"
            )
    if args.list:
        return 0

    with tempfile.TemporaryDirectory(prefix="omi-checks-") as temp_dir:
        temp = Path(temp_dir)
        files_path = temp / "changed-files.txt"
        files_path.write_text("".join(f"{path}\n" for path in files), encoding="utf-8")
        body_path = args.pr_body_file or temp / "pr-body.txt"
        if not args.pr_body_file:
            body_path.write_text("", encoding="utf-8")
        return execute_checks(
            root,
            checks,
            changed_files_path=files_path,
            base=resolved_base,
            target_base=args.base,
            head=args.head,
            pr_body_file=body_path,
            skip_changelog=args.skip_changelog,
            keep_going=args.keep_going or args.metadata_only,
        )


if __name__ == "__main__":
    raise SystemExit(main())
