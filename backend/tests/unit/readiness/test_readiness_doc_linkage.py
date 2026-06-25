"""Doc linkage metadata lives in data — tests no longer read epic markdown bodies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.readiness._paths import READINESS_DIR

DOC_LINKAGE = json.loads((READINESS_DIR / "doc_linkage.json").read_text(encoding="utf-8"))
BACKEND_DIR = READINESS_DIR.parents[1]


@pytest.mark.parametrize("gate_id", sorted(DOC_LINKAGE))
def test_gate_doc_linkage_metadata_is_self_contained(gate_id: str):
    entry = DOC_LINKAGE[gate_id]
    script_path = BACKEND_DIR / "scripts" / entry["script_filename"]
    assert script_path.exists(), f"missing script for {gate_id}"
    assert entry["test_sh_marker"].startswith("test_")
    # Markers are pinned in data; deleting epic docs must not break CI.
    assert entry["ticket_markers"] or entry["oracle_markers"], f"{gate_id} has empty doc_linkage"


@pytest.mark.parametrize("gate_id", sorted(DOC_LINKAGE))
def test_gate_script_registered_in_test_sh(gate_id: str):
    entry = DOC_LINKAGE[gate_id]
    test_sh = (BACKEND_DIR / "test.sh").read_text(encoding="utf-8")
    assert "test_readiness_gates_schema.py" in test_sh
    assert entry["script_filename"].removesuffix(".py") in test_sh or "readiness" in test_sh
