#!/usr/bin/env python3
"""Require desktop user-facing PRs to add an unreleased changelog entry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


CHANGELOG_PATH = Path("desktop/macos/CHANGELOG.json")
DESKTOP_PREFIX = "desktop/macos/"
EXEMPT_DESKTOP_PATHS = {
    "desktop/macos/CHANGELOG.json",
    "desktop/macos/AGENTS.md",
}


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    output = run_git(["diff", "--name-only", "--diff-filter=ACM", f"{base_ref}...{head_ref}"])
    return [line for line in output.splitlines() if line]


def is_desktop_change_requiring_changelog(path: str) -> bool:
    if not path.startswith(DESKTOP_PREFIX):
        return False
    if path in EXEMPT_DESKTOP_PATHS:
        return False
    return True


def unreleased_entries(ref: str) -> list[str]:
    try:
        raw = run_git(["show", f"{ref}:{CHANGELOG_PATH}"])
    except subprocess.CalledProcessError:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {CHANGELOG_PATH} is not valid JSON at {ref}: {exc}") from exc

    unreleased = data.get("unreleased", [])
    if not isinstance(unreleased, list):
        raise SystemExit(f"FAIL: {CHANGELOG_PATH} field 'unreleased' must be a list")
    return [entry for entry in unreleased if isinstance(entry, str) and entry.strip()]


def has_new_unreleased_entry(base_ref: str, head_ref: str) -> bool:
    before = Counter(unreleased_entries(base_ref))
    after = Counter(unreleased_entries(head_ref))
    return bool(after - before)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base git ref, usually origin/main")
    parser.add_argument("--head", default="HEAD", help="Head git ref to inspect")
    parser.add_argument(
        "--skip",
        action="store_true",
        help="Skip enforcement, used for PRs labeled no-changelog-needed",
    )
    args = parser.parse_args()

    if args.skip:
        print("Desktop changelog check skipped by no-changelog-needed label.")
        return 0

    files = changed_files(args.base, args.head)
    requiring_changelog = [path for path in files if is_desktop_change_requiring_changelog(path)]

    if not requiring_changelog:
        print("No desktop changes require a changelog entry.")
        return 0

    if has_new_unreleased_entry(args.base, args.head):
        print("Desktop changelog entry found.")
        return 0

    print("FAIL: desktop changes require an unreleased changelog entry.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Changed desktop files:", file=sys.stderr)
    for path in requiring_changelog:
        print(f"  - {path}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Add a one-line user-facing entry to desktop/macos/CHANGELOG.json under "
        "'unreleased', or label the PR no-changelog-needed for internal-only changes.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
