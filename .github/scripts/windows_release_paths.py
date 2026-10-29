#!/usr/bin/env python3
"""Classify changes that should cut a Windows desktop release."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

WINDOWS_ROOT = "desktop/windows/"
RELEASE_NEUTRAL_PREFIXES = ("desktop/windows/docs/",)


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized.removeprefix("./")


def is_releasable_windows_path(path: str) -> bool:
    normalized = normalize_path(path)
    return normalized.startswith(WINDOWS_ROOT) and not any(
        normalized.startswith(prefix) for prefix in RELEASE_NEUTRAL_PREFIXES
    )


def git_paths(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def releasable_paths(root: Path, base: str = "") -> list[str]:
    if base:
        paths = git_paths(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMR",
            f"{base}..HEAD",
            "--",
            WINDOWS_ROOT,
        )
    else:
        paths = git_paths(root, "ls-files", "--", WINDOWS_ROOT)
    return sorted({normalize_path(path) for path in paths if is_releasable_windows_path(path)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="", help="Latest Windows release tag; empty means the first release.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = releasable_paths(args.root.resolve(), args.base.strip())
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: could not classify Windows release paths: {exc.stderr.strip()}", file=sys.stderr)
        return 1
    if paths:
        print(f"Windows release paths ({len(paths)}): {', '.join(paths)}", file=sys.stderr)
    else:
        print("Windows release paths: none", file=sys.stderr)
    print(str(bool(paths)).lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
