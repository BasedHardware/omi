"""Additive contracts for the array-shaped Developer API read endpoints."""

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import HTTPException


def reject_unknown_query(request: Any, allowed: Iterable[str]) -> None:
    if request is None or not hasattr(request, 'query_params'):
        return
    if set(request.query_params) - set(allowed):
        # Do not echo arbitrary names or values into errors/logs.
        raise HTTPException(status_code=400, detail="Unknown query parameter. Check the documented parameters.")


def utc_window(start: Optional[datetime], end: Optional[datetime]) -> tuple:
    start = start.replace(tzinfo=timezone.utc) if start is not None and start.tzinfo is None else start
    end = end.replace(tzinfo=timezone.utc) if end is not None and end.tzinfo is None else end
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    return start, end


def pagination_headers(
    response: Any, *, limit: int, has_more: bool, next_offset: Optional[int] = None, next_cursor: Optional[str] = None
) -> None:
    if response is None:
        return
    response.headers['X-Omi-Effective-Limit'] = str(limit)
    response.headers['X-Omi-Has-More'] = str(has_more).lower()
    if has_more and next_offset is not None:
        response.headers['X-Omi-Next-Offset'] = str(next_offset)
    if next_cursor:
        response.headers['X-Omi-Next-Cursor'] = next_cursor
