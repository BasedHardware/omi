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
                "health": {"type": "tcp", "host": "127.0.0.1"},
                "port": "dynamic",
                "runtime": "non-python",
                "guarded": False,
            },
            "worker": {
                "command": ["python", "-m", "uvicorn"],
                "health": {"type": "http", "host": "127.0.0.1", "path": "/__replay/health", "expect_role": "worker"},
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
    # Every topology role carries a role_allocated launcher/health-observation
    # record — the raw source the artifact-controlled summary is bound to.
    return [
        {"event": "guard_installed", "role": "worker", "allow_count": 2},
        {
            "event": "role_allocated",
            "role": "redis",
            "host": "127.0.0.1",
            "port": 6390,
            "pid": 1000,
            "health": {"type": "tcp"},
            "ready": True,
        },
        {
            "event": "role_allocated",
            "role": "worker",
            "host": "127.0.0.1",
            "port": 8090,
            "pid": 1000,
            "health": {"type": "http", "path": "/__replay/health", "expect_role": "worker"},
            "status": 200,
            "ready": True,
        },
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


# --------------------------------------------------------------------------- #
# Final-review 1 — a feasible outcome must require zero denied egress
# --------------------------------------------------------------------------- #


class TestOutcomeEgressBinding:
    """A ``feasible`` outcome must be invalid if any denied egress attempt exists.

    The validator previously accepted a self-consistent artifact that honestly
    reported ``no_denied_egress=false`` alongside an honest denied remote attempt,
    because it only checked summary consistency — not that a feasible outcome
    requires every required safety invariant (including zero denied egress) to
    hold. This is the honest-raw-denied-attempt-with-self-consistent-false-summary
    adversarial case.
    """

    def test_feasible_outcome_with_honest_denied_remote_rejected(self):
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
        # Honest summary: recompute to reflect the denied attempt so the artifact
        # is internally self-consistent — the only defect is outcome=feasible.
        record["egress"]["denied"] = record["egress"].get("denied", 0) + 1
        record["egress"]["attempts_observed"] = record["egress"].get("attempts_observed", 0) + 1
        record["invariants"]["no_denied_egress"] = False
        record["invariants"]["no_undeclared_loopback_peer"] = False
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert violations
        assert any("feasible" in v.lower() for v in violations)

    def test_non_feasible_outcome_with_denied_egress_not_outcome_violation(self):
        """A non-feasible outcome (e.g. blocked) may honestly carry denied egress
        without tripping the outcome-binding check (it must still be self-consistent)."""
        record = _valid_attestation()
        record["outcome"] = "blocked"
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
        record["egress"]["denied"] = record["egress"].get("denied", 0) + 1
        record["egress"]["attempts_observed"] = record["egress"].get("attempts_observed", 0) + 1
        record["invariants"]["no_denied_egress"] = False
        record["invariants"]["no_undeclared_loopback_peer"] = False
        violations = att.validate_attestation(record, expected_topology=_topology())
        # Self-consistent: the only violations, if any, must NOT be the outcome binding.
        assert not any("feasible" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Final-review 2 — undeclared loopback aliases rejected at the attestation layer
# --------------------------------------------------------------------------- #


class TestEgressAliasRejection:
    """Undeclared ``localhost``/``::1`` aliases on a declared port must recompute to
    deny at the attestation layer, with identical semantics to the runtime guard.
    The topology declares only ``127.0.0.1`` endpoints; an alias is not a declared
    endpoint.
    """

    def test_localhost_alias_on_declared_port_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "localhost",
                "port": 6390,  # redis declared on 127.0.0.1:6390, not localhost:6390
                "loopback": True,
                "decision": "allow",
            }
        )
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("localhost" in v.lower() or "not a declared" in v.lower() for v in violations)

    def test_ipv6_loopback_alias_on_declared_port_rejected(self):
        record = _valid_attestation()
        record["raw_evidence"].append(
            {
                "event": "egress_attempt",
                "role": "worker",
                "host": "::1",
                "port": 6390,  # redis declared on 127.0.0.1:6390, not [::1]:6390
                "loopback": True,
                "decision": "allow",
            }
        )
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("not a declared" in v.lower() or "host" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Final-review 3 — bind role readiness/ports/probes to the checked-in topology
# --------------------------------------------------------------------------- #


class TestRolePortProbeBinding:
    """Role readiness, resolved ports, and health probes must be bound to the
    independently supplied checked-in topology. The validator previously accepted
    fabricated role-ready summaries and arbitrary resolved ports because it checked
    only truthiness.
    """

    def test_role_port_not_matching_resolved_ports_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "worker":
                r["port"] = 9999  # ports["worker"] is 8090
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("worker" in v.lower() and "port" in v.lower() for v in violations)

    def test_altered_resolved_port_map_rejected(self):
        record = _valid_attestation()
        record["ports"]["worker"] = 7777  # summary still reports 8090
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("worker" in v.lower() and "port" in v.lower() for v in violations)

    def test_ready_probe_type_mismatch_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"] = {"type": "tcp"}  # topology declares http
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("worker" in v.lower() and ("probe" in v.lower() or "health" in v.lower()) for v in violations)

    def test_ready_probe_http_path_mismatch_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"] = {"type": "http", "path": "/wrong", "status": 200, "role": "worker"}
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("worker" in v.lower() and ("probe" in v.lower() or "health" in v.lower()) for v in violations)

    def test_ready_probe_http_role_mismatch_rejected(self):
        record = _valid_attestation()
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"] = {
                    "type": "http",
                    "path": "/__replay/health",
                    "status": 200,
                    "role": "not-worker",  # topology expect_role is "worker"
                }
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("worker" in v.lower() and ("probe" in v.lower() or "health" in v.lower()) for v in violations)

    def test_fabricated_role_not_in_topology_rejected(self):
        record = _valid_attestation()
        record["roles"].append({"name": "evil", "pid": 1, "port": 1, "ready": True, "ready_probe": {"type": "tcp"}})
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("evil" in v.lower() for v in violations)

    def test_dynamic_role_missing_from_resolved_ports_rejected(self):
        record = _valid_attestation()
        del record["ports"]["redis"]
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("redis" in v.lower() and "port" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Fourth review — topology health contract must enforce ready-success semantics
# --------------------------------------------------------------------------- #


class TestHealthSuccessSemantics:
    """The topology health contract must specify/enforce ready-success semantics.
    The validator previously checked probe type/path/role but never the successful
    response status, so a readiness probe that returned HTTP 500 passed.
    """

    def test_http_500_health_observation_rejected(self):
        """Raw observation and summary both report status=500 coherently; the
        validator must still reject it because 500 is not a success status."""
        record = _valid_attestation()
        for e in record["raw_evidence"]:
            if e.get("event") == "role_allocated" and e.get("role") == "worker":
                e["status"] = 500
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"]["status"] = 500
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("status" in v.lower() or "success" in v.lower() for v in violations)

    def test_http_404_health_observation_rejected(self):
        record = _valid_attestation()
        for e in record["raw_evidence"]:
            if e.get("event") == "role_allocated" and e.get("role") == "worker":
                e["status"] = 404
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"]["status"] = 404
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("status" in v.lower() or "success" in v.lower() for v in violations)

    def test_declared_expected_status_enforced(self):
        """When the topology declares an explicit expected_status, only that status
        satisfies success semantics (a 2xx that is not the declared value fails)."""
        record = _valid_attestation()
        record["topology_contract"]["roles"]["worker"]["health"]["expected_status"] = 204
        for e in record["raw_evidence"]:
            if e.get("event") == "role_allocated" and e.get("role") == "worker":
                e["status"] = 200
        for r in record["roles"]:
            if r["name"] == "worker":
                r["ready_probe"]["status"] = 200
        topo = _topology()
        topo["roles"]["worker"]["health"]["expected_status"] = 204
        violations = att.validate_attestation(record, expected_topology=topo)
        assert any("status" in v.lower() or "expected_status" in v.lower() for v in violations)


# --------------------------------------------------------------------------- #
# Fourth review — paired role+port+probe forgery bound to raw allocation record
# --------------------------------------------------------------------------- #


class TestRolePortProbeForge:
    """Dynamic role/port readiness must not be accepted merely because two
    artifact-controlled summary fields match. The validator must bind the summary
    to an explicit launcher allocation/health-observation raw record and validate
    role identity, endpoint, allocated port, probe contract, successful response,
    and process identity coherently against the checked-in topology and raw record.
    """

    def test_paired_role_port_pid_status_forge_rejected(self):
        """The exact adversarial case from the review: ports[worker] and
        roles[worker].port changed together to 7777, pid=1, probe status=500.
        The raw allocation record still reports the real port/pid/status, so the
        forged summary does not cohere with it."""
        record = _valid_attestation()
        record["ports"]["worker"] = 7777
        for r in record["roles"]:
            if r["name"] == "worker":
                r["port"] = 7777
                r["pid"] = 1
                r["ready_probe"]["status"] = 500
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert violations

    def test_paired_role_port_pid_forge_rejected_with_valid_status(self):
        """The port/pid forge alone (status still a valid 200) must be rejected on
        coherence grounds, proving rejection is not solely the status check."""
        record = _valid_attestation()
        record["ports"]["worker"] = 7777
        for r in record["roles"]:
            if r["name"] == "worker":
                r["port"] = 7777
                r["pid"] = 1
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any(
            "port" in v.lower() or "pid" in v.lower() or "cohere" in v.lower() or "allocation" in v.lower()
            for v in violations
        )

    def test_missing_role_allocated_record_rejected(self):
        """Every topology role must carry a role_allocated raw record; dropping it
        (so the summary is the only source) must be rejected."""
        record = _valid_attestation()
        record["raw_evidence"] = [
            e for e in record["raw_evidence"] if not (e.get("event") == "role_allocated" and e.get("role") == "worker")
        ]
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any(
            "worker" in v.lower()
            and ("allocation" in v.lower() or "role_allocated" in v.lower() or "health-observation" in v.lower())
            for v in violations
        )

    def test_role_allocated_wrong_endpoint_host_rejected(self):
        """The raw allocation host must match the topology-declared endpoint host;
        an alias (localhost) where the contract declares 127.0.0.1 is rejected."""
        record = _valid_attestation()
        for e in record["raw_evidence"]:
            if e.get("event") == "role_allocated" and e.get("role") == "worker":
                e["host"] = "localhost"
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("host" in v.lower() or "endpoint" in v.lower() for v in violations)

    def test_role_allocated_contract_path_mismatch_rejected(self):
        """The raw allocation's probe contract must match the topology health
        contract; a forged http path is rejected."""
        record = _valid_attestation()
        for e in record["raw_evidence"]:
            if e.get("event") == "role_allocated" and e.get("role") == "worker":
                e["health"]["path"] = "/wrong"
        violations = att.validate_attestation(record, expected_topology=_topology())
        assert any("path" in v.lower() or "probe" in v.lower() or "health" in v.lower() for v in violations)
