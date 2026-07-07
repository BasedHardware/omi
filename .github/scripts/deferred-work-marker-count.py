#!/usr/bin/env python3
"""Count explicit deferred-work markers in repository text files."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

MARKERS = ("TO" "DO", "FIX" "ME", "HA" "CK")
MARKER_RE = re.compile(r"\b(" + "|".join(MARKERS) + r")\b", re.IGNORECASE)

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
    parser.add_argument(
        "--format",
        choices=("plain", "github-summary"),
        default="plain",
        help="Output format.",
    )
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    marker_counts, file_counts = count_markers(root, args.raw)

    if args.format == "github-summary":
        print_github_summary(marker_counts, file_counts, args.raw)
    else:
        print_plain(marker_counts, file_counts, args.raw)


if __name__ == "__main__":
    main()
