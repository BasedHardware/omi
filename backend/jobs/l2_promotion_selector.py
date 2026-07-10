from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

DEFAULT_COMPLETION_INACTIVITY_MINUTES = 30
DEFAULT_MAX_SESSIONS_PER_BATCH = 3
DEFAULT_MAX_L1_ITEMS_PER_BATCH = 50


def _empty_raw_record() -> Dict[str, Any]:
    return {}


@dataclass(frozen=True)
class PromotionSelectorConfig:
    max_sessions_per_batch: int = DEFAULT_MAX_SESSIONS_PER_BATCH
    max_l1_items_per_batch: int = DEFAULT_MAX_L1_ITEMS_PER_BATCH
    completion_inactivity_minutes: int = DEFAULT_COMPLETION_INACTIVITY_MINUTES

    def __post_init__(self) -> None:
        if self.max_sessions_per_batch < 1:
            raise ValueError('max_sessions_per_batch must be positive')
        if self.max_l1_items_per_batch < 1:
            raise ValueError('max_l1_items_per_batch must be positive')
        if self.completion_inactivity_minutes < 1:
            raise ValueError('completion_inactivity_minutes must be positive')


@dataclass(frozen=True)
class L1PromotionCandidate:
    uid: str
    l1_item_id: str
    session_id: str
    content: str
    created_at: datetime
    source_type: str = ''
    promoted: bool = False
    session_status: Optional[str] = None
    session_completed_at: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=_empty_raw_record)


@dataclass(frozen=True)
class PromotionWorkItem:
    uid: str
    session_ids: List[str]
    l1_item_ids: List[str]
    mode: str = 'forward'
    reason: str = 'completed_session'


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('promotion selector timestamps must be timezone-aware')
    return value.astimezone(timezone.utc)


def _coerce_datetime(value: Any, *, fallback: Optional[datetime] = None) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str) and value:
        return _utc(datetime.fromisoformat(value.replace('Z', '+00:00')))
    if fallback is not None:
        return _utc(fallback)
    raise ValueError('timestamp is required')


def candidate_from_record(record: Mapping[str, Any]) -> L1PromotionCandidate:
    uid = str(record.get('uid') or record.get('user_id') or '').strip()
    l1_item_id = str(record.get('l1_item_id') or record.get('memory_id') or record.get('id') or '').strip()
    session_id = str(
        record.get('session_id')
        or record.get('source_id')
        or record.get('conversation_id')
        or record.get('chat_session_id')
        or ''
    ).strip()
    content = str(record.get('content') or record.get('text') or '').strip()
    if not uid:
        raise ValueError('uid is required')
    if not l1_item_id:
        raise ValueError('l1 item id is required')
    if not session_id:
        raise ValueError('session id is required')
    created_at = _coerce_datetime(record.get('created_at') or record.get('captured_at') or record.get('updated_at'))
    completed_at = record.get('session_completed_at') or record.get('completed_at')
    return L1PromotionCandidate(
        uid=uid,
        l1_item_id=l1_item_id,
        session_id=session_id,
        content=content,
        created_at=created_at,
        source_type=str(record.get('source_type') or ''),
        promoted=bool(
            record.get('promoted_to_l2')
            or record.get('l2_promoted')
            or record.get('l2_processed')
            or record.get('consolidated_commit_id')
        ),
        session_status=record.get('session_status') or record.get('status'),
        session_completed_at=_coerce_datetime(completed_at) if completed_at else None,
        raw=dict(record),
    )


def _session_completed(
    items: Sequence[L1PromotionCandidate],
    *,
    now: datetime,
    config: PromotionSelectorConfig,
) -> bool:
    explicit_completed = any(
        item.session_completed_at is not None or str(item.session_status or '').lower() == 'completed' for item in items
    )
    if explicit_completed:
        return True
    latest = max(item.created_at for item in items)
    cutoff = _utc(now) - timedelta(minutes=config.completion_inactivity_minutes)
    return latest <= cutoff


def select_promotion_work_items(
    candidates: Iterable[L1PromotionCandidate | Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    config: Optional[PromotionSelectorConfig] = None,
    mode: str = 'forward',
) -> List[PromotionWorkItem]:
    current_time = _utc(now or datetime.now(timezone.utc))
    cfg = config or PromotionSelectorConfig()
    normalized: List[L1PromotionCandidate] = [
        candidate if isinstance(candidate, L1PromotionCandidate) else candidate_from_record(candidate)
        for candidate in candidates
    ]
    pending = [candidate for candidate in normalized if not candidate.promoted]

    sessions: Dict[tuple[str, str], List[L1PromotionCandidate]] = {}
    for item in pending:
        sessions.setdefault((item.uid, item.session_id), []).append(item)

    completed_sessions: List[tuple[str, str, List[L1PromotionCandidate]]] = []
    for (uid, session_id), items in sessions.items():
        ordered = sorted(items, key=lambda item: (item.created_at, item.l1_item_id))
        if _session_completed(ordered, now=current_time, config=cfg):
            completed_sessions.append((uid, session_id, ordered))

    completed_sessions.sort(key=lambda item: (item[0], item[2][0].created_at, item[1]))
    work_items: List[PromotionWorkItem] = []
    active_uid: Optional[str] = None
    batch_sessions: List[str] = []
    batch_l1_ids: List[str] = []

    def flush() -> None:
        nonlocal active_uid, batch_sessions, batch_l1_ids
        if active_uid and batch_sessions and batch_l1_ids:
            work_items.append(
                PromotionWorkItem(
                    uid=active_uid,
                    session_ids=list(batch_sessions),
                    l1_item_ids=list(batch_l1_ids),
                    mode=mode,
                )
            )
        active_uid = None
        batch_sessions = []
        batch_l1_ids = []

    for uid, session_id, items in completed_sessions:
        item_ids = [item.l1_item_id for item in items]
        would_exceed_sessions = len(batch_sessions) >= cfg.max_sessions_per_batch
        would_exceed_items = len(batch_l1_ids) + len(item_ids) > cfg.max_l1_items_per_batch
        if active_uid is not None and (uid != active_uid or would_exceed_sessions or would_exceed_items):
            flush()
        active_uid = uid
        batch_sessions.append(session_id)
        remaining = cfg.max_l1_items_per_batch - len(batch_l1_ids)
        batch_l1_ids.extend(item_ids[:remaining])
        if len(batch_l1_ids) >= cfg.max_l1_items_per_batch:
            flush()
    flush()
    return work_items
