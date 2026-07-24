"""Hermetic unit tests for the Phase 0A replay-harness attestation checker.

The validator must be independently machine-verifiable: it recomputes every
claimed invariant from the embedded raw evidence and topology contract, and
rejects fabricated summaries.  No emulator, network, or live service required.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

from testing.replay_harness_phase0a import attestation as att

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_FIRESTORE_HOST = "127.0.0.1:8123"


def _topology() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "harness": "omi-replay-harness",
        "roles": {
            "redis": {"command": ["redis-server"], "health": {"type": "tcp"}, "port": "dynamic"},
            "worker": {
                "command": ["python", "-m", "uvicorn"],
                "health": {"type": "http", "path": "/__replay/health", "expect_role": "worker"},
                "port": "dynamic",
            },
        },
        "egress_allow_list": [
            {"role": "worker", "to": "firestore", "purpose": "firestore-emulator"},
            {"role": "worker", "to": "redis", "purpose": "redis"},
        ],
        "fault_controls": [],
        "non_goals": [],
    }


def _rh(name: str, port: int, probe: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, pid=1000, port=port, ready=True, ready_probe=probe or {"type": "tcp"})


def _health_records() -> list[SimpleNamespace]:
    return [
        _rh("redis", 6390),
        _rh("worker", 8090, {"type": "http", "path": "/__replay/health", "status": 200, "role": "worker"}),
    ]


def _ports() -> dict[str, int]:
    return {"redis": 6390, "worker": 8090}


def _egress_events() -> list[dict[str, Any]]:
    return [
        {"event": "guard_installed", "role": "worker", "allow_count": 2},
        {
            "event": "egress_attempt",
            "role": "worker",
            "host": "127.0.0.1",
            "port": 8123,
            "loopback": True,
            "decision": "allow",
        },
        {
            "event": "egress_attempt",
            "role": "worker",
            "host": "127.0.0.1",
            "port": 6390,
            "loopback": True,
            "decision": "allow",
        },
    ]


def _valid_attestation() -> dict[str, Any]:
    return att.build_attestation(
        topology=_topology(),
        health_records=_health_records(),
        events=_egress_events(),
        ports=_ports(),
        firestore_emulator_host=_FIRESTORE_HOST,
        outcome="feasible",
        fault_controls={},
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


class TestValidAttestation:
    def test_well_formed_attestation_has_no_violations(self):
        violations = att.validate_attestation(_valid_attestation())
        assert violations == []

    def test_redis_tcp_role_is_included(self):
        """Redis uses a TCP health probe and must appear in the attestation roles."""
        record = _valid_attestation()
        role_names = [r["name"] for r in record["roles"]]
        assert "redis" in role_names
        violations = att.validate_attestation(record)
        assert violations == []

    def test_topology_hash_is_recomputable(self):
        record = _valid_attestation()
        canonical = json.dumps(record["topology_contract"], sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        assert record["topology_contract_sha256"] == expected

    def test_topology_and_raw_evidence_embedded(self):
        record = _valid_attestation()
        assert "topology_contract" in record
        assert "raw_evidence" in record
        assert isinstance(record["raw_evidence"], list) and len(record["raw_evidence"]) >= 2


# --------------------------------------------------------------------------- #
# Forgery rejection — topology binding
# --------------------------------------------------------------------------- #


class TestTopologyBinding:
    def test_forged_topology_hash_rejected(self):
        record = _valid_attestation()
        record["topology_contract_sha256"] = "0" * 64
        violations = att.validate_attestation(record)
        assert any("topology" in v.lower() and "hash" in v.lower() for v in violations)

    def test_swapped_topology_contract_rejected(self):
        record = _valid_attestation()
        record["topology_contract"]["roles"]["evil"] = {"health": {"type": "tcp"}}
        violations = att.validate_attestation(record)
        assert any("topology" in v.lower() and "hash" in v.lower() for v in violations)

    def test_missing_topology_role_rejected(self):
        record = _valid_attestation()
        record["roles"] = [r for r in record["roles"] if r["name"] != "redis"]
        violations = att.validate_attestation(record)
        assert any("redis" in v for v in violations)

    def test_unready_role_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "redis":
                r["ready"] = False
        violations = att.validate_attestation(record)
        assert any("redis" in v and "ready" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Forgery rejection — egress recomputation
# --------------------------------------------------------------------------- #


class TestEgressRecomputation:
    def test_forged_zero_denied_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "10.0.0.1",
                "port": 443,
                "loopback": False,
                "decision": "deny",
            }
        )
        violations = att.validate_attestation(record)
        assert any("denied" in v.lower() for v in violations)

    def test_forged_allowed_count_rejected(self):
        record = _valid_attestation()
        record["egress"]["allowed"] = 999
        violations = att.validate_attestation(record)
        assert any("allowed" in v.lower() for v in violations)

    def test_allowed_egress_to_undeclared_port_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "127.0.0.1",
                "port": 54321,
                "loopback": True,
                "decision": "allow",
            }
        )
        violations = att.validate_attestation(record)
        assert any("54321" in v for v in violations)

    def test_no_raw_evidence_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"] = []
        violations = att.validate_attestation(record)
        assert any("evidence" in v.lower() or "guard" in v.lower() for v in violations)

    def test_removed_evidence_event_rejected(self):
        """Removing an egress event from raw_evidence but keeping the summary is a forgery."""
        record = _valid_attestation()
        record["raw_evidence"] = record["raw_evidence"][:1]  # drop an allow
        violations = att.validate_attestation(record)
        assert any("allowed" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Forgery rejection — invariant recomputation
# --------------------------------------------------------------------------- #


class TestInvariantRecomputation:
    def test_forged_invariant_true_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "10.0.0.1",
                "port": 443,
                "loopback": False,
                "decision": "deny",
            }
        )
        record["invariants"]["no_denied_egress"] = True
        violations = att.validate_attestation(record)
        assert any("no_denied_egress" in v for v in violations)

    def test_no_roles_rejected(self):
        record = _valid_attestation()
        record["roles"] = []
        violations = att.validate_attestation(record)
        assert any("role" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Scope accuracy
# --------------------------------------------------------------------------- #


class TestScopeAccuracy:
    def test_egress_scope_documented_and_bounded(self):
        """The attestation must state its enforcement scope, not over-claim."""
        record = _valid_attestation()
        scope = record["egress"]["scope"]
        assert isinstance(scope, str) and len(scope) > 20
