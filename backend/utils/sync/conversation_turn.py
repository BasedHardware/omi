"""At most one fresh-lane job persists into one user's conversation at a time.

Concurrent fresh jobs for one conversation each ran the sync assignment
transaction and the bridge audio copy against the same documents and object
names, which surfaced as FirestoreContentionExhausted and GCS per-object 429s.
This turn reuses the sync run lock's Redis compare-and-delete lease (no new
store) around persistence and finalize only; STT stays parallel. It is a
throughput guard, not a correctness lock: the assignment transaction remains
authoritative, so a wait timeout or an unavailable Redis proceeds unserialized.
Backfill already runs one job per UID through the UID sequencer.

Kill switch: ``SYNC_FRESH_CONVERSATION_TURN=off``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from database.redis_db import r
from utils.metrics import OMI_SYNC_FRESH_CONVERSATION_TURN_TOTAL
from utils.sync import stage as sync_stage

logger = logging.getLogger(__name__)

KEY_PREFIX = 'sync_fresh_conversation_turn:'
# Persistence plus bridge finalize normally takes seconds. The TTL bounds a dead
# holder; the wait bounds how long a sync_executor thread may sit idle.
TURN_TTL_SECONDS = 90
TURN_WAIT_SECONDS = 15.0
_POLL_SECONDS = 0.2

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class ConversationTurn:
    key: str
    token: str


def enabled() -> bool:
    return os.getenv('SYNC_FRESH_CONVERSATION_TURN', 'on').strip().lower() not in {'off', 'false', '0'}


def turn_key(uid: str, conversation_id: str | None) -> str:
    # Hash so neither the uid nor the conversation id appears in the keyspace.
    digest = hashlib.sha256(f'{uid}:{conversation_id or ""}'.encode()).hexdigest()[:32]
    return sync_stage.redis_key(f'{KEY_PREFIX}{digest}')


def acquire(
    uid: str,
    conversation_id: str | None,
    lane: str,
    *,
    wait_seconds: float = TURN_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> ConversationTurn | None:
    """Wait for this conversation's fresh turn; ``None`` means proceed unserialized.

    A new conversation (no candidate yet) takes no turn: a uid-wide key would
    serialize every new capture for the user.
    """
    if lane != 'fresh' or not conversation_id or not enabled():
        return None
    token = uuid.uuid4().hex
    deadline = clock() + wait_seconds
    waited = False
    try:
        key = turn_key(uid, conversation_id)
        while not r.set(key, token, nx=True, ex=TURN_TTL_SECONDS):
            if clock() >= deadline:
                OMI_SYNC_FRESH_CONVERSATION_TURN_TOTAL.labels(outcome='timeout').inc()
                logger.warning('event=sync_fresh_conversation_turn outcome=timeout')
                return None
            waited = True
            sleep(_POLL_SECONDS + random.random() * _POLL_SECONDS)
    except Exception as error:
        OMI_SYNC_FRESH_CONVERSATION_TURN_TOTAL.labels(outcome='unavailable').inc()
        logger.warning('event=sync_fresh_conversation_turn outcome=unavailable exception_type=%s', type(error).__name__)
        return None
    OMI_SYNC_FRESH_CONVERSATION_TURN_TOTAL.labels(outcome='waited' if waited else 'acquired').inc()
    return ConversationTurn(key, token)


def release(turn: ConversationTurn | None) -> None:
    """Best-effort compare-and-delete; on failure the TTL frees the turn."""
    if turn is None:
        return
    try:
        r.eval(_RELEASE_SCRIPT, 1, turn.key, turn.token)
    except Exception as error:
        logger.warning(
            'event=sync_fresh_conversation_turn outcome=release_failed exception_type=%s', type(error).__name__
        )
