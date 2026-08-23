#!/usr/bin/env python3
"""Admit the newest proven commit on main for an automatic development deploy.

The workflow resolves a *target* commit -- the newest commit on main carrying a
first-attempt, successful Release Eligibility proof and reachable from current
main -- and this guard fails closed unless that target is safe to deploy.

Why the target is resolved rather than taken from the triggering proof:

* **Convergence.** Requiring the triggering SHA to still be main's tip rejected
  a merged, reviewed commit whenever anything else merged while eligibility
  ran. That was 8 of the 13 automatic development deploy failures in the 25
  runs before this changed, and it left development a day behind main.
* **No downgrade.** Accepting any ancestor of main would let a late-scheduled
  run for an older commit deploy after a newer one already had, because Actions
  concurrency groups are not FIFO. Resolving the newest proven commit makes
  concurrent runs converge on the same target instead of racing.
* **No revert resurrection.** A commit stays an ancestor of main after it is
  reverted, so an ancestor-only rule could redeploy the pre-revert tree. The
  revert is newer, so the newest proven commit is the reverted state.

``--trigger-is-ancestor-of-sha`` keeps the resolved target at least as new as
the proof that triggered this run, so a stale or misresolved listing can never
move development backwards from its own trigger.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 40
BOOL_CHOICES = ("true", "false")


class AutomaticReleaseAdmissionError(ValueError):
    """The completed workflow_run cannot safely trigger a backend deployment."""


@dataclass(frozen=True)
class AutomaticReleaseIdentity:
    sha: str
    trigger_sha: str
    main_sha: str
    run_attempt: str
    sha_is_ancestor_of_main: bool
    trigger_is_ancestor_of_sha: bool


def require_full_sha(label: str, value: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise AutomaticReleaseAdmissionError(f"{label} must be a full 40-character lowercase hexadecimal SHA")
    if value == ZERO_SHA:
        raise AutomaticReleaseAdmissionError(f"{label} must not be the all-zero initial-push sentinel")


def validate(identity: AutomaticReleaseIdentity) -> None:
    """Accept only a first-attempt proof for the newest merged, proven commit."""

    require_full_sha("admitted SHA", identity.sha)
    require_full_sha("triggering release SHA", identity.trigger_sha)
    require_full_sha("current main SHA", identity.main_sha)

    if identity.run_attempt != "1":
        raise AutomaticReleaseAdmissionError("automatic release admission requires the proof's first run attempt")
    if not identity.sha_is_ancestor_of_main:
        raise AutomaticReleaseAdmissionError("admitted SHA must be merged into current main")
    if not identity.trigger_is_ancestor_of_sha:
        raise AutomaticReleaseAdmissionError("admitted SHA must not be older than the triggering release SHA")


def _parse_bool(value: str) -> bool:
    if value not in BOOL_CHOICES:
        raise AutomaticReleaseAdmissionError(f"expected one of {BOOL_CHOICES}, got {value!r}")
    return value == "true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="Resolved newest proven commit to deploy.")
    parser.add_argument("--trigger-sha", required=True, help="head_sha of the Release Eligibility run that fired.")
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument(
        "--sha-is-ancestor-of-main",
        required=True,
        choices=BOOL_CHOICES,
        help="Result of `git merge-base --is-ancestor <sha> <main>`.",
    )
    parser.add_argument(
        "--trigger-is-ancestor-of-sha",
        required=True,
        choices=BOOL_CHOICES,
        help="Result of `git merge-base --is-ancestor <trigger-sha> <sha>`.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        identity = AutomaticReleaseIdentity(
            sha=args.sha,
            trigger_sha=args.trigger_sha,
            main_sha=args.main_sha,
            run_attempt=args.run_attempt,
            sha_is_ancestor_of_main=_parse_bool(args.sha_is_ancestor_of_main),
            trigger_is_ancestor_of_sha=_parse_bool(args.trigger_is_ancestor_of_sha),
        )
        validate(identity)
    except AutomaticReleaseAdmissionError as exc:
        print(f"automatic backend release admission failed: {exc}", file=sys.stderr)
        return 1
    print(f"automatic backend release source admitted: sha={identity.sha} trigger={identity.trigger_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
