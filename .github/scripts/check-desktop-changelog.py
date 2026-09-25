#!/usr/bin/env python3
"""Require desktop user-facing PRs to add an unreleased changelog fragment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Literal

UNRELEASED_CHANGELOG_PREFIX = "desktop/macos/changelog/unreleased/"
CHANGELOG_PREFIX = "desktop/macos/changelog/"
DESKTOP_PREFIX = "desktop/macos/"
NONE_KIND = "none"
EXEMPT_DESKTOP_PATHS = {
    "desktop/macos/CHANGELOG.json",
    "desktop/macos/AGENTS.md",
    "desktop/macos/docs/release.md",
    # CI-only flow-validation script and its shared action-source inventory do
    # not alter the desktop application a user receives.
    "desktop/macos/scripts/desktop-flow-lint.py",
    "desktop/macos/scripts/desktop_flow_contract.py",
    # Signed-artifact smoke harness: release infrastructure that inspects and
    # launches the built app on CI builders, never ships inside it.
    "desktop/macos/scripts/smoke-signed-desktop-artifact.sh",
}
# Test and release-infra changes are likewise never user-facing app notes.
# `no-changelog-needed` is not an exemption for production desktop paths: the
# label is invisible on the post-merge push run and would redden main. Internal
# production edits use an in-repo `{"kind": "none"}` fragment instead.
EXEMPT_DESKTOP_PATH_PREFIXES = (
    "desktop/macos/tests/",
    "desktop/macos/Desktop/Tests/",
    # Generated Swift (e.g. Sources/Generated/OmiApi.generated.swift) is
    # deterministically derived from the backend OpenAPI contract, never a
    # user-facing app note. Regenerating it after a spec change must not demand
    # a changelog fragment, and — like tests/ above — the post-merge push run
    # would otherwise redden main. Same directory the swift-format linter skips.
    "desktop/macos/Desktop/Sources/Generated/",
    # E2E flow definitions and their docs are CI/harness test artifacts that never
    # ship in the desktop app. Registering a new source file in a flow's `covers:`
    # is exactly the kind of internal-only edit that reddened main on the merge
    # push for #11039.
    "desktop/macos/e2e/",
)

FragmentKind = Literal["none", "user_facing"]


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


def classify_fragment(data: object, path: str) -> FragmentKind:
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must contain a JSON object")

    if data.get("kind") == NONE_KIND:
        return "none"

    if isinstance(data.get("change"), str) and data["change"].strip():
        return "user_facing"
    if isinstance(data.get("changes"), list) and any(
        isinstance(entry, str) and entry.strip() for entry in data["changes"]
    ):
        return "user_facing"

    raise SystemExit(
        f"FAIL: {path} must contain a non-empty 'change' string, 'changes' list, " f"or 'kind': '{NONE_KIND}'"
    )


def load_fragment(head_ref: str, path: str) -> FragmentKind:
    try:
        raw = run_git(["show", f"{head_ref}:{path}"])
    except subprocess.CalledProcessError:
        raise SystemExit(f"FAIL: could not read changelog fragment {path} at {head_ref}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {path} is not valid JSON at {head_ref}: {exc}") from exc

    return classify_fragment(data, path)


def validate_unreleased_fragment(head_ref: str, path: str) -> None:
    load_fragment(head_ref, path)


def added_unreleased_fragment_paths(base_ref: str, head_ref: str) -> list[str]:
    return [
        path
        for path in added_files(base_ref, head_ref)
        if path.startswith(UNRELEASED_CHANGELOG_PREFIX) and path.endswith(".json")
    ]


def has_new_unreleased_fragment(base_ref: str, head_ref: str) -> bool:
    """Whether this diff added a valid exemption fragment (user-facing or kind none)."""
    fragment_paths = added_unreleased_fragment_paths(base_ref, head_ref)
    for path in fragment_paths:
        load_fragment(head_ref, path)
    return bool(fragment_paths)


def tree_has_unreleased_fragment(head_ref: str) -> bool:
    """Whether the tree at head carries at least one user-facing unreleased fragment.

    The release lane (Release Eligibility on main pushes) cares that the NEXT
    RELEASE will have notes, not that this particular push added them. A leftover
    `kind: none` fragment is not notes — only user-facing fragments satisfy this.
    """
    try:
        output = run_git(["ls-tree", "-r", "--name-only", head_ref, UNRELEASED_CHANGELOG_PREFIX])
    except subprocess.CalledProcessError:
        return False
    fragment_paths = [path for path in output.splitlines() if path.endswith(".json")]
    saw_user_facing = False
    for path in fragment_paths:
        if load_fragment(head_ref, path) == "user_facing":
            saw_user_facing = True
    return saw_user_facing


def evaluate_changelog_requirement(
    *,
    requiring_changelog: list[str],
    skip: bool,
    has_new_fragment: bool,
    accept_tree_fragments: bool,
    has_tree_user_facing_fragment: bool,
) -> tuple[int, str]:
    """Return (exit_code, stdout_or_stderr_message) for one gate evaluation.

    `--skip` (the PR label, changelog/v branches, local hatches, the macOS CI
    lane) is not an exemption when the diff touches production desktop paths.
    Those paths need an in-repo fragment so the PR run and the post-merge push
    run see the same evidence. #11778 / #11373 / #11039 all wedged main because
    the label was invisible after merge.
    """
    if not requiring_changelog:
        if skip:
            return 0, "Desktop changelog check skipped: no production desktop paths require a fragment."
        return 0, "No desktop changes require a changelog entry."

    if has_new_fragment:
        return 0, "Desktop changelog fragment found."

    if accept_tree_fragments and has_tree_user_facing_fragment:
        return 0, "Release lane: unreleased changelog fragments already present in the tree."

    lines = [
        "FAIL: desktop changes require an unreleased changelog fragment.",
        "",
        "Changed desktop files:",
    ]
    lines.extend(f"  - {path}" for path in requiring_changelog)
    lines.extend(
        [
            "",
            "Add a user-facing JSON fragment under desktop/macos/changelog/unreleased/, ",
            f"or a {{\"kind\": \"{NONE_KIND}\"}} fragment for internal-only production edits.",
            "The no-changelog-needed PR label is not an exemption: it is invisible after",
            "merge and would redden main's Release Eligibility run.",
        ]
    )
    return 1, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base git ref, usually origin/main")
    parser.add_argument("--head", default="HEAD", help="Head git ref to inspect")
    parser.add_argument(
        "--skip",
        action="store_true",
        help=(
            "Legacy skip request (PR label, changelog/v, local hatch, macOS CI). "
            "Ignored for production desktop paths; those need an in-repo fragment."
        ),
    )
    parser.add_argument(
        "--accept-tree-fragments",
        action="store_true",
        default=os.getenv("DESKTOP_CHANGELOG_ACCEPT_TREE_FRAGMENTS") == "1",
        help=(
            "Release-lane mode: also pass when the tree at --head already carries a valid "
            "user-facing unreleased fragment (set by Release Eligibility)"
        ),
    )
    args = parser.parse_args()

    files = changed_files(args.base, args.head)
    requiring_changelog = [path for path in files if is_desktop_change_requiring_changelog(path)]
    has_new_fragment = bool(requiring_changelog) and has_new_unreleased_fragment(args.base, args.head)
    has_tree_user_facing_fragment = (
        bool(requiring_changelog) and args.accept_tree_fragments and tree_has_unreleased_fragment(args.head)
    )

    code, message = evaluate_changelog_requirement(
        requiring_changelog=requiring_changelog,
        skip=args.skip,
        has_new_fragment=has_new_fragment,
        accept_tree_fragments=args.accept_tree_fragments,
        has_tree_user_facing_fragment=has_tree_user_facing_fragment,
    )
    if code:
        print(message, file=sys.stderr)
    else:
        print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
