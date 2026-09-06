"""Admission-time judged evidence events. Similarity never writes by itself."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel

from models.memory_contracts import LifecycleState
from models.product_memory import MemoryItem
from utils.memory.belief_model import belief_model_enabled

logger = logging.getLogger(__name__)

ADMISSION_NEIGHBOR_LIMIT = 5
# Cosine similarity needed before the judge is asked. Below this the neighbor
# is unrelated and there is no model call. The score never writes by itself.
# Override with MEMORY_BELIEF_ADMISSION_MIN_SCORE.
ADMISSION_JUDGE_MIN_SCORE = 0.75
MEMORY_BELIEF_ADMISSION_MIN_SCORE_ENV = "MEMORY_BELIEF_ADMISSION_MIN_SCORE"


class EvidenceEventKind(str, Enum):
    restated = "restated"
    contradicted = "contradicted"
    resolved = "resolved"
    unrelated = "unrelated"


class EvidenceEventJudgment(BaseModel):
    event: EvidenceEventKind
    target_memory_id: Optional[str] = None
    rationale: str = ""


NeighborFetcher = Callable[[str, str], Sequence[Dict[str, Any]]]
JudgeFn = Callable[[str, Sequence[Dict[str, Any]]], EvidenceEventJudgment]
ApplierFn = Callable[[str, str, Dict[str, Any], Dict[str, Any], Any], Any]
ReaderFn = Callable[[str, str, Any], Optional[MemoryItem]]


def patch_for_evidence_event(
    existing: MemoryItem,
    judgment: EvidenceEventJudgment,
    *,
    pointer: str,
    now: datetime,
    new_is_as_authoritative: bool = True,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Return (logical_updates, extra_item_updates) or None when nothing writes."""
    if judgment.event is EvidenceEventKind.unrelated:
        return None
    metadata = {"evidence_event": judgment.event.value, "pointer": pointer, "rationale": judgment.rationale}
    if judgment.event is EvidenceEventKind.restated:
        return (
            {"metadata": metadata},
            {
                "last_corroborated_at": now,
                "corroboration_count": int(existing.corroboration_count or 0) + 1,
            },
        )
    if judgment.event is EvidenceEventKind.resolved:
        # History by date, not by status: /v3 still lists the row with band=history.
        return (
            {"valid_to": now, "metadata": metadata},
            {},
        )
    if judgment.event is EvidenceEventKind.contradicted:
        extra: Dict[str, Any] = {"confidence": 0.0}
        logical: Dict[str, Any] = {"metadata": metadata}
        if new_is_as_authoritative:
            logical["result_status"] = LifecycleState.superseded.value
            extra["superseded_by"] = pointer
        return logical, extra
    return None


def admission_judge_min_score() -> float:
    """Call-boundary env read. Invalid or unset values keep the documented default."""
    raw = os.getenv(MEMORY_BELIEF_ADMISSION_MIN_SCORE_ENV)
    if raw is None or not str(raw).strip():
        return ADMISSION_JUDGE_MIN_SCORE
    try:
        return float(raw)
    except ValueError:
        return ADMISSION_JUDGE_MIN_SCORE


def _neighbor_score(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def default_judge(new_content: str, neighbors: Sequence[Dict[str, Any]]) -> EvidenceEventJudgment:
    """LLM judge. Empty neighbors are unrelated without a model call."""
    if not neighbors:
        return EvidenceEventJudgment(event=EvidenceEventKind.unrelated, rationale="no neighbors")
    from langchain_core.output_parsers import PydanticOutputParser

    from utils.llm.clients import get_llm

    listed = "\n".join(
        f"- id={row.get('memory_id')} content={row.get('content')!r}" for row in neighbors[:ADMISSION_NEIGHBOR_LIMIT]
    )
    parser = PydanticOutputParser(pydantic_object=EvidenceEventJudgment)
    prompt = (
        "A NEW claim was just admitted. Label its relationship to the nearest EXISTING memories.\n"
        "Events: restated (same claim, later observation), contradicted (opposite), "
        "resolved (the state/plan finished), unrelated (write nothing).\n"
        "Similarity is not evidence. Only judge a true restatement, contradiction, or resolution.\n"
        f"NEW: {new_content!r}\nEXISTING:\n{listed}\n"
        f"{parser.get_format_instructions()}"
    )
    content = get_llm("memory_conflict").invoke([("human", prompt)]).content
    text = "\n".join(str(part) for part in content) if isinstance(content, list) else str(content)
    parsed = parser.parse(text)
    return EvidenceEventJudgment.model_validate(parsed)


def _default_neighbor_fetcher(uid: str, content: str, db_client: Any) -> Sequence[Dict[str, Any]]:
    from database.vector_db import query_memory_vector_candidates
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    result = query_memory_vector_candidates(uid, content, limit=ADMISSION_NEIGHBOR_LIMIT)
    rows: List[Dict[str, Any]] = []
    for hit in result.hits:
        item = read_canonical_memory_item(uid, hit.memory_id, db_client=db_client)
        rows.append(
            {
                "memory_id": hit.memory_id,
                "content": (item.content if item is not None else "") or "",
                "score": hit.score,
            }
        )
    return rows


def _default_applier(
    uid: str,
    memory_id: str,
    logical_updates: Dict[str, Any],
    extra_updates: Dict[str, Any],
    db_client: Any,
) -> Any:
    from utils.memory.canonical_memory_adapter import apply_canonical_user_mutation

    def build_patch(_item: MemoryItem, _now: datetime) -> tuple[Dict[str, Any], Dict[str, Any]]:
        return logical_updates, extra_updates

    _previous, updated = apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind=f"belief_evidence:{logical_updates.get('metadata', {}).get('evidence_event', 'event')}",
        build_patch=build_patch,
        db_client=db_client,
    )
    return updated


def admit_claim_against_neighbors(
    uid: str,
    new_memory_id: str,
    new_content: str,
    *,
    db_client: Any,
    now: Optional[datetime] = None,
    new_user_asserted: bool = False,
    neighbor_fetcher: Optional[NeighborFetcher] = None,
    judge: Optional[JudgeFn] = None,
    applier: Optional[ApplierFn] = None,
    reader: Optional[ReaderFn] = None,
) -> Optional[EvidenceEventJudgment]:
    """New data looks for memories it touches. Flag off and unrelated write nothing."""
    if not belief_model_enabled():
        return None
    content = (new_content or "").strip()
    if not content or not new_memory_id:
        return None
    try:
        neighbors = [
            row
            for row in (
                neighbor_fetcher or (lambda _uid, _content: _default_neighbor_fetcher(_uid, _content, db_client))
            )(uid, content)
            if row.get("memory_id") and row["memory_id"] != new_memory_id
        ]
        min_score = admission_judge_min_score()
        neighbors = [row for row in neighbors if _neighbor_score(row) >= min_score]
        if not neighbors:
            return EvidenceEventJudgment(event=EvidenceEventKind.unrelated, rationale="below similarity gate")
        judgment = (judge or default_judge)(content, neighbors)
    except Exception:
        logger.warning("belief evidence admission lookup failed memory_id=%s", new_memory_id, exc_info=False)
        return None
    if judgment.event is EvidenceEventKind.unrelated:
        return judgment
    target_id = judgment.target_memory_id or (neighbors[0].get("memory_id") if neighbors else None)
    if not target_id or target_id == new_memory_id:
        return EvidenceEventJudgment(event=EvidenceEventKind.unrelated, rationale="no target")
    if reader is not None:
        existing = reader(uid, target_id, db_client)
    else:
        from utils.memory.canonical_memory_adapter import read_canonical_memory_item

        existing = read_canonical_memory_item(uid, target_id, db_client=db_client)
    if existing is None:
        return EvidenceEventJudgment(event=EvidenceEventKind.unrelated, rationale="target missing")
    patch = patch_for_evidence_event(
        existing,
        judgment,
        pointer=new_memory_id,
        now=now or datetime.now(timezone.utc),
        new_is_as_authoritative=new_user_asserted or not existing.user_asserted,
    )
    if patch is None:
        return judgment
    logical, extra = patch
    try:
        (applier or _default_applier)(uid, existing.memory_id, logical, extra, db_client)
    except Exception:
        logger.warning("belief evidence admission apply failed memory_id=%s", existing.memory_id, exc_info=False)
        return None
    return judgment


def admit_committed_claims(
    uid: str,
    committed_ids: Sequence[str],
    payloads: Sequence[Dict[str, Any]],
    *,
    db_client: Any,
    **kwargs: Any,
) -> None:
    if not belief_model_enabled():
        return
    by_id = {str(row.get("id") or row.get("memory_id") or ""): row for row in payloads}
    for memory_id in committed_ids:
        payload = by_id.get(memory_id) or {}
        try:
            admit_claim_against_neighbors(
                uid,
                memory_id,
                str(payload.get("content") or ""),
                db_client=db_client,
                new_user_asserted=bool(payload.get("manually_added") or payload.get("user_asserted")),
                **kwargs,
            )
        except Exception:
            logger.warning("belief evidence admission failed memory_id=%s", memory_id, exc_info=False)


def schedule_belief_admission(
    uid: str,
    memory_id: str,
    content: str,
    *,
    db_client: Any,
    new_user_asserted: bool = False,
) -> None:
    """Fire-and-forget admission judge. Does not wait on the executor future."""
    if not belief_model_enabled():
        return
    from utils.executors import llm_executor, submit_with_context

    submit_with_context(
        llm_executor,
        admit_claim_against_neighbors,
        uid,
        memory_id,
        content,
        db_client=db_client,
        new_user_asserted=new_user_asserted,
    )
