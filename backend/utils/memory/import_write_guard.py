from __future__ import annotations

import os
from typing import Any, Mapping, Optional, cast

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


def import_write_violation(payload: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    source = normalized_import_marker(payload.get("source") or payload.get("source_type"))
    if source in IMPORT_MEMORY_SOURCES:
        return {"source": source}
    raw_metadata = payload.get("metadata")
    metadata: Mapping[str, Any] = cast(Mapping[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
    has_import_metadata = any(key in metadata for key in IMPORT_METADATA_KEYS)
    if not has_import_metadata:
        return None
    raw_tags = payload.get("tags")
    if isinstance(raw_tags, list):
        tags = cast(list[Any], raw_tags)
        normalized_tags = {marker for tag in tags if (marker := normalized_import_marker(tag)) is not None}
        matched = sorted(normalized_tags.intersection(IMPORT_MEMORY_TAGS))
        if matched:
            return {"tags": matched}
    return None


def import_write_block_mode() -> str:
    mode = (os.getenv(IMPORT_WRITE_BLOCK_MODE_ENV) or "log").strip().lower()
    return mode if mode in {"off", "log", "enforce"} else "log"
