#!/usr/bin/env python3
"""Shared helpers for memory readiness scripts with optional fail-closed --require-go."""

from __future__ import annotations

import argparse
from typing import Any

GATE_STATUS_GO = "GO"
GATE_STATUS_BLOCKED = "BLOCKED"
GATE_STATUS_NOT_RUN = "NOT_RUN"


def evaluate_gates(gates: dict[str, Any]) -> tuple[str, list[str]]:
    """Return overall status and blockers for gate dicts with per-gate ``status`` keys."""
    if not gates:
        return GATE_STATUS_NOT_RUN, ["no_gates_defined"]

    blockers: list[str] = []
    non_go_statuses: list[str] = []

    for gate_name, gate in gates.items():
        if isinstance(gate, dict):
            status = str(gate.get("status", GATE_STATUS_NOT_RUN))
        else:
            status = GATE_STATUS_NOT_RUN
        if status != GATE_STATUS_GO:
            blockers.append(f"{gate_name}:{status}")
            non_go_statuses.append(status)

    if not blockers:
        return GATE_STATUS_GO, []

    if GATE_STATUS_BLOCKED in non_go_statuses:
        overall = GATE_STATUS_BLOCKED
    elif GATE_STATUS_NOT_RUN in non_go_statuses:
        overall = GATE_STATUS_NOT_RUN
    else:
        overall = non_go_statuses[0]

    return overall, blockers


def exit_code_for_status(status: str, require_go: bool) -> int:
    """Inventory mode always exits 0; --require-go exits 0 only when status is GO."""
    if not require_go:
        return 0
    return 0 if status == GATE_STATUS_GO else 1


def add_require_go_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--require-go",
        action="store_true",
        help="Fail closed: exit non-zero unless every evaluated gate status is GO.",
    )


def collect_gates_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Collect gate-like status entries from a readiness artifact payload."""
    gates: dict[str, Any] = {}
    artifact_gates = artifact.get("gates")
    if isinstance(artifact_gates, dict):
        gates.update(artifact_gates)
    elif "status" in artifact:
        gates["overall"] = {"status": artifact["status"]}

    proof_cases = artifact.get("proof_cases")
    if isinstance(proof_cases, dict):
        for name, case in proof_cases.items():
            if isinstance(case, dict) and "status" in case:
                gates[f"proof_case:{name}"] = case

    return gates
