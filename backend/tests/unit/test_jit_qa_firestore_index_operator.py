from pathlib import Path

import pytest

from scripts import jit_qa_firestore_index_operator as operator


def test_selected_manifest_is_canonical_and_contains_only_ten_required_queries():
    manifest, signatures = operator.selected_manifest()

    assert len(manifest["indexes"]) == 10
    assert signatures == {requirement.signature for requirement in operator.TARGET_REQUIREMENTS}
    assert {
        (
            entry["collectionGroup"],
            entry["queryScope"],
            tuple((field["fieldPath"], field.get("order")) for field in entry["fields"]),
        )
        for entry in manifest["indexes"]
    } == signatures


def test_plan_reads_only_fixed_named_database_and_reports_all_required_indexes(monkeypatch):
    calls = []

    def list_live_indexes(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(operator.reconciler, "list_live_indexes", list_live_indexes)
    result = operator.build_plan(project=operator.PROJECT, database=operator.DATABASE)

    assert calls == [
        {"project": "based-hardware-dev", "database": "jit-qa", "runner": operator.reconciler.subprocess.run}
    ]
    assert result["manifest_validated"] is True
    assert result["selected_index_count"] == 10
    assert result["missing_count"] == 10
    assert {entry["state"] for entry in result["indexes"]} == {"MISSING"}
    assert {entry["identifier"] for entry in result["indexes"]} == {
        "memory_items_universal_list_scan",
        "conversations_entity_timeline_completed",
        "memories_universal_list_scan_updated_at",
        "memories_universal_list_scan_created_at",
        "daily_sweep_active_fact_subject",
        "daily_sweep_active_fact_slot",
        "daily_sweep_active_fact_entity",
        "daily_sweep_active_fact_entity_slot",
        "daily_sweep_active_fact_subject_content",
        "daily_sweep_active_fact_entity_content",
    }


def test_plan_rejects_non_qa_targets():
    with pytest.raises(operator.IndexOperatorError, match="project is fixed"):
        operator.build_plan(project="based-hardware", database=operator.DATABASE)
    with pytest.raises(operator.IndexOperatorError, match="database is fixed"):
        operator.build_plan(project=operator.PROJECT, database="(default)")


def test_apply_requires_confirmation_and_delegates_only_selected_signatures(monkeypatch):
    calls = []
    monkeypatch.setattr(operator.reconciler, "list_live_indexes", lambda **kwargs: [])

    def provision_missing_indexes(**kwargs):
        calls.append(("provision", kwargs))
        return set(kwargs["expected"])

    def wait_for_indexes(**kwargs):
        calls.append(("wait", kwargs))

    monkeypatch.setattr(operator.reconciler, "provision_missing_indexes", provision_missing_indexes)
    monkeypatch.setattr(operator.reconciler, "wait_for_indexes", wait_for_indexes)

    with pytest.raises(operator.IndexOperatorError, match="requires APPLY_JIT_QA_INDEXES"):
        operator.apply_plan(
            project=operator.PROJECT,
            database=operator.DATABASE,
            manifest_path=Path(operator.MANIFEST_PATH),
            confirmation="",
            timeout_seconds=1,
            poll_interval_seconds=1,
        )

    result = operator.apply_plan(
        project=operator.PROJECT,
        database=operator.DATABASE,
        confirmation=operator.APPLY_CONFIRMATION,
        timeout_seconds=1,
        poll_interval_seconds=1,
    )
    assert result["schema_version"] == "omi.jit.qa.firestore-index-apply.v1"
    assert result["created_index_count"] == 10
    assert calls[0][0] == "provision"
    assert calls[1][0] == "wait"
    assert calls[0][1]["project"] == operator.PROJECT
    assert calls[0][1]["database"] == operator.DATABASE
    assert len(calls[0][1]["expected"]) == 10
    assert calls[1][1]["expected"] == calls[0][1]["expected"]


def test_apply_cli_keeps_reconciler_progress_out_of_json_receipt(monkeypatch, capsys):
    import json

    signatures = operator._target_signatures()
    monkeypatch.setattr(operator.reconciler, "provision_missing_indexes", lambda **kwargs: signatures)
    # Exercise the actual wait function and its READY progress print.
    monkeypatch.setattr(operator.reconciler, "list_live_indexes", lambda **kwargs: [])
    monkeypatch.setattr(
        operator.reconciler,
        "expected_index_states",
        lambda **kwargs: {signature: "READY" for signature in signatures},
    )
    assert (
        operator.main(
            [
                "--project",
                operator.PROJECT,
                "--database",
                operator.DATABASE,
                "apply",
                "--confirmation",
                operator.APPLY_CONFIRMATION,
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt["missing_count"] == 0
    assert receipt["created_index_count"] == 10
    assert "READY" in captured.err
