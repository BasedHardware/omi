"""Value cursors and bounded two-way merge, independent of Firestore."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Callable

from utils.home_feed.projection import utc

VERSION = 1
KINDS = ('conversation', 'episode')


def encode_cursor(uid: str, state: dict[str, Any], policy: str, secret: bytes) -> str:
    payload = json.dumps(
        {'v': VERSION, 'u': uid, 'p': policy, 's': state}, separators=(',', ':'), sort_keys=True
    ).encode()
    signature = hmac.new(secret, b'omi:home-feed:' + payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + payload).decode().rstrip('=')


def decode_cursor(uid: str, cursor: str | None, policy: str, secret: bytes) -> dict[str, Any]:
    empty = {kind: {'after': None, 'done': False} for kind in KINDS}
    if cursor is None:
        return empty
    try:
        if len(cursor) > 4096:
            raise ValueError()
        raw = base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True)
        signature, payload = raw[:32], raw[32:]
        expected = hmac.new(secret, b'omi:home-feed:' + payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        value = json.loads(payload)
        if value['v'] != VERSION or value['u'] != uid or value['p'] != policy:
            raise ValueError()
        state = value['s']
        if set(state) != set(KINDS):
            raise ValueError()
        for frontier in state.values():
            if set(frontier) != {'after', 'done'} or type(frontier['done']) is not bool:
                raise ValueError()
            after = frontier['after']
            if after is not None:
                if not isinstance(after, list) or len(after) != 2 or not isinstance(after[1], str) or not after[1]:
                    raise ValueError()
                stamp = datetime.fromisoformat(after[0])
                if stamp.tzinfo is None:
                    raise ValueError()
        return state
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError('Invalid Home feed cursor') from None


def key(row: dict[str, Any], kind: str) -> tuple[datetime, str, str]:
    stamp = utc(row['home_sort_at'])
    assert stamp is not None
    return stamp, kind, row['id']


def merge_page(
    state: dict[str, Any],
    fetch: Callable[[str, Any, int], list[dict[str, Any]]],
    project: Callable[[str, dict[str, Any]], dict[str, Any] | None],
    *,
    limit: int,
    scan_limit: int = 256,
    byte_limit: int = 262144,
    batch_size: int = 32,
) -> tuple[list[dict[str, Any]], bool, bool]:
    """Advance only CONSUMED source values, never a prefetched frontier.

    Prefetched but unused candidates are queried again next page. This bounds
    cursor size without skipping the losing stream or relying on anchor docs.
    An exhausted budget keeps every unconsumed frontier, even on an empty page.
    """
    buffers: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    exhausted = {kind: bool(state[kind]['done']) for kind in KINDS}
    items: list[dict[str, Any]] = []
    scanned, fetched, used = 0, 0, 0
    budget_blocked = False
    while len(items) < limit and scanned < scan_limit:
        for kind in KINDS:
            if not buffers[kind] and not exhausted[kind]:
                size = min(batch_size, limit - len(items) + 1, scan_limit - fetched)
                if size <= 0:
                    budget_blocked = True
                    break
                rows = fetch(kind, state[kind]['after'], size)
                fetched += len(rows)
                buffers[kind] = rows
                exhausted[kind] = len(rows) < size
                if not rows:
                    state[kind]['done'] = True
        if budget_blocked:
            break
        candidates = [(key(rows[0], kind), kind) for kind, rows in buffers.items() if rows]
        if not candidates:
            break
        _, kind = max(candidates)
        row = buffers[kind][0]
        item = project(kind, row)
        item_bytes = len(json.dumps(item, default=str, ensure_ascii=False).encode()) if item else 0
        if items and used + item_bytes > byte_limit:
            break
        # Consume skipped rows too, so sparse pages make bounded progress.
        buffers[kind].pop(0)
        state[kind]['after'] = [row['home_sort_at'].isoformat(), row['id']]
        if not buffers[kind] and exhausted[kind]:
            state[kind]['done'] = True
        scanned += 1
        if item:
            items.append(item)
            used += item_bytes
    has_more = any(not state[kind]['done'] for kind in KINDS)
    truncated = has_more and len(items) < limit
    return items, has_more, truncated
