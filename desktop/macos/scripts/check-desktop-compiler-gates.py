#!/usr/bin/env python3
"""Fail closed on compiler-version gates that hide Apple SDK APIs from the ship toolchain.

PR #12867 shipped a Liquid Glass tab bar that only compiled on a local Xcode 26:
the glass APIs sat behind ``#if compiler(>=6.2)`` while desktop CI compiled with
Xcode 16.4, so every CI lane stayed green while the shipped binary silently
built the icon-less system Picker fallback (reverted in #13548). The desktop
ship/CI toolchain is now pinned (``desktop/macos/ci/xcode-pin.json``); the
policy this tripwire enforces is: every Apple SDK / SwiftUI API the app ships
must be typechecked by that pinned toolchain. Gate OS availability at RUNTIME
(``if #available(macOS 26, *)`` plus a working fallback, per the deployment
floor rules in desktop AGENTS) — never at COMPILE TIME with
``#if compiler(...)``/``#elseif compiler(...)``.

This is a narrow forbidden-pattern static tripwire (the exception desktop
AGENTS "Swift test quality" allows), not behavioral coverage; the pinned-Xcode
compile remains the authoritative typecheck.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DESKTOP_ROOT = SCRIPT_DIR.parent / "Desktop"

COMPILER_GATE_RE = re.compile(r"^\s*#(?:if|elseif)\s+compiler\s*\(")
SCANNED_SUBROOTS = ("Sources", "Tests")


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    line: str

    def describe(self, root: Path) -> str:
        relative = self.path.relative_to(root)
        return f"{relative}:{self.line_number}: {self.line.strip()}"


@dataclass(frozen=True)
class AllowlistEntry:
    """A documented, one-line exception to the no-compiler-gate policy.

    Adding an entry requires updating the exact-contents assertion in
    .github/scripts/test_check_desktop_compiler_gates.py in the same change,
    so the allowlist cannot silently grow.
    """

    relative_path: str
    line_contains: str
    reason: str


# Empty by default. Only genuine language-version exceptions belong here —
# never a convenience escape hatch for an API the pinned SDK typechecks fine.
ALLOWED_COMPILER_GATES: tuple[AllowlistEntry, ...] = ()


def _is_allowed(finding: Finding, root: Path, allowlist: tuple[AllowlistEntry, ...]) -> bool:
    try:
        relative = str(finding.path.relative_to(root))
    except ValueError:
        relative = finding.path.name
    return any(
        entry.relative_path == relative and entry.line_contains in finding.line
        for entry in allowlist
    )


def find_compiler_gates(path: Path) -> list[Finding]:
    """Return every active ``#if compiler(...)``/``#elseif compiler(...)`` line."""
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if COMPILER_GATE_RE.match(line):
            findings.append(Finding(path=path, line_number=line_number, line=line))
    return findings


def find_all_compiler_gates(
    desktop_root: Path, allowlist: tuple[AllowlistEntry, ...] = ALLOWED_COMPILER_GATES
) -> tuple[list[Finding], list[Finding]]:
    """Scan Sources/ and Tests/; return (violations, allowed findings)."""
    violations: list[Finding] = []
    allowed: list[Finding] = []
    for subroot in SCANNED_SUBROOTS:
        tree = desktop_root / subroot
        if not tree.is_dir():
            continue
        for path in sorted(tree.rglob("*.swift")):
            for finding in find_compiler_gates(path):
                if _is_allowed(finding, desktop_root, allowlist):
                    allowed.append(finding)
                else:
                    violations.append(finding)
    return violations, allowed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_DESKTOP_ROOT,
        help="Desktop package root containing Sources/ and Tests/ (default: the real tree)",
    )
    args = parser.parse_args()

    violations, allowed = find_all_compiler_gates(args.root)
    for finding in allowed:
        print(f"allowed compiler gate: {finding.describe(args.root)}")
    if violations:
        print(
            "FAIL: compiler-version gates compile Apple SDK APIs out of the pinned ship "
            "toolchain (the #12867/#13548 class). Gate OS availability at runtime with "
            "`if #available(macOS X, *)` plus a working fallback instead:",
            file=sys.stderr,
        )
        for finding in violations:
            print(f"  {finding.describe(args.root)}", file=sys.stderr)
        return 1
    print("desktop compiler gates: none found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
