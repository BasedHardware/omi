"""Thirty-second metadata cache for acknowledged Home lists only.

Firestore remains authoritative. Never cache speech-derived content, refresh on
hits, or use this answer for pending-work, detail, membership writes or leases.
"""

import json
import logging
import math
import time
from datetime import datetime
from typing import Callable

from prometheus_client import Counter

from database import redis_db
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
TTL_SECONDS = 30
_FIELDS = ('id', 'status', 'conversation_ids', 'started_at', 'last_activity_at')
LOOKUPS = Counter(
    'omi_home_live_owner_lookups_total',
    'Eligible acknowledged Home-list owner lookups by serving source; no user labels',
    ['source'],
)


_client = None


def _redis():
    """Bounded client (0.1 s connect and read): a stall fails open to Firestore, never hangs the Home request."""
    global _client
    if _client is None:
        _client = redis_db.create_bounded_redis_client(0.1)
    return _client


def _redis_error(error: Exception) -> None:
    record_fallback(component='firestore_read', from_mode='redis', to_mode='none', reason='other', outcome='recovered')
    logger.warning('event=home_live_owner_cache outcome=firestore exception_type=%s', type(error).__name__)


def read(uid: str, fetch: Callable[[], dict | None], *, enabled: bool = True) -> dict | None:
    def fresh():
        LOOKUPS.labels(source='firestore').inc()
        return fetch()

    if not enabled:
        return fresh()
    key = f'episodes:home_live_owner:v1:{uid}'
    try:
        raw = _redis().get(key)
        if raw is not None:
            cached = json.loads(raw)
            deadline = cached['valid_until']
            owner = cached['owner']
            valid = owner is None or (
                isinstance(owner, dict)
                and isinstance(owner.get('id'), str)
                and bool(owner['id'])
                and owner.get('status') == 'live'
                and isinstance(owner.get('conversation_ids'), list)
                and all(isinstance(cid, str) for cid in owner['conversation_ids'])
            )
            remaining = deadline - time.time()
            if valid and math.isfinite(remaining) and 0 < remaining <= TTL_SECONDS:
                LOOKUPS.labels(source='cache').inc()
                return owner
    except Exception as error:
        _redis_error(error)
        return fresh()

    # Start the freshness window before Firestore: a slow read/SET or delayed
    # concurrent writer must not give an old snapshot another thirty seconds.
    deadline = time.time() + TTL_SECONDS
    owner = fresh()
    try:
        metadata = None
        if owner is not None:
            metadata = {name: owner.get(name) for name in _FIELDS}
            metadata['conversation_ids'] = owner.get('conversation_ids') or []
            for name in ('started_at', 'last_activity_at'):
                value = metadata[name]
                if isinstance(value, datetime):
                    metadata[name] = value.isoformat()
        if time.time() < deadline:
            _redis().set(key, json.dumps({'valid_until': deadline, 'owner': metadata}), ex=TTL_SECONDS, nx=True)
    except Exception as error:
        _redis_error(error)
    return owner
