"""Canonical memory read api module (WS-G8a).

Neutral ``memory_read_api`` is the source of truth. Legacy ``memory_read_api`` remains an importable alias.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, cast

from database.product_memory_items import filter_default_product_memory_items
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from models.memory_contracts import (
    L1MemoryArchiveClass,
    WorkingObservationArchiveItem,
    LifecycleState,
    WorkingObservation,
    derive_allowed_use,
    filter_l1_archive_for_normal_search,
)
from models.product_memory import MemoryAccessPolicy, MemoryLayer, MemoryItem, is_archive_access_eligible

MemoryResult = Dict[str, Any]


def _tokens(query: str) -> set[str]:
    return {token.lower() for token in (query or "").replace(".", " ").replace(",", " ").split() if len(token) > 2}


def _matches(query: str, content: str) -> bool:
    query_tokens = _tokens(query)
    if not query_tokens:
        return True
    content_lower = (content or "").lower()
    return any(token in content_lower for token in query_tokens)


def _risk_flags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(flag) for flag in cast(List[Any], raw)]


def _agent_use_for_working(status: str, risk_flags: List[str]) -> str:
    if derive_allowed_use(status, risk_flags) == "hidden":
        return "hidden"
    if status == LifecycleState.review.value:
        return "review_only_not_profile_fact"
    if status == LifecycleState.context_only.value:
        return "context_only_not_profile_fact"
    return "working_context_not_stable_profile"


def _agent_use_for_durable(status: str, risk_flags: List[str]) -> str:
    if derive_allowed_use(status, risk_flags) == "hidden":
        return "hidden"
    if status == LifecycleState.active.value:
        return "stable_profile_fact"
    if status == LifecycleState.review.value:
        return "review_only_not_profile_fact"
    if status == LifecycleState.context_only.value:
        return "context_only_not_profile_fact"
    if status == LifecycleState.superseded.value:
        return "history_only_not_current_truth"
    return "audit_only_not_profile_fact"


def query_working_memory(query: str, records: Iterable[WorkingObservation | Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[MemoryResult] = []
    for record in records:
        if isinstance(record, WorkingObservation):
            data = record.model_dump(mode="json")
        else:
            data = dict(record)
        content = data.get("content") or ""
        if not _matches(query, content):
            continue
        status = data.get("status") or LifecycleState.working.value
        risk_flags = _risk_flags(data.get("risk_flags"))
        results.append(
            {
                "memory_id": data.get("observation_id"),
                "memory_layer": "working",
                "content": content,
                "lifecycle_status": status,
                "confidence": data.get("confidence"),
                "source": data.get("source_id") or data.get("packet_id"),
                "date": data.get("created_at") or data.get("observed_at"),
                "evidence": data.get("source_refs") or [],
                "agent_use": _agent_use_for_working(status, risk_flags),
                "superseded_by": data.get("superseded_by"),
            }
        )
    return results


def _coerce_archive_item(record: WorkingObservationArchiveItem | Dict[str, Any]) -> WorkingObservationArchiveItem:
    if isinstance(record, WorkingObservationArchiveItem):
        return record
    return WorkingObservationArchiveItem.model_validate(record)


def _coerce_product_memory_item(record: MemoryItem | Dict[str, Any]) -> MemoryItem:
    if isinstance(record, MemoryItem):
        return record
    return MemoryItem.model_validate(record)


def _tier_value(item: MemoryItem) -> str:
    return item.tier.value


def _product_memory_result(item: MemoryItem, *, agent_use: str, access_reason: str) -> Dict[str, Any]:
    return {
        "memory_id": item.memory_id,
        "memory_layer": "product_memory",
        "tier": _tier_value(item),
        "content": item.content or "",
        "lifecycle_status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "processing_state": (
            item.processing_state.value if hasattr(item.processing_state, "value") else str(item.processing_state)
        ),
        "confidence": None,
        "visibility": item.visibility,
        "visibility_source": "memory_item.visibility",
        "source": item.evidence[0].source_id if item.evidence else None,
        "date": item.updated_at.isoformat(),
        "evidence": [evidence.model_dump(mode="json") for evidence in item.evidence],
        "agent_use": agent_use,
        "access_reason": access_reason,
        "superseded_by": None,
    }


def query_default_product_memory_items(
    query: str,
    records: Iterable[MemoryItem | Dict[str, Any]],
    *,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Search memory product memory items for default-visible product output.

    Callers pass authoritative `memory_items`; this seam applies the product default
    memory filter before query matching, so stale Short-term and Archive records are
    never default-visible even when their content matches.
    """

    items = [_coerce_product_memory_item(record) for record in records]
    report = filter_default_product_memory_items(items, policy=policy, now=now)
    current_time = now or datetime.now(timezone.utc)
    visible_items = filter_canonical_default_visible_items(items, policy=policy, now=current_time)
    results: List[MemoryResult] = []
    for item in visible_items:
        content = item.content or ""
        if not _matches(query, content):
            continue
        decision = report.decisions[item.memory_id]
        access_reason = decision.reason if decision.allowed else "default_memory_allowed"
        results.append(_product_memory_result(item, agent_use="default_access_memory", access_reason=access_reason))
    return results


def query_archive_product_memory_items(
    query: str,
    records: Iterable[MemoryItem | Dict[str, Any]],
    *,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Search Archive product memory only for explicit archive-capable callers."""

    results: List[MemoryResult] = []
    for item in [_coerce_product_memory_item(record) for record in records]:
        if item.tier != MemoryLayer.archive:
            continue
        content = item.content or ""
        if not _matches(query, content):
            continue
        access = is_archive_access_eligible(item, policy, now=now)
        if not access.allowed:
            continue
        results.append(_product_memory_result(item, agent_use="explicit_archive_memory", access_reason=access.reason))
    return results


def query_l1_archive(
    query: str, records: Iterable[WorkingObservationArchiveItem | Dict[str, Any]], *, include_sensitive: bool = False
) -> List[Dict[str, Any]]:
    archive_items = [_coerce_archive_item(record) for record in records]
    if include_sensitive:
        items = [item for item in archive_items if _matches(query, item.text)]
    else:
        items = filter_l1_archive_for_normal_search(archive_items, query=query)
    results: List[MemoryResult] = []
    for item in items:
        archive_class = item.archive_class.value
        if archive_class == L1MemoryArchiveClass.sensitive.value and not include_sensitive:
            continue
        results.append(
            {
                "memory_id": item.archive_id,
                "memory_layer": "l1_archive",
                "content": item.text,
                "archive_class": archive_class,
                "confidence": item.confidence,
                "source": item.source_id,
                "source_type": item.source_type,
                "evidence": item.source_refs
                or [{"quote": quote, "source_id": item.source_id} for quote in item.evidence_quotes],
                "agent_use": "archived_evidence_not_stable_profile",
                "search_result_label": item.search_result_label,
                "normal_search_allowed": item.normal_search_allowed,
            }
        )
    return results


def query_durable_memory(
    query: str, records: Iterable[Dict[str, Any]], *, include_superseded: bool = False
) -> List[Dict[str, Any]]:
    results: List[MemoryResult] = []
    for record in records:
        status = record.get("status") or record.get("memory_state") or LifecycleState.active.value
        if status == LifecycleState.superseded.value and not include_superseded:
            continue
        content = record.get("content") or record.get("memory_text") or ""
        if not _matches(query, content):
            continue
        risk_flags = _risk_flags(record.get("risk_flags"))
        results.append(
            {
                "memory_id": record.get("id") or record.get("memory_id") or record.get("card_id"),
                "memory_layer": "durable",
                "content": content,
                "lifecycle_status": status,
                "confidence": record.get("confidence") or record.get("provenance_confidence"),
                "source": record.get("source") or record.get("source_example_id"),
                "date": record.get("created_at") or record.get("valid_at"),
                "evidence": record.get("evidence_set")
                or record.get("evidence_refs")
                or record.get("evidence_quotes")
                or [],
                "agent_use": _agent_use_for_durable(status, risk_flags),
                "superseded_by": record.get("superseded_by"),
                "supersedes": record.get("supersedes") or [],
            }
        )
    return results


def query_memory_context(
    query: str,
    *,
    working_records: Iterable[WorkingObservation | Dict[str, Any]],
    durable_records: Iterable[Dict[str, Any]],
    l1_archive_records: Iterable[WorkingObservationArchiveItem | Dict[str, Any]] = (),
    include_superseded: bool = False,
    include_l1_archive: bool = False,
) -> List[Dict[str, Any]]:
    durable = query_durable_memory(query, durable_records, include_superseded=include_superseded)
    working = query_working_memory(query, working_records)
    archive = query_l1_archive(query, l1_archive_records) if include_l1_archive else []
    return durable + working + archive
