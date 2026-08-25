#!/usr/bin/env python3
"""Fail closed unless a first-attempt proof names current, checked-out main."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 40


class AutomaticReleaseAdmissionError(ValueError):
    """The completed workflow_run cannot safely trigger a backend deployment."""


@dataclass(frozen=True)
class AutomaticReleaseIdentity:
    sha: str
    main_sha: str
    checkout_sha: str
    run_attempt: str


def require_full_sha(label: str, value: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise AutomaticReleaseAdmissionError(f"{label} must be a full 40-character lowercase hexadecimal SHA")
    if value == ZERO_SHA:
        raise AutomaticReleaseAdmissionError(f"{label} must not be the all-zero initial-push sentinel")


def validate(identity: AutomaticReleaseIdentity) -> None:
    """Accept only the first proof completion for the exact current main SHA."""

    require_full_sha("release SHA", identity.sha)
    require_full_sha("current main SHA", identity.main_sha)
    require_full_sha("current-main checkout SHA", identity.checkout_sha)

    if identity.run_attempt != "1":
        raise AutomaticReleaseAdmissionError("automatic release admission requires the proof's first run attempt")
    if identity.sha != identity.main_sha:
        raise AutomaticReleaseAdmissionError("release SHA must still equal current main")
    if identity.sha != identity.checkout_sha:
        raise AutomaticReleaseAdmissionError("release SHA must equal the current-main guard checkout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-attempt", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    identity = AutomaticReleaseIdentity(
        sha=args.sha,
        main_sha=args.main_sha,
        checkout_sha=args.checkout_sha,
        run_attempt=args.run_attempt,
    )
    try:
        validate(identity)
    except AutomaticReleaseAdmissionError as exc:
        print(f"automatic backend release admission failed: {exc}", file=sys.stderr)
        return 1
    print(f"automatic backend release source admitted: sha={identity.sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
