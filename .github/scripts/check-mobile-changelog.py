#!/usr/bin/env python3
"""Require user-facing mobile app changes to add an unreleased changelog fragment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PREFIX = "app/"
CHANGELOG_PREFIX = "app/changelog/"
UNRELEASED_CHANGELOG_PREFIX = "app/changelog/unreleased/"
NONE_KIND = "none"
EXEMPT_APP_PATHS = {
    "app/AGENTS.md",
    "app/scripts/mobile_play_build_number.py",
    "app/scripts/mobile_play_build_number_test.py",
    "app/scripts/mobile_release_identity.py",
    "app/scripts/mobile_release_identity_test.py",
    "app/scripts/mobile_store_promote.py",
    "app/scripts/mobile_store_promote_test.py",
    "app/scripts/mobile_store_version.py",
    "app/scripts/mobile_store_version_test.py",
}


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True, cwd=REPO_ROOT).strip()


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    output = run_git(["diff", "--name-only", "--diff-filter=ACM", f"{base_ref}...{head_ref}"])
    return [line for line in output.splitlines() if line]


def added_files(base_ref: str, head_ref: str) -> list[str]:
    output = run_git(["diff", "--name-status", "--diff-filter=A", f"{base_ref}...{head_ref}"])
    return [line.split("\t", 1)[1] for line in output.splitlines() if line.startswith("A\t")]


def is_app_change_requiring_changelog(path: str) -> bool:
    if not path.startswith(APP_PREFIX):
        return False
    if path.startswith(CHANGELOG_PREFIX):
        return False
    if path in EXEMPT_APP_PATHS:
        return False
    return True


def validate_fragment(data: object, path: str) -> None:
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must contain a JSON object")
    if data.get("kind") == NONE_KIND:
        return
    change = data.get("change")
    if isinstance(change, str) and change.strip():
        return
    raise SystemExit(f"FAIL: {path} must contain a non-empty 'change' string or 'kind': '{NONE_KIND}'")


def load_fragment(head_ref: str, path: str) -> None:
    try:
        raw = run_git(["show", f"{head_ref}:{path}"])
    except subprocess.CalledProcessError:
        raise SystemExit(f"FAIL: could not read changelog fragment {path} at {head_ref}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {path} is not valid JSON at {head_ref}: {exc}") from exc

    validate_fragment(data, path)


def added_unreleased_fragment_paths(base_ref: str, head_ref: str) -> list[str]:
    return [
        path
        for path in added_files(base_ref, head_ref)
        if path.startswith(UNRELEASED_CHANGELOG_PREFIX) and path.endswith(".json")
    ]


def check_changelog(base_ref: str, head_ref: str) -> tuple[int, str]:
    """Return (exit_code, message) for the changelog gate.

    The verdict depends only on the git diff — never on PR labels or the
    GitHub API — so a PR run and the metadata-free post-merge push run see
    identical evidence for the same diff.
    """
    files = changed_files(base_ref, head_ref)
    requiring_changelog = [path for path in files if is_app_change_requiring_changelog(path)]
    if not requiring_changelog:
        return 0, "No app changes require a changelog entry."

    fragment_paths = added_unreleased_fragment_paths(base_ref, head_ref)
    for path in fragment_paths:
        load_fragment(head_ref, path)
    if fragment_paths:
        return 0, "Mobile changelog fragment found."

    lines = [
        "FAIL: app changes require an unreleased changelog fragment.",
        "",
        "Changed app files:",
    ]
    lines.extend(f"  - {path}" for path in requiring_changelog)
    lines.extend(
        [
            "",
            "Add a user-facing JSON fragment under app/changelog/unreleased/, ",
            f"or a {{\"kind\": \"{NONE_KIND}\"}} fragment for internal-only production edits.",
            "The fragment travels with the commit, so the PR run and the",
            "post-merge push run reach the same verdict without PR metadata.",
        ]
    )
    return 1, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base git ref, usually origin/main")
    parser.add_argument("--head", default="HEAD", help="Head git ref to inspect")
    args = parser.parse_args()

    code, message = check_changelog(args.base, args.head)
    if code:
        print(message, file=sys.stderr)
    else:
        print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
