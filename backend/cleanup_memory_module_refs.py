#!/usr/bin/env python3
"""
Cleanup: remove leftover references to memory modules deleted in PR #12697.

Context
-------
PR #12697 removed the legacy in-process memory modules
(`backend/utils/memory/*`) in favour of the new vector-store backed
memory service. Several call sites, imports, config keys and docstrings
still reference the deleted symbols, which causes:

  * ImportError / ModuleNotFoundError at runtime when the old modules
    are imported by stale code paths,
  * dead configuration keys that silently do nothing,
  * confusing developer experience (grep still returns hits).

This script performs a safe, idempotent, repo-wide cleanup:

  1. Scans tracked Python/Markdown files for references to the deleted
     module paths and symbols.
  2. Rewrites imports/usages to the new canonical location
     (`backend.services.memory`).
  3. Flags (does not silently delete) any reference it cannot map to a
     known replacement so a human can review it.

Usage
-----
    python backend/cleanup_memory_module_refs.py --dry-run
    python backend/cleanup_memory_module_refs.py --apply

The script is deliberately conservative: it only touches lines that
match a known legacy pattern, and it writes a report of every change.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Legacy -> new mapping.  Keys are the deleted module paths / symbols that
# PR #12697 removed; values are the replacement that should be used instead.
# ---------------------------------------------------------------------------
REPLACEMENTS: dict[str, str] = {
    # module paths
    "backend.utils.memory": "backend.services.memory",
    "utils.memory": "services.memory",
    "backend.memory.legacy": "backend.services.memory",
    # symbols
    "LegacyMemoryStore": "MemoryService",
    "InMemoryBuffer": "MemoryService",
    "get_memory_store": "get_memory_service",
    "MemoryStoreConfig": "MemoryServiceConfig",
}

# Patterns we consider "legacy references" worth rewriting.
LEGACY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bbackend\.utils\.memory(\.\w+)*\b"),
    re.compile(r"\butils\.memory(\.\w+)*\b"),
    re.compile(r"\bbackend\.memory\.legacy(\.\w+)*\b"),
    re.compile(r"\bLegacyMemoryStore\b"),
    re.compile(r"\bInMemoryBuffer\b"),
    re.compile(r"\bget_memory_store\b"),
    re.compile(r"\bMemoryStoreConfig\b"),
]

# Files/dirs we never touch.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TARGET_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini"}


@dataclass
class Change:
    path: Path
    line_no: int
    before: str
    after: str


@dataclass
class Report:
    changed: list[Change] = field(default_factory=list)
    unresolved: list[Change] = field(default_factory=list)


def iter_candidate_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in TARGET_SUFFIXES:
            continue
        yield path


def rewrite_line(line: str) -> tuple[str, bool]:
    """Return (new_line, resolved). resolved=False means a legacy hit
    remained that we could not map to a known replacement."""
    new_line = line
    for legacy, replacement in REPLACEMENTS.items():
        # Word-boundary-ish replacement that also handles dotted paths.
        new_line = re.sub(rf"(?<![\w.]){re.escape(legacy)}(?![\w])", replacement, new_line)
    hit_before = any(p.search(line) for p in LEGACY_PATTERNS)
    hit_after = any(p.search(new_line) for p in LEGACY_PATTERNS)
    return new_line, (not hit_after) if hit_before else True


def process(root: Path, apply: bool) -> Report:
    report = Report()
    for path in iter_candidate_files(root):
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if not any(p.search(original) for p in LEGACY_PATTERNS):
            continue

        lines = original.splitlines(keepends=True)
        new_lines: list[str] = []
        file_changed = False

        for idx, line in enumerate(lines, start=1):
            new_line, resolved = rewrite_line(line)
            if new_line != line:
                file_changed = True
                change = Change(path, idx, line.rstrip("\n"), new_line.rstrip("\n"))
                if resolved:
                    report.changed.append(change)
                else:
                    report.unresolved.append(change)
            new_lines.append(new_line)

        if file_changed and apply:
            path.write_text("".join(new_lines), encoding="utf-8")

    return report


def print_report(report: Report, apply: bool) -> None:
    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"[{mode}] resolved rewrites: {len(report.changed)}")
    for c in report.changed:
        print(f"  {c.path}:{c.line_no}")
        print(f"    - {c.before}")
        print(f"    + {c.after}")
    if report.unresolved:
        print(f"\n[{mode}] UNRESOLVED (needs human review): {len(report.unresolved)}")
        for c in report.unresolved:
            print(f"  {c.path}:{c.line_no}  ->  {c.after}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="report only (default)")
    group.add_argument("--apply", action="store_true", help="write changes to disk")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root to scan",
    )
    args = parser.parse_args(argv)

    apply = bool(args.apply)
    report = process(args.root, apply=apply)
    print_report(report, apply)

    if report.unresolved:
        print(
            "\nSome legacy references could not be mapped automatically. "
            "Review the UNRESOLVED list above before merging.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
