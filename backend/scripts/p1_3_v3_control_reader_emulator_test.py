#!/usr/bin/env python3
"""Firestore-emulator proof for the memory `/v3` control-reader adapter.

This script is intentionally emulator-only. It exits before constructing a
Firestore client unless FIRESTORE_EMULATOR_HOST is set by `firebase emulators:exec`.
It writes only local emulator fixtures under users/{uid}/memory_control/state and
server-owned gate docs, then reads them through the same adapter/contract seam used
by unit tests. It does not wire runtime routes or contact production Firestore.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from google.cloud import firestore

from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from utils.memory.v3.control_reader_contract import (
    V3ControlDecisionReason,
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    decide_v3_control_route,
)
from utils.memory.v3.control_state_adapter import read_v3_control

PROJECT_ID = os.environ.get("GCLOUD_PROJECT") or os.environ.get("FIREBASE_PROJECT") or "demo-memory"
# This is the code-owned canonical entitlement; the emulator remains isolated
# by FIRESTORE_EMULATOR_HOST and never contacts the real account.
UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
CONTROL_PATH = MemoryCollections(uid=UID).memory_control_state
GLOBAL_READ_GATE_PATH = "memory_control/global_read_gate"
WRITE_CONVERGENCE_GATE_PATH = "memory_control/write_convergence_gate"


@dataclass(frozen=True)
class ProofCase:
    case_id: str
    route_family: V3ControlRouteFamily
    reason: V3ControlDecisionReason
    control_overrides: dict[str, Any] | None = None
    global_gate_overrides: dict[str, Any] | None = None
    write_gate_overrides: dict[str, Any] | None = None
    request: V3ControlReaderRequest = V3ControlReaderRequest(UID, 50, False, True)
    write_control_doc: bool = True


def _require_emulator() -> None:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise SystemExit("BLOCKED: FIRESTORE_EMULATOR_HOST is required; refusing production Firestore access")


def _control_doc(**overrides: Any) -> dict[str, Any]:
    doc = {
        "uid": UID,
        "schema_version": 1,
        "mode": "read",
        "mode_epoch": 1,
        "cutover_epoch": 1,
        "account_generation": 50,
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": {"shadow": "passed", "write": "passed", "read": "passed"},
        "grants": {"omi_chat": {"default_memory": True, "archive": False}},
    }
    doc.update(overrides)
    return doc


def _global_gate(**overrides: Any) -> dict[str, Any]:
    doc = {"memory_reads_enabled": True, "kill_switch_active": False}
    doc.update(overrides)
    return doc


def _write_gate(**overrides: Any) -> dict[str, Any]:
    doc = {
        "durable_outbox_enabled": True,
        "dual_write_projection_ready": True,
        "delete_convergence_ready": True,
        "idempotency_contract_ready": True,
    }
    doc.update(overrides)
    return doc


def _reset_fixture(db: firestore.Client) -> None:
    for path in (CONTROL_PATH, GLOBAL_READ_GATE_PATH, WRITE_CONVERGENCE_GATE_PATH):
        db.document(path).delete()


def _write_fixture(db: firestore.Client, case: ProofCase) -> None:
    _reset_fixture(db)
    if case.write_control_doc:
        db.document(CONTROL_PATH).set(_control_doc(**(case.control_overrides or {})))  # type: ignore[reportUnknownMemberType]  # firestore set
    db.document(GLOBAL_READ_GATE_PATH).set(_global_gate(**(case.global_gate_overrides or {})))  # type: ignore[reportUnknownMemberType]  # firestore set
    db.document(WRITE_CONVERGENCE_GATE_PATH).set(_write_gate(**(case.write_gate_overrides or {})))  # type: ignore[reportUnknownMemberType]  # firestore set


def _assert_case(db: firestore.Client, case: ProofCase) -> None:
    _write_fixture(db, case)
    result = read_v3_control(uid=UID, db_client=db)
    decision = decide_v3_control_route(case.request, result)
    assert result.source_path == CONTROL_PATH, case.case_id
    assert decision.route_family == case.route_family, (case.case_id, decision)
    assert decision.reason == case.reason, (case.case_id, decision)
    assert decision.fallback_to_legacy_allowed is False, case.case_id
    if case.route_family == V3ControlRouteFamily.MEMORY_PROJECTION:
        assert result.state is not None, case.case_id
        assert result.state.uid == UID, case.case_id
        assert result.state.effective_mode == MemoryRolloutMode.read, case.case_id
        assert result.state.default_memory_grant is True, case.case_id
        assert result.state.projection_ready is True, case.case_id
        assert result.state.rollout_write_ready is True, case.case_id
        assert result.state.global_read_gate_open is True, case.case_id
        assert result.state.write_convergence_ready is True, case.case_id
        assert decision.requires_projection_reader is True, case.case_id


def main() -> int:
    _require_emulator()
    db = firestore.Client(project=PROJECT_ID)
    cases = [
        ProofCase(
            "memory_projection_allowed",
            V3ControlRouteFamily.MEMORY_PROJECTION,
            V3ControlDecisionReason.MEMORY_PROJECTION_ALLOWED,
        ),
        ProofCase(
            "missing_control_doc",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.MISSING_CONTROL_DOC,
            write_control_doc=False,
        ),
        ProofCase(
            "malformed_control_doc",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
            control_overrides={"mode_epoch": "bad"},
        ),
        ProofCase(
            "no_default_memory_grant",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT,
            control_overrides={"grants": {"omi_chat": {"default_memory": False, "archive": False}}},
        ),
        ProofCase(
            "projection_not_ready",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.PROJECTION_NOT_READY,
            control_overrides={"fallback_projection_ready": False},
        ),
        ProofCase(
            "write_convergence_not_ready",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY,
            write_gate_overrides={"dual_write_projection_ready": False},
        ),
        ProofCase(
            "global_gate_closed",
            V3ControlRouteFamily.FAIL_CLOSED,
            V3ControlDecisionReason.GLOBAL_READ_GATE_CLOSED,
            global_gate_overrides={"memory_reads_enabled": False},
        ),
    ]
    try:
        for case in cases:
            _assert_case(db, case)
    finally:
        _reset_fixture(db)
    print(
        "PASS: emulator Admin-context fixture read from users/{uid}/memory_control/state mapped "
        f"through read_v3_control/decide_v3_control_route for {len(cases)} cases; "
        "no production Firestore or runtime /v3 wiring used"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
