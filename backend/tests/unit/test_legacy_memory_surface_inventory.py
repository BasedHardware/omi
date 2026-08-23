"""Hermetic tests for the Gate F legacy-memory source ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import legacy_memory_surface_inventory as inventory


def _fixture_rules() -> tuple[inventory.InventoryRule, ...]:
    return (
        inventory.InventoryRule(
            "legacy_fixture",
            ("fixtures/*.py",),
            r"LEGACY_MARKER",
            "marker",
            ("reader",),
        ),
    )


def test_inventory_is_deterministic_and_never_returns_source_content(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "b.py").write_text("# LEGACY_MARKER\n", encoding="utf-8")
    (fixture_dir / "a.py").write_text("LEGACY_MARKER\nignored user-shaped text\n", encoding="utf-8")

    first = inventory.scan(tmp_path, _fixture_rules())
    second = inventory.scan(tmp_path, _fixture_rules())

    assert first == second
    assert [(item.path, item.line) for item in first] == [("fixtures/a.py", 1), ("fixtures/b.py", 1)]
    assert all(set(item.as_dict()) == {"classification", "line", "path", "potential_roles", "symbol"} for item in first)
    assert "ignored user-shaped text" not in json.dumps([item.as_dict() for item in first])


def test_gate_f_rules_declare_only_potential_reader_writer_or_job_roles() -> None:
    roles = {role for rule in inventory.RULES for role in rule.potential_roles}
    role_by_classification = {rule.classification: rule.potential_roles for rule in inventory.RULES}

    assert roles == inventory.POTENTIAL_SURFACE_ROLES
    assert all(set(rule.potential_roles) <= inventory.POTENTIAL_SURFACE_ROLES for rule in inventory.RULES)
    assert role_by_classification == {
        "conversation_eager_memory_writer": ("writer",),
        "short_term_lifecycle": ("reader", "writer", "job"),
        "consolidation_promotion": ("reader", "writer", "job"),
        "profile_synthesis": ("reader", "writer"),
        "old_proactive_assistants": ("reader", "writer"),
        "maintenance_resources": ("job",),
    }


def test_potential_role_inventory_is_deterministic_and_separate_from_ratchet_keys() -> None:
    findings = inventory.scan(inventory.ROOT)

    first = inventory.potential_role_counts(findings)
    second = inventory.potential_role_counts(findings)

    assert first == second
    assert {key.split("|", 1)[0] for key in first} == inventory.POTENTIAL_SURFACE_ROLES
    assert all(key.split("|", 1)[1:] for key in first)
    assert set(first).isdisjoint(inventory.counts(findings))


def test_representative_paths_keep_evidence_backed_potential_roles() -> None:
    findings = inventory.scan(inventory.ROOT)

    process_writer = [
        item
        for item in findings
        if item.path == "backend/utils/conversations/process_conversation.py"
        and item.classification == "conversation_eager_memory_writer"
    ]
    maintenance_job = [
        item
        for item in findings
        if item.path == ".github/workflows/gcp_memory_maintenance_job.yml"
        and item.classification == "maintenance_resources"
    ]
    lifecycle_worker = [
        item
        for item in findings
        if item.path == "backend/jobs/short_term_lifecycle_worker.py" and item.classification == "short_term_lifecycle"
    ]

    assert process_writer and {item.potential_roles for item in process_writer} == {("writer",)}
    assert maintenance_job and {item.potential_roles for item in maintenance_job} == {("job",)}
    assert lifecycle_worker and {item.potential_roles for item in lifecycle_worker} == {("reader", "writer", "job")}


def test_report_labels_source_evidence_without_claiming_runtime_proof() -> None:
    payload = inventory.report()

    assert payload["evidence_scope"] == "checked_in_source_and_resources"
    assert payload["runtime_proof"] is False
    assert payload["potential_role_scope"] == "marker_family_not_per_line"


def test_ratchet_fails_only_on_growth_and_allows_shrinkage() -> None:
    growth, shrinkage = inventory.compare_counts(
        {"legacy_fixture|marker|fixtures/a.py": 3, "removed|marker|fixtures/old.py": 0},
        {"legacy_fixture|marker|fixtures/a.py": 2, "removed|marker|fixtures/old.py": 4},
    )

    assert growth == ["legacy_fixture|marker|fixtures/a.py: 2 -> 3"]
    assert shrinkage == ["removed|marker|fixtures/old.py: 4 -> 0"]


def test_new_class_without_a_baseline_is_a_failure() -> None:
    growth, shrinkage = inventory.compare_counts({"new_surface|marker|fixtures/new.py": 1}, {})

    assert growth == ["new_surface|marker|fixtures/new.py: 0 -> 1"]
    assert shrinkage == []


def test_working_baseline_cannot_be_inflated_in_same_change() -> None:
    key = "legacy_fixture|marker|fixtures/a.py"

    growth, shrinkage = inventory.evaluate_ratchet(
        {key: 2},
        {key: 2},
        base_baseline={key: 1},
    )

    assert growth == [f"baseline {key}: 1 -> 2"]
    assert shrinkage == []


def test_first_introduction_without_base_baseline_uses_working_ratchet() -> None:
    key = "legacy_fixture|marker|fixtures/a.py"

    growth, shrinkage = inventory.evaluate_ratchet({key: 1}, {key: 1})

    assert growth == []
    assert shrinkage == []


def test_checked_in_inventory_has_no_baseline_growth() -> None:
    current = inventory.counts(inventory.scan(inventory.ROOT))
    baseline = inventory.load_baseline(inventory.BASELINE_PATH)

    growth, _shrinkage = inventory.compare_counts(current, baseline)

    assert growth == []
