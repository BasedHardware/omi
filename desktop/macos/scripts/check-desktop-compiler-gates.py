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

DIRECTIVE_RE = re.compile(r"^\s*#(?:if|elseif)\b(.*)$")
COMPILER_CALL_RE = re.compile(r"\bcompiler\s*\(")
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


def _active_code_lines(text: str) -> list[tuple[int, str]]:
    """Yield (line_number, code) with Swift strings and comments stripped.

    Line numbers stay aligned with the original file so findings point at the
    directive, not at a collapsed buffer. Nested ``/* */`` is Swift-legal.
    """
    lines = text.splitlines()
    active: list[tuple[int, str]] = []
    in_block = 0
    in_string: str | None = None
    for line_number, original in enumerate(lines, start=1):
        out: list[str] = []
        i = 0
        while i < len(original):
            ch = original[i]
            nxt = original[i + 1] if i + 1 < len(original) else ""
            if in_string:
                out.append(" ")
                if ch == "\\" and nxt:
                    i += 2
                    continue
                if ch == in_string:
                    in_string = None
                i += 1
                continue
            if in_block:
                if ch == "*" and nxt == "/":
                    in_block -= 1
                    i += 2
                    continue
                if ch == "/" and nxt == "*":
                    in_block += 1
                    i += 2
                    continue
                i += 1
                continue
            if ch == "/" and nxt == "/":
                break
            if ch == "/" and nxt == "*":
                in_block += 1
                i += 2
                continue
            if ch in "\"'":
                in_string = ch
                out.append(" ")
                i += 1
                continue
            out.append(ch)
            i += 1
        active.append((line_number, "".join(out)))
    return active


def find_compiler_gates(path: Path) -> list[Finding]:
    """Return every active ``#if``/``#elseif`` whose condition calls ``compiler(``."""
    findings: list[Finding] = []
    original_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    text = "\n".join(original_lines)
    for line_number, active in _active_code_lines(text):
        match = DIRECTIVE_RE.match(active)
        if not match:
            continue
        if not COMPILER_CALL_RE.search(match.group(1)):
            continue
        raw = original_lines[line_number - 1] if 0 < line_number <= len(original_lines) else active
        findings.append(Finding(path=path, line_number=line_number, line=raw))
    return findings


def scan_root_errors(desktop_root: Path) -> list[str]:
    """Fail closed when the checker would otherwise scan nothing."""
    present = [name for name in SCANNED_SUBROOTS if (desktop_root / name).is_dir()]
    if not present:
        return [f"missing Sources/ and Tests/ under {desktop_root}"]
    swift_count = sum(1 for name in present for _ in (desktop_root / name).rglob("*.swift"))
    if swift_count == 0:
        return [f"no .swift files under {desktop_root}/Sources or Tests"]
    return []


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
    root_errors = scan_root_errors(args.root)
    if root_errors:
        print("FAIL: compiler-gate checker scanned nothing:", file=sys.stderr)
        for error in root_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

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
