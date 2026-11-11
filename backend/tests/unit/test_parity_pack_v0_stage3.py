from __future__ import annotations

import json
from pathlib import Path

import pytest

from testing.parity_pack_v0.gold import double_run_gold, drift_report
from testing.parity_pack_v0.matrix import SYNTHETIC_MATRIX
from testing.parity_pack_v0.rewrite import rewrite_launch_descriptor
from testing.parity_pack_v0.runner import hermetic_run


def test_double_run_requires_determinism_and_only_writes_gold_explicitly(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "c1", "expected_outcomes": {"status": "old"}}]}))
    drifts = double_run_gold(manifest, lambda _: {"status": "new"})
    assert drift_report(drifts)["status"] == "warn"
    assert json.loads(manifest.read_text())["cases"][0]["expected_outcomes"] == {"status": "old"}
    double_run_gold(manifest, lambda _: {"status": "new"}, write_gold=True)
    assert json.loads(manifest.read_text())["cases"][0]["expected_outcomes"] == {"status": "new"}


def test_double_run_rejects_nondeterminism(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "c1", "expected_outcomes": {}}]}))
    responses = iter(({"status": "one"}, {"status": "two"}))
    with pytest.raises(AssertionError, match="non-deterministic"):
        double_run_gold(manifest, lambda _: next(responses))


def test_matrix_rewrite_slot_and_hermetic_canary_are_explicit() -> None:
    assert len(SYNTHETIC_MATRIX) == 6
    descriptor = rewrite_launch_descriptor(Path("in.json"), Path("out.json"))
    assert not descriptor.available and descriptor.command[0] == "omi-replay-rewrite"
    with hermetic_run() as fakes:
        fakes.hit("stt")
        fakes.hit("llm")
        fakes.require(stt=1, llm=1)
