"""Self-consistent topology/egress attestation builder and checker.

The builder joins a checked-in topology contract, per-role health probes, and
the egress-attempt log into a single JSON artifact. The checker recomputes every
claimed invariant from the embedded raw evidence AND an expected checked-in
topology contract supplied independently of the artifact — it does not trust the
builder's summary assertions, the recorded event ``decision`` field, or an
artifact-embedded topology hash.

HONEST SCOPE (not over-claimed): the raw evidence is emitted by the in-process
socket guard, which is itself part of the SUT under test. Therefore the
attestation proves **self-consistency and summary-forgery rejection** (every
summary is recomputed from raw evidence + checked-in contract, and any mismatch
is rejected), **not** independent/third-party attestation of real kernel egress.
The attestation mechanism composes end-to-end; it is not a security audit.

Guarded-scope claims:

* Python SUT role processes (admission, worker, cloud-tasks-loopback) install the
  in-process socket guard and emit ``guard_installed`` evidence.
* The runner/orchestrator launches and observes roles; it is the trusted launcher
  and is **not** per-connection guarded.
* Non-Python dependency processes (Redis server, Firestore emulator JVM) are
  bind-constrained to loopback by the runner; their own outbound egress is not
  per-connection observed.

Observed/enforced egress surface (in guarded Python roles):

* TCP connection-oriented egress (``connect``, ``connect_ex``,
  ``create_connection``) and DNS resolution (``getaddrinfo``,
  ``gethostbyname``, ``gethostbyname_ex``) are observed and enforced.
* UDP unconnected sends (``sendto``, ``sendmsg``) are observed and enforced.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EGRESS_SCOPE = (
    "In-process socket guard in guarded Python SUT roles (admission, worker, "
    "cloud-tasks-loopback): TCP connect/connect_ex/create_connection, DNS "
    "(getaddrinfo/gethostbyname/gethostbyname_ex), and UDP sendto/sendmsg are "
    "observed and enforced (default-deny + declared loopback allow-list). The "
    "runner/orchestrator is the trusted launcher and is not per-connection guarded. "
    "Non-Python dependency processes (Redis server, Firestore emulator JVM) are "
    "bind-constrained to loopback; their own outbound egress is not per-connection "
    "observed. Raw evidence is emitted by the in-process guard (part of the SUT); "
    "the attestation proves self-consistency and summary-forgery rejection, not "
    "independent attestation of real kernel egress."
)


def _topology_hash(topology: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the canonical topology-contract encoding."""
    canonical = json.dumps(topology, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _is_loopback(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("idna", errors="replace")
    if not isinstance(host, str):
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized in {"", "localhost"}:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback


def _resolve_allow_endpoints(
    topology: dict[str, Any], ports: dict[str, int], firestore_host: str
) -> dict[str, frozenset[tuple[str, int | None]]]:
    """Resolve every declared egress_allow_list entry to a (host, port) endpoint per role.

    Returns ``{role: frozenset[(host, port)]}``. This is what the validator
    recomputes to bind allowed egress attempts to BOTH the declared host and port
    of the topology contract — a remote host on a declared port is not a match.
    """
    firestore_host_part = ""
    firestore_port: int | None = None
    if ":" in firestore_host:
        firestore_host_part = firestore_host.rsplit(":", 1)[0]
        try:
            firestore_port = int(firestore_host.rsplit(":", 1)[1])
        except ValueError:
            firestore_port = None
    result: dict[str, frozenset[tuple[str, int | None]]] = {}
    for entry in topology.get("egress_allow_list", []):
        role = entry.get("role", "")
        target = entry.get("to", "")
        if target == "firestore":
            if firestore_port is not None:
                result.setdefault(role, set()).add((firestore_host_part, firestore_port))
        elif target in ports:
            result.setdefault(role, set()).add(("127.0.0.1", ports[target]))
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


def _recompute_decision(event: dict[str, Any], allow_endpoints: dict[str, frozenset[tuple[str, int | None]]]) -> str:
    """Recompute the allow/deny decision from the event's host+port and the topology
    allow-list, WITHOUT trusting the recorded ``decision`` field.

    - DNS attempts: allow iff the host is loopback.
    - Egress attempts: allow iff ``(host, port)`` is a declared endpoint for the role.
    """
    if event.get("event") == "dns_attempt":
        return "allow" if _is_loopback(event.get("host")) else "deny"
    host = event.get("host")
    port = event.get("port")
    role = event.get("role", "")
    declared = allow_endpoints.get(role, frozenset())
    return "allow" if (host, port) in declared else "deny"


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
    raw evidence stream so the checker can recompute every claim. Summary fields
    are convenience only — the checker never trusts them.
    """
    egress_attempts = [e for e in events if e.get("event") in ("egress_attempt", "dns_attempt")]
    allow_endpoints = _resolve_allow_endpoints(topology, ports, firestore_emulator_host)

    by_purpose: dict[str, int] = {}
    allowed_count = 0
    denied_count = 0
    for e in egress_attempts:
        decision = _recompute_decision(e, allow_endpoints)
        if decision == "allow":
            allowed_count += 1
            purpose = _classify_attempt(e, ports, firestore_emulator_host)
            by_purpose[purpose] = by_purpose.get(purpose, 0) + 1
        else:
            denied_count += 1

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
        "schema_version": 3,
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
            "denied": denied_count,
            "by_purpose": by_purpose,
        },
        "invariants": {
            "all_roles_started": all(rh.ready for rh in health_records) if health_records else False,
            "all_roles_ready": all(rh.ready for rh in health_records) if health_records else False,
            "no_denied_egress": denied_count == 0,
            "no_undeclared_loopback_peer": denied_count == 0,
        },
        "fault_controls_active": fault_controls,
        "outcome": outcome,
        "raw_evidence": events,
    }


def validate_attestation(attestation: dict[str, Any], *, expected_topology: dict[str, Any] | None = None) -> list[str]:
    """Validate an attestation artifact.

    Returns a list of human-readable violations (empty = pass). Every claimed
    invariant is recomputed from the embedded raw evidence and (when supplied)
    the expected checked-in topology contract supplied independently of the
    artifact — builder-produced summary fields and recorded event decisions are
    cross-checked, never trusted.

    ``expected_topology`` is the checked-in contract read independently (e.g. the
    committed ``topology.json``). When supplied, the artifact's embedded topology
    must match it exactly, so a modified worker command with a recomputed
    embedded hash is rejected.
    """
    violations: list[str] = []

    topology = attestation.get("topology_contract")
    if not isinstance(topology, dict):
        return ["attestation missing embedded topology_contract"]

    # 1. Bind to the checked-in contract (independent of the artifact).
    if expected_topology is not None and topology != expected_topology:
        violations.append(
            "embedded topology does not match the expected checked-in contract "
            "(worker command/role/allow-list may have been modified)"
        )
    # 2. Internal hash binding (catches hash-field tampering).
    recomputed_hash = _topology_hash(topology)
    if attestation.get("topology_contract_sha256") != recomputed_hash:
        violations.append(
            f"topology hash mismatch: claimed {attestation.get('topology_contract_sha256')!r}, "
            f"recomputed {recomputed_hash}"
        )
    # 3. Role completeness: every topology role present and ready.
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

    # 4. Egress recompute from raw evidence — do NOT trust the decision field.
    raw = attestation.get("raw_evidence")
    if not isinstance(raw, list) or not raw:
        violations.append("no raw_evidence embedded — cannot verify egress (guard may not have been installed)")
        raw = []
    egress_events = [e for e in raw if isinstance(e, dict) and e.get("event") in ("egress_attempt", "dns_attempt")]
    ports = attestation.get("ports", {})
    firestore_host = attestation.get("firestore_emulator_host", "")
    if not isinstance(ports, dict):
        ports = {}
    if not isinstance(firestore_host, str):
        firestore_host = ""
    allow_endpoints = _resolve_allow_endpoints(topology, ports, firestore_host)

    recomputed_allowed = 0
    recomputed_denied = 0
    for e in egress_events:
        host = e.get("host")
        port = e.get("port")
        role = e.get("role", "")
        decision = _recompute_decision(e, allow_endpoints)
        if decision == "allow":
            recomputed_allowed += 1
        else:
            recomputed_denied += 1
        recorded = e.get("decision")
        if recorded == "allow" and decision == "deny":
            # Critical forgery: an event marked allow that is not a declared
            # loopback endpoint (e.g. a remote host on a declared port).
            kind = "remote host (not loopback)" if not _is_loopback(host) else "undeclared loopback port"
            violations.append(
                f"egress event marked allow is not a declared endpoint: {kind} "
                f"(role={role}, host={host!r}, port={port}); decision recomputed as deny"
            )
        elif recorded == "deny" and decision == "allow":
            violations.append(
                f"egress event marked deny is actually a declared endpoint "
                f"(role={role}, host={host!r}, port={port}); recorded decision contradicts recompute"
            )

    egress = attestation.get("egress", {})
    if egress.get("denied", -1) != recomputed_denied:
        violations.append(
            f"egress.denied forgery: claimed {egress.get('denied')}, recomputed {recomputed_denied} from raw evidence"
        )
    if egress.get("allowed", -1) != recomputed_allowed:
        violations.append(
            f"egress.allowed forgery: claimed {egress.get('allowed')}, recomputed {recomputed_allowed} from raw evidence"
        )
    if recomputed_allowed == 0 and recomputed_denied == 0:
        violations.append("zero egress attempts observed — guard may not have been installed")

    # 5. Guard-installation evidence for every explicitly guarded Python role.
    guarded_roles = {
        name for name, r in topology.get("roles", {}).items() if isinstance(r, dict) and r.get("guarded") is True
    }
    installed_roles = {e.get("role") for e in raw if isinstance(e, dict) and e.get("event") == "guard_installed"}
    for role in sorted(guarded_roles):
        if role not in installed_roles:
            violations.append(
                f"guarded role {role!r} has no guard_installed evidence in raw_evidence "
                "(guard may not have been installed in this Python role)"
            )

    # 6. Invariant recompute.
    invariants = attestation.get("invariants", {})
    expected_no_denied = recomputed_denied == 0
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


def validate_attestation_file(path: str | Path, *, expected_topology_path: str | Path | None = None) -> int:
    """CLI entry point: validate an attestation JSON file. Exit 0 = pass.

    When ``expected_topology_path`` is supplied, the artifact is bound to that
    checked-in contract independently of the artifact's embedded copy.
    """
    attestation = json.loads(Path(path).read_text())
    expected_topology = None
    if expected_topology_path is not None:
        expected_topology = json.loads(Path(expected_topology_path).read_text())
    violations = validate_attestation(attestation, expected_topology=expected_topology)
    if violations:
        import sys

        print(f"FAIL: {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"OK: attestation valid (outcome={attestation.get('outcome')})")
    return 0
