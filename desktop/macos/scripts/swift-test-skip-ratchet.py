#!/usr/bin/env python3
"""Validate and expose the known-red Swift XCTest method skip list.

The skip list is intentionally machine-readable and ratcheted: adding a skipped
method without also making an explicit baseline change fails this check. The
ratchet stores both the current count and the exact allowed skipped test IDs so
same-count swaps do not silently introduce a new known-red test.
Removing skips is allowed and should be followed by lowering max_skip_count.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_SKIP_FILE = Path(__file__).with_name("swift-test-skips.json")
DEFAULT_TESTS_ROOT = Path(__file__).resolve().parents[1] / "Desktop" / "Tests"
TEST_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*/test[A-Za-z0-9_]+$")
METHOD_RE_TEMPLATE = r"\bfunc\s+{method}\s*\("


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-file", default=str(DEFAULT_SKIP_FILE), help="Path to swift-test-skips.json.")
    parser.add_argument(
        "--tests-root",
        default=str(DEFAULT_TESTS_ROOT),
        help="Desktop Swift tests root used to verify skipped methods still exist.",
    )
    parser.add_argument("--check", action="store_true", help="Validate the ratchet file and skipped test existence.")
    parser.add_argument("--args-for-suite", metavar="SUITE", help="Print SwiftPM --skip arguments for one suite.")
    parser.add_argument("--list", action="store_true", help="Print skipped test identifiers, one per line.")
    return parser.parse_args()


def load_skip_file(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("skip file must contain a JSON object")
    return data


def normalized_skips(data: dict[str, Any]) -> list[dict[str, str]]:
    raw_skips = data.get("skips")
    if not isinstance(raw_skips, list):
        raise ValueError("skip file must contain a skips array")

    skips: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_skip in enumerate(raw_skips):
        if not isinstance(raw_skip, dict):
            raise ValueError(f"skips[{index}] must be an object")
        skip = {}
        for key in ("test", "issue", "reason"):
            value = raw_skip.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"skips[{index}].{key} must be a non-empty string")
            skip[key] = value.strip()
        if not TEST_ID_RE.match(skip["test"]):
            raise ValueError(f"skips[{index}].test must look like SuiteName/testMethodName")
        if skip["test"] in seen:
            raise ValueError(f"duplicate skipped test: {skip['test']}")
        seen.add(skip["test"])
        skips.append(skip)
    return skips


def validate_ratchet(data: dict[str, Any], skips: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    max_skip_count = data.get("max_skip_count")
    if not isinstance(max_skip_count, int) or max_skip_count < 0:
        errors.append("max_skip_count must be a non-negative integer")
    elif len(skips) > max_skip_count:
        errors.append(f"skip count rose to {len(skips)} (max_skip_count {max_skip_count})")

    raw_allowed = data.get("allowed_tests")
    if not isinstance(raw_allowed, list):
        errors.append("allowed_tests must list the exact ratcheted skipped test IDs")
        return errors
    allowed: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_allowed):
        if not isinstance(value, str) or not TEST_ID_RE.match(value):
            errors.append(f"allowed_tests[{index}] must look like SuiteName/testMethodName")
            continue
        if value in seen:
            errors.append(f"duplicate allowed skipped test: {value}")
        seen.add(value)
        allowed.append(value)
    skip_ids = [skip["test"] for skip in skips]
    new_skips = sorted(set(skip_ids) - set(allowed))
    stale_allowed = sorted(set(allowed) - set(skip_ids))
    if new_skips:
        errors.append(
            "new skipped test IDs are not in the ratcheted baseline: " + ", ".join(new_skips)
        )
    if stale_allowed:
        errors.append(
            "allowed_tests contains IDs not present in skips; remove them to ratchet the gain: "
            + ", ".join(stale_allowed)
        )
    return errors


def validate_skipped_methods_exist(tests_root: Path, skips: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    files_by_suite: dict[str, list[Path]] = {}
    if not tests_root.exists():
        errors.append(f"tests root does not exist: {tests_root}")
        return errors

    for path in sorted(tests_root.rglob("*.swift")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for suite in {skip["test"].split("/", 1)[0] for skip in skips}:
            if re.search(rf"\b(class|extension)\s+{re.escape(suite)}\b", text):
                files_by_suite.setdefault(suite, []).append(path)

    for skip in skips:
        suite, method = skip["test"].split("/", 1)
        files = files_by_suite.get(suite, [])
        method_re = re.compile(METHOD_RE_TEMPLATE.format(method=re.escape(method)))
        if not files:
            errors.append(f"skipped suite no longer exists: {suite}")
            continue
        if not any(method_re.search(path.read_text(encoding="utf-8")) for path in files):
            errors.append(f"skipped method no longer exists: {skip['test']}")
    return errors


def main() -> int:
    args = parse_args()
    try:
        data = load_skip_file(Path(args.skip_file))
        skips = normalized_skips(data)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.args_for_suite:
        suite = args.args_for_suite
        for skip in skips:
            if skip["test"].split("/", 1)[0] == suite:
                print("--skip")
                print(skip["test"])
        return 0

    if args.list:
        for skip in skips:
            print(skip["test"])
        return 0

    errors = validate_ratchet(data, skips)
    errors.extend(validate_skipped_methods_exist(Path(args.tests_root), skips))
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(
            "Swift XCTest method skips are ratcheted in "
            "desktop/macos/scripts/swift-test-skips.json; fix the test or make "
            "an explicit ratchet change with an issue and reason.",
            file=sys.stderr,
        )
        return 1

    max_skip_count = data["max_skip_count"]
    if len(skips) < max_skip_count:
        print(
            f"NOTE: Swift XCTest method skips dropped to {len(skips)} "
            f"(max_skip_count {max_skip_count}). Lower max_skip_count to ratchet the gain."
        )
    else:
        print(f"OK: Swift XCTest method skips at ratchet ({len(skips)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
