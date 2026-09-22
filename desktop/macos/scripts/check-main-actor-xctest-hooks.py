#!/usr/bin/env python3
"""Reject an Xcode 16.4 XCTest concurrency error before a full Swift build.

``XCTestCase.setUp()/tearDown()`` are nonisolated in the pinned SDK. Calling
their async forms from an ``@MainActor XCTestCase`` transfers the non-Sendable
test instance across actors, which Swift 6 correctly rejects. This is a static
tripwire for that narrow compiler failure; the full Swift test compile remains
the authoritative concurrency check.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TESTS_ROOT = SCRIPT_DIR.parent / "Desktop/Tests"

CLASS_RE = re.compile(
    r"^\s*(?P<inline_actor>@MainActor\s+)?(?:public\s+|internal\s+|private\s+|fileprivate\s+)?"
    r"(?:final\s+)?class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*.*\bXCTestCase\b"
)
MAIN_ACTOR_RE = re.compile(r"^\s*@MainActor\s*$")
ASYNC_SUPER_HOOK_RE = re.compile(r"^\s*try\s+await\s+super\.(?P<hook>setUp|tearDown)\(\)\s*$")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    class_name: str
    hook: str


def _brace_delta(line: str) -> int:
    """Return a sufficient brace delta for test class source declarations."""
    code = line.split("//", maxsplit=1)[0]
    return code.count("{") - code.count("}")


def find_unsafe_hooks(path: Path) -> list[Finding]:
    """Find async XCTest superclass hooks called from an ``@MainActor`` class."""
    findings: list[Finding] = []
    pending_main_actor = False
    actor_class_name: str | None = None
    actor_class_depth = 0

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if actor_class_name is not None:
            hook_match = ASYNC_SUPER_HOOK_RE.match(line)
            if hook_match:
                findings.append(
                    Finding(path=path, line=line_number, class_name=actor_class_name, hook=hook_match.group("hook"))
                )
            actor_class_depth += _brace_delta(line)
            if actor_class_depth <= 0:
                actor_class_name = None
            continue

        if MAIN_ACTOR_RE.match(line):
            pending_main_actor = True
            continue

        class_match = CLASS_RE.match(line)
        if class_match:
            is_main_actor = pending_main_actor or class_match.group("inline_actor") is not None
            pending_main_actor = False
            if is_main_actor:
                actor_class_name = class_match.group("name")
                actor_class_depth = _brace_delta(line)
                if actor_class_depth <= 0:
                    actor_class_name = None
            continue

        stripped = line.strip()
        if stripped and not stripped.startswith("//") and not stripped.startswith("@"):
            pending_main_actor = False

    return findings


def find_all_unsafe_hooks(tests_root: Path) -> list[Finding]:
    return [finding for path in sorted(tests_root.rglob("*.swift")) for finding in find_unsafe_hooks(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests-root", type=Path, default=DEFAULT_TESTS_ROOT)
    args = parser.parse_args()
    findings = find_all_unsafe_hooks(args.tests_root)
    if findings:
        for finding in findings:
            print(
                f"FAIL: {finding.path}:{finding.line}: @MainActor XCTestCase "
                f"{finding.class_name} must not call try await super.{finding.hook}()",
                file=sys.stderr,
            )
        return 1
    print("OK: @MainActor XCTestCase lifecycle hooks are Xcode 16.4-safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
