#!/usr/bin/env python3
"""Static anti-regrowth guard for the desktop agent convergence boundary.

The lifecycle reducer and context-plan decision core must remain independently
testable.  This script deliberately checks only static boundaries: behavioral
coverage lives in the Swift/Node fixture and sequence-fuzzer suites.

The two historic coordinator files get 10% post-convergence line headroom for
near-term deletion/migration work.  Raising a limit requires an issue URL or
invariant ID and is recorded in the committed baseline file.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from pathlib import Path

TARGETS = (
    "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
    "desktop/macos/Desktop/Sources/Chat/AgentRuntimeProcess.swift",
)
EXTRACTED_DECISION_CORES = ("AgentRuntimeBridgeLifecycle", "AgentConversationContextPlan")
DECLARATION = re.compile(r"^\s*(?:final\s+)?(?:struct|enum|class|actor)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[3]


def baseline_path(root: Path) -> Path:
    return root / "desktop/macos/scripts/agent-runtime-convergence-ratchet.json"


def load_baseline(root: Path) -> dict:
    path = baseline_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"FAIL: invalid convergence ratchet baseline: {error}") from error
    if set(value.get("limits", {})) != set(TARGETS):
        raise SystemExit("FAIL: convergence ratchet baseline targets drifted")
    return value


def check(root: Path, baseline: dict) -> list[str]:
    failures: list[str] = []
    for relative in TARGETS:
        path = root / relative
        if not path.is_file():
            failures.append(f"missing guarded source: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        limit = baseline["limits"][relative]
        if line_count > limit:
            failures.append(f"{relative} is {line_count} lines (limit {limit})")
        declarations = set(DECLARATION.findall(text))
        forbidden = declarations.intersection(EXTRACTED_DECISION_CORES)
        if forbidden:
            failures.append(f"{relative} re-declares extracted decision core(s): {', '.join(sorted(forbidden))}")
    return failures


def self_test() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for relative in TARGETS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("struct SafeProjection {}\n", encoding="utf-8")
        baseline = {"limits": {relative: 1 for relative in TARGETS}}
        if check(root, baseline):
            print("FAIL: ratchet self-test rejected a safe fixture", file=sys.stderr)
            return 1
        for decision_core in EXTRACTED_DECISION_CORES:
            guarded = root / TARGETS[0]
            guarded.write_text(f"struct {decision_core} {{}}\n", encoding="utf-8")
            if not check(root, baseline):
                print("FAIL: ratchet self-test accepted a reintroduced decision core", file=sys.stderr)
                return 1
            guarded.write_text("struct SafeProjection {}\n", encoding="utf-8")
    print("OK: convergence ratchet self-test")
    return 0


def update_baseline(root: Path, justification: str) -> int:
    if not (justification.startswith("http") or justification.startswith("INV-")):
        print("FAIL: --justification must be a tracking issue URL or invariant ID", file=sys.stderr)
        return 2
    baseline = load_baseline(root)
    for relative in TARGETS:
        count = len((root / relative).read_text(encoding="utf-8").splitlines())
        baseline["limits"][relative] = math.ceil(count * 1.10)
    baseline.setdefault("raise_justifications", {})[justification] = "intentional post-review convergence headroom"
    baseline_path(root).write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Updated convergence ratchet with justification {justification}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--justification")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = repo_root(args.root)
    if args.update_baseline:
        return update_baseline(root, args.justification or "")
    failures = check(root, load_baseline(root))
    if failures:
        print("FAIL: agent runtime convergence ratchet", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print("OK: agent runtime convergence boundary and line-count ratchets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
