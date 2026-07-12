#!/usr/bin/env python3
"""Check changed files for whitespace errors and unresolved conflict markers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    diff = subprocess.run(["git", "diff", "--check", args.base, args.head], check=False)
    if args.head == "HEAD":
        worktree_diff = subprocess.run(["git", "diff", "--check", "HEAD"], check=False)
        if worktree_diff.returncode:
            return worktree_diff.returncode
    if diff.returncode:
        return diff.returncode

    failed = False
    for path in args.changed_files.read_text(encoding="utf-8").splitlines():
        candidate = Path(path)
        if not candidate.is_file():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, start=1):
            if line.startswith(("<<<<<<<", ">>>>>>>")):
                print(f"{path}:{lineno}: unresolved merge conflict marker", file=sys.stderr)
                failed = True
    if failed:
        print("FAIL: unresolved merge conflict markers found in changed files", file=sys.stderr)
        return 1
    print("Diff hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
