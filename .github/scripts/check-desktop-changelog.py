#!/usr/bin/env python3
"""Require desktop user-facing PRs to add an unreleased changelog fragment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


UNRELEASED_CHANGELOG_PREFIX = "desktop/macos/changelog/unreleased/"
CHANGELOG_PREFIX = "desktop/macos/changelog/"
DESKTOP_PREFIX = "desktop/macos/"
EXEMPT_DESKTOP_PATHS = {
    "desktop/macos/CHANGELOG.json",
    "desktop/macos/AGENTS.md",
    "desktop/macos/docs/release.md",
    "desktop/macos/scripts/qualify-desktop-beta.sh",
    # Sibling qualification-runner helper to qualify-desktop-beta.sh: internal
    # release infrastructure with no user-facing app surface.
    "desktop/macos/scripts/qualification-swift-cache.sh",
    # Pre-tag readiness gate script: internal release infrastructure (runs on the
    # trusted M1 before tagging), no user-facing app surface.
    "desktop/macos/scripts/pre-tag-readiness.sh",
}
# Server-side Rust backend changes are internal reliability work, not user-facing app notes.
# Test and release-infra changes are likewise never user-facing app notes; the
# `no-changelog-needed` PR label only satisfies the PR run, so post-merge push
# runs of this gate must exempt these paths by path or they redden main
# (qualify-desktop-beta.sh timeout bump #10374 tripped tests/ on the merge push).
EXEMPT_DESKTOP_PATH_PREFIXES = (
    "desktop/macos/Backend-Rust/",
    "desktop/macos/tests/",
    # Generated Swift (e.g. Sources/Generated/OmiApi.generated.swift) is
    # deterministically derived from the backend OpenAPI contract, never a
    # user-facing app note. Regenerating it after a spec change must not demand
    # a changelog fragment, and — like tests/ above — the post-merge push run
    # would otherwise redden main. Same directory the swift-format linter skips.
    "desktop/macos/Desktop/Sources/Generated/",
)


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    output = run_git(["diff", "--name-only", "--diff-filter=ACM", f"{base_ref}...{head_ref}"])
    return [line for line in output.splitlines() if line]


def added_files(base_ref: str, head_ref: str) -> list[str]:
    output = run_git(["diff", "--name-status", "--diff-filter=A", f"{base_ref}...{head_ref}"])
    return [line.split("\t", 1)[1] for line in output.splitlines() if line.startswith("A\t")]


def is_desktop_change_requiring_changelog(path: str) -> bool:
    if not path.startswith(DESKTOP_PREFIX):
        return False
    if path in EXEMPT_DESKTOP_PATHS:
        return False
    if path.startswith(CHANGELOG_PREFIX):
        return False
    if any(path.startswith(prefix) for prefix in EXEMPT_DESKTOP_PATH_PREFIXES):
        return False
    return True


def validate_unreleased_fragment(head_ref: str, path: str) -> None:
    try:
        raw = run_git(["show", f"{head_ref}:{path}"])
    except subprocess.CalledProcessError:
        raise SystemExit(f"FAIL: could not read changelog fragment {path} at {head_ref}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {path} is not valid JSON at {head_ref}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must contain a JSON object")

    if isinstance(data.get("change"), str) and data["change"].strip():
        return
    if isinstance(data.get("changes"), list) and any(isinstance(entry, str) and entry.strip() for entry in data["changes"]):
        return

    raise SystemExit(f"FAIL: {path} must contain a non-empty 'change' string or 'changes' list")


def has_new_unreleased_fragment(base_ref: str, head_ref: str) -> bool:
    fragment_paths = [
        path
        for path in added_files(base_ref, head_ref)
        if path.startswith(UNRELEASED_CHANGELOG_PREFIX) and path.endswith(".json")
    ]
    for path in fragment_paths:
        validate_unreleased_fragment(head_ref, path)
    return bool(fragment_paths)


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

    if has_new_unreleased_fragment(args.base, args.head):
        print("Desktop changelog fragment found.")
        return 0

    print("FAIL: desktop changes require an unreleased changelog fragment.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Changed desktop files:", file=sys.stderr)
    for path in requiring_changelog:
        print(f"  - {path}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Add a one-line user-facing JSON fragment under desktop/macos/changelog/unreleased/, "
        "or label the PR no-changelog-needed for internal-only changes.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
