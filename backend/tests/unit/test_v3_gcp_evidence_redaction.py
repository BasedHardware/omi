import json

import pytest

from testing.memory.v3_f6.redaction import (
    RedactionContractError,
    fingerprint,
    render_redacted_evidence_json,
    validate_redacted_evidence,
)


def _safe_report():
    return {
        "artifact_version": "memory-V3-F6F",
        "status": "INCONCLUSIVE",
        "target": "dev",
        "project_fingerprint": fingerprint("omi-memory-dev-123", key_id="project"),
        "principal_fingerprint": fingerprint(
            "serviceAccount:memory-evidence@example.iam.gserviceaccount.com", key_id="principal"
        ),
        "run_fingerprint": fingerprint("run-20260620-0001", key_id="run"),
        "approved_metadata_paths": ["control/config metadata"],
        "read_bounds": {"max_documents_per_path": 25, "max_paths": 1, "allow_collection_scans": False},
        "index_expectations": {"memory_items_by_uid_generation_updated_at": {"state": "READY"}},
        "audit": {"enabled": True, "zero_write_methods": []},
        "observations": [
            {"name": "control_config_metadata", "status": "PASS", "metadata": {"field_count": 3, "document_count": 1}}
        ],
        "non_claims": ["no raw memory content emitted", "no cloud client constructed"],
    }


def _assert_exact_error(call, error_type: type[Exception], message: str) -> None:
    with pytest.raises(error_type) as exc_info:
        call()
    assert str(exc_info.value) == message


def test_render_redacted_output_uses_keyed_fingerprints_and_stable_safe_json():
    rendered = render_redacted_evidence_json(_safe_report())
    decoded = json.loads(rendered)

    assert decoded["project_fingerprint"].startswith("hmac:project:")
    assert decoded["principal_fingerprint"].startswith("hmac:principal:")
    assert "omi-memory-dev-123" not in rendered
    assert "serviceAccount:" not in rendered
    assert "control/config metadata" in rendered


def test_redaction_contract_fails_closed_on_unknown_fields_and_sensitive_field_names():
    report = _safe_report()
    report["debug"] = "not allowlisted"
    with pytest.raises(RedactionContractError, match="unknown fields"):
        validate_redacted_evidence(report)

    report = _safe_report()
    report["observations"][0]["metadata"]["raw_memory_content"] = "my private memory"
    with pytest.raises(RedactionContractError, match="forbidden field"):
        render_redacted_evidence_json(report)

    report = _safe_report()
    report["observations"][0]["metadata"]["request_body"] = {"query": "coffee"}
    with pytest.raises(RedactionContractError, match="forbidden field"):
        render_redacted_evidence_json(report)


def test_redaction_contract_blocks_raw_urls_tokens_credentials_query_values_and_user_ids():
    forbidden_values = [
        "https://firestore.googleapis.com/v1/projects/x",
        "Authorization: Bearer abc123",
        "cursor-token-123",
        "password=hunter2",
        "uid_1234567890",
        "raw query value coffee shop near home",
    ]

    for value in forbidden_values:
        report = _safe_report()
        report["observations"][0]["metadata"] = {"note": value}
        with pytest.raises(RedactionContractError):
            render_redacted_evidence_json(report)


def test_redaction_exact_field_errors_preserve_type_message_and_order():
    report = _safe_report()
    report.pop("audit")
    report["debug"] = "not allowlisted"
    _assert_exact_error(
        lambda: validate_redacted_evidence(report),
        RedactionContractError,
        "missing fields: ['audit']",
    )

    report = _safe_report()
    report["read_bounds"] = {"max_documents_per_path": 25, "surprise": True}
    _assert_exact_error(
        lambda: validate_redacted_evidence(report),
        RedactionContractError,
        "read_bounds unknown fields: ['surprise']",
    )

    report = _safe_report()
    report["audit"] = {"surprise": True}
    _assert_exact_error(
        lambda: validate_redacted_evidence(report),
        RedactionContractError,
        "audit unknown fields: ['surprise']",
    )
