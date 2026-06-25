"""Schema validation for consolidated memory rollout readiness gates."""

from __future__ import annotations

import json

import pytest

from scripts.readiness.loader import build_report, list_gate_ids

ALLOWED_STATUS = {"BLOCKED", "NOT_RUN", "READY_LOCAL_CONTRACT", "PASSED", "NO_GO"}
SAFE_BY_DEFAULT_KEYS = {
    "read_only": True,
    "mutation_allowed": False,
    "production_rollout_approved": False,
    "approval_claimed": False,
}


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_report_round_trips_json(gate_id: str):
    report = build_report(gate_id, execute=False)
    round_tripped = json.loads(json.dumps(report, sort_keys=True, default=str))
    assert round_tripped == report


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_safe_by_default_inventory(gate_id: str):
    report = build_report(gate_id, execute=False)
    if "status" in report:
        assert report["status"] in ALLOWED_STATUS
    for key, expected in SAFE_BY_DEFAULT_KEYS.items():
        if key in report:
            assert report[key] is expected, f"{gate_id}.{key}"
    if "network_or_provider_calls_executed" in report:
        assert report["network_or_provider_calls_executed"] is False
    if "firestore_reads_executed" in report:
        assert report["firestore_reads_executed"] is False
    if "firestore_writes_executed" in report:
        assert report["firestore_writes_executed"] is False


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_execute_mode_preserves_blocked_posture(gate_id: str):
    report = build_report(gate_id, execute=True)
    if "status" in report:
        assert report["status"] in ALLOWED_STATUS
    if "production_rollout_approved" in report:
        assert report["production_rollout_approved"] is False
    if "approval_claimed" in report:
        assert report["approval_claimed"] is False
