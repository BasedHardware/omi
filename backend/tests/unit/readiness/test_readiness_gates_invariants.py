"""Data-driven per-gate invariants (replaces per-script REQUIRED_* boilerplate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.readiness._paths import READINESS_DIR
from scripts.readiness.loader import build_report, list_gate_ids

INVARIANTS_DIR = READINESS_DIR / "invariants"


def _load_invariants(gate_id: str) -> dict:
    path = INVARIANTS_DIR / f"{gate_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_required_surface_ids_present(gate_id: str):
    invariants = _load_invariants(gate_id)
    required_surfaces = invariants.get("REQUIRED_SURFACES")
    if not required_surfaces:
        return
    report = build_report(gate_id, execute=False)
    matrix = report.get("surface_contract_matrix") or report.get("behavior_contract_matrix") or {}
    if isinstance(matrix, dict):
        missing = set(required_surfaces) - set(matrix)
        assert not missing, f"{gate_id} missing surfaces {missing}"


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_required_gap_ids_present(gate_id: str):
    invariants = _load_invariants(gate_id)
    required_gaps = invariants.get("REQUIRED_GAPS")
    if not required_gaps:
        return
    report = build_report(gate_id, execute=True)
    gaps = {gap["gap_id"]: gap for gap in report.get("remaining_gaps", [])}
    missing = set(required_gaps) - set(gaps)
    assert not missing, f"{gate_id} missing gaps {missing}"


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_required_route_references_present(gate_id: str):
    invariants = _load_invariants(gate_id)
    required_routes = invariants.get("REQUIRED_ROUTE_REFERENCES")
    if not required_routes:
        return
    report = build_report(gate_id, execute=True)
    routes = {surface["route"]: surface for surface in report.get("v3_surfaces", [])}
    for route, expected_id in required_routes.items():
        assert route in routes, f"{gate_id} missing route {route}"
        assert routes[route]["surface_id"] == expected_id


@pytest.mark.parametrize("gate_id", list_gate_ids())
def test_gate_proof_matrix_keys_when_present(gate_id: str):
    invariants = _load_invariants(gate_id)
    required_keys = invariants.get("REQUIRED_CASE_KEYS")
    if not required_keys:
        return
    report = build_report(gate_id, execute=False)
    proof_matrix = report.get("proof_matrix")
    if isinstance(proof_matrix, dict):
        assert set(proof_matrix) == set(required_keys), f"{gate_id} proof_matrix keys mismatch"
        for case in proof_matrix.values():
            assert case.get("evidence") == []
            assert case.get("status") == "NOT_RUN"
