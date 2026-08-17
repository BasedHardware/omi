#!/usr/bin/env python3
"""Verify trusted-M1 pre-tag readiness evidence before an immutable tag is created.

The desktop auto-release tag job runs this against the readiness evidence
artifact produced on the trusted self-hosted M1. It never trusts that the
readiness *job* merely succeeded: it loads the evidence and proves it covers the
EXACT source SHA the tag job is about to tag, that it ran offline, and that it
carries no production-pointer authority.

Readiness is deliberately distinct from signed-artifact qualification: this
verifier accepts only readiness evidence and rejects qualification evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KIND = "omi-desktop-pre-tag-readiness-v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LANES = frozenset({"local", "ci"})
REQUIRED_CHECKS = (
    "source_resolved_from_origin",
    "exact_sha_checkout_verified",
    "swift_cache_prepared",
    "self_check",
    "offline_stack_ready",
)
# Readiness must never carry production authority; qualification/promotion own
# those decisions separately.
FORBIDDEN_FIELDS = frozenset(
    {
        "beta_pointer",
        "stable_pointer",
        "is_live",
        "promoted",
        "production",
        "qualified_beta",
        "qualifiedbeta",
    }
)


class EvidenceError(ValueError):
    """Pre-tag readiness evidence violates the fail-closed contract."""


def _fail(message: str) -> None:
    raise EvidenceError(message)


def verify(evidence: object, expected_sha: str) -> dict:
    if not isinstance(evidence, dict):
        _fail("evidence must be a JSON object")
    unexpected = sorted(evidence.keys() & FORBIDDEN_FIELDS)
    if unexpected:
        _fail(f"readiness evidence must not carry production/qualification fields: {', '.join(unexpected)}")
    if evidence.get("kind") != KIND:
        _fail(f"evidence kind must be {KIND!r}, got {evidence.get('kind')!r}")
    if evidence.get("passed") is not True:
        _fail(f"readiness did not pass: {evidence.get('passed')!r}")
    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha):
        _fail(f"evidence source_sha must be 40 lowercase hex, got {source_sha!r}")
    # The load-bearing check: the evidence must cover the EXACT SHA about to be
    # tagged. A stale or mismatched evidence record must never authorize a tag.
    if source_sha != expected_sha:
        _fail(f"evidence source_sha {source_sha!r} != tag source {expected_sha!r}")
    provider_mode = evidence.get("provider_mode")
    if provider_mode != "offline":
        _fail(f"evidence provider_mode must be 'offline', got {provider_mode!r}")
    lane = evidence.get("lane")
    if lane not in LANES:
        _fail(f"evidence lane must be one of {sorted(LANES)}, got {lane!r}")
    checks = evidence.get("checks")
    if not isinstance(checks, dict):
        _fail("evidence checks must be an object")
    missing = sorted(set(REQUIRED_CHECKS) - checks.keys())
    if missing:
        _fail(f"evidence missing required checks: {', '.join(missing)}")
    failed = sorted(name for name in REQUIRED_CHECKS if checks.get(name) is not True)
    if failed:
        _fail(f"evidence has failed checks: {', '.join(failed)}")
    return evidence


def _self_test() -> int:
    failures: list[str] = []

    def ok(name: str) -> None:
        print(f"ok: {name}")

    def expect_fail(name: str, evidence: object, expected_sha: str, needle: str) -> None:
        try:
            verify(evidence, expected_sha)
        except EvidenceError as exc:
            if needle in str(exc):
                ok(name)
            else:
                failures.append(f"{name}: expected {needle!r} in error, got {exc}")
        else:
            failures.append(f"{name}: expected EvidenceError, verify accepted bad evidence")

    def expect_ok(name: str, evidence: object, expected_sha: str) -> None:
        try:
            verify(evidence, expected_sha)
        except EvidenceError as exc:
            failures.append(f"{name}: unexpected EvidenceError: {exc}")
        else:
            ok(name)

    base = {
        "kind": KIND,
        "passed": True,
        "source_sha": "a" * 40,
        "lane": "ci",
        "provider_mode": "offline",
        "checks": {name: True for name in REQUIRED_CHECKS},
    }

    expect_ok("valid evidence passes", dict(base), "a" * 40)
    expect_ok("local lane accepted", {**base, "lane": "local"}, "a" * 40)

    expect_fail("wrong kind", {**base, "kind": "qualification-evidence-v1"}, "a" * 40, "kind")
    expect_fail("passed false", {**base, "passed": False}, "a" * 40, "did not pass")
    expect_fail("sha mismatch — the load-bearing check", base, "b" * 40, "!=")
    expect_fail("malformed sha", {**base, "source_sha": "deadbeef"}, "deadbeef", "40 lowercase hex")
    expect_fail("non-offline provider", {**base, "provider_mode": "production"}, "a" * 40, "offline")
    expect_fail("bad lane", {**base, "lane": "staging"}, "a" * 40, "lane")
    expect_fail("missing check", {**base, "checks": {n: True for n in REQUIRED_CHECKS if n != "self_check"}}, "a" * 40, "missing")
    expect_fail("failed check", {**base, "checks": {**base["checks"], "self_check": False}}, "a" * 40, "failed")
    expect_fail("forbidden production field", {**base, "is_live": True}, "a" * 40, "production/qualification")
    expect_fail("forbidden qualification field", {**base, "qualified_beta": True}, "a" * 40, "production/qualification")
    expect_fail("not an object", ["nope"], "a" * 40, "JSON object")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"\n{len(failures)} self-test failure(s)", file=sys.stderr)
        return 1
    print("verify-pre-tag-readiness self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify", help="Verify readiness evidence against an exact source SHA")
    verify_parser.add_argument("--evidence", required=True)
    verify_parser.add_argument("--source-sha", required=True)
    sub.add_parser("self-test", help="Run built-in fixture tests")
    args = parser.parse_args(argv)
    if args.command == "self-test":
        return _self_test()
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    verify(evidence, args.source_sha)
    print(f"pre-tag readiness evidence verified for {args.source_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
