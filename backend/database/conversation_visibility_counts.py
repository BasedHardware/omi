"""Counts exclude privacy tombstones and reversible duplicate-capture links."""

from typing import Any, Mapping, Optional, List
from datetime import datetime
from google.cloud.firestore_v1 import FieldFilter


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
    stamp = data.get(date_field)
    if start_date is not None and (stamp is None or stamp < start_date):
        return False
    if end_date is not None and (stamp is None or stamp > end_date):
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
) -> int:
    """Count `deleted==True` rows that would have matched the list query.

    Equality on `deleted` only matches documents that have the field, so
    pre-#15193 conversations (no `deleted` field) are not subtracted. Tombstones
    per user are few; this avoids a composite index on every list-filter combo.
    """
    matching = 0
    queries = (collection.where(filter=FieldFilter('deleted', '==', True)),)
    if not include_discarded:
        queries += (collection.where(filter=FieldFilter('dream_duplicate_of', '>', '')),)
    for index, query in enumerate(queries):
        for doc in query.stream():
            data = doc.to_dict() or {}
            if index == 1 and data.get('deleted'):
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
