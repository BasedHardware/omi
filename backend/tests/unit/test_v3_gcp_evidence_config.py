import pytest

from testing.memory.v3_f6.config import EvidenceTargetRegistry, ValidationError
from testing.memory.v3_f6.local_defaults import DEFAULT_EVIDENCE_TARGETS


def test_default_registry_has_dev_and_prod_but_placeholders_do_not_authorize_real_execution():
    registry = EvidenceTargetRegistry.from_dict(DEFAULT_EVIDENCE_TARGETS)

    assert set(registry.target_names()) == {"dev", "prod"}
    dev = registry.get("dev")
    prod = registry.get("prod")
    assert dev.env_label == "dev"
    assert prod.env_label == "prod"
    assert dev.audit_settings.enabled is True
    assert prod.audit_settings.enabled is True
    assert "control/config metadata" in dev.approved_metadata_paths
    assert "memory_items_by_uid_generation_updated_at" in dev.index_expectations

    for target in (dev, prod):
        with pytest.raises(ValidationError, match="placeholder"):
            target.validate_for_real_execution(
                project_id=target.project_id,
                project_number=target.project_number,
                evidence_principal=target.evidence_principal,
            )


def test_registry_rejects_unknown_target_and_unknown_or_incomplete_schema_fields():
    with pytest.raises(ValidationError, match="unknown target"):
        EvidenceTargetRegistry.from_dict(DEFAULT_EVIDENCE_TARGETS).get("staging")

    bad = {
        "dev": {
            **DEFAULT_EVIDENCE_TARGETS["dev"],
            "unexpected": "closed",
        }
    }
    with pytest.raises(ValidationError, match="unknown fields"):
        EvidenceTargetRegistry.from_dict(bad)

    incomplete = {"dev": {k: v for k, v in DEFAULT_EVIDENCE_TARGETS["dev"].items() if k != "limits"}}
    with pytest.raises(ValidationError, match="missing fields"):
        EvidenceTargetRegistry.from_dict(incomplete)


def test_registry_exact_field_errors_preserve_type_message_and_order():
    both_missing_and_unknown = {
        "dev": {
            **{k: v for k, v in DEFAULT_EVIDENCE_TARGETS["dev"].items() if k != "limits"},
            "unexpected": "closed",
        }
    }
    with pytest.raises(ValidationError) as exc_info:
        EvidenceTargetRegistry.from_dict(both_missing_and_unknown)
    assert str(exc_info.value) == "target dev missing fields: ['limits']"

    bad_audit = {
        "dev": {
            **DEFAULT_EVIDENCE_TARGETS["dev"],
            "audit_settings": {"enabled": True, "surprise": True},
        }
    }
    with pytest.raises(ValidationError) as exc_info:
        EvidenceTargetRegistry.from_dict(bad_audit)
    assert str(exc_info.value) == "audit_settings missing fields: ['log_name', 'require_zero_write_methods']"


def test_concrete_target_allows_real_execution_only_on_exact_project_and_principal():
    concrete = {
        "dev": {
            **DEFAULT_EVIDENCE_TARGETS["dev"],
            "project_id": "omi-memory-dev-123",
            "project_number": "111222333444",
            "evidence_principal": "serviceAccount:memory-evidence@omi-memory-dev-123.iam.gserviceaccount.com",
        }
    }
    target = EvidenceTargetRegistry.from_dict(concrete).get("dev")

    target.validate_for_real_execution(
        project_id="omi-memory-dev-123",
        project_number="111222333444",
        evidence_principal="serviceAccount:memory-evidence@omi-memory-dev-123.iam.gserviceaccount.com",
    )

    with pytest.raises(ValidationError, match="project_id"):
        target.validate_for_real_execution(
            project_id="wrong-project",
            project_number="111222333444",
            evidence_principal="serviceAccount:memory-evidence@omi-memory-dev-123.iam.gserviceaccount.com",
        )
