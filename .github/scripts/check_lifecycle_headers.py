#!/usr/bin/env python3
"""Enforce lifecycle headers for rollout and operational scaffolding."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASELINE_PATH = ".github/lifecycle-header-baseline.txt"
HEADER_LINE_LIMIT = 32
LIFECYCLE_VALUES = {"one-time", "permanent"}
ISSUE_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/issues/\d+(?:[?#][^\s]*)?$")
INVARIANT_ID_RE = re.compile(r"INV-[A-Z0-9]+-\d+$")
SKIP_DIRECTORY_NAMES = {"__pycache__"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", required=True, help="File containing changed repository-relative paths.")
    parser.add_argument("--baseline", default=BASELINE_PATH, help="Repository-relative lifecycle baseline path.")
    parser.add_argument("--root", default=".", help="Repository root.")
    return parser.parse_args()


def is_designated_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = Path(normalized).parts
    name = Path(normalized).name.lower()
    if normalized.startswith("backend/scripts/"):
        return any(marker in name for marker in ("readiness", "gauntlet", "proof"))
    return normalized.startswith("backend/utils/") and any(
        marker in part.lower() for marker in ("rollout", "compat") for part in parts[2:]
    )


def header_values(text: str, name: str) -> list[str]:
    pattern = re.compile(rf"^\s*(?:#|//)\s*{re.escape(name)}:\s*(.*?)\s*$")
    values: list[str] = []
    for line in text.splitlines()[:HEADER_LINE_LIMIT]:
        match = pattern.match(line)
        if match:
            values.append(match.group(1))
    return values


def parse_lifecycle_header(path: Path) -> tuple[str | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, "must be UTF-8 text to carry a lifecycle header"
    except OSError as exc:
        return None, f"could not read file: {exc}"

    lifecycles = header_values(text, "LIFECYCLE")
    if not lifecycles:
        return None, None
    if len(lifecycles) != 1:
        return None, "must declare exactly one LIFECYCLE header near the top"

    lifecycle = lifecycles[0]
    if lifecycle not in LIFECYCLE_VALUES:
        return None, "LIFECYCLE must be one-time or permanent"

    delete_after = header_values(text, "DELETE-AFTER")
    if lifecycle == "permanent":
        if delete_after:
            return None, "permanent files must not declare DELETE-AFTER"
        return lifecycle, None

    if len(delete_after) != 1:
        return None, "one-time files must declare exactly one DELETE-AFTER reference"
    target = delete_after[0]
    if not (ISSUE_URL_RE.fullmatch(target) or INVARIANT_ID_RE.fullmatch(target)):
        return None, "DELETE-AFTER must be a GitHub issue URL or product invariant ID (for example INV-MEM-3)"
    return lifecycle, None


def load_baseline(path: Path) -> tuple[set[str], list[str]]:
    entries: set[str] = set()
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return set(), [f"could not read lifecycle baseline {path}: {exc}"]

    for line_number, line in enumerate(lines, start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry in entries:
            errors.append(f"{path}: duplicate baseline entry on line {line_number}: {entry}")
        elif not is_designated_path(entry):
            errors.append(f"{path}: non-designated baseline entry on line {line_number}: {entry}")
        else:
            entries.add(entry)
    return entries, errors


def iter_designated_files(root: Path):
    for path in root.joinpath("backend").rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRECTORY_NAMES for part in path.relative_to(root).parts):
            relative_path = path.relative_to(root).as_posix()
            if is_designated_path(relative_path):
                yield relative_path, path


def validate(root: Path, changed_paths: list[str], baseline_path: Path) -> list[str]:
    errors: list[str] = []
    baseline, baseline_errors = load_baseline(baseline_path)
    errors.extend(baseline_errors)

    headerless: set[str] = set()
    parsed_headers: dict[str, str | None] = {}
    for relative_path, path in iter_designated_files(root):
        lifecycle, header_error = parse_lifecycle_header(path)
        parsed_headers[relative_path] = lifecycle
        if header_error:
            errors.append(f"{relative_path}: {header_error}")
        elif lifecycle is None:
            headerless.add(relative_path)

    if headerless != baseline:
        missing_from_baseline = sorted(headerless - baseline)
        stale_baseline_entries = sorted(baseline - headerless)
        errors.append("lifecycle baseline must exactly match the current headerless designated files")
        for path in missing_from_baseline:
            errors.append(f"  add a valid header (preferred) or record existing legacy debt: {path}")
        for path in stale_baseline_entries:
            errors.append(f"  remove stale lifecycle baseline entry: {path}")

    for relative_path in changed_paths:
        normalized = relative_path.replace("\\", "/")
        if not is_designated_path(normalized):
            continue
        path = root / normalized
        if not path.is_file():
            continue
        if parsed_headers.get(normalized) is None:
            errors.append(
                f"{normalized}: changed designated files require a valid lifecycle header near the top "
                "(# LIFECYCLE: permanent or one-time)."
            )
    return errors


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    changed_file = Path(args.changed_files)
    if not changed_file.is_absolute():
        changed_file = root / changed_file
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path

    try:
        changed_paths = [line.strip() for line in changed_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        print(f"FAIL: could not read changed-files input: {exc}")
        return 1

    errors = validate(root, changed_paths, baseline_path)
    if errors:
        print("FAIL: lifecycle header policy")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK: lifecycle headers and frozen baseline are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
