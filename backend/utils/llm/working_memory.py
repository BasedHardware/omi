"""Backward-compatible shim — implementation lives in ``utils.llm.working_observations`` (WS-G11)."""

from utils.llm.working_observations import (
    L1MemoryArchiveItems,
    WorkingObservationBatch,
    _CLIENT_IMPORT_ERROR,
    _build_l1_messages,
    _content_from_response,
    _persist_l1_archive_route_outcomes,
    _source_type_instructions,
    _with_deterministic_archive_ids,
    extract_l1_memory_archive_items_from_text,
    get_llm,
    logger,
    persist_non_active_route_outcome,
)

__all__ = [
    "L1MemoryArchiveItems",
    "WorkingObservationBatch",
    "_CLIENT_IMPORT_ERROR",
    "_build_l1_messages",
    "_content_from_response",
    "_persist_l1_archive_route_outcomes",
    "_source_type_instructions",
    "_with_deterministic_archive_ids",
    "extract_l1_memory_archive_items_from_text",
    "get_llm",
    "logger",
    "persist_non_active_route_outcome",
]
