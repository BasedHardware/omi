"""Content-free signal for routed-domain Firestore access by cell owners."""

import logging
from typing import Any, Literal

from prometheus_client import Counter

from database.firestore_read_origin import current_read_origin
from database.memory_collections import MemoryCollections
from utils.log_sanitizer import hash_log_identifier
from utils.other import plane_routing

logger = logging.getLogger(__name__)
PLANE_LEAK = Counter(
    'plane_leak_total',
    'Routed-domain Firestore reads and committed writes for cell owners.',
    ['op', 'collection', 'origin'],
)
# W5 domains only. Descendants use their owning domain's bounded label; memory head
# documents (memory_state/...) are covered through the canonical catalog below.
ROUTED_COLLECTIONS = frozenset(
    {
        'conversations',
        'memories',
        'memory_control',
        'action_items',
        'goals',
        'workstreams',
        'messages',
        'chat_messages',
        'chat_sessions',
    }
) | frozenset(path.split('/')[2] for path in MemoryCollections(uid='').all_collection_paths())


def record_plane_leak(path_parts: Any, op: Literal['read', 'write'], amount: float = 1) -> None:
    """Observe an access without changing its outcome. No work while routing is off."""
    try:
        if not plane_routing.has_cell_plane():
            return
        parts = tuple(path_parts or ())
        if len(parts) < 3 or parts[0] != 'users' or parts[2] not in ROUTED_COLLECTIONS:
            return
        if plane_routing.plane_for(parts[1]) != 'cell':
            return
        collection = parts[2]
        origin = current_read_origin()
        PLANE_LEAK.labels(op=op, collection=collection, origin=origin).inc(amount)
        logger.warning(
            'event=plane_leak op=%s collection=%s origin=%s uid_hash=%s',
            op,
            collection,
            origin,
            hash_log_identifier(parts[1]),
        )
    except Exception:
        pass  # Telemetry must never change the result of a read or committed write.
