"""Tests for the R1 benchmark -> route-artifact emitter.

T-003 covers the core emission logic (emit_for_lane, emit_all, write_proposed_yaml)
with snapshot + parity assertions. T-004 adds CLI tests.

Per PLAN.md §R1, the emitter:
- Reads benchmarks.json (v3 format)
- Scores every R0 lane's candidates against the lane's declared objective
- Emits top-3 picks per lane to route_artifacts.proposed.yaml
- NEVER edits route_artifacts.yaml directly (asserted in write_proposed_yaml)
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.schemas import compute_route_artifact_digest
from llm_gateway.gateway.schemas import RouteArtifact
from llm_gateway.scripts.sync_benchmarks_to_route_artifacts import (
    LANE_TO_V3_TASK,
    _benchmark_snapshot_hash,
    _modelspec_from_dict,
    _objective_to_taskspec,
    _route_id_for,
    emit_all,
    emit_for_lane,
    load_benchmarks,
    main,
    write_proposed_yaml,
)

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "benchmarks_emitter_sample.json"


# ---------------------------------------------------------------------------
# Helpers / sanity
# ---------------------------------------------------------------------------


def test_fixture_loads_with_expected_shape():
    benchmarks = load_benchmarks(FIXTURE)
    assert "tasks" in benchmarks and "models" in benchmarks
    assert len(benchmarks["tasks"]) == 5
    assert set(benchmarks["models"].keys()) == {
        "ptt_response",
        "screenshot_understanding",
        "screenshot_embedding",
        "general_assistant",
        "transcription",
    }


def test_lane_to_v3_task_mapping_covers_exactly_five_lanes():
    """R0 has 16 lanes; v3 covers 5. The mapping is locked to those 5."""
    assert len(LANE_TO_V3_TASK) == 5
    assert set(LANE_TO_V3_TASK.keys()) == {
        "omi:auto:realtime-ptt",
        "omi:auto:screenshot-understanding",
        "omi:auto:screenshot-embedding",
        "omi:auto:general-assistant",
        "omi:auto:transcription",
    }


def test_route_id_format_matches_r0_pattern():
    """route.<capability>.<YYYY_MM_DD>.001 — matches R0's id pattern."""
    rid = _route_id_for("omi:auto:realtime-ptt", date(2026, 7, 1))
    assert rid == "route.realtime_ptt.2026_07_01.001"
    rid = _route_id_for("omi:auto:general-assistant", date(2026, 12, 31))
    assert rid == "route.general_assistant.2026_12_31.001"


def test_benchmark_snapshot_hash_is_deterministic_and_sha256_prefixed():
    benchmarks = {"a": 1, "b": [2, 3]}
    h = _benchmark_snapshot_hash(benchmarks)
    assert h.startswith("sha256:")
    # Same input -> same output (deterministic via sort_keys)
    assert _benchmark_snapshot_hash(benchmarks) == h
    # Different input -> different output
    assert _benchmark_snapshot_hash({"b": [2, 3], "a": 1}) == h  # same due to sort_keys
    assert _benchmark_snapshot_hash({"a": 2, "b": [2, 3]}) != h


def test_objective_to_taskspec_round_trip():
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:realtime-ptt"]
    # objective q=0.65 l=0.25 c=0.10 for realtime-ptt
    task = _objective_to_taskspec(lane.objective, "ptt_response")
    assert task.name == "ptt_response"
    assert task.quality_weight == lane.objective.quality
    assert task.latency_weight == lane.objective.latency
    assert task.cost_weight == lane.objective.cost


def test_modelspec_from_dict_handles_missing_scores():
    m = _modelspec_from_dict({"id": "x", "provider": "p"})  # no scores
    assert m.quality_score is None
    assert m.latency_score is None
    assert m.cost_score is None


# ---------------------------------------------------------------------------
# emit_for_lane
# ---------------------------------------------------------------------------


def test_emit_for_lane_picks_top_scorer_as_primary():
    """For realtime-ptt (objective q=0.65 l=0.25 c=0.10):
    - claude-sonnet-4-6: 0.65*0.9 + 0.25*0.7 + 0.10*0.5 = 0.585+0.175+0.05 = 0.810
    - gpt-5.4-mini:      0.65*0.7 + 0.25*0.9 + 0.10*0.8 = 0.455+0.225+0.08 = 0.760
    - gemini-3-flash:    0.65*0.6 + 0.25*0.95+ 0.10*0.9 = 0.390+0.2375+0.09 = 0.7175
    Winner: claude-sonnet-4-6 (0.810).
    """
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:realtime-ptt"]
    benchmarks = load_benchmarks(FIXTURE)
    candidates = benchmarks["models"]["ptt_response"]
    art = emit_for_lane(
        lane,
        candidates,
        today=date(2026, 7, 1),
        benchmark_snapshot="sha256:abc",
        eval_report_id="eval.ptt_response.v1",
    )
    assert art.primary.model == "claude-sonnet-4-6"
    assert art.primary.provider == "anthropic"
    assert len(art.fallbacks) == 2


def test_emit_for_lane_includes_top_3_with_correct_lane_metadata():
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:screenshot-understanding"]
    benchmarks = load_benchmarks(FIXTURE)
    candidates = benchmarks["models"]["screenshot_understanding"]
    art = emit_for_lane(
        lane,
        candidates,
        today=date(2026, 7, 1),
        benchmark_snapshot="sha256:abc",
        eval_report_id="eval.screenshot_understanding.v1",
    )
    assert art.lane_id == "omi:auto:screenshot-understanding"
    assert art.route_artifact_id == "route.screenshot_understanding.2026_07_01.001"
    # Evidence shape — prod-eligible
    assert art.evidence.benchmark_source.value == "external_benchmark"
    assert art.evidence.dev_only is False
    assert art.evidence.eval_report == "eval.screenshot_understanding.v1"
    # Shadow rollout (R1 ships shadow-only)
    assert art.rollout.stage == "shadow"
    assert art.rollout.percent == 0


def test_emit_for_lane_rejects_empty_candidates():
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:realtime-ptt"]
    with pytest.raises(ValueError, match="no candidates"):
        emit_for_lane(
            lane,
            [],
            today=date(2026, 7, 1),
            benchmark_snapshot="sha256:abc",
            eval_report_id="eval.ptt_response.v1",
        )


def test_emit_for_lane_deterministic_tie_break_by_id():
    """When scores tie, lower model.id wins (deterministic)."""
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:realtime-ptt"]
    candidates = [
        {"id": "z-model", "provider": "openai", "quality_score": 0.8, "latency_score": 0.8, "cost_score": 0.8},
        {"id": "a-model", "provider": "openai", "quality_score": 0.8, "latency_score": 0.8, "cost_score": 0.8},
        {"id": "m-model", "provider": "openai", "quality_score": 0.8, "latency_score": 0.8, "cost_score": 0.8},
    ]
    art = emit_for_lane(
        lane,
        candidates,
        today=date(2026, 7, 1),
        benchmark_snapshot="sha256:abc",
        eval_report_id="eval.ptt_response.v1",
    )
    # All same score — tie-break by id ASC: a-model wins
    assert art.primary.model == "a-model"


def test_emit_for_lane_produces_valid_route_artifact_with_stable_digest():
    """Every emitted artifact must pass model_validate + have a stable sha256 digest."""
    cfg = load_gateway_config()
    lane = cfg.lanes["omi:auto:general-assistant"]
    benchmarks = load_benchmarks(FIXTURE)
    art = emit_for_lane(
        lane,
        benchmarks["models"]["general_assistant"],
        today=date(2026, 7, 1),
        benchmark_snapshot="sha256:abc",
        eval_report_id="eval.general_assistant.v1",
    )
    # Round-trip through Pydantic + recompute digest
    payload = art.model_dump(mode="json", exclude={"content_digest"})
    redigest = compute_route_artifact_digest(payload)
    assert redigest == art.content_digest
    assert redigest.startswith("sha256:")


# ---------------------------------------------------------------------------
# emit_all
# ---------------------------------------------------------------------------


def test_emit_all_produces_5_artifacts_and_11_warnings_for_sample_fixture():
    """5 lanes have v3 coverage; 11 are skipped with 'no v3 task mapping' warnings."""
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, warnings = emit_all(benchmarks, today=date(2026, 7, 1))
    assert len(artifacts) == 5
    assert sum(1 for w in warnings if "no v3 task mapping" in w) == 11
    # Every artifact is for a v3-covered lane
    covered = set(LANE_TO_V3_TASK.keys())
    assert {a.lane_id for a in artifacts} == covered


def test_emit_all_returns_artifacts_with_correct_lane_ids():
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    lane_ids = {a.lane_id for a in artifacts}
    assert lane_ids == {
        "omi:auto:realtime-ptt",
        "omi:auto:screenshot-understanding",
        "omi:auto:screenshot-embedding",
        "omi:auto:general-assistant",
        "omi:auto:transcription",
    }


def test_emit_all_skips_lanes_with_empty_candidates():
    """If a v3 task has no candidates (empty list), the lane is skipped, not errored."""
    benchmarks = load_benchmarks(FIXTURE)
    # Empty out ptt_response candidates
    benchmarks["models"]["ptt_response"] = []
    artifacts, warnings = emit_all(benchmarks, today=date(2026, 7, 1))
    assert len(artifacts) == 4
    assert any("ptt_response" in w and "no candidates" in w for w in warnings)


def test_emit_all_benchmark_snapshot_is_consistent_across_lanes():
    """All artifacts in one emit_all run share the same benchmark_snapshot."""
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    snapshots = {a.evidence.benchmark_snapshot for a in artifacts}
    assert len(snapshots) == 1
    assert next(iter(snapshots)).startswith("sha256:")


# ---------------------------------------------------------------------------
# write_proposed_yaml + safety
# ---------------------------------------------------------------------------


def test_write_proposed_yaml_writes_valid_yaml_with_artifact_digests(tmp_path):
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    out = tmp_path / "route_artifacts.proposed.yaml"
    write_proposed_yaml(artifacts, out)
    assert out.exists()
    loaded = yaml.safe_load(out.read_text())
    assert "route_artifacts" in loaded
    assert len(loaded["route_artifacts"]) == 5
    # Every emitted artifact has a valid sha256 digest
    for entry in loaded["route_artifacts"]:
        assert entry["artifact_digest"].startswith("sha256:")


def test_write_proposed_yaml_refuses_route_artifacts_yaml(tmp_path):
    """Safety: emitter must NOT be able to overwrite route_artifacts.yaml directly."""
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    bad = tmp_path / "route_artifacts.yaml"
    with pytest.raises(AssertionError, match="must not edit route_artifacts.yaml"):
        write_proposed_yaml(artifacts, bad)


def test_write_proposed_yaml_artifact_digests_match_model_validation():
    """Every artifact's emitted digest must match what RouteArtifact would compute."""
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    import tempfile, os

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "route_artifacts.proposed.yaml"
        write_proposed_yaml(artifacts, out)
        loaded = yaml.safe_load(out.read_text())
    for entry in loaded["route_artifacts"]:
        # Re-validate and check digest
        body = {k: v for k, v in entry.items() if k != "artifact_digest"}
        redigest = compute_route_artifact_digest(body)
        assert entry["artifact_digest"] == redigest, f"digest mismatch for {entry['route_artifact_id']}"


def test_write_proposed_yaml_loads_via_config_loader_with_proposed_renamed(tmp_path):
    """The emitted YAML is loadable as a GatewayConfig IF renamed to route_artifacts.yaml
    (sanity check: every emitted artifact is a valid RouteArtifact)."""
    benchmarks = load_benchmarks(FIXTURE)
    artifacts, _ = emit_all(benchmarks, today=date(2026, 7, 1))
    proposed = tmp_path / "route_artifacts.proposed.yaml"
    write_proposed_yaml(artifacts, proposed)
    # Move proposed to a name the config loader can find
    route_artifacts_path = tmp_path / "route_artifacts.yaml"
    route_artifacts_path.write_text(proposed.read_text())
    # The loader will pick it up — just verify it parses + artifacts are valid
    import yaml as _yaml

    parsed = _yaml.safe_load(route_artifacts_path.read_text())
    for entry in parsed["route_artifacts"]:
        validated = RouteArtifact.model_validate(entry)
        assert validated.lane_id == entry["lane_id"]
        assert validated.route_artifact_id == entry["route_artifact_id"]


# ---------------------------------------------------------------------------
# CLI (T-004)
# ---------------------------------------------------------------------------


def test_cli_dry_run_prints_json_summary_and_does_not_write(tmp_path, monkeypatch, capsys):
    """--dry-run prints the summary to stdout and never touches the filesystem."""
    monkeypatch.chdir(tmp_path)
    rc = main(["--dry-run", "--benchmarks", str(FIXTURE)])
    assert rc == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["count"] == 5
    assert set(summary["emitted"]) == set(LANE_TO_V3_TASK.keys())
    assert len(summary["skipped"]) == 11
    # No proposed YAML was written
    assert not (tmp_path / "backend" / "llm_gateway" / "config" / "route_artifacts.proposed.yaml").exists()


def test_cli_lane_filter_writes_only_that_lane(tmp_path, monkeypatch):
    """--lane filters to one lane; the proposed YAML contains exactly that lane."""
    monkeypatch.chdir(tmp_path)
    rc = main(["--lane", "omi:auto:realtime-ptt", "--benchmarks", str(FIXTURE)])
    assert rc == 0
    proposed = tmp_path / "backend" / "llm_gateway" / "config" / "route_artifacts.proposed.yaml"
    assert proposed.exists()
    parsed = yaml.safe_load(proposed.read_text())
    assert len(parsed["route_artifacts"]) == 1
    assert parsed["route_artifacts"][0]["lane_id"] == "omi:auto:realtime-ptt"


def test_cli_lane_filter_unknown_lane_returns_error_code_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["--lane", "omi:auto:does-not-exist", "--benchmarks", str(FIXTURE)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown lane" in captured.err


def test_cli_missing_benchmarks_file_returns_error_code_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["--dry-run", "--benchmarks", str(tmp_path / "no-such-file.json")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_cli_emitter_never_edits_route_artifacts_yaml(tmp_path, monkeypatch):
    """Pre-create route_artifacts.yaml with a sentinel; emitter must leave it alone."""
    monkeypatch.chdir(tmp_path)
    # Sentinel: write route_artifacts.yaml in the cwd's backend/llm_gateway/config/
    config_dir = tmp_path / "backend" / "llm_gateway" / "config"
    config_dir.mkdir(parents=True)
    sentinel = config_dir / "route_artifacts.yaml"
    sentinel.write_text("# sentinel — must NOT be touched by emitter\nroute_artifacts: []\n")
    sentinel_mtime_before = sentinel.stat().st_mtime

    rc = main(["--benchmarks", str(FIXTURE)])
    assert rc == 0
    # mtime unchanged AND content unchanged
    assert sentinel.stat().st_mtime == sentinel_mtime_before
    assert sentinel.read_text().startswith("# sentinel")
    # Proposed YAML was written next to it
    proposed = config_dir / "route_artifacts.proposed.yaml"
    assert proposed.exists()


def test_cli_is_idempotent(tmp_path, monkeypatch):
    """Same input twice -> byte-identical proposed YAML (modulo date suffix)."""
    monkeypatch.chdir(tmp_path)
    rc1 = main(["--benchmarks", str(FIXTURE)])
    assert rc1 == 0
    first = (tmp_path / "backend" / "llm_gateway" / "config" / "route_artifacts.proposed.yaml").read_text()
    rc2 = main(["--benchmarks", str(FIXTURE)])
    assert rc2 == 0
    second = (tmp_path / "backend" / "llm_gateway" / "config" / "route_artifacts.proposed.yaml").read_text()
    assert first == second


def test_cli_writes_to_known_relative_path(tmp_path, monkeypatch):
    """The emitter writes to backend/llm_gateway/config/route_artifacts.proposed.yaml
    relative to the current working directory."""
    monkeypatch.chdir(tmp_path)
    rc = main(["--benchmarks", str(FIXTURE)])
    assert rc == 0
    expected = tmp_path / "backend" / "llm_gateway" / "config" / "route_artifacts.proposed.yaml"
    assert expected.exists()
