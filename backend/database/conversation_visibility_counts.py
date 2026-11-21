"""Counts exclude tombstones, duplicate-capture links and unexpired live-bridge holds."""

from typing import Any, Mapping, Optional, List
from datetime import datetime
from google.cloud.firestore_v1 import FieldFilter
from fastapi import HTTPException

from utils.sync import bridge_pending

from .conversation_revisions import ensure_timezone_aware


def matches_list_predicates(
    data: Mapping[str, Any],
    *,
    include_discarded: bool,
    statuses: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
    date_field: str = 'created_at',
) -> bool:
    if not include_discarded and data.get('discarded'):
        return False
    if statuses and data.get('status') not in statuses:
        return False
    if sources and data.get('source') not in sources:
        return False
    if categories:
        structured = data.get('structured') if isinstance(data.get('structured'), dict) else {}
        if (structured or {}).get('category') not in categories:
            return False
    if folder_id is not None and data.get('folder_id') != folder_id:
        return False
    if starred is not None and bool(data.get('starred')) != starred:
        return False
    stamp = ensure_timezone_aware(raw_stamp) if isinstance(raw_stamp := data.get(date_field), datetime) else None
    if start_date is not None and (stamp is None or stamp < ensure_timezone_aware(start_date)):
        return False
    if end_date is not None and (stamp is None or stamp > ensure_timezone_aware(end_date)):
        return False
    return True


def count_hidden(
    collection: Any,
    *,
    include_discarded: bool,
    statuses: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
    hide_home: bool = False,
    include_recordings: bool = False,
) -> int:
    """Count hidden rows that would otherwise match the list query.

    Equality on `deleted` only matches documents that have the field, so
    pre-#15193 conversations (no `deleted` field) are not subtracted. Tombstones
    per user are few. Pending holds use a single-field deadline range and are
    deduplicated against tombstones/duplicate links, without a new composite index.
    """
    matching = 0
    now = bridge_pending.current_time()

    def count_layer(*fields):
        query = collection
        for field in fields:
            query = query.where(filter=FieldFilter(field, '==', True))
        if not include_discarded:
            query = query.where(filter=FieldFilter('discarded', '==', False))
        filtered = bool(
            statuses or sources or categories or start_date or end_date or folder_id is not None or starred is not None
        )
        if filtered:
            # Rare filtered counts inspect at most 10k matching-layer metadata rows.
            # No optional-predicate composite indexes, no transcript decoding.
            snapshots = list(
                query.select(
                    ['discarded', 'status', 'source', 'structured.category', 'folder_id', 'starred', 'created_at']
                )
                .limit(10001)
                .stream()
            )
            if len(snapshots) > 10000:
                raise HTTPException(503, 'Filtered conversation count exceeds scan budget')
            return sum(
                (starred is None or (doc.to_dict() or {}).get('starred') is starred)
                and matches_list_predicates(
                    doc.to_dict() or {},
                    include_discarded=include_discarded,
                    statuses=statuses,
                    sources=sources,
                    start_date=start_date,
                    end_date=end_date,
                    categories=categories,
                    folder_id=folder_id,
                    starred=starred,
                )
                for doc in snapshots
            )
        return int(query.count().get()[0][0].value)

    if not include_recordings:
        matching += count_layer('recording')
    if hide_home:
        matching += count_layer('home_hidden')
        if not include_recordings:
            matching -= count_layer('recording', 'home_hidden')
    queries = [(collection.where(filter=FieldFilter('deleted', '==', True)), False)]
    if not include_discarded:
        queries.append((collection.where(filter=FieldFilter('dream_duplicate_of', '>', '')), False))
    # Most users have no active bridge holds. Pay one bounded probe
    # rather than opening a second full document stream on every count call.
    if not include_discarded:
        pending = collection.where(filter=FieldFilter('sync_bridge_pending.expires_at', '>', now))
        if next(iter(pending.limit(1).stream()), None) is not None:
            queries.append((pending, True))
    seen = set()
    for query, pending_only in queries:
        for doc in query.stream():
            data = doc.to_dict() or {}
            identity = doc.id
            if identity in seen:
                continue
            if pending_only and not bridge_pending.hidden(data, now=now):
                continue
            seen.add(identity)
            if (not include_recordings and data.get('recording')) or (hide_home and data.get('home_hidden')):
                continue
            if matches_list_predicates(
                data,
                include_discarded=include_discarded,
                statuses=statuses,
                sources=sources,
                start_date=start_date,
                end_date=end_date,
                categories=categories,
                folder_id=folder_id,
                starred=starred,
            ):
                matching += 1
    return matching
