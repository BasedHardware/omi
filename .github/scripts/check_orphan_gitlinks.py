#!/usr/bin/env python3
"""Fail closed when the tree has gitlinks (mode 160000) without .gitmodules maps.

actions/checkout post-steps run `git submodule foreach` whenever a gitlink is
present. An unmapped gitlink yields:

  no submodule mapping found in .gitmodules for path '...'

and can hang or fail M1 tag-release checkout cleanup. Static checker.
"""
from __future__ import annotations

import configparser
import subprocess
import sys
from pathlib import Path


def _gitlinks(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-s"],
        text=True,
    )
    paths: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        mode = meta.split()[0]
        if mode == "160000":
            paths.append(path)
    return paths


def _mapped_paths(repo: Path) -> set[str]:
    gm = repo / ".gitmodules"
    if not gm.is_file():
        return set()
    parser = configparser.ConfigParser()
    parser.read(gm)
    mapped: set[str] = set()
    for section in parser.sections():
        path = parser.get(section, "path", fallback="").strip()
        if path:
            mapped.add(path)
    return mapped


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    links = _gitlinks(repo)
    if not links:
        print("check_orphan_gitlinks: no gitlinks")
        return 0
    mapped = _mapped_paths(repo)
    orphans = sorted(p for p in links if p not in mapped)
    if orphans:
        print("Orphan gitlink(s) without .gitmodules path mapping:", file=sys.stderr)
        for path in orphans:
            print(f"  - {path}", file=sys.stderr)
        print(
            "Remove the gitlink (`git rm`) or add a matching .gitmodules entry.",
            file=sys.stderr,
        )
        return 1
    print(f"check_orphan_gitlinks: {len(links)} gitlink(s) mapped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
