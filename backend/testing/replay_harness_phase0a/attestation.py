"""Machine-verifiable topology/egress attestation builder and checker.

The builder joins the topology contract, per-role health probes, and the
egress-attempt log into a single JSON artifact.  The checker is runnable
independently (third-party-verifiable): it recomputes the topology hash, role
completeness, and every egress decision from the embedded raw evidence and
topology contract — it does **not** trust the builder's summary assertions.

Scope (stated in the artifact, not over-claimed):

* TCP connection-oriented egress (``connect``, ``connect_ex``,
  ``create_connection``) and DNS resolution (``getaddrinfo``,
  ``gethostbyname``, ``gethostbyname_ex``) are observed and enforced in the
  Python SUT / runner / loopback processes.
* UDP unconnected sends (``sendto``, ``sendmsg``) are observed and enforced
  when the guard is installed.
* Non-Python dependency processes (Redis server, Firestore emulator JVM) are
  bind-constrained to loopback by the runner; their own outbound egress is
  **not** per-connection observed by this guard.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EGRESS_SCOPE = (
    "Process-level socket guard in Python SUT/runner/loopback: TCP connect/connect_ex/"
    "create_connection and DNS (getaddrinfo/gethostbyname/gethostbyname_ex) and UDP "
    "unconnected sendto/sendmsg are observed and enforced (default-deny + declared "
    "loopback allow-list). Non-Python dependency processes (Redis server, Firestore "
    "emulator JVM) are bind-constrained to loopback by the runner; their own outbound "
    "egress is not per-connection observed by this guard."
)


def _topology_hash(topology: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the canonical topology-contract encoding."""
    canonical = json.dumps(topology, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _resolve_allow_ports(
    topology: dict[str, Any], ports: dict[str, int], firestore_host: str
) -> dict[str, frozenset[int]]:
    """Resolve every declared egress_allow_list entry to the actual port per role.

    Returns ``{role: frozenset[int]}`` of ports the guard is permitted to allow
    for that role.  This is what the validator recomputes to bind allowed
    egress attempts to the topology contract.
    """
    firestore_port: int | None = None
    if ":" in firestore_host:
        try:
            firestore_port = int(firestore_host.rsplit(":", 1)[1])
        except ValueError:
            firestore_port = None
    result: dict[str, frozenset[int]] = {}
    for entry in topology.get("egress_allow_list", []):
        role = entry.get("role", "")
        target = entry.get("to", "")
        port: int | None = None
        if target == "firestore":
            port = firestore_port
        elif target in ports:
            port = ports[target]
        if port is not None:
            result.setdefault(role, set()).add(port)
    return {role: frozenset(ps) for role, ps in result.items()}


def _classify_attempt(event: dict[str, Any], ports: dict[str, int], firestore_host: str) -> str:
    port = event.get("port")
    firestore_port = None
    if ":" in firestore_host:
        try:
            firestore_port = int(firestore_host.rsplit(":", 1)[1])
        except ValueError:
            pass
    if port is not None:
        if firestore_port is not None and port == firestore_port:
            return "firestore-emulator"
        for name, p in ports.items():
            if p == port:
                return name
        return f"port:{port}"
    return "dns-loopback"


def build_attestation(
    *,
    topology: dict[str, Any],
    health_records: list[Any],
    events: list[dict[str, Any]],
    ports: dict[str, int],
    firestore_emulator_host: str,
    outcome: str,
    fault_controls: dict[str, str],
) -> dict[str, Any]:
    """Build the attestation artifact from raw evidence.

    Embeds the topology contract, resolved ports, Firestore host, and the full
    raw evidence stream so the checker can recompute every claim independently.
    """
    egress_attempts = [e for e in events if e.get("event") in ("egress_attempt", "dns_attempt")]
    denied = [e for e in egress_attempts if e.get("decision") == "deny"]

    by_purpose: dict[str, int] = {}
    allowed_count = 0
    for e in egress_attempts:
        if e.get("decision") == "allow":
            allowed_count += 1
            purpose = _classify_attempt(e, ports, firestore_emulator_host)
            by_purpose[purpose] = by_purpose.get(purpose, 0) + 1

    roles_summary = [
        {
            "name": rh.name,
            "pid": rh.pid,
            "port": rh.port,
            "ready": rh.ready,
            "ready_probe": rh.ready_probe,
        }
        for rh in health_records
    ]

    return {
        "schema_version": 2,
        "harness": "omi-replay-harness",
        "phase": "0A",
        "feasibility_only": True,
        "topology_contract": topology,
        "topology_contract_sha256": _topology_hash(topology),
        "ports": dict(ports),
        "firestore_emulator_host": firestore_emulator_host,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "roles": roles_summary,
        "egress": {
            "policy": "default-deny",
            "scope": EGRESS_SCOPE,
            "attempts_observed": len(egress_attempts),
            "allowed": allowed_count,
            "denied": len(denied),
            "by_purpose": by_purpose,
            "denied_attempts": denied,
            "every_attempt_matched_declared_fake": len(denied) == 0,
        },
        "invariants": {
            "all_roles_started": all(rh.ready for rh in health_records) if health_records else False,
            "all_roles_ready": all(rh.ready for rh in health_records) if health_records else False,
            "no_denied_egress": len(denied) == 0,
            "no_undeclared_loopback_peer": len(denied) == 0,
        },
        "fault_controls_active": fault_controls,
        "outcome": outcome,
        "raw_evidence": events,
    }


def validate_attestation(attestation: dict[str, Any]) -> list[str]:
    """Independently validate an attestation artifact.

    Returns a list of human-readable violations (empty = pass).  Every claimed
    invariant is recomputed from the embedded topology contract, ports,
    Firestore host, and raw evidence — builder-produced summary fields are
    cross-checked, never trusted.
    """
    violations: list[str] = []

    topology = attestation.get("topology_contract")
    if not isinstance(topology, dict):
        return ["attestation missing embedded topology_contract"]

    # 1. Topology hash binding.
    recomputed_hash = _topology_hash(topology)
    if attestation.get("topology_contract_sha256") != recomputed_hash:
        violations.append(
            f"topology hash mismatch: claimed {attestation.get('topology_contract_sha256')!r}, "
            f"recomputed {recomputed_hash}"
        )
    # 2. Role completeness: every topology role present and ready.
    topology_roles = set(topology.get("roles", {}).keys())
    roles = attestation.get("roles", [])
    attested_roles = {r.get("name") for r in roles if isinstance(r, dict)}
    for name in sorted(topology_roles):
        if name not in attested_roles:
            violations.append(f"topology role {name!r} missing from attestation roles")
    if not roles:
        violations.append("no roles in attestation")
    for role in roles:
        if not isinstance(role, dict):
            violations.append(f"role entry is not an object: {role!r}")
            continue
        if not role.get("ready"):
            violations.append(f"role {role.get('name')} not ready")
        if not role.get("ready_probe"):
            violations.append(f"role {role.get('name')} missing ready_probe")

    # 3. Egress recompute from raw evidence.
    raw = attestation.get("raw_evidence")
    if not isinstance(raw, list) or not raw:
        violations.append("no raw_evidence embedded — cannot verify egress (guard may not have been installed)")
        raw = []
    egress_events = [e for e in raw if isinstance(e, dict) and e.get("event") in ("egress_attempt", "dns_attempt")]
    recomputed_denied = [e for e in egress_events if e.get("decision") == "deny"]
    recomputed_allowed = sum(1 for e in egress_events if e.get("decision") == "allow")

    egress = attestation.get("egress", {})
    if egress.get("denied", -1) != len(recomputed_denied):
        violations.append(
            f"egress.denied forgery: claimed {egress.get('denied')}, recomputed {len(recomputed_denied)} from raw evidence"
        )
    if egress.get("allowed", -1) != recomputed_allowed:
        violations.append(
            f"egress.allowed forgery: claimed {egress.get('allowed')}, recomputed {recomputed_allowed} from raw evidence"
        )
    if recomputed_allowed == 0:
        violations.append("zero allowed egress attempts — guard may not have been installed")

    # 4. Allow-list binding: every allowed attempt must match a declared entry.
    ports = attestation.get("ports", {})
    firestore_host = attestation.get("firestore_emulator_host", "")
    if isinstance(ports, dict) and isinstance(firestore_host, str):
        allowed_by_role = _resolve_allow_ports(topology, ports, firestore_host)
        for e in egress_events:
            if e.get("decision") != "allow":
                continue
            port = e.get("port")
            role = e.get("role", "")
            if port is None:
                continue  # DNS-loopback allow; no port to bind.
            permitted = allowed_by_role.get(role, frozenset())
            if port not in permitted:
                violations.append(
                    f"allowed egress to undeclared port {port} (role={role}) — not in topology allow-list"
                )

    # 5. Invariant recompute.
    invariants = attestation.get("invariants", {})
    expected_no_denied = len(recomputed_denied) == 0
    expected_all_ready = bool(roles) and all(r.get("ready") for r in roles if isinstance(r, dict))
    recomputed_invariants = {
        "all_roles_started": expected_all_ready,
        "all_roles_ready": expected_all_ready,
        "no_denied_egress": expected_no_denied,
        "no_undeclared_loopback_peer": expected_no_denied,
    }
    for key, value in recomputed_invariants.items():
        if invariants.get(key) != value:
            violations.append(f"invariant {key} claimed {invariants.get(key)!r}, recomputed {value!r}")

    return violations


def validate_attestation_file(path: str | Path) -> int:
    """CLI entry point: validate an attestation JSON file. Exit 0 = pass."""
    attestation = json.loads(Path(path).read_text())
    violations = validate_attestation(attestation)
    if violations:
        import sys

        print(f"FAIL: {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"OK: attestation valid (outcome={attestation.get('outcome')})")
    return 0
