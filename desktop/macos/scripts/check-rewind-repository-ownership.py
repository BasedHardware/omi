#!/usr/bin/env python3
"""Reject per-feature copies of the shared Rewind database pool cache."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_ROOT = REPOSITORY_ROOT / "desktop/macos/Desktop/Sources"
FORBIDDEN = re.compile(r"\bprivate\s+var\s+_db(?:Queue|Generation)\b")


def violations(source_root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(source_root.rglob("*.swift")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                try:
                    display_path = path.relative_to(REPOSITORY_ROOT)
                except ValueError:
                    display_path = path.relative_to(source_root)
                found.append(
                    f"{display_path}:{line_number}: Rewind pool ownership belongs in "
                    "RewindRepository; use a repository instance instead of a private _dbQueue/_dbGeneration cache"
                )
    return found


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        clean = root / "CleanStorage.swift"
        clean.write_text(
            'actor CleanStorage { private let repository = RewindRepository(owner: "CleanStorage") }\n',
            encoding="utf-8",
        )
        if violations(root):
            print("self-test failed: repository-owned storage was rejected", file=sys.stderr)
            return 1

        bad = root / "CopiedStorage.swift"
        bad.write_text(
            "actor CopiedStorage {\n"
            "  private var _dbQueue: DatabasePool?\n"
            "  private var _dbGeneration = -1\n"
            "}\n",
            encoding="utf-8",
        )
        found = violations(root)
        if len(found) != 2 or not all("CopiedStorage.swift" in item for item in found):
            print(f"self-test failed: expected two actionable violations, got {found!r}", file=sys.stderr)
            return 1

    print("rewind repository ownership guard self-test: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    found = violations(args.source_root)
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1

    print("rewind repository ownership guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
