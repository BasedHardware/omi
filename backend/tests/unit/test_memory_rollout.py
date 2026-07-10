from datetime import datetime, timezone

import pytest

from utils.memory_ingestion.rollout import (
    LEGACY_EVIDENCE_KIND,
    MemoryGraphRolloutFlags,
    benchmark_rows_from_pipeline_outputs,
    build_genesis_ledger_backfill,
    compare_benchmark_summaries,
    decide_rollout,
    diff_legacy_vs_graph_projection,
    legacy_memory_to_migrated_fact,
)

MIGRATION_TIME = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _legacy_memory(**overrides):
    base = {
        "id": "mem-1",
        "content": "User prefers concise updates.",
        "category": "preference",
        "conversation_id": "conv-1",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "scoring": 0.8,
        "visibility": "public",
        "reviewed": False,
        "user_review": None,
        "arguments": {"topic": "updates"},
    }
    base.update(overrides)
    return base


def test_legacy_memory_migrates_as_second_class_legacy_evidence():
    fact = legacy_memory_to_migrated_fact(_legacy_memory(), migration_time=MIGRATION_TIME)

    assert fact["legacy_migrated"] is True
    assert fact["subject_entity_id"] == "user"
    assert fact["subject_attribution"] == "legacy_assumed"
    assert fact["valid_time_status"] == "unknown"
    assert fact["valid_at"] is None
    assert fact["veracity"] == 0.5
    assert fact["qualifiers"]["epistemic_status"] == "legacy_default"
    assert fact["migration_metadata"]["legacy_epistemic_status"] == "legacy_default"
    assert fact["evidence"] == [
        {
            "evidence_id": "legacy:mem-1",
            "kind": LEGACY_EVIDENCE_KIND,
            "source_id": "conv-1",
            "independence_group": "conv-1",
            "capture_confidence": 0.5,
            "redaction_status": "active",
            "migration_version": "genesis_ledger_backfill.v1",
        }
    ]
    assert "artifact_ref" not in fact["evidence"][0]


def test_genesis_backfill_adds_facts_and_typed_legacy_supersession():
    backfill = build_genesis_ledger_backfill(
        "uid-1",
        [
            _legacy_memory(id="mem-old", superseded_by="mem-new"),
            _legacy_memory(id="mem-new", content="User prefers direct updates."),
            _legacy_memory(id="mem-retracted", invalid_at=datetime(2026, 2, 1, tzinfo=timezone.utc)),
            _legacy_memory(id="mem-deleted", deleted=True),
        ],
        migration_time=MIGRATION_TIME,
    )
    mutations = backfill["commit"]["mutations"]

    assert backfill["migrated_count"] == 3
    assert [mutation["type"] for mutation in mutations].count("add_fact") == 3
    assert {
        (mutation.get("fact_id"), mutation.get("type"), mutation.get("kind"))
        for mutation in mutations
        if mutation["type"] == "supersede_fact"
    } == {("mem-old", "supersede_fact", "legacy_superseded")}
    assert {
        (mutation.get("fact_id"), mutation.get("type"), mutation.get("reason"))
        for mutation in mutations
        if mutation["type"] == "retract_fact"
    } == {("mem-retracted", "retract_fact", "legacy_invalidated")}


def test_rollout_keeps_reads_on_legacy_until_all_gates_pass():
    blocked = decide_rollout(
        MemoryGraphRolloutFlags(
            write_mode="dual_write",
            read_mode="graph_head",
            parity_status="passed",
            shadow_eval_status="running",
            benchmark_compare_status="passed",
        )
    )
    allowed = decide_rollout(
        MemoryGraphRolloutFlags(
            write_mode="dual_write",
            read_mode="graph_head",
            parity_status="passed",
            shadow_eval_status="passed",
            benchmark_compare_status="passed",
        )
    )

    assert blocked.write_legacy is True
    assert blocked.write_graph is True
    assert blocked.read_source == "legacy"
    assert allowed.read_source == "graph_head"
    assert allowed.rollback_read_source == "legacy"


def test_projection_parity_diff_is_zero_for_matching_legacy_view():
    legacy = [_legacy_memory(evidence=[])]
    graph = {"mem-1": {**_legacy_memory(evidence=[]), "invalid_at": None}}

    diff = diff_legacy_vs_graph_projection(legacy, graph)

    assert diff["parity"] is True
    assert diff["diff_count"] == 0


def test_projection_parity_diff_reports_mismatch():
    legacy = [_legacy_memory(content="User prefers concise updates.", evidence=[])]
    graph = {"mem-1": {**_legacy_memory(content="User prefers long updates.", evidence=[]), "invalid_at": None}}

    diff = diff_legacy_vs_graph_projection(legacy, graph)

    assert diff["parity"] is False
    assert diff["diff_count"] == 1
    assert diff["mismatched"][0]["id"] == "mem-1"


def test_benchmark_rows_require_example_id_map_for_pipeline_outputs():
    output = {
        "run_id": "run-1",
        "input_fingerprint": "ifp",
        "entity_ops": [],
        "event_frames": [{"frame_id": "frame-1"}],
        "derived_triples": [],
        "decisions": [],
        "review_items": [],
        "rejected_items": [],
        "audit": {"redactions": [{"category": "api_key"}]},
        "private_input_fingerprint": "pifp_test",
    }

    with pytest.raises(ValueError):
        benchmark_rows_from_pipeline_outputs([output])

    assert benchmark_rows_from_pipeline_outputs([output], example_id_by_run_id={"run-1": "ex-1"}) == [
        {
            "example_id": "ex-1",
            "run_id": "run-1",
            "input_fingerprint": "ifp",
            "entity_ops": [],
            "entities": [],
            "event_frames": [{"frame_id": "frame-1"}],
            "derived_triples": [],
            "decisions": [],
            "review_items": [],
            "rejected_items": [],
            "audit": {"redactions": [{"category": "api_key"}]},
            "private_input_fingerprint": "pifp_test",
        }
    ]


def test_benchmark_compare_gate_requires_dedup_and_supersession_parity():
    assert compare_benchmark_summaries({"dedup": 0.8, "supersession": 0.7}, {"dedup": 0.8, "supersession": 0.71})[
        "parity_or_better"
    ]
    assert not compare_benchmark_summaries({"dedup": 0.8, "supersession": 0.7}, {"dedup": 0.79, "supersession": 0.71})[
        "parity_or_better"
    ]


def test_benchmark_compare_gate_fails_closed_when_required_metrics_are_missing():
    result = compare_benchmark_summaries({"overall": 0.9}, {"overall": 0.95})

    assert result["parity_or_better"] is False
    assert result["missing_metrics"] == ["dedup", "supersession"]
