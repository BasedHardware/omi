#!/usr/bin/env python3
"""Freeze growth of oversized product-source files.

This diff-scoped ratchet covers Swift and Rust under ``desktop/macos/`` and
Python under ``backend/``. Files at or above 1,500 lines are pinned to their
checked-in count. Smaller files remain free to evolve, but cannot cross the
threshold without an explicit, reviewable baseline raise.

The committed baseline contains only files currently at or above the threshold.
After a split, run this checker with ``--update-baseline`` to remove or lower
the affected entry automatically; that mode never raises a limit. Intentional
raises are exceptional: edit the JSON in the same diff as the source and add a
single-line ``raise_justifications`` entry for the path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

THRESHOLD = 1500
BASELINE_RELATIVE = ".github/scripts/product_file_line_count_ratchet_baseline.json"
DESKTOP_ROOT = "desktop/macos/"
BACKEND_ROOT = "backend/"
VENDORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "vendor",
    "vendored",
    "third_party",
    "third-party",
    "node_modules",
    "Pods",
    "Carthage",
    "target",
}
TEST_PARTS = {"test", "tests", "Tests"}


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def is_product_source(relative: str) -> bool:
    """Return whether a repository-relative path belongs to the guarded scope."""
    path = PurePosixPath(relative)
    parts = path.parts
    if any(part in VENDORED_PARTS or part == "Generated" for part in parts):
        return False
    if any(part in TEST_PARTS for part in parts):
        return False
    name = path.name
    if ".gen." in name or ".g." in name or name.startswith("test_") or name.endswith("_test.py"):
        return False
    if relative.startswith(BACKEND_ROOT):
        return path.suffix == ".py"
    if relative.startswith(DESKTOP_ROOT):
        return path.suffix in {".swift", ".rs"}
    return False


def line_count(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    return source.count("\n") + (0 if not source or source.endswith("\n") else 1)


def baseline_path(root: Path) -> Path:
    return root / BASELINE_RELATIVE


def validate_baseline(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"files", "raise_justifications", "threshold"}:
        raise ValueError("baseline must contain exactly files, raise_justifications, and threshold")
    if value["threshold"] != THRESHOLD:
        raise ValueError(f"baseline threshold must be {THRESHOLD}")
    files = value["files"]
    justifications = value["raise_justifications"]
    if not isinstance(files, dict) or not isinstance(justifications, dict):
        raise ValueError("baseline files and raise_justifications must be objects")
    for relative, count in files.items():
        if not isinstance(relative, str) or not is_product_source(relative):
            raise ValueError(f"baseline contains unsupported source path: {relative!r}")
        if not isinstance(count, int) or isinstance(count, bool) or count < THRESHOLD:
            raise ValueError(f"baseline count for {relative} must be an integer at least {THRESHOLD}")
    for relative, justification in justifications.items():
        if relative not in files:
            raise ValueError(f"raise justification without a baseline entry: {relative}")
        if not isinstance(justification, str) or not justification.strip() or "\n" in justification:
            raise ValueError(f"raise justification for {relative} must be one non-empty line")
    return value


def load_baseline(root: Path) -> dict[str, Any]:
    try:
        return validate_baseline(json.loads(baseline_path(root).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid line-count ratchet baseline: {error}") from error


def write_baseline(root: Path, baseline: dict[str, Any]) -> None:
    validate_baseline(baseline)
    baseline_path(root).write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_changed_files(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def changed_product_sources(changed: set[str]) -> list[str]:
    return sorted(relative for relative in changed if is_product_source(relative))


def source_count(root: Path, relative: str) -> int | None:
    path = root / relative
    return line_count(path) if path.is_file() else None


def check_changed_sources(
    root: Path, baseline: dict[str, Any], changed: set[str]
) -> tuple[list[str], dict[str, int | None]]:
    """Return growth failures and the safe downward updates they require."""
    failures: list[str] = []
    downward: dict[str, int | None] = {}
    for relative in changed_product_sources(changed):
        current = source_count(root, relative)
        recorded = baseline["files"].get(relative)
        if current is None:
            if recorded is not None:
                downward[relative] = None
            continue
        if current < THRESHOLD:
            if recorded is not None:
                downward[relative] = None
            continue
        if recorded is None:
            failures.append(
                f"{relative}: {current} lines has no baseline entry. Split the file, or add its exact count "
                f"and a one-line raise_justifications entry to {BASELINE_RELATIVE} in this PR."
            )
        elif current > recorded:
            failures.append(
                f"{relative}: grew from baseline {recorded} to {current} lines. Split the file, or raise its "
                f"exact baseline with a one-line justification in {BASELINE_RELATIVE}."
            )
        elif current < recorded:
            downward[relative] = current
    return failures, downward


def baseline_transition_errors(
    root: Path, previous: dict[str, Any] | None, current: dict[str, Any], changed: set[str]
) -> list[str]:
    """Ensure explicit raises and baseline removals remain tied to source changes."""
    if previous is None:
        return []

    failures: list[str] = []
    old_files = previous["files"]
    new_files = current["files"]
    for relative, new_count in new_files.items():
        old_count = old_files.get(relative)
        if old_count is not None and new_count <= old_count:
            continue
        actual = source_count(root, relative)
        if relative not in changed:
            failures.append(f"{relative}: a baseline raise must include the source file in the PR diff")
        if actual != new_count:
            failures.append(
                f"{relative}: raised baseline {new_count} must exactly match the changed source count {actual}"
            )
        if relative not in current["raise_justifications"]:
            failures.append(f"{relative}: a baseline raise requires a one-line raise_justifications entry")

    for relative, old_count in old_files.items():
        new_count = new_files.get(relative)
        if new_count is not None and new_count >= old_count:
            continue
        actual = source_count(root, relative)
        if relative not in changed:
            failures.append(f"{relative}: lowering or removing a baseline requires the source file in the PR diff")
        if new_count is None:
            if actual is not None and actual >= THRESHOLD:
                failures.append(f"{relative}: cannot remove the baseline while the source remains oversized")
        elif actual != new_count:
            failures.append(
                f"{relative}: lowered baseline {new_count} must exactly match the changed source count {actual}"
            )
    return failures


def baseline_at_ref(root: Path, ref: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{BASELINE_RELATIVE}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return None
    try:
        return validate_baseline(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid baseline at {ref}: {error}") from error


def update_downward(root: Path, baseline: dict[str, Any], changed: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Return a baseline with only safe decreases/removals applied."""
    updated = {
        "threshold": THRESHOLD,
        "files": dict(baseline["files"]),
        "raise_justifications": dict(baseline["raise_justifications"]),
    }
    failures, downward = check_changed_sources(root, baseline, changed)
    if failures:
        return updated, failures
    for relative, count in downward.items():
        if count is None:
            updated["files"].pop(relative, None)
            updated["raise_justifications"].pop(relative, None)
        else:
            updated["files"][relative] = count
    return updated, []


def initial_baseline(root: Path) -> dict[str, Any]:
    files: dict[str, int] = {}
    for prefix in (BACKEND_ROOT, DESKTOP_ROOT):
        for path in (root / prefix).rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if is_product_source(relative):
                count = line_count(path)
                if count >= THRESHOLD:
                    files[relative] = count
    return {"threshold": THRESHOLD, "files": files, "raise_justifications": {}}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Repository root (default: inferred from this script)")
    parser.add_argument("--changed-files", type=Path, help="Newline-delimited repository-relative changed paths")
    parser.add_argument("--base", help="Git ref used to validate explicit baseline raises")
    parser.add_argument("--bootstrap", action="store_true", help="Create the initial snapshot when no baseline exists")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite only downward entries for changed source files; never raises a count",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    path = baseline_path(root)
    if args.bootstrap:
        if args.changed_files or args.update_baseline or path.exists():
            print(
                "FAIL: --bootstrap requires no existing baseline and cannot be combined with other modes",
                file=sys.stderr,
            )
            return 2
        write_baseline(root, initial_baseline(root))
        print(f"Wrote initial oversized-file snapshot to {BASELINE_RELATIVE}.")
        return 0
    if not args.changed_files:
        print("FAIL: --changed-files is required outside --bootstrap mode", file=sys.stderr)
        return 2

    try:
        changed = read_changed_files(args.changed_files)
        baseline = load_baseline(root)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2

    if args.update_baseline:
        updated, failures = update_downward(root, baseline, changed)
        if failures:
            print("FAIL: refusing to raise the line-count baseline", file=sys.stderr)
            print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
            return 1
        if updated == baseline:
            print("OK: no oversized-file baseline reduction is needed.")
            return 0
        write_baseline(root, updated)
        print(f"Updated {BASELINE_RELATIVE} downward; stage the generated baseline with the source split.")
        return 0

    try:
        previous = baseline_at_ref(root, args.base) if args.base else None
        failures = baseline_transition_errors(root, previous, baseline, changed)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    growth_failures, downward = check_changed_sources(root, baseline, changed)
    failures.extend(growth_failures)
    if downward:
        files = ", ".join(sorted(downward))
        failures.append(
            f"baseline must ratchet down for {files}; run this checker with --update-baseline and stage the result"
        )
    if failures:
        print("FAIL: product file line-count ratchet", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"OK: no line-count increase across {len(changed_product_sources(changed))} changed product source file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
