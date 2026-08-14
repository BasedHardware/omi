#!/usr/bin/env python3
"""Resolve and run deterministic checks from .github/checks-manifest.yaml."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import platform as _platform_mod
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
    if value.startswith(("[", '"')) or value in {"true", "false", "null"}:
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
            elif pattern != "all" and not glob.has_magic(pattern) and not (root / pattern).exists():
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
    resolved_base = merge_base(root, base, head)
    files = set(run_git(root, "diff", "--name-only", "--diff-filter=ACMRD", f"{resolved_base}...{head}").splitlines())
    if include_worktree and head == "HEAD":
        files.update(run_git(root, "diff", "--name-only", "--diff-filter=ACMRD", "HEAD").splitlines())
        files.update(run_git(root, "diff", "--name-only", "--diff-filter=ACMRD", "--cached").splitlines())
        files.update(run_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(path for path in files if path)


def trigger_matches(pattern: str, path: str) -> bool:
    if pattern == "all":
        return True
    if pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    if fnmatch.fnmatchcase(path, pattern) or PurePath(path).match(pattern):
        return True
    if "/**/" in pattern:
        return fnmatch.fnmatchcase(path, pattern.replace("/**/", "/"))
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
    """Resolve manifest interpreter aliases through the active Windows toolchain."""
    platform = platform_name or os.name
    if platform != "nt" or not command:
        return command
    if command[0] == "bash":
        return [bash_executable(platform_name=platform), *command[1:]]
    if command[0] == "python3":
        return [python_executable or sys.executable, *command[1:]]
    return command


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
) -> int:
    failures: list[str] = []
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
        command = command_for_host(command)
        returncode = subprocess.run(command, cwd=root, check=False).returncode
        status = "PASS" if returncode == 0 else "FAIL"
        print(f"<== {status} {check.id} ({time.monotonic() - started:.2f}s)", flush=True)
        if returncode:
            failures.append(check.id)
            break
    if failures:
        print(f"Manifest checks failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"Manifest checks passed: {len(checks)} check(s).")
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
        )


if __name__ == "__main__":
    raise SystemExit(main())
