from __future__ import annotations

import os
from typing import Any, Dict, Optional

IMPORT_WRITE_BLOCK_MODE_ENV = "MEMORY_IMPORT_WRITE_BLOCK_MODE"

IMPORT_MEMORY_SOURCES = frozenset(
    {
        "apple_notes",
        "calendar",
        "chatgpt",
        "chatgpt_memory_log",
        "claude",
        "claude_memory_log",
        "gmail",
        "google_calendar",
        "local_files",
    }
)
IMPORT_MEMORY_TAGS = frozenset(
    {
        "apple_notes",
        "calendar",
        "chatgpt",
        "claude",
        "gmail",
        "google_calendar",
        "import",
        "local_files",
        "onboarding",
    }
)
IMPORT_METADATA_KEYS = frozenset(
    {
        "import_kind",
        "importer_version",
        "source_artifact_id",
        "source_account_hash",
        "external_id",
    }
)


def normalized_import_marker(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    marker = "_".join(value.strip().lower().replace("-", "_").split())
    return marker or None


def import_write_violation(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source = normalized_import_marker(payload.get("source") or payload.get("source_type"))
    if source in IMPORT_MEMORY_SOURCES:
        return {"source": source}
    metadata = payload.get("metadata") or {}
    has_import_metadata = isinstance(metadata, dict) and any(key in metadata for key in IMPORT_METADATA_KEYS)
    if not has_import_metadata:
        return None
    tags = payload.get("tags") or []
    if isinstance(tags, list):
        normalized_tags = {normalized_import_marker(tag) for tag in tags}
        matched = sorted((normalized_tags - {None}).intersection(IMPORT_MEMORY_TAGS))
        if matched:
            return {"tags": matched}
    return None


def import_write_block_mode() -> str:
    mode = (os.getenv(IMPORT_WRITE_BLOCK_MODE_ENV) or "log").strip().lower()
    return mode if mode in {"off", "log", "enforce"} else "log"
