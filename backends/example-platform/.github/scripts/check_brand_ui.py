#!/usr/bin/env python3
"""INV-UI-1: no-increase ratchet on purple UI literals in changed files.

Compares purple-hit counts in changed UI sources against the merge base.
Existing debt may remain; introducing new purple (raising a file's count, or
adding purple in a new file) fails.

Allowlist: paths in ALLOWLIST_FILES are skipped (document why in a comment here).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

UI_ROOTS = (
    "desktop/macos/Desktop/Sources/",
    "app/lib/",
    "web/",
)
UI_SUFFIXES = {".swift", ".dart", ".ts", ".tsx", ".js", ".jsx", ".css"}
SKIP_PARTS = {".git", "node_modules", "build", "dist", ".next", "__pycache__"}

# Paths exempt from the ratchet (legacy debt being migrated, generated, etc.).
# Prefer shrinking this list; do not grow it without citing INV-UI-1 in the PR.
ALLOWLIST_FILES: set[str] = {
    # Theme token definitions still expose purple* names during migration.
    "desktop/macos/Desktop/Sources/Theme/OmiColors.swift",
}

PURPLE_PATTERNS = [
    re.compile(r"Color\.purple\b"),
    re.compile(r"\.purple\b"),  # SwiftUI shorthand: .foregroundStyle(.purple)
    re.compile(r"Colors\.purple\b"),  # Flutter
    re.compile(r"#(?:7C3AED|8B5CF6|A855F7|9333EA|6D28D9|AF52DE|D946EF|A78BFA|C4B5FD)\b", re.I),
    re.compile(r"purple(?:Primary|Secondary|Accent|Light|Gradient|LightGradient)\b"),
    re.compile(r"purple-(?:primary|secondary|accent|\d{2,4})\b"),  # Tailwind: bg-purple-500 etc.
    re.compile(r"--purple-"),
    re.compile(r"""['"]Purple['"]"""),
    re.compile(r"""\bpurple\b""", re.I),  # CSS: color: purple; also catches bare "purple" references
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", required=True, help="File listing changed paths.")
    parser.add_argument(
        "--base",
        default=None,
        help="Git ref for the merge base content (required for ratchet vs base).",
    )
    parser.add_argument("--root", default=".", help="Repository root.")
    return parser.parse_args()


def is_ui_source(path: str) -> bool:
    if path in ALLOWLIST_FILES:
        return False
    if not any(path.startswith(prefix) for prefix in UI_ROOTS):
        return False
    if Path(path).suffix not in UI_SUFFIXES:
        return False
    parts = set(Path(path).parts)
    if parts & SKIP_PARTS:
        return False
    return True


def count_purple(text: str) -> int:
    return sum(len(p.findall(text)) for p in PURPLE_PATTERNS)


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    changed = [
        line.strip()
        for line in Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        if line.strip() and is_ui_source(line.strip())
    ]
    if not changed:
        print("OK: no UI sources in changed files for INV-UI-1.")
        return 0
    if not args.base:
        print("FAIL: --base is required for the brand UI ratchet.")
        return 1

    regressions: list[str] = []
    for path in changed:
        head_file = root / path
        if not head_file.is_file():
            continue
        head_text = head_file.read_text(encoding="utf-8", errors="ignore")
        head_count = count_purple(head_text)
        base_text = git_show(args.base, path)
        base_count = count_purple(base_text) if base_text is not None else 0
        if head_count > base_count:
            regressions.append(f"{path}: purple hits {base_count} → {head_count}")

    if regressions:
        print("FAIL: INV-UI-1 — purple usage increased in changed UI files.")
        print("Purple is off-brand. Use white/neutral accents. See docs/product/invariants/brand-ui.md")
        for line in regressions:
            print(f"  - {line}")
        return 1

    print(f"OK: INV-UI-1 — no purple increase across {len(changed)} changed UI file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
