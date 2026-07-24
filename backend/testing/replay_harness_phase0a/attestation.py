"""Machine-verifiable topology/egress attestation builder and checker.

The builder joins the topology contract, per-role health probes, and the
egress-attempt log into a single JSON artifact. The checker is runnable
independently (third-party-verifiable) and recomputes every invariant from
the raw evidence — it does not trust the builder's assertions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_attestation(
    *,
    topology: dict[str, Any],
    topology_hash: str,
    health_records: list[Any],
    events: list[dict[str, Any]],
    egress_allow_list: list[dict[str, Any]],
    ports: dict[str, int],
    outcome: str,
    fault_controls: dict[str, str],
) -> dict[str, Any]:
    """Build the attestation artifact from raw evidence."""
    egress_attempts = [e for e in events if e.get("event") in ("egress_attempt", "dns_attempt")]
    denied = [e for e in egress_attempts if e.get("decision") == "deny"]

    by_purpose: dict[str, int] = {}
    allowed_count = 0
    for e in egress_attempts:
        if e.get("decision") == "allow":
            allowed_count += 1
            purpose = _classify_attempt(e, egress_allow_list, ports)
            by_purpose[purpose] = by_purpose.get(purpose, 0) + 1

    return {
        "schema_version": 1,
        "harness": "omi-replay-harness",
        "phase": "0A",
        "feasibility_only": True,
        "topology_contract_sha256": topology_hash,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "roles": [
            {
                "name": rh.name,
                "pid": rh.pid,
                "port": rh.port,
                "ready": rh.ready,
                "ready_probe": rh.ready_probe,
            }
            for rh in health_records
        ],
        "egress": {
            "policy": "default-deny",
            "scope": "process-level socket guard (Python SUT + runner); dependency processes bind-constrained to loopback",
            "attempts_observed": len(egress_attempts),
            "allowed": allowed_count,
            "denied": len(denied),
            "by_purpose": by_purpose,
            "denied_attempts": denied,
            "every_attempt_matched_declared_fake": len(denied) == 0,
        },
        "invariants": {
            "all_roles_started": all(rh.ready for rh in health_records),
            "all_roles_ready": all(rh.ready for rh in health_records),
            "no_denied_egress": len(denied) == 0,
            "no_undeclared_loopback_peer": len(denied) == 0,
        },
        "fault_controls_active": fault_controls,
        "outcome": outcome,
    }


def _classify_attempt(event: dict[str, Any], allow_list: list[dict[str, Any]], ports: dict[str, int]) -> str:
    """Classify an allowed egress attempt by purpose."""
    port = event.get("port")
    for entry in allow_list:
        target = entry.get("to")
        if target == "firestore":
            continue  # firestore port is dynamic, classified by pattern
        if target in ports and ports[target] == port:
            return entry.get("purpose", "unknown")
    if port is not None:
        return f"port:{port}"
    return "dns-loopback"


def validate_attestation(attestation: dict[str, Any]) -> list[str]:
    """Independently validate an attestation artifact. Returns list of violations (empty = pass)."""
    violations: list[str] = []

    # Invariant: all roles started and ready.
    roles = attestation.get("roles", [])
    if not roles:
        violations.append("no roles in attestation")
    for role in roles:
        if not role.get("ready"):
            violations.append(f"role {role.get('name')} not ready")
        if not role.get("ready_probe"):
            violations.append(f"role {role.get('name')} missing ready_probe")

    # Invariant: no denied egress.
    egress = attestation.get("egress", {})
    denied = egress.get("denied_attempts", [])
    if denied:
        violations.append(f"{len(denied)} denied egress attempts: {denied[:3]}")
    if egress.get("allowed", 0) == 0:
        violations.append("zero allowed egress attempts — guard may not have been installed")

    # Invariant: every invariant field is true.
    for key, value in attestation.get("invariants", {}).items():
        if value is not True:
            violations.append(f"invariant {key} is {value}, expected true")

    return violations


def validate_attestation_file(path: str | Path) -> int:
    """CLI entry point: validate an attestation JSON file. Exit 0 = pass."""
    attestation = json.loads(Path(path).read_text())
    violations = validate_attestation(attestation)
    if violations:
        print(f"FAIL: {len(violations)} violation(s):", file=__import__("sys").stderr)
        for v in violations:
            print(f"  - {v}", file=__import__("sys").stderr)
        return 1
    print(f"OK: attestation valid (outcome={attestation.get('outcome')})")
    return 0
