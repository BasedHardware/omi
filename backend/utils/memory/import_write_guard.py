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


# Tags that mark one-memory-per-indexed-file items from the desktop local-file
# onboarding scan: the folder tag the scanner attached (projects/documents/
# downloads) or the per-file "recently modified" variant. Aggregate local_files
# facts use profile/project/technology tags instead and are not matched.
PER_FILE_LOCAL_IMPORT_TAGS = frozenset({"projects", "documents", "downloads", "recent_file"})


def normalized_import_marker(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    marker = "_".join(value.strip().lower().replace("-", "_").split())
    return marker or None


def is_per_file_local_import_tags(tags: Any) -> bool:
    """True for per-file local_files import items (one memory per indexed file).

    These carry no durable signal — up to 2800 path facts per onboarding scan —
    and historically buried users' real memories (bulk-purged server-side in
    July 2026). They are dropped unconditionally, independent of
    MEMORY_IMPORT_WRITE_BLOCK_MODE, so desktop clients released before the
    scanner stopped emitting them cannot recreate the spam.
    """
    if not isinstance(tags, list):
        return False
    normalized = {normalized_import_marker(tag) for tag in cast('list[Any]', tags)} - {None}
    if not {"local_files", "onboarding"} <= normalized:
        return False
    return bool(normalized & PER_FILE_LOCAL_IMPORT_TAGS)


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


def import_write_violation_for_guard(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """`import_write_violation`, except per-file local-file items are exempt.

    The memory endpoints acknowledge-and-drop per-file items without
    persisting them; letting the guard see them would 409 an old desktop
    build's whole onboarding batch in enforce mode before the drop can
    happen, defeating the backstop.
    """
    if is_per_file_local_import_tags(payload.get("tags")):
        return None
    return import_write_violation(payload)


def import_write_block_mode() -> str:
    mode = (os.getenv(IMPORT_WRITE_BLOCK_MODE_ENV) or "log").strip().lower()
    return mode if mode in {"off", "log", "enforce"} else "log"
