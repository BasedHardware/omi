import logging
import uuid
from concurrent.futures import as_completed
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database.action_items as action_items_db
import database.redis_db as redis_db
from database.vector_db import delete_action_item_vectors_batch
from utils.executors import postprocess_executor
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
_VALID_STRATEGIES = frozenset(
    {'stale_age', 'overdue', 'semantic_dedup', 'llm_relevance', 'conversation_context', 'vague'}
)


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
    scan_cursor: Optional[str] = Field(
        default=None,
        description="Resume token from a prior cleanup preview to scan the next oldest open tasks",
    )


class CleanupSampleItem(BaseModel):
    description: str
    strategy: str


class CleanupCandidateMeta(BaseModel):
    id: str
    strategy: str
    description: str


class CleanupPreviewResponse(BaseModel):
    session_id: str
    total_candidates: int
    breakdown: dict
    sample: List[CleanupSampleItem]
    candidate_ids: List[str]
    candidate_meta: List[CleanupCandidateMeta]
    expires_in_seconds: int
    total_open_action_items: int = Field(
        description="True count of the user's open action items, independent of any scan cap"
    )
    scan_cap: int = Field(description="Per-strategy Firestore scan cap (see _ACTION_ITEMS_LIST_HARD_MAX)")
    scan_truncated: bool = Field(
        description="True when more open tasks remain beyond this preview's oldest-first scan window"
    )
    next_scan_cursor: Optional[str] = Field(
        default=None,
        description="Pass on the next preview to continue scanning from the oldest remaining open tasks",
    )


class CleanupExecuteRequest(BaseModel):
    session_id: str
    excluded_ids: List[str] = Field(
        default_factory=list, description="Candidate IDs from the preview to keep (not delete)"
    )


class CleanupExecuteResponse(BaseModel):
    deleted_count: int


# ---------------------------------------------------------------------------
# Redis session helpers
# ---------------------------------------------------------------------------


def _session_key(uid: str, session_id: str) -> str:
    return f'cleanup_session:{uid}:{session_id}'


def _result_key(uid: str, session_id: str) -> str:
    return f'cleanup_result:{uid}:{session_id}'


def _save_session(uid: str, session_id: str, data: dict) -> None:
    redis_db.set_generic_cache(_session_key(uid, session_id), data, ttl=_SESSION_TTL)


def _claim_session(uid: str, session_id: str) -> Optional[dict]:
    return redis_db.pop_generic_cache(_session_key(uid, session_id))


def _save_terminal_result(uid: str, session_id: str, deleted_count: int) -> None:
    redis_db.set_generic_cache(
        _result_key(uid, session_id),
        {'deleted_count': deleted_count},
        ttl=_SESSION_TTL,
    )


def _load_terminal_result(uid: str, session_id: str) -> Optional[dict]:
    return redis_db.get_generic_cache(_result_key(uid, session_id))


def _preflight_unlocked_ids(uid: str, action_item_ids: List[str]) -> None:
    for i in range(0, len(action_item_ids), 500):
        chunk = action_item_ids[i : i + 500]
        existing_items = action_items_db.get_action_items_by_ids(uid, chunk)
        if any(item.get('is_locked', False) for item in existing_items):
            raise HTTPException(
                status_code=402,
                detail='A paid plan is required to delete locked action items.',
            )


def _validate_strategies(strategies: List[str]) -> None:
    unknown = sorted(set(strategies) - _VALID_STRATEGIES)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f'Unknown cleanup strategies: {unknown}',
        )


def _run_strategies(
    strategy_fns: dict[str, Callable[[], tuple[list[dict], Optional[str]]]],
) -> tuple[dict[str, list], Optional[str]]:
    results: dict[str, list] = {}
    next_cursor: Optional[str] = None
    futures = {postprocess_executor.submit(fn): name for name, fn in strategy_fns.items()}
    for future in as_completed(futures):
        name = futures[future]
        try:
            candidates, strategy_next_cursor = future.result()
            results[name] = candidates
            if strategy_next_cursor:
                next_cursor = strategy_next_cursor
        except Exception as e:
            logger.error(f'Strategy {name} failed: {e}')
            results[name] = []
    return results, next_cursor


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post('/v1/action-items/cleanup/preview', response_model=CleanupPreviewResponse, tags=['action-items'])
def cleanup_preview(
    request: CleanupPreviewRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'action_items:cleanup_preview')),
):
    """
    Compute cleanup candidates and stage them server-side.
    Returns a session_id, summary counts, and a small sample for user review.
    Does not delete anything.
    """
    _validate_strategies(request.strategies)

    strategy_fns: dict[str, Callable[[], tuple[list[dict], Optional[str]]]] = {}
    scan_cursor = request.scan_cursor
    if 'stale_age' in request.strategies:
        strategy_fns['stale_age'] = lambda: candidates_stale_age(uid, request.age_days, scan_cursor=scan_cursor)
    if 'overdue' in request.strategies:
        strategy_fns['overdue'] = lambda: candidates_overdue(uid, request.overdue_days, scan_cursor=scan_cursor)
    if 'semantic_dedup' in request.strategies:
        strategy_fns['semantic_dedup'] = lambda: candidates_semantic_dedup(
            uid, request.similarity_threshold, scan_cursor=scan_cursor
        )
    if 'llm_relevance' in request.strategies:
        strategy_fns['llm_relevance'] = lambda: candidates_llm_relevance(
            uid, request.llm_confidence_threshold, scan_cursor=scan_cursor
        )
    if 'conversation_context' in request.strategies:
        strategy_fns['conversation_context'] = lambda: candidates_conversation_context(
            uid, request.llm_confidence_threshold, scan_cursor=scan_cursor
        )
    if 'vague' in request.strategies:
        strategy_fns['vague'] = lambda: candidates_vague(uid, scan_cursor=scan_cursor)

    total_open = action_items_db.get_open_action_items_count(uid)
    scan_cap = action_items_db.get_action_items_list_scan_cap()

    if not strategy_fns:
        return CleanupPreviewResponse(
            session_id='',
            total_candidates=0,
            breakdown={},
            sample=[],
            candidate_ids=[],
            candidate_meta=[],
            expires_in_seconds=_SESSION_TTL,
            total_open_action_items=total_open,
            scan_cap=scan_cap,
            scan_truncated=total_open > scan_cap,
            next_scan_cursor=None,
        )

    results, next_scan_cursor = _run_strategies(strategy_fns)
    scan_truncated = next_scan_cursor is not None

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
            'scan_cursor': request.scan_cursor,
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
        candidate_meta=[
            CleanupCandidateMeta(id=c['id'], strategy=c['strategy'], description=c['description']) for c in candidates
        ],
        expires_in_seconds=_SESSION_TTL,
        total_open_action_items=total_open,
        scan_cap=scan_cap,
        scan_truncated=scan_truncated,
        next_scan_cursor=next_scan_cursor,
    )


@router.post('/v1/action-items/cleanup/execute', response_model=CleanupExecuteResponse, tags=['action-items'])
def cleanup_execute(
    request: CleanupExecuteRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'action_items:cleanup_execute')),
):
    """Delete the candidates staged by a prior preview call."""
    terminal = _load_terminal_result(uid, request.session_id)
    if terminal is not None:
        return CleanupExecuteResponse(deleted_count=int(terminal['deleted_count']))

    session = _claim_session(uid, request.session_id)
    if not session:
        raise HTTPException(
            status_code=410,
            detail='Cleanup session expired. Please run preview again.',
        )

    excluded = set(request.excluded_ids)
    ids = [item_id for item_id in session['ids'] if item_id not in excluded]

    if not ids:
        _save_terminal_result(uid, request.session_id, 0)
        return CleanupExecuteResponse(deleted_count=0)

    _preflight_unlocked_ids(uid, ids)
    deleted_ids = action_items_db.delete_action_items_batch(uid, ids)

    if deleted_ids:
        delete_action_item_vectors_batch(uid, deleted_ids)
        send_action_items_batch_deletion_message(user_id=uid, action_item_ids=deleted_ids)

    deleted_count = len(deleted_ids)
    _save_terminal_result(uid, request.session_id, deleted_count)
    logger.info(f'cleanup_execute uid={uid} requested={len(ids)} deleted={deleted_count}')

    return CleanupExecuteResponse(deleted_count=deleted_count)
