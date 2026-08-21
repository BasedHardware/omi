#!/usr/bin/env python3
"""Fail closed unless a first-attempt proof names merged, current-main source.

Admission answers one question: may this completed Release Eligibility run
deploy its commit to the development backend?

The property that protects the runtime is that the commit is **merged** --
reachable from main -- so unreviewed code can never deploy. Requiring the
commit to still be main's *tip* is a stricter proxy that also rejects a
perfectly good deploy whenever any unrelated commit merges while Release
Eligibility runs. On a busy main that is the common case, not the edge case:
it accounted for 8 of the 13 automatic development deploy failures in the 25
runs preceding this change, and left development a day behind main.

So ancestry is required and tip-equality is not. Ordering between concurrent
admissions is left to the workflow's `deploy-backend-stack-development`
concurrency group; a rare out-of-order pair converges on the next merge, which
is an acceptable trade for development and is not reachable in production
(production deploys are dispatched explicitly, never by this path).
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
    main_sha: str
    checkout_sha: str
    run_attempt: str
    sha_is_ancestor_of_main: bool


def require_full_sha(label: str, value: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise AutomaticReleaseAdmissionError(f"{label} must be a full 40-character lowercase hexadecimal SHA")
    if value == ZERO_SHA:
        raise AutomaticReleaseAdmissionError(f"{label} must not be the all-zero initial-push sentinel")


def validate(identity: AutomaticReleaseIdentity) -> None:
    """Accept only a first-attempt proof for a commit merged into current main."""

    require_full_sha("release SHA", identity.sha)
    require_full_sha("current main SHA", identity.main_sha)
    require_full_sha("current-main checkout SHA", identity.checkout_sha)

    if identity.run_attempt != "1":
        raise AutomaticReleaseAdmissionError("automatic release admission requires the proof's first run attempt")
    # The guard runs against a checkout of main itself, so this asserts the
    # guard read the same main the ancestry proof was computed against. It is
    # not a statement about the release SHA.
    if identity.checkout_sha != identity.main_sha:
        raise AutomaticReleaseAdmissionError("current-main checkout must equal current main")
    if not identity.sha_is_ancestor_of_main:
        raise AutomaticReleaseAdmissionError("release SHA must be merged into current main")


def _parse_bool(value: str) -> bool:
    if value not in BOOL_CHOICES:
        raise AutomaticReleaseAdmissionError(f"expected one of {BOOL_CHOICES}, got {value!r}")
    return value == "true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument(
        "--sha-is-ancestor-of-main",
        required=True,
        choices=BOOL_CHOICES,
        help="Result of `git merge-base --is-ancestor <sha> <main>` from the guard checkout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        identity = AutomaticReleaseIdentity(
            sha=args.sha,
            main_sha=args.main_sha,
            checkout_sha=args.checkout_sha,
            run_attempt=args.run_attempt,
            sha_is_ancestor_of_main=_parse_bool(args.sha_is_ancestor_of_main),
        )
        validate(identity)
    except AutomaticReleaseAdmissionError as exc:
        print(f"automatic backend release admission failed: {exc}", file=sys.stderr)
        return 1
    print(f"automatic backend release source admitted: sha={identity.sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
