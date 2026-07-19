#!/usr/bin/env python3
"""Fail closed unless a release proof names the exact checked-out main commit."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


MAIN_REF = "refs/heads/main"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 40


class ReleaseEligibilityError(ValueError):
    """The workflow context cannot safely identify one release commit."""


@dataclass(frozen=True)
class ReleaseIdentity:
    ref: str
    sha: str
    before: str
    after: str
    checkout_sha: str


def require_full_sha(label: str, value: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise ReleaseEligibilityError(f"{label} must be a full 40-character lowercase hexadecimal SHA")
    if value == ZERO_SHA:
        raise ReleaseEligibilityError(f"{label} must not be the all-zero initial-push sentinel")


def validate(identity: ReleaseIdentity) -> None:
    """Reject refs and identities that cannot prove one immutable main commit."""

    if identity.ref != MAIN_REF:
        raise ReleaseEligibilityError(f"release eligibility requires ref {MAIN_REF}, got {identity.ref!r}")

    require_full_sha("release SHA", identity.sha)
    require_full_sha("release base SHA", identity.before)
    require_full_sha("event after SHA", identity.after)
    require_full_sha("checkout SHA", identity.checkout_sha)

    if identity.sha != identity.after:
        raise ReleaseEligibilityError("release SHA must equal the push event after SHA")
    if identity.sha != identity.checkout_sha:
        raise ReleaseEligibilityError("release SHA must equal the checked-out SHA")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--checkout-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    identity = ReleaseIdentity(
        ref=args.ref,
        sha=args.sha,
        before=args.before,
        after=args.after,
        checkout_sha=args.checkout_sha,
    )
    try:
        validate(identity)
    except ReleaseEligibilityError as exc:
        print(f"release eligibility failed: {exc}", file=sys.stderr)
        return 1
    print(f"release eligibility identity verified: sha={identity.sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
