"""Content-free projection handoff; imports and producers use only the standard library.

The composer task drains this bounded process-local queue. Assignment remains
the durable authority; existing member metadata/Home recovery covers a restart
or overflow, as it does for the composer's process-local settle queue.
"""

from collections import OrderedDict
from collections.abc import Mapping
import logging
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)
MAX_PENDING = 10_000
_pending: OrderedDict[tuple[str, str], Any] = OrderedDict()
_lock = Lock()
_dropped = 0


def enqueue(uid: str, row: Mapping[str, Any], *, firestore_client: Any = None) -> bool:
    """Coalesce IDs only. No reads, provider calls, threads or composer imports."""
    global _dropped
    accepted = True
    for member in [row, *(part for part, _ in row.get('_sync_size_rollover_rows', []))]:
        cid = member.get('id')
        if not uid or not cid:
            continue
        key = (uid, str(cid))
        with _lock:
            if key not in _pending and len(_pending) >= MAX_PENDING:
                _dropped += 1
                accepted = False
            else:
                _pending[key] = firestore_client
    if not accepted:
        logger.warning('event=episode_transcript_receipt outcome=capacity_full')
    return accepted


def take(limit: int = 32) -> list[tuple[str, str, Any]]:
    """Transfer a bounded batch to the composer's worker, never the projection thread."""
    with _lock:
        return [
            (*key, client) for key, client in (_pending.popitem(last=False) for _ in range(min(limit, len(_pending))))
        ]


def take_dropped() -> int:
    global _dropped
    with _lock:
        count, _dropped = _dropped, 0
    return count
