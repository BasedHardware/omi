#!/usr/bin/env python3
"""Enforce that the root AGENTS.md stays lean (high-level guidance + index).

Root AGENTS.md is loaded into every agent session for every task, so every line
costs context in every session. Detail belongs in the component guides
(backend/AGENTS.md, app/AGENTS.md, desktop/macos/AGENTS.md, omi/firmware/AGENTS.md)
or docs/, which agents load just-in-time.

Budgets are a ratchet: shrink them when the file shrinks; never raise them to
admit new detail that has a component-guide home.
"""

import sys
import tempfile
from pathlib import Path

MAX_LINES = 180
MAX_BYTES = 18_000

FAILURE_HINT = (
    "Root AGENTS.md must stay lean: it is loaded into every agent session.\n"
    "Move detail into the matching component guide (backend/AGENTS.md,\n"
    "app/AGENTS.md, desktop/macos/AGENTS.md, omi/firmware/AGENTS.md) or docs/,\n"
    "and keep only the high-level rule plus a pointer here.\n"
    "Do not raise the budget to admit detail that has a component-guide home."
)


def check(path: Path) -> list[str]:
    data = path.read_bytes()
    lines = data.decode("utf-8").count("\n") + (0 if data.endswith(b"\n") else 1)
    errors = []
    if lines > MAX_LINES:
        errors.append(f"{path}: {lines} lines exceeds budget of {MAX_LINES}")
    if len(data) > MAX_BYTES:
        errors.append(f"{path}: {len(data)} bytes exceeds budget of {MAX_BYTES}")
    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        small = Path(tmp) / "small.md"
        small.write_text("# ok\n")
        assert check(small) == [], "lean file must pass"

        long_file = Path(tmp) / "long.md"
        long_file.write_text("x\n" * (MAX_LINES + 1))
        assert any("lines" in e for e in check(long_file)), "over-lines must fail"

        fat = Path(tmp) / "fat.md"
        fat.write_text("y" * (MAX_BYTES + 1))
        assert any("bytes" in e for e in check(fat)), "over-bytes must fail"


def main() -> int:
    self_test()
    root = Path(__file__).resolve().parents[2]
    target = root / "AGENTS.md"
    if not target.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 1
    errors = check(target)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(FAILURE_HINT, file=sys.stderr)
        return 1
    print(f"ok: AGENTS.md within budget ({MAX_LINES} lines / {MAX_BYTES} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
