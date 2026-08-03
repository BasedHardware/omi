"""Small dependency-free contracts shared by bulk legacy backfill modules.

LIFECYCLE: permanent
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

ControlT = TypeVar("ControlT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class LegacyBackfillInventoryReport:
    """Content-free legacy inventory for bulk migration planning."""

    uid: str
    source_count: int
    bucket_counts: Dict[str, int]
    admitted_candidate_count: int
    content_character_count: int
    estimated_tokens: int
    admitted_candidate_estimated_tokens: int


@dataclass(frozen=True)
class RefreshedApplyAttempt(Generic[ControlT, ResultT]):
    control: ControlT
    result: Optional[ResultT]
    error: Optional[Exception]


def apply_with_control_refresh(
    *,
    control: ControlT,
    apply_fn: Callable[[ControlT], ResultT],
    refresh_control: Callable[[], ControlT],
    retry_once: bool,
) -> RefreshedApplyAttempt[ControlT, ResultT]:
    """Retry one deterministic row mutation after refreshing its control head."""
    attempts = 2 if retry_once else 1
    current_control = control
    for attempt in range(attempts):
        try:
            return RefreshedApplyAttempt(current_control, apply_fn(current_control), None)
        except Exception as exc:
            if attempt + 1 == attempts:
                return RefreshedApplyAttempt(current_control, None, exc)
            current_control = refresh_control()
    raise AssertionError("unreachable apply retry state")


def fetch_active_legacy_rows(
    uid: str,
    *,
    db_client: Any,
    reader: Callable[..., List[Dict[str, Any]]],
    is_active: Callable[[Dict[str, Any]], bool],
    scan_page_size: int,
) -> List[Dict[str, Any]]:
    """Page a raw legacy reader before applying its in-process active filter."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            page = reader(uid, limit=scan_page_size, offset=offset, firestore_client=db_client)
        except TypeError as exc:
            if "firestore_client" not in str(exc):
                raise
            page = reader(uid, limit=scan_page_size, offset=offset)
        if not page:
            break
        rows.extend(row for row in page if is_active(row))
        if len(page) < scan_page_size:
            break
        offset += scan_page_size
    return sorted(rows, key=lambda row: str(row.get("id") or ""))


__all__ = [
    "LegacyBackfillInventoryReport",
    "RefreshedApplyAttempt",
    "apply_with_control_refresh",
    "fetch_active_legacy_rows",
]
