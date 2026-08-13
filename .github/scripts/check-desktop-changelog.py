#!/usr/bin/env python3
"""Require desktop user-facing PRs to add an unreleased changelog fragment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

UNRELEASED_CHANGELOG_PREFIX = "desktop/macos/changelog/unreleased/"
CHANGELOG_PREFIX = "desktop/macos/changelog/"
DESKTOP_PREFIX = "desktop/macos/"
EXEMPT_DESKTOP_PATHS = {
    "desktop/macos/CHANGELOG.json",
    "desktop/macos/AGENTS.md",
    "desktop/macos/docs/release.md",
    "desktop/macos/docs/qualification-environment.md",
    "desktop/macos/scripts/qualify-desktop-beta.sh",
    # Capacity/lease authority for the same internal qualification runner.
    "desktop/macos/scripts/qualification-cache-reclaim.py",
    # M1 self-clean / lost-communication recovery for the qualification runner
    # (#10759). Internal release infrastructure; post-merge push must not demand
    # a user-facing changelog fragment (FC-push-gate-internal-path-scope).
    "desktop/macos/scripts/qualification-runner-self-clean.py",
    "desktop/macos/scripts/qualification-watchdog.py",
    # Sibling qualification-runner helper to qualify-desktop-beta.sh: internal
    # release infrastructure with no user-facing app surface.
    "desktop/macos/scripts/qualification-swift-cache.sh",
    # Lease transport for the same qualification runner: it only moves
    # machine-readable lease evidence and never ships in the desktop app.
    "desktop/macos/scripts/qualification-lease-command.sh",
    # Pre-tag readiness gate script: internal release infrastructure (runs on the
    # trusted M1 before tagging), no user-facing app surface.
    "desktop/macos/scripts/pre-tag-readiness.sh",
    # CI-only offline M1 qualification lifecycle proof: internal release
    # infrastructure (pre-dispatch before canonical qualification), no
    # user-facing app surface.
    "desktop/macos/scripts/qualification-local-proof.sh",
    # Release-keyvalue metadata tooling: internal release-channel metadata,
    # never ships in the desktop app.
    "desktop/macos/scripts/release-keyvalue.py",
    # Internal qualification environment documentation for CI runners; not a
    # user-facing app note.
    "desktop/macos/docs/qualification-environment.md",
    # Manual cleanup inventory for deprecated per-version host qual artifacts.
    "desktop/macos/docs/qualification-cleanup.md",
    # Portable tag-arg qualification babysitter: host-local release
    # infrastructure, never ships in the desktop app.
    "desktop/macos/scripts/qualify-desktop-beta-service.py",
    # CI-only flow-validation script and its shared action-source inventory do
    # not alter the desktop application a user receives.
    "desktop/macos/scripts/desktop-flow-lint.py",
    "desktop/macos/scripts/desktop_flow_contract.py",
    # Signed-artifact smoke harness: release infrastructure that inspects and
    # launches the built app on CI builders, never ships inside it.
    "desktop/macos/scripts/smoke-signed-desktop-artifact.sh",
}
# Test and release-infra changes are likewise never user-facing app notes; the
# `no-changelog-needed` PR label only satisfies the PR run, so post-merge push
# runs of this gate must exempt these paths by path or they redden main
# (qualify-desktop-beta.sh timeout bump #10374 tripped tests/ on the merge push).
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
    if isinstance(data.get("changes"), list) and any(
        isinstance(entry, str) and entry.strip() for entry in data["changes"]
    ):
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


def tree_has_unreleased_fragment(head_ref: str) -> bool:
    """Whether the tree at head carries at least one valid unreleased fragment.

    The release lane (Release Eligibility on main pushes) cares that the NEXT
    RELEASE will have notes, not that this particular push added them — PR
    labels that exempted the merged PR are invisible on the push lane, and a
    fragment landed by a sibling commit since the last tag satisfies the
    release's contract. Per-PR enforcement stays with the diff-scoped check.
    """
    try:
        output = run_git(["ls-tree", "-r", "--name-only", head_ref, UNRELEASED_CHANGELOG_PREFIX])
    except subprocess.CalledProcessError:
        return False
    fragment_paths = [path for path in output.splitlines() if path.endswith(".json")]
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
    parser.add_argument(
        "--accept-tree-fragments",
        action="store_true",
        default=os.getenv("DESKTOP_CHANGELOG_ACCEPT_TREE_FRAGMENTS") == "1",
        help=(
            "Release-lane mode: also pass when the tree at --head already carries a valid "
            "unreleased fragment (set by Release Eligibility, where PR labels are invisible)"
        ),
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

    if args.accept_tree_fragments and tree_has_unreleased_fragment(args.head):
        print("Release lane: unreleased changelog fragments already present in the tree.")
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
