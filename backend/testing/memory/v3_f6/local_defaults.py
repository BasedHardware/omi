"""Canonical local placeholder defaults for memory-V3-F6 evidence targets."""

from __future__ import annotations

from typing import Any

DEFAULT_APPROVED_METADATA_PATHS = (
    "control/config metadata",
    "cursor secret metadata",
    "projection state metadata",
    "canary approval metadata",
    "iam policy",
    "firestore index state",
    "audit read log metadata",
)

DEFAULT_INDEX_EXPECTATIONS = {
    "memory_items_by_uid_generation_updated_at": {
        "fields": [("uid", "ASCENDING"), ("generation", "ASCENDING"), ("updated_at", "DESCENDING")],
        "query_scope": "COLLECTION",
        "state": "READY",
    }
}

DEFAULT_EVIDENCE_TARGETS: dict[str, dict[str, Any]] = {
    "dev": {
        "project_id": "PLACEHOLDER-dev-project-id",
        "project_number": "000000000000",
        "env_label": "dev",
        "evidence_principal": "serviceAccount:PLACEHOLDER-memory-evidence@PLACEHOLDER-dev-project-id.iam.gserviceaccount.com",
        "approved_metadata_paths": list(DEFAULT_APPROVED_METADATA_PATHS),
        "index_expectations": DEFAULT_INDEX_EXPECTATIONS,
        "audit_settings": {
            "enabled": True,
            "log_name": "cloudaudit.googleapis.com%2Fdata_access",
            "require_zero_write_methods": True,
        },
        "limits": {
            "max_documents_per_path": 25,
            "max_paths": len(DEFAULT_APPROVED_METADATA_PATHS),
            "per_rpc_timeout_seconds": 5,
            "overall_deadline_seconds": 60,
        },
    },
    "prod": {
        "project_id": "PLACEHOLDER-prod-project-id",
        "project_number": "000000000000",
        "env_label": "prod",
        "evidence_principal": "serviceAccount:PLACEHOLDER-memory-evidence@PLACEHOLDER-prod-project-id.iam.gserviceaccount.com",
        "approved_metadata_paths": list(DEFAULT_APPROVED_METADATA_PATHS),
        "index_expectations": DEFAULT_INDEX_EXPECTATIONS,
        "audit_settings": {
            "enabled": True,
            "log_name": "cloudaudit.googleapis.com%2Fdata_access",
            "require_zero_write_methods": True,
        },
        "limits": {
            "max_documents_per_path": 25,
            "max_paths": len(DEFAULT_APPROVED_METADATA_PATHS),
            "per_rpc_timeout_seconds": 5,
            "overall_deadline_seconds": 60,
        },
    },
}

__all__ = [
    "DEFAULT_APPROVED_METADATA_PATHS",
    "DEFAULT_EVIDENCE_TARGETS",
    "DEFAULT_INDEX_EXPECTATIONS",
]
