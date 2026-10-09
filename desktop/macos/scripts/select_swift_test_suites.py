#!/usr/bin/env python3
"""Record a conservative test-only PR suite subset; shadow by default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SMOKE_SUITES = frozenset({"APIClientRoutingTests", "AuthRefreshResilienceTests", "ChatDiscoverabilityTests"})
TEST_PREFIX = "desktop/macos/Desktop/Tests/"


def select(suite_map: dict[str, set[str]], runnable: list[str], changed: list[str]) -> tuple[list[str], str]:
    # Source, manifest, runner, deletion, or unknown changes retain the full
    # contract. Only a PR changing known test declarations alone can narrow.
    if not changed or any(not path.startswith(TEST_PREFIX) or not path.endswith(".swift") for path in changed):
        return runnable, "non-test or unknown input: full"
    selected = {suite for suite, files in suite_map.items() if any(TEST_PREFIX + file in changed for file in files)}
    if not selected or any(path not in {TEST_PREFIX + file for files in suite_map.values() for file in files} for path in changed):
        return runnable, "unmapped test input: full"
    selected.update(SMOKE_SUITES)
    return [suite for suite in runnable if suite in selected], "known test-only input"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-map", type=Path, required=True)
    parser.add_argument("--runnable", type=Path, required=True)
    parser.add_argument("--changed", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--mode", choices=("shadow", "on"), default="shadow")
    args = parser.parse_args()
    suite_map: dict[str, set[str]] = {}
    for line in args.suite_map.read_text().splitlines():
        suite, file = line.split("\t", 1)
        suite_map.setdefault(suite, set()).add(file)
    runnable = args.runnable.read_text().splitlines()
    changed = args.changed.read_text().splitlines()
    selected, reason = select(suite_map, runnable, changed)
    args.selected.write_text("".join(f"{suite}\n" for suite in selected))
    args.record.write_text(json.dumps({"schema": 1, "mode": args.mode, "reason": reason,
                                      "changed_files": changed, "runnable_suites": runnable,
                                      "selected_suites": selected}, indent=2) + "\n")
    print(f"Swift suite shadow selection: {len(selected)}/{len(runnable)} ({reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
