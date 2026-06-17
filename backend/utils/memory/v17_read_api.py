from typing import Any, Dict, Iterable, List

from models.v17_memory_contracts import LifecycleState, WorkingMemoryObservation, derive_allowed_use


def _tokens(query: str) -> set[str]:
    return {token.lower() for token in (query or "").replace(".", " ").replace(",", " ").split() if len(token) > 2}


def _matches(query: str, content: str) -> bool:
    query_tokens = _tokens(query)
    if not query_tokens:
        return True
    content_lower = (content or "").lower()
    return any(token in content_lower for token in query_tokens)


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


def query_working_memory(
    query: str, records: Iterable[WorkingMemoryObservation | Dict[str, Any]]
) -> List[Dict[str, Any]]:
    results = []
    for record in records:
        if isinstance(record, WorkingMemoryObservation):
            data = record.model_dump(mode="json")
        else:
            data = dict(record)
        content = data.get("content") or ""
        if not _matches(query, content):
            continue
        status = data.get("status") or LifecycleState.working.value
        risk_flags = data.get("risk_flags") or []
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


def query_durable_memory(
    query: str, records: Iterable[Dict[str, Any]], *, include_superseded: bool = False
) -> List[Dict[str, Any]]:
    results = []
    for record in records:
        status = record.get("status") or record.get("memory_state") or LifecycleState.active.value
        if status == LifecycleState.superseded.value and not include_superseded:
            continue
        content = record.get("content") or record.get("memory_text") or ""
        if not _matches(query, content):
            continue
        risk_flags = record.get("risk_flags") or []
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
    working_records: Iterable[WorkingMemoryObservation | Dict[str, Any]],
    durable_records: Iterable[Dict[str, Any]],
    include_superseded: bool = False,
) -> List[Dict[str, Any]]:
    durable = query_durable_memory(query, durable_records, include_superseded=include_superseded)
    working = query_working_memory(query, working_records)
    return durable + working
