"""Additive contracts for the array-shaped Developer API read endpoints."""

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import HTTPException


def reject_unknown_query(request: Any, allowed: Iterable[str]) -> None:
    if request is None or not hasattr(request, 'query_params'):
        return
    allowed_names = set(allowed)
    unknown = {
        name for name in request.query_params if name not in allowed_names and not _is_cache_buster_parameter(name)
    }
    if unknown:
        # Do not echo arbitrary names or values into errors/logs.
        raise HTTPException(status_code=400, detail="Unknown query parameter. Check the documented parameters.")


def ignore_unknown_query(request: Any, allowed: Iterable[str], response: Any = None) -> None:
    """Released list/detail routes ignored unknown query parameters before the explicit
    read contract; live third-party clients still send extra filters (for example
    ``include_discarded``, ``statuses`` or ``order``), so these routes keep ignoring them.
    The count is reported in ``X-Omi-Ignored-Query-Params`` so callers can notice."""
    if request is None or not hasattr(request, 'query_params'):
        return
    if 'query' in request.query_params and 'query' not in set(allowed):
        # A silently ignored search term returns an unfiltered page that looks like results.
        raise HTTPException(
            status_code=400, detail="Unknown query parameter. List routes do not search; use the /search route."
        )
    allowed_names = set(allowed)
    ignored = {
        name for name in request.query_params if name not in allowed_names and not _is_cache_buster_parameter(name)
    }
    if ignored and response is not None:
        response.headers['X-Omi-Ignored-Query-Params'] = str(len(ignored))


def _is_cache_buster_parameter(name: str) -> bool:
    """Keep common inert cache-buster query keys compatible with older callers."""
    normalized = ''.join(character for character in name.lower() if character.isalnum())
    return name == '_' or normalized in {'t', 'ts', 'timestamp', 'cb', 'cachebust', 'cachebuster'}


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
