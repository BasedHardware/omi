import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database.action_items as action_items_db
import database.redis_db as redis_db
from database.vector_db import delete_action_item_vectors_batch
from utils.other import endpoints as auth
from utils.notifications import send_action_items_batch_deletion_message
from utils.action_item_cleanup import (
    candidates_stale_age,
    candidates_overdue,
    candidates_semantic_dedup,
    candidates_llm_relevance,
    candidates_conversation_context,
    candidates_vague,
    merge_candidates,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_TTL = 300  # 5 minutes
_SAMPLE_PER_STRATEGY = 5


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CleanupPreviewRequest(BaseModel):
    strategies: List[str] = Field(
        default=['stale_age'],
        description="Strategies to apply: stale_age, overdue, semantic_dedup, llm_relevance, conversation_context, vague",
    )
    age_days: int = Field(default=30, ge=1, le=365, description="Threshold for stale_age strategy")
    overdue_days: int = Field(default=7, ge=1, le=365, description="Threshold for overdue strategy")
    similarity_threshold: float = Field(
        default=0.92, ge=0.5, le=1.0, description="Similarity threshold for semantic_dedup"
    )
    llm_confidence_threshold: float = Field(
        default=0.92, ge=0.5, le=1.0, description="Confidence threshold for llm_relevance"
    )


class CleanupSampleItem(BaseModel):
    description: str
    strategy: str


class CleanupCandidateMeta(BaseModel):
    id: str
    strategy: str


class CleanupPreviewResponse(BaseModel):
    session_id: str
    total_candidates: int
    breakdown: dict
    sample: List[CleanupSampleItem]
    candidate_ids: List[str]
    candidate_meta: List[CleanupCandidateMeta]
    expires_in_seconds: int


class CleanupExecuteRequest(BaseModel):
    session_id: str


class CleanupExecuteResponse(BaseModel):
    deleted_count: int


# ---------------------------------------------------------------------------
# Redis session helpers
# ---------------------------------------------------------------------------


def _session_key(uid: str, session_id: str) -> str:
    return f'cleanup_session:{uid}:{session_id}'


def _save_session(uid: str, session_id: str, data: dict) -> None:
    redis_db.set_generic_cache(_session_key(uid, session_id), data, ttl=_SESSION_TTL)


def _load_session(uid: str, session_id: str) -> Optional[dict]:
    return redis_db.get_generic_cache(_session_key(uid, session_id))


def _delete_session(uid: str, session_id: str) -> None:
    redis_db.delete_generic_cache(_session_key(uid, session_id))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post('/v1/action-items/cleanup/preview', response_model=CleanupPreviewResponse, tags=['action-items'])
def cleanup_preview(request: CleanupPreviewRequest, uid: str = Depends(auth.get_current_user_uid)):
    """
    Compute cleanup candidates and stage them server-side.
    Returns a session_id, summary counts, and a small sample for user review.
    Does not delete anything.
    """
    strategy_fns = {}
    if 'stale_age' in request.strategies:
        strategy_fns['stale_age'] = lambda: candidates_stale_age(uid, request.age_days)
    if 'overdue' in request.strategies:
        strategy_fns['overdue'] = lambda: candidates_overdue(uid, request.overdue_days)
    if 'semantic_dedup' in request.strategies:
        strategy_fns['semantic_dedup'] = lambda: candidates_semantic_dedup(uid, request.similarity_threshold)
    if 'llm_relevance' in request.strategies:
        strategy_fns['llm_relevance'] = lambda: candidates_llm_relevance(uid, request.llm_confidence_threshold)
    if 'conversation_context' in request.strategies:
        strategy_fns['conversation_context'] = lambda: candidates_conversation_context(
            uid, request.llm_confidence_threshold
        )
    if 'vague' in request.strategies:
        strategy_fns['vague'] = lambda: candidates_vague(uid)

    if not strategy_fns:
        return CleanupPreviewResponse(
            session_id='',
            total_candidates=0,
            breakdown={},
            sample=[],
            candidate_ids=[],
            candidate_meta=[],
            expires_in_seconds=_SESSION_TTL,
        )

    results: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=len(strategy_fns)) as pool:
        futures = {pool.submit(fn): name for name, fn in strategy_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error(f'Strategy {name} failed: {e}')
                results[name] = []

    candidate_lists = [results[name] for name in request.strategies if name in results]
    breakdown = {name: len(results.get(name, [])) for name in request.strategies}

    candidates = merge_candidates(candidate_lists)

    session_id = str(uuid.uuid4())
    _save_session(
        uid,
        session_id,
        {
            'ids': [c['id'] for c in candidates],
            'strategies': request.strategies,
            'age_days': request.age_days,
        },
    )

    seen_per_strategy: dict[str, int] = {}
    sample = []
    for c in candidates:
        s = c['strategy']
        if seen_per_strategy.get(s, 0) < _SAMPLE_PER_STRATEGY:
            sample.append(CleanupSampleItem(description=c['description'], strategy=c['strategy']))
            seen_per_strategy[s] = seen_per_strategy.get(s, 0) + 1

    return CleanupPreviewResponse(
        session_id=session_id,
        total_candidates=len(candidates),
        breakdown=breakdown,
        sample=sample,
        candidate_ids=[c['id'] for c in candidates],
        candidate_meta=[CleanupCandidateMeta(id=c['id'], strategy=c['strategy']) for c in candidates],
        expires_in_seconds=_SESSION_TTL,
    )


@router.post('/v1/action-items/cleanup/execute', response_model=CleanupExecuteResponse, tags=['action-items'])
def cleanup_execute(request: CleanupExecuteRequest, uid: str = Depends(auth.get_current_user_uid)):
    """
    Delete the candidates staged by a prior preview call.
    Falls back to recomputing if the session has expired.
    """
    session = _load_session(uid, request.session_id)

    if session:
        ids = session['ids']
        _delete_session(uid, request.session_id)
    else:
        # Session expired — recompute from stored parameters
        # For now surface an error; once all strategies are implemented
        # we can reconstruct the full candidate list from parameters.
        raise HTTPException(
            status_code=410,
            detail='Cleanup session expired. Please run preview again.',
        )

    if not ids:
        return CleanupExecuteResponse(deleted_count=0)

    deleted_ids = action_items_db.delete_action_items_batch(uid, ids)

    if deleted_ids:
        delete_action_item_vectors_batch(uid, deleted_ids)
        send_action_items_batch_deletion_message(user_id=uid, action_item_ids=deleted_ids)

    logger.info(f'cleanup_execute uid={uid} requested={len(ids)} deleted={len(deleted_ids)}')

    return CleanupExecuteResponse(deleted_count=len(deleted_ids))
