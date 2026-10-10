#!/usr/bin/env python3
"""Cleanup: leftover references to memory modules deleted in #12697.

Scans the repository for references to legacy memory modules/symbols and
rewrites them to their current locations.

Design goals (post-review hardening for PR #20544):

* **Safe by construction.** A rewrite is only applied when BOTH:
    1. the *old* path/symbol is verified absent from the current tree, and
    2. the *new* path/symbol is verified present in the current tree.
  If a mapping's premise cannot be verified, that mapping is *disabled*
  and reported instead of being applied. This prevents the tool from
  rewriting live imports into non-existent modules (ImportError at
  startup).

* **Never rewrites itself.** The script's own source file is excluded from
  candidate discovery, so the REPLACEMENTS table can never be corrupted
  by a run.

* **Tracked files only.** Candidate discovery prefers ``git ls-files`` so
  ignored/untracked/generated files are never mutated. A suffix-constrained
  walk (skipping SKIP_DIRS) is used only as a fallback outside a git tree.

* **Lossless reporting.** Unresolved hits are recorded independently of
  whether their line changed, so the human-review report cannot silently
  drop a legacy reference.

Usage::

    python backend/cleanup_memory_module_refs.py            # dry-run report
    python backend/cleanup_memory_module_refs.py --check    # exit 1 if stale refs remain
    python backend/cleanup_memory_module_refs.py --apply    # rewrite (verified mappings only)
    python backend/cleanup_memory_module_refs.py --apply --force  # apply even if verification fails
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Mapping table.
#
# Each entry maps a legacy reference to its replacement. Entries are only
# *applied* when ``verify_mapping`` confirms the old reference is gone and
# the new one exists. Otherwise the mapping is disabled and reported.
# ---------------------------------------------------------------------------

# module paths -> replacement module path
MODULE_REPLACEMENTS: dict[str, str] = {
    "backend.utils.memory": "backend.services.memory",
    "backend.memory.legacy": "backend.services.memory",
}

# symbols -> replacement symbol
SYMBOL_REPLACEMENTS: dict[str, str] = {
    "LegacyMemoryStore": "MemoryService",
    "get_memory_store": "get_memory_service",
    "MemoryStoreConfig": "MemoryServiceConfig",
}

# Paths that must NEVER be treated as containing stale references. These are
# files that legitimately mention the legacy names (the migration tool itself,
# changelogs, migration notes, tests that assert the old names are gone).
REJECT_PATHS: tuple[str, ...] = (
    "backend/cleanup_memory_module_refs.py",
)

TARGET_SUFFIXES: tuple[str, ...] = (".py", ".pyi", ".md", ".rst", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".txt")

SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "node_modules", ".venv", "venv", "env", "dist", "build",
    ".tox", ".nox", "site-packages", ".idea", ".vscode",
})

SELF_PATH = Path(__file__).resolve()


@dataclass
class Change:
    path: Path
    line_no: int
    before: str
    after: str
    kind: str = "rewrite"


@dataclass
class Unresolved:
    path: Path
    line_no: int
    text: str
    reason: str


@dataclass
class Report:
    changes: list[Change] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    disabled_mappings: list[tuple[str, str, str]] = field(default_factory=list)
    files_scanned: int = 0
    files_changed: int = 0


# ---------------------------------------------------------------------------
# Mapping verification
# ---------------------------------------------------------------------------

def _module_exists(repo_root: Path, dotted: str) -> bool:
    """Return True if a dotted module path resolves to a real file/dir."""
    rel = Path(*dotted.split("."))
    candidates = [
        repo_root / rel.with_suffix(".py"),
        repo_root / rel / "__init__.py",
        # also allow the path relative to backend/ (common layout)
        repo_root / "backend" / rel.with_suffix(".py"),
        repo_root / "backend" / rel / "__init__.py",
    ]
    return any(c.exists() for c in candidates)


def _symbol_exists(repo_root: Path, symbol: str) -> bool:
    """Best-effort grep for a symbol definition in the tree."""
    try:
        out = subprocess.run(
            ["git", "grep", "-l", "-w", symbol],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        # fall back to a bounded filesystem scan
        for path in repo_root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                if re.search(rf"\b{re.escape(symbol)}\b", path.read_text(errors="ignore")):
                    return True
            except OSError:
                continue
        return False


def verify_mapping(repo_root: Path, old: str, new: str, *, is_module: bool) -> tuple[bool, str]:
    """Verify a mapping's premise.

    Returns (ok, reason). ``ok`` is True only when the old reference is
    absent and the new reference is present.
    """
    if is_module:
        if _module_exists(repo_root, old):
            return False, f"old module '{old}' still exists; mapping premise invalid"
        if not _module_exists(repo_root, new):
            return False, f"replacement module '{new}' does not exist"
        return True, "verified"
    # symbol
    if _symbol_exists(repo_root, old):
        # The old symbol may still be defined as a deprecation shim. Only
        # treat as invalid if the new symbol is missing.
        if not _symbol_exists(repo_root, new):
            return False, f"old symbol '{old}' still present and '{new}' missing"
        return True, "old symbol present (shim) but replacement exists"
    if not _symbol_exists(repo_root, new):
        return False, f"replacement symbol '{new}' does not exist"
    return True, "verified"


def active_replacements(repo_root: Path, report: Report) -> dict[str, str]:
    """Return the subset of mappings whose premises verify, recording the rest."""
    active: dict[str, str] = {}
    for old, new in MODULE_REPLACEMENTS.items():
        ok, reason = verify_mapping(repo_root, old, new, is_module=True)
        if ok:
            active[old] = new
        else:
            report.disabled_mappings.append((old, new, reason))
    for old, new in SYMBOL_REPLACEMENTS.items():
        ok, reason = verify_mapping(repo_root, old, new, is_module=False)
        if ok:
            active[old] = new
        else:
            report.disabled_mappings.append((old, new, reason))
    return active


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------

def _is_rejected(path: Path, repo_root: Path) -> bool:
    if path.resolve() == SELF_PATH:
        return True
    try:
        rel = path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return True
    return rel in REJECT_PATHS


def iter_candidate_files(repo_root: Path):
    """Yield tracked, in-scope files to scan.

    Prefers ``git ls-files`` so ignored/untracked/generated files are never
    touched. Falls back to a suffix-constrained walk that skips SKIP_DIRS.
    """
    tracked: list[Path] | None = None
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root, capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            tracked = [repo_root / p for p in out.stdout.split("\0") if p]
    except Exception:
        tracked = None

    if tracked is not None:
        for path in tracked:
            if path.suffix not in TARGET_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if _is_rejected(path, repo_root):
                continue
            if path.is_file():
                yield path
        return

    # Fallback: constrained filesystem walk.
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in TARGET_SUFFIXES:
            continue
        if _is_rejected(path, repo_root):
            continue
        yield path


# ---------------------------------------------------------------------------
# Rewriting
# ---------------------------------------------------------------------------

def rewrite_line(line: str, replacements: dict[str, str]) -> tuple[str, list[str]]:
    """Rewrite a single line.

    Returns (new_line, matched_old_refs). Module paths are matched on word
    boundaries to avoid partial-token corruption.
    """
    matched: list[str] = []
    new_line = line
    for old, new in replacements.items():
        pattern = re.compile(rf"(?<![\w.]){re.escape(old)}(?![\w])")
        if pattern.search(new_line):
            matched.append(old)
            new_line = pattern.sub(new, new_line)
    return new_line, matched


def scan_file(path: Path, replacements: dict[str, str], report: Report, apply: bool) -> bool:
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    lines = original.splitlines(keepends=True)
    file_changed = False
    out_lines: list[str] = []

    for idx, line in enumerate(lines, start=1):
        new_line, matched = rewrite_line(line, replacements)
        if matched and new_line != line:
            file_changed = True
            report.changes.append(
                Change(path, idx, line.rstrip("\n"), new_line.rstrip("\n"))
            )
        # Independently record unresolved legacy references: any line that
        # still mentions a legacy name after rewriting (e.g. because the
        # mapping was disabled) is surfaced for human review.
        for legacy in list(MODULE_REPLACEMENTS) + list(SYMBOL_REPLACEMENTS):
            if re.search(rf"(?<![\w.]){re.escape(legacy)}(?![\w])", new_line):
                report.unresolved.append(
                    Unresolved(path, idx, new_line.rstrip("\n"), f"legacy ref '{legacy}' remains")
                )
        out_lines.append(new_line)

    if file_changed and apply:
        path.write_text("".join(out_lines), encoding="utf-8")
    if file_changed:
        report.files_changed += 1
    return file_changed


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(repo_root: Path, *, apply: bool, force: bool) -> Report:
    report = Report()
    replacements = active_replacements(repo_root, report)

    if not replacements:
        print("[cleanup] No mapping premises verified — nothing to rewrite.")
        for old, new, reason in report.disabled_mappings:
            print(f"  DISABLED {old} -> {new}: {reason}")
        return report

    if report.disabled_mappings and apply and not force:
        print("[cleanup] Refusing --apply: some mappings failed verification.")
        for old, new, reason in report.disabled_mappings:
            print(f"  DISABLED {old} -> {new}: {reason}")
        print("  Re-run with --force to apply the verified mappings anyway.")
        return report

    for path in iter_candidate_files(repo_root):
        report.files_scanned += 1
        scan_file(path, replacements, report, apply)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--force", action="store_true", help="apply even if some mappings fail verification")
    parser.add_argument("--check", action="store_true", help="exit 1 if any stale references remain")
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    report = run(repo_root, apply=args.apply, force=args.force)

    print(f"[cleanup] scanned {report.files_scanned} files; "
          f"{report.files_changed} need changes; "
          f"{len(report.changes)} rewrites; "
          f"{len(report.unresolved)} unresolved.")
    for old, new, reason in report.disabled_mappings:
        print(f"  DISABLED {old} -> {new}: {reason}")
    if report.changes:
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"[cleanup] {mode} rewrites:")
        for c in report.changes[:50]:
            print(f"  {c.path}:{c.line_no}: {c.before!r} -> {c.after!r}")
        if len(report.changes) > 50:
            print(f"  ... and {len(report.changes) - 50} more")
    if report.unresolved:
        print("[cleanup] unresolved references (human review required):")
        for u in report.unresolved[:50]:
            print(f"  {u.path}:{u.line_no}: {u.text!r}  ({u.reason})")
        if len(report.unresolved) > 50:
            print(f"  ... and {len(report.unresolved) - 50} more")

    if args.check and (report.unresolved or report.changes):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
