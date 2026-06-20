from __future__ import annotations

import importlib


def test_old_config_facade_exports_are_identical_to_canonical_config_and_defaults():
    old = importlib.import_module("utils.memory.v17_v3_gcp_evidence_config")
    config = importlib.import_module("utils.memory.v17_v3_f6.config")
    defaults = importlib.import_module("utils.memory.v17_v3_f6.local_defaults")

    for name in (
        "ValidationError",
        "AuditSettings",
        "EvidenceLimits",
        "EvidenceTarget",
        "EvidenceTargetRegistry",
        "PLACEHOLDER_MARKERS",
        "TARGET_FIELDS",
        "AUDIT_FIELDS",
        "LIMIT_FIELDS",
        "INDEX_FIELDS",
    ):
        assert getattr(old, name) is getattr(config, name)

    for name in (
        "DEFAULT_APPROVED_METADATA_PATHS",
        "DEFAULT_INDEX_EXPECTATIONS",
        "DEFAULT_EVIDENCE_TARGETS",
    ):
        assert getattr(old, name) is getattr(defaults, name)


def test_old_run_record_facade_exports_are_identical_to_canonical_run_record():
    old = importlib.import_module("utils.memory.v17_v3_gcp_evidence_run_record")
    canonical = importlib.import_module("utils.memory.v17_v3_f6.run_record")

    for name in (
        "RunRecordValidationError",
        "RUN_RECORD_FIELDS",
        "WINDOW_FIELDS",
        "READ_BOUNDS_FIELDS",
        "APPROVAL_FIELDS",
        "ExecutionWindow",
        "ValidatedRunRecord",
        "validate_run_record",
    ):
        assert getattr(old, name) is getattr(canonical, name)


def test_old_redaction_facade_exports_are_identical_to_canonical_redaction_and_fingerprints():
    old = importlib.import_module("utils.memory.v17_v3_gcp_evidence_redaction")
    redaction = importlib.import_module("utils.memory.v17_v3_f6.redaction")
    fingerprints = importlib.import_module("utils.memory.v17_v3_f6.fingerprints")

    for name in (
        "RedactionContractError",
        "FingerprintContractError",
        "HMAC_KEY",
        "FINGERPRINT_RE",
        "TOP_LEVEL_FIELDS",
        "OBSERVATION_FIELDS",
        "READ_BOUNDS_FIELDS",
        "AUDIT_FIELDS",
        "FORBIDDEN_FIELD_FRAGMENTS",
        "FORBIDDEN_VALUE_PATTERNS",
        "fingerprint",
        "validate_redacted_evidence",
        "render_redacted_evidence_json",
    ):
        assert getattr(old, name) is getattr(redaction, name)

    assert old.fingerprint is fingerprints.fingerprint
    assert old.FINGERPRINT_RE is fingerprints.FINGERPRINT_RE
    assert old.HMAC_KEY is fingerprints.HMAC_KEY
    assert old.RedactionContractError is fingerprints.RedactionContractError
