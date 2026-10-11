#!/usr/bin/env python3
"""Validate that desktop bridge health belongs to the expected artifact."""

from __future__ import annotations

import argparse
import json
import re


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def evaluate(
    *,
    expected_bundle: str,
    health: dict[str, object],
    expected_source_identity: dict[str, object] | None,
    require_protocol: bool,
) -> str:
    if not health.get("ok"):
        raise ValueError(f"bridge unhealthy: {health}")

    actual_bundle = health.get("bundleIdentifier")
    if actual_bundle != expected_bundle:
        raise ValueError(
            f"wrong bundle on port: expected {expected_bundle}, got {actual_bundle}"
        )

    source_identity = health.get("sourceIdentity")
    if expected_source_identity is not None:
        if not _is_revision_specific_identity(expected_source_identity):
            raise ValueError(
                "expected source identity is not revision-specific: "
                f"{expected_source_identity}"
            )
        if source_identity != expected_source_identity:
            raise ValueError(
                "wrong source in running bundle: "
                f"expected {expected_source_identity}, got {source_identity}"
            )

    if require_protocol:
        running = health.get("agentRuntimeRunning")
        expected_protocol = health.get("agentRuntimeExpectedProtocolVersion")
        negotiated_protocol = health.get("agentRuntimeProtocolVersion")
        if running is not True:
            raise ValueError(f"agent runtime not running on bridge: {health}")
        if not isinstance(expected_protocol, int):
            raise ValueError(f"missing agentRuntimeExpectedProtocolVersion: {health}")
        if negotiated_protocol != expected_protocol:
            raise ValueError(
                "agent protocol not ready: "
                f"expected {expected_protocol}, negotiated {negotiated_protocol}"
            )

        source_summary = _source_summary(source_identity)
        return (
            f"bridge health ok: bundleIdentifier={actual_bundle}{source_summary} "
            f"protocol={negotiated_protocol} runtime={health.get('agentRuntimeVersion')}"
        )

    return f"bridge health ok: bundleIdentifier={actual_bundle}{_source_summary(source_identity)}"


def _source_summary(source_identity: object) -> str:
    if not isinstance(source_identity, dict):
        return ""
    return (
        f" source={source_identity.get('revision')}"
        f" workingTree={source_identity.get('workingTreeState')}"
    )


def _is_revision_specific_identity(source_identity: object) -> bool:
    return (
        isinstance(source_identity, dict)
        and source_identity.get("schemaVersion") == 1
        and isinstance(source_identity.get("revision"), str)
        and REVISION_PATTERN.fullmatch(source_identity["revision"]) is not None
        and source_identity.get("workingTreeState") in {"clean", "dirty"}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-bundle", required=True)
    parser.add_argument("--health-json", required=True)
    parser.add_argument("--expected-source-identity")
    parser.add_argument("--require-protocol", action="store_true")
    args = parser.parse_args()

    expected_source_identity = (
        json.loads(args.expected_source_identity)
        if args.expected_source_identity is not None
        else None
    )
    try:
        message = evaluate(
            expected_bundle=args.expected_bundle,
            health=json.loads(args.health_json),
            expected_source_identity=expected_source_identity,
            require_protocol=args.require_protocol,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"{error}\n")

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
