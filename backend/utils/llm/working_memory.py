"""Backward-compatible shim — implementation lives in ``utils.llm.working_observations`` (WS-G11)."""

from typing import Any, Callable, cast

from utils.llm import working_observations as _working_observations
from utils.llm.working_observations import L1MemoryArchiveItems, WorkingObservationBatch
from utils.llm.working_observations import extract_l1_memory_archive_items_from_text
from utils.llm.working_observations import get_llm, logger, persist_non_active_route_outcome

_CLIENT_IMPORT_ERROR = cast(Exception | None, getattr(_working_observations, "_CLIENT_IMPORT_ERROR"))
_build_l1_messages = cast(Callable[..., list[tuple[str, str]]], getattr(_working_observations, "_build_l1_messages"))
_content_from_response = cast(Callable[[object], str], getattr(_working_observations, "_content_from_response"))
_persist_l1_archive_route_outcomes = cast(
    Callable[..., None], getattr(_working_observations, "_persist_l1_archive_route_outcomes")
)
_source_type_instructions = cast(Callable[[str, str], str], getattr(_working_observations, "_source_type_instructions"))
_with_deterministic_archive_ids = cast(
    Callable[..., list[Any]], getattr(_working_observations, "_with_deterministic_archive_ids")
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
