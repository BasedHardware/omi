"""One page of historical index work per ordering, owned by a cursor request."""

from typing import Any
from google.api_core.datetime_helpers import DatetimeWithNanoseconds

from utils.memory.index_window_cursor import decode_cursor, encode_cursor, query_scope


class MemoryIndexWindowLimit(Exception):
    """A resumable raw window ended before the visible page filled."""

    def __init__(self, lower_bound: tuple[int, str] | None = None):
        super().__init__()
        self.lower_bound = lower_bound


def position_cursor(uid: str, kind: str, position: tuple) -> str:
    field = 'updated_at' if kind == 'updated' else 'created_at'
    return encode_cursor(position[0], position[1], query_scope({'uid': uid, 'order': field}))


def validate_window_cursors(state: Any, uid: str) -> None:
    for keyset, field in ((state.historical_updated_scan, 'updated_at'), (state.historical_created_scan, 'created_at')):
        if keyset is not None:
            if keyset.index_window_cursor is None:
                raise ValueError('legacy cursor has no exact index-window position')
            decode_cursor(keyset.index_window_cursor, query_scope({'uid': uid, 'order': field}))


def _position_sort_key(stamp: Any, memory_id: str) -> tuple[int, str]:
    if isinstance(stamp, DatetimeWithNanoseconds):
        value = stamp.timestamp_pb()
        return (-(value.seconds * 1_000_000_000 + value.nanos), memory_id)
    return (-(int(stamp.replace(microsecond=0).timestamp()) * 1_000_000_000 + stamp.microsecond * 1000), memory_id)


def window_sort_key(memory: Any) -> tuple[int, str]:
    return _position_sort_key(memory.updated_at or memory.created_at, memory.id)


def peek_index_window(stream: Any):
    """Return a head or a lower bound on every unscanned row in this source.

    Once a raw window ends, another source's newer heads are safe to emit:
    no unseen row can precede the last consumed raw position. In particular,
    a created window consisting entirely of updated-stream duplicates must
    not block an otherwise full updated page.
    """
    try:
        return stream.peek(), None
    except MemoryIndexWindowLimit:
        stamp, memory_id = decode_cursor(stream.scan_keyset.index_window_cursor, query_scope(stream.window_scope))
        return None, _position_sort_key(stamp, memory_id)
