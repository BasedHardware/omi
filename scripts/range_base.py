#!/usr/bin/env python3
"""Resolve the review-range base shared by local repository guards."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


class RangeBaseError(RuntimeError):
    """A deterministic Git/configuration error while resolving a range base."""


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RangeBaseError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def git_config_value(root: Path, key: str) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 1:
        return None
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RangeBaseError(f"git config --get {key} failed: {detail}")
    return result.stdout.strip() or None


def resolve_base(root: Path, explicit_base: str | None) -> str:
    """Resolve explicit base, recorded lane trunk, upstream, then main fallback."""
    if explicit_base is not None:
        return explicit_base

    branch = run_git(root, "branch", "--show-current")
    if branch:
        lane_trunk = git_config_value(root, f"branch.{branch}.omiLaneTrunk")
        if lane_trunk:
            # omi-lane records the local branch name after branching from the
            # corresponding origin ref. The local trunk may have moved or be stale.
            return f"origin/{lane_trunk}"
        upstream = run_git(
            root,
            "for-each-ref",
            "--format=%(upstream:short)",
            f"refs/heads/{branch}",
        )
        if upstream:
            return upstream

    return "origin/main"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base")
    args = parser.parse_args()
    try:
        print(resolve_base(args.root.resolve(), args.base))
    except RangeBaseError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
