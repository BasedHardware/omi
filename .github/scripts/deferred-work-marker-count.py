#!/usr/bin/env python3
"""Count explicit deferred-work markers in repository text files."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MARKERS = ("TO" "DO", "FIX" "ME", "HA" "CK")
MARKER_RE = re.compile(r"\b(" + "|".join(MARKERS) + r")\b", re.IGNORECASE)
TRACKING_ISSUE_RE = re.compile(r"(?:https://github\.com/[^/\s]+/[^/\s]+/(?:issues|pull)/\d+|(?<!\w)#\d+\b)")

EXCLUDED_DIR_NAMES = {
    ".build",
    ".dart_tool",
    ".git",
    ".next",
    ".pub-cache",
    "build",
    "DerivedData",
    "node_modules",
    "Pods",
    "target",
}

NORMALIZED_EXCLUDED_DIR_NAMES = {
    ".pio",
    "Generated",
    "generated",
    "vendor",
}

NORMALIZED_EXCLUDED_PREFIXES = (
    ".github/workflows/",
    "app/lib/l10n/",
    "backend/charts/deepgram-self-hosted/nova-3/charts/",
    "omi/firmware/devkit/src/lib/opus-1.2.1/",
    "omi/firmware/omi/src/lib/core/lib/opus-1.2.1/",
)

NORMALIZED_EXCLUDED_SUFFIXES = (
    ".g.dart",
    ".gen.dart",
    "Package.resolved",
    "package-lock.json",
    "pubspec.lock",
)

NORMALIZED_EXCLUDED_FILES = {
    ".github/scripts/deferred-work-marker-count.py",
    "AGENTS.md",
    "CLAUDE.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    parser.add_argument("--raw", action="store_true", help="Include generated, vendored, policy, and workflow files.")
    parser.add_argument("--changed-files", type=Path, help="File listing changed paths for the new-marker guard.")
    parser.add_argument("--base", help="Git base ref for the new-marker guard.")
    parser.add_argument("--check-new", action="store_true", help="Fail when an added marker lacks a tracking issue.")
    parser.add_argument(
        "--format",
        choices=("plain", "github-summary"),
        default="plain",
        help="Output format.",
    )
    return parser.parse_args()


def added_lines(base: str, path: str) -> list[tuple[int, str]]:
    exists_at_base = subprocess.run(
        ["git", "cat-file", "-e", f"{base}:{path}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists_at_base and not tracked:
        try:
            return list(enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1))
        except (OSError, UnicodeDecodeError):
            return []
    result = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", base, "--", path],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git diff failed for {path}")
    additions: list[tuple[int, str]] = []
    head_line = 0
    for raw_line in result.stdout.splitlines():
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            head_line = int(match.group(1)) - 1 if match else 0
            continue
        if raw_line.startswith("+++"):
            continue
        if raw_line.startswith("+"):
            head_line += 1
            additions.append((head_line, raw_line[1:]))
        elif not raw_line.startswith("-") and head_line:
            head_line += 1
    return additions


def check_new_markers(base: str, changed_files_path: Path) -> int:
    violations: list[str] = []
    for path in changed_files_path.read_text(encoding="utf-8").splitlines():
        if not path or excluded_by_normalized_policy(path) or not Path(path).is_file():
            continue
        try:
            additions = added_lines(base, path)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        for lineno, line in additions:
            if MARKER_RE.search(line) and not TRACKING_ISSUE_RE.search(line):
                violations.append(f"{path}:{lineno}: {line.strip()}")
    if violations:
        print("FAIL: new deferred-work markers must reference a tracking issue (#123 or GitHub URL).")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("OK: new deferred-work markers reference tracking issues.")
    return 0


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(4096)
    except OSError:
        return True


def excluded_by_normalized_policy(relative_path: str) -> bool:
    if any(part in NORMALIZED_EXCLUDED_DIR_NAMES for part in Path(relative_path).parts):
        return True
    if relative_path in NORMALIZED_EXCLUDED_FILES:
        return True
    if relative_path.endswith(NORMALIZED_EXCLUDED_SUFFIXES):
        return True
    return relative_path.startswith(NORMALIZED_EXCLUDED_PREFIXES)


def iter_files(root: Path, raw: bool):
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIR_NAMES]
        for filename in filenames:
            path = current / filename
            relative_path = path.relative_to(root).as_posix()
            if not raw and excluded_by_normalized_policy(relative_path):
                continue
            if is_binary(path):
                continue
            yield path, relative_path


def count_markers(root: Path, raw: bool) -> tuple[dict[str, int], dict[str, int]]:
    marker_counts = {marker: 0 for marker in MARKERS}
    file_counts: dict[str, int] = {}

    for path, relative_path in iter_files(root, raw):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except OSError:
                continue
        except OSError:
            continue

        matches = MARKER_RE.findall(text)
        if not matches:
            continue

        file_counts[relative_path] = len(matches)
        for marker in matches:
            marker_counts[marker.upper()] += 1

    return marker_counts, file_counts


def print_plain(marker_counts: dict[str, int], file_counts: dict[str, int], raw: bool) -> None:
    label = "raw" if raw else "normalized"
    total = sum(marker_counts.values())
    print(f"{label} total: {total}")
    for marker in MARKERS:
        print(f"{marker}: {marker_counts[marker]}")
    print(f"files: {len(file_counts)}")


def print_github_summary(marker_counts: dict[str, int], file_counts: dict[str, int], raw: bool) -> None:
    label = "Raw" if raw else "Normalized"
    total = sum(marker_counts.values())
    print(f"### {label} deferred-work marker count")
    print()
    print("| Marker | Count |")
    print("| --- | ---: |")
    for marker in MARKERS:
        print(f"| `{marker}` | {marker_counts[marker]} |")
    print(f"| **Total** | **{total}** |")
    print()
    print(f"Files with markers: {len(file_counts)}")
    if not raw:
        print()
        print("Normalized count excludes generated, vendored, build, lock, policy, and workflow files.")


def main() -> int:
    args = parse_args()
    if args.check_new:
        if not args.changed_files or not args.base:
            print("FAIL: --check-new requires --changed-files and --base", file=sys.stderr)
            return 2
        return check_new_markers(args.base, args.changed_files)
    root = Path(args.root).resolve()
    marker_counts, file_counts = count_markers(root, args.raw)

    if args.format == "github-summary":
        print_github_summary(marker_counts, file_counts, args.raw)
    else:
        print_plain(marker_counts, file_counts, args.raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
