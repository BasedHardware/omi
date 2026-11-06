"""Resumable server-wide task filtering over the existing browse/search owners."""

import asyncio
import base64
import hmac
import json
import os
import time
from typing import Any, Awaitable, Callable, Optional, TypedDict

from database.conversations import is_visible_conversation
from models.conversation_tasks import TaskConversationPageRequest
from utils.conversation_page_cursor import query_scope
from utils.executors import db_executor, run_blocking
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


class TaskFilterUnavailable(Exception):
    pass


class TaskFilterCursorError(ValueError):
    pass


class _BrowsePosition(TypedDict):
    after: str


class _SearchPosition(TypedDict):
    page: int
    offset: int


_Position = _BrowsePosition | _SearchPosition
_Row = dict[str, Any]


def _eligible_rows(
    candidates: list[tuple[Optional[_Position], Optional[_Row]]],
    filters: TaskConversationPageRequest,
    allow_locked: bool,
) -> list[_Row]:
    # The shared visibility owner is decorated with shadow-policy I/O. Keep
    # that existing boundary off the event loop, even for a small raw page.
    return [
        row
        for _, row in candidates
        if row
        and row.get('id')
        and is_visible_conversation(row, include_discarded=filters.include_discarded, presentation=True)
        and row.get('status') in ('processing', 'completed')
        and (not filters.folder_id or row.get('folder_id') == filters.folder_id)
        and (filters.starred is None or bool(row.get('starred')) == filters.starred)
        and (allow_locked or not row.get('is_locked'))
    ]


def _sign(payload: bytes) -> bytes:
    secret = os.getenv('ENCRYPTION_SECRET')
    if not secret:
        raise TaskFilterUnavailable('task filter cursor signing unavailable')
    return hmac.digest(secret.encode(), b'conversation-task-filter-v1:' + payload, 'sha256')


def _encode(position: _Position, scope: str) -> str:
    payload = json.dumps({'v': 1, 'scope': scope, 'position': position, 'issued': int(time.time())}).encode()
    return base64.urlsafe_b64encode(_sign(payload) + payload).decode().rstrip('=')


def _decode(token: str, scope: str) -> _Position:
    try:
        packed = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        signature, payload = packed[:32], packed[32:]
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError('invalid signature')
        data = json.loads(payload)
        issued = data.get('issued')
        if type(issued) is not int:
            raise ValueError('invalid cursor time')
        age = time.time() - issued
        position = data['position']
        if data.get('v') != 1 or data.get('scope') != scope or not -60 <= age <= 3600:
            raise ValueError('invalid scope/version/expiry')
        if not isinstance(position, dict):
            raise ValueError('invalid position')
        if set(position) == {'after'}:
            if not isinstance(position['after'], str) or len(position['after']) > 3000:
                raise ValueError('invalid browse position')
            return {'after': position['after']}
        elif set(position) == {'page', 'offset'}:
            if type(position['page']) is not int or not 1 <= position['page'] <= 1_000_000:
                raise ValueError('invalid search page')
            if type(position['offset']) is not int or not 0 <= position['offset'] <= 250:
                raise ValueError('invalid search offset')
            return {'page': position['page'], 'offset': position['offset']}
        else:
            raise ValueError('invalid position shape')
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError) as error:
        raise TaskFilterCursorError('invalid or expired task-filter cursor') from error


async def task_conversation_page(
    uid: str,
    filters: TaskConversationPageRequest,
    *,
    budget: ListReadBudget,
    browse_page: Callable[[Optional[str], str], Awaitable[tuple[list[tuple[str, Optional[_Row]]], bool]]],
    search_page: Callable[[int], Awaitable[dict[str, Any]]],
    presence: Callable[[list[str]], Awaitable[dict[str, bool]]],
    can_recover_locked: Callable[[_Row], bool] | None = None,
) -> dict[str, Any]:
    """Filter before pagination, retaining the exact raw position at every stop.

    Sparse matches can require several requests. A bounded intermediate page
    carries a continuation even when empty; no prefix is labelled the full set.
    """
    scope = query_scope({'uid': uid, 'task-filter-v1': filters.model_dump(exclude={'cursor'})})
    searching = bool(filters.query.strip())
    position: Optional[_Position] = (
        _decode(filters.cursor, scope) if filters.cursor else ({'page': 1, 'offset': 0} if searching else None)
    )
    if position and searching != ('page' in position):
        raise TaskFilterCursorError('invalid task-filter cursor kind')
    initial_position = position
    # Validate configuration before any read, even for an empty initial page.
    _sign(b'')
    items: list[_Row] = []
    next_position: Optional[_Position] = position
    try:
        while True:
            budget.check()
            if searching:
                page = position['page'] if position and 'page' in position else 1
                offset = position['offset'] if position and 'offset' in position else 0
                async with asyncio.timeout(budget.remaining_seconds):
                    result = await search_page(page)
                source = result.get('items', [])
                more = result.get('total_pages', page) > page
                candidates: list[tuple[Optional[_Position], Optional[_Row]]] = []
                for index in range(offset, len(source)):
                    after: Optional[_Position] = (
                        {'page': page, 'offset': index + 1}
                        if index + 1 < len(source)
                        else ({'page': page + 1, 'offset': 0} if more else None)
                    )
                    candidates.append((after, source[index]))
                source_next: Optional[_Position] = {'page': page + 1, 'offset': 0} if more else None
            else:
                source, more = await browse_page(position['after'] if position and 'after' in position else None, scope)
                candidates = [({'after': after}, row) for after, row in source]
                source_next = {'after': source[-1][0]} if source and more else None
            budget.check()
            eligible = await run_blocking(
                db_executor, _eligible_rows, candidates, filters, can_recover_locked is not None
            )
            async with asyncio.timeout(budget.remaining_seconds):
                linked = await presence(list(dict.fromkeys(row['id'] for row in eligible))) if eligible else {}
            eligible_ids = {row['id'] for row in eligible}
            for after, row in candidates:
                budget.check()
                matched = row and row.get('id') in eligible_ids and linked.get(row['id']) is True
                if matched and row and row.get('is_locked'):
                    async with asyncio.timeout(budget.remaining_seconds):
                        matched = can_recover_locked is not None and await run_blocking(
                            db_executor, can_recover_locked, row
                        )
                next_position = after
                if matched and row:
                    items.append(row)
                    if len(items) == filters.limit:
                        # At the end of a known terminal raw page there is no
                        # continuation, even if that last row filled the page.
                        if not more and after == candidates[-1][0]:
                            next_position = None
                        return {
                            'items': items,
                            'next_cursor': _encode(next_position, scope) if next_position else None,
                            'partial': False,
                        }
            next_position = source_next
            if source_next is None:
                return {'items': items, 'next_cursor': None, 'partial': False}
            position = source_next
    except (ListReadBudgetExhausted, TimeoutError):
        if next_position is None or (next_position == initial_position and not items):
            # No proven raw progress: retry is honest, an empty success is not.
            raise TaskFilterUnavailable('task filter could not advance within its read budget')
        return {'items': items, 'next_cursor': _encode(next_position, scope), 'partial': True}
