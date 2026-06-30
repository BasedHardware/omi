from datetime import datetime, timezone

import pytest

from testing.memory.v3_f6.config import EvidenceTargetRegistry
from testing.memory.v3_f6.local_defaults import DEFAULT_EVIDENCE_TARGETS
from testing.memory.v3_f6.run_record import RunRecordValidationError, validate_run_record


def _concrete_registry():
    return EvidenceTargetRegistry.from_dict(
        {
            "dev": {
                **DEFAULT_EVIDENCE_TARGETS["dev"],
                "project_id": "omi-memory-dev-123",
                "project_number": "111222333444",
                "evidence_principal": "serviceAccount:memory-evidence@omi-memory-dev-123.iam.gserviceaccount.com",
            },
            "prod": {
                **DEFAULT_EVIDENCE_TARGETS["prod"],
                "project_id": "omi-memory-prod-456",
                "project_number": "555666777888",
                "evidence_principal": "serviceAccount:memory-evidence@omi-memory-prod-456.iam.gserviceaccount.com",
            },
        }
    )


def _record(target="dev", **overrides):
    base = {
        "artifact_version": "memory-V3-F6B",
        "run_id": "run-20260620-0001",
        "one_run_scope": True,
        "target": target,
        "project_id": f"omi-memory-{target}-123" if target == "dev" else "omi-memory-prod-456",
        "project_number": "111222333444" if target == "dev" else "555666777888",
        "evidence_principal": (
            "serviceAccount:memory-evidence@omi-memory-dev-123.iam.gserviceaccount.com"
            if target == "dev"
            else "serviceAccount:memory-evidence@omi-memory-prod-456.iam.gserviceaccount.com"
        ),
        "approved_metadata_paths": ["control/config metadata", "cursor secret metadata"],
        "commit": "abcdef1234567890abcdef1234567890abcdef12",
        "runner_hashes": {"runner.py": "sha256:" + "a" * 64},
        "helper_hashes": {"helper.py": "sha256:" + "b" * 64},
        "execution_window": {
            "started_at": "2026-06-20T10:00:00Z",
            "ended_at": "2026-06-20T10:05:00Z",
            "max_seconds": 600,
        },
        "read_bounds": {"max_documents_per_path": 25, "max_paths": 2, "allow_collection_scans": False},
        "approvals": [],
    }
    base.update(overrides)
    return base


def test_dev_run_record_validates_bounded_one_run_scope_exact_target_and_hashes():
    validated = validate_run_record(_record(), _concrete_registry(), now=datetime(2026, 6, 20, tzinfo=timezone.utc))

    assert validated.target == "dev"
    assert validated.project_id == "omi-memory-dev-123"
    assert validated.execution_window.started_at.isoformat().startswith("2026-06-20T10:00:00")


def test_run_record_fails_closed_on_unknown_fields_unapproved_paths_unbounded_reads_and_target_mismatch():
    with pytest.raises(RunRecordValidationError, match="unknown fields"):
        validate_run_record(_record(unexpected="closed"), _concrete_registry())

    with pytest.raises(RunRecordValidationError, match="approved_metadata_paths"):
        validate_run_record(_record(approved_metadata_paths=["memory/raw content"]), _concrete_registry())

    with pytest.raises(RunRecordValidationError, match="collection scans"):
        validate_run_record(
            _record(read_bounds={"max_documents_per_path": 25, "max_paths": 2, "allow_collection_scans": True}),
            _concrete_registry(),
        )

    with pytest.raises(RunRecordValidationError, match="project_id"):
        validate_run_record(_record(project_id="omi-memory-prod-456"), _concrete_registry())


def test_run_record_exact_field_errors_preserve_type_message_and_order():
    raw = _record(unexpected="closed")
    raw.pop("approvals")
    with pytest.raises(RunRecordValidationError) as exc_info:
        validate_run_record(raw, _concrete_registry())
    assert str(exc_info.value) == "run record missing fields: ['approvals']"

    raw = _record(read_bounds={"surprise": True})
    with pytest.raises(RunRecordValidationError) as exc_info:
        validate_run_record(raw, _concrete_registry())
    assert (
        str(exc_info.value)
        == "read_bounds missing fields: ['allow_collection_scans', 'max_documents_per_path', 'max_paths']"
    )

    raw = _record(approvals=[{"role": "platform", "unexpected": "closed"}])
    with pytest.raises(RunRecordValidationError) as exc_info:
        validate_run_record(raw, _concrete_registry())
    assert str(exc_info.value) == "approval missing fields: ['approved_at', 'approver']"


def test_prod_run_record_requires_named_platform_and_security_approvals():
    with pytest.raises(RunRecordValidationError, match="prod requires"):
        validate_run_record(_record("prod"), _concrete_registry())

    approved = _record(
        "prod",
        approvals=[
            {"role": "platform", "approver": "Pat Platform", "approved_at": "2026-06-20T09:50:00Z"},
            {"role": "security", "approver": "Sam Security", "approved_at": "2026-06-20T09:55:00Z"},
        ],
    )
    assert validate_run_record(approved, _concrete_registry()).target == "prod"
