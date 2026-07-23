#!/usr/bin/env python3
"""Validate and record the closed macOS Beta release-profile contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROFILES = ("nightly-rigorous", "manual-fast")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_profile(profile: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f"release profile must be exactly one of {', '.join(PROFILES)}; got {profile or 'missing'}")
    return profile


def build_evidence(profile: str, source_sha: str, rigorous_result: dict | None) -> dict:
    validate_profile(profile)
    if SHA_RE.fullmatch(source_sha) is None:
        raise ValueError("release profile evidence requires an exact lowercase source SHA")

    if profile == "nightly-rigorous":
        if not isinstance(rigorous_result, dict):
            raise ValueError("nightly-rigorous requires pre-sign T2 evidence")
        required = {
            "passed": True,
            "source_sha": source_sha,
            "tier": "T2",
            "provider_mode": "offline",
            "fault_suite_passed": True,
        }
        for key, expected in required.items():
            if rigorous_result.get(key) != expected:
                raise ValueError(f"nightly-rigorous pre-sign evidence has invalid {key}")
        rigorous_passed = True
    else:
        if rigorous_result is not None:
            raise ValueError("manual-fast must not claim or consume pre-sign T2 evidence")
        rigorous_passed = False

    return {
        "schema_version": 1,
        "release_profile": profile,
        "source_sha": source_sha,
        "rigorous_pre_sign_passed": rigorous_passed,
        "pre_sign_qualification": rigorous_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--profile", required=True)
    evidence = subparsers.add_parser("evidence")
    evidence.add_argument("--profile", required=True)
    evidence.add_argument("--source-sha", required=True)
    evidence.add_argument("--rigorous-result")
    evidence.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        if args.command == "validate":
            validate_profile(args.profile)
            return 0
        result = None
        if args.rigorous_result:
            result = json.loads(Path(args.rigorous_result).read_text(encoding="utf-8"))
        payload = build_evidence(args.profile, args.source_sha, result)
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
