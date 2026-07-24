"""Hermetic unit tests for the Phase 0A replay-harness attestation checker.

The validator recomputes every claimed invariant from the embedded raw evidence
and a checked-in topology contract supplied independently of the artifact, and
rejects fabricated summaries. It is NOT an independent witness of process
behavior: the raw evidence is emitted by the in-process socket guard (part of
the SUT). The attestation proves self-consistency and summary-forgery rejection,
not third-party attestation of real kernel egress. No emulator/network needed.
"""

from __future__ import annotations

import copy
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
        "schema_version": 2,
        "harness": "omi-replay-harness",
        "phase": "0A",
        "roles": {
            "redis": {
                "command": ["redis-server"],
                "health": {"type": "tcp"},
                "port": "dynamic",
                "runtime": "non-python",
                "guarded": False,
            },
            "worker": {
                "command": ["python", "-m", "uvicorn"],
                "health": {"type": "http", "path": "/__replay/health", "expect_role": "worker"},
                "port": "dynamic",
                "startup_timeout_seconds": 120,
                "runtime": "python",
                "guarded": True,
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
    # Every guarded Python role must carry a guard_installed event.
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
        violations = att.validate_attestation(_valid_attestation(), expected_topology=_topology())
        assert violations == []

    def test_redis_tcp_role_is_included(self):
        record = _valid_attestation()
        role_names = [r["name"] for r in record["roles"]]
        assert "redis" in role_names
        violations = att.validate_attestation(record, expected_topology=_topology())
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
# Point 2 — pin to checked-in contract (independent of the artifact)
# --------------------------------------------------------------------------- #


class TestCheckedInTopologyBinding:
    def test_modified_worker_command_with_recomputed_hash_rejected(self):
        """The adversarial case: an attacker edits the embedded worker command and
        recomputes the embedded topology hash. Without an independent expected
        contract, this would pass. The validator must reject it."""
        record = _valid_attestation()
        record["topology_contract"]["roles"]["worker"]["command"] = ["python", "-m", "evil"]
        record["topology_contract_sha256"] = att._topology_hash(record["topology_contract"])
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("does not match" in v or "expected" in v.lower() for v in violations)

    def test_embedded_topology_tampered_hash_rejected(self):
        """Tamper with the hash field but not the topology body."""
        record = _valid_attestation()
        record["topology_contract_sha256"] = "f" * 64
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("hash" in v.lower() for v in violations)

    def test_swapped_topology_contract_rejected(self):
        record = _valid_attestation()
        record["topology_contract"]["roles"]["evil"] = {"health": {"type": "tcp"}}
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("does not match" in v or "expected" in v.lower() for v in violations)

    def test_no_expected_topology_still_checks_internal_hash(self):
        """When no expected contract is supplied, the internal hash binding still holds."""
        record = _valid_attestation()
        record["topology_contract_sha256"] = "0" * 64
        violations = att.validate_attestation(record)
        assert any("hash" in v.lower() for v in violations)

    def test_missing_topology_role_rejected(self):
        record = _valid_attestation()
        record["roles"] = [r for r in record["roles"] if r["name"] != "redis"]
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("redis" in v for v in violations)

    def test_unready_role_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "redis":
                r["ready"] = False
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("redis" in v and "ready" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Point 3 — recompute allowed egress with host (not just port)
# --------------------------------------------------------------------------- #


class TestEgressHostRecomputation:
    def test_remote_host_on_declared_port_marked_allow_rejected(self):
        """The critical forgery: a remote host using a declared port, marked allow.
        A port-only check accepts this; the validator must recompute the decision
        from host+port and reject it."""
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "10.0.0.1",
                "port": 6390,  # redis port is declared
                "loopback": False,
                "decision": "allow",
            }
        )
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("remote" in v.lower() or "not loopback" in v.lower() or "host" in v.lower() for v in violations)

    def test_decision_field_trusted_not_recomputed_rejected(self):
        """An event whose recorded decision contradicts the recomputed decision is a forgery."""
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "10.0.0.1",
                "port": 443,
                "loopback": False,
                "decision": "allow",  # recorded allow, but host is remote → should be deny
            }
        )
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("remote" in v.lower() or "not loopback" in v.lower() for v in violations)

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
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("54321" in v or "undeclared" in v.lower() for v in violations)

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
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("denied" in v.lower() for v in violations)

    def test_forged_allowed_count_rejected(self):
        record = _valid_attestation()
        record["egress"]["allowed"] = 999
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("allowed" in v.lower() for v in violations)

    def test_no_raw_evidence_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"] = []
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("evidence" in v.lower() or "guard" in v.lower() for v in violations)

    def test_removed_evidence_event_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"] = record["raw_evidence"][:1]  # drop an allow
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("allowed" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Point 4 — guard-installation evidence per guarded role; non-Python exempt
# --------------------------------------------------------------------------- #


class TestGuardEvidence:
    def test_guarded_role_missing_guard_installed_rejected(self):
        """Every explicitly guarded Python role must carry guard_installed evidence."""
        record = _valid_attestation()
        record["raw_evidence"] = [e for e in record["raw_evidence"] if e.get("event") != "guard_installed"]
        # Restore one egress event so the zero-allowed check does not dominate.
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "127.0.0.1",
                "port": 6390,
                "loopback": True,
                "decision": "allow",
            }
        )
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("guard" in v.lower() and "worker" in v.lower() for v in violations)

    def test_non_python_role_does_not_require_guard_evidence(self):
        """redis is non-Python (bind-constrained); it must not require guard evidence."""
        record = _valid_attestation()
        # worker has guard_installed; redis is exempt.
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert not any("redis" in v and "guard" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Point 4 — runner removed from claimed scope; invariant recomputation
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
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("no_denied_egress" in v for v in violations)

    def test_no_roles_rejected(self):
        record = _valid_attestation()
        record["roles"] = []
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("role" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Scope accuracy (honest, narrowed claims)
# --------------------------------------------------------------------------- #


class TestScopeAccuracy:
    def test_egress_scope_documented_and_bounded(self):
        record = _valid_attestation()
        scope = record["egress"]["scope"]
        assert isinstance(scope, str) and len(scope) > 20

    def test_scope_does_not_overclaim_independent_verification(self):
        """The scope must not claim independent/third-party verification of egress."""
        record = _valid_attestation()
        scope = record["egress"]["scope"].lower()
        assert "independently verif" not in scope
        assert "third-party" not in scope
