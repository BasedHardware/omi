"""Bounded closed-episode compose recovery on the enrichment maintenance tick.

The cursor lease makes discovery cooperative across replicas. Scheduling remains
only an admission decision: the composer owns freshness, throttling, settling,
its paid-once lease and the final CAS.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from config.episodes import (
    COMPOSER_SWEEP_INTERVAL_SECONDS,
    COMPOSER_SWEEP_MIN_CLOSED_AGE_SECONDS,
    COMPOSER_SWEEP_SCAN_LIMIT,
    COMPOSER_SWEEP_SCHEDULE_LIMIT,
    episode_compose_sweep_enabled,
    episode_composer_enabled,
    episodes_enabled,
)
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_blocks_user_work
from database.episode_compose_sweep_queries import closed_episodes_for_compose_sweep
from database import episodes as episodes_db
from utils.episodes import composer, metrics, policy

CURSOR = 'maintenance/episode_compose_sweep_v1'
logger = logging.getLogger(__name__)


def empty_counts() -> dict[str, int]:
    return {
        'scanned': 0,
        'scheduled': 0,
        'skipped_composed': 0,
        'skipped_inflight': 0,
        'budget_exhausted': 0,
        'errors': 0,
    }


def _record(counts: dict[str, int], outcome: str) -> None:
    counts[outcome] += 1
    metrics.record_compose_sweep(outcome)


def _owner_and_episode_id(snapshot: Any) -> tuple[str, str] | None:
    parts = snapshot.reference.path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == 'episodes' and parts[1] and parts[3]:
        return parts[1], parts[3]
    return None


def tick(*, now: float | None = None, client: Any = None) -> dict[str, int]:
    """Admit at most four stale closed episodes from one newest-first page."""
    counts = empty_counts()
    if not episodes_enabled() or not episode_compose_sweep_enabled() or not episode_composer_enabled():
        return counts
    current = time.time() if now is None else now
    client = client if client is not None else get_firestore_client()
    cursor_ref = client.document(CURSOR)
    owner = uuid.uuid4().hex

    @firestore.transactional
    def claim(transaction: Any) -> dict[str, Any] | None:
        old = cursor_ref.get(transaction=transaction).to_dict() or {}
        if old.get('lease_until', 0) > current or old.get('next_at', 0) > current:
            return None
        transaction.set(
            cursor_ref,
            {
                **old,
                'owner': owner,
                'lease_until': current + COMPOSER_SWEEP_INTERVAL_SECONDS,
                'next_at': current + COMPOSER_SWEEP_INTERVAL_SECONDS,
            },
        )
        return old

    cursor = claim(client.transaction())
    if cursor is None:
        return counts

    page = closed_episodes_for_compose_sweep(limit=COMPOSER_SWEEP_SCAN_LIMIT, after=cursor, firestore_client=client)
    closed_before = datetime.fromtimestamp(current, timezone.utc) - timedelta(
        seconds=COMPOSER_SWEEP_MIN_CLOSED_AGE_SECONDS
    )
    for snapshot in page:
        counts['scanned'] += 1
        identity = _owner_and_episode_id(snapshot)
        if identity is None:
            counts['errors'] += 1
            metrics.record_compose_sweep('error')
            continue
        uid, episode_id = identity
        raw = snapshot.to_dict() or {}
        if raw.get('recorded_merged_into'):
            continue
        try:
            episode = episodes_db.unseal(uid, dict(raw, id=episode_id))
            if not composer.needs_compose(episode):
                _record(counts, 'skipped_composed')
                continue
            closed_at = policy.utc((episode or {}).get('closed_at'))
            if closed_at is None or closed_at > closed_before:
                continue
            if counts['scheduled'] >= COMPOSER_SWEEP_SCHEDULE_LIMIT:
                _record(counts, 'budget_exhausted')
                continue
            if account_deletion_blocks_user_work(uid, firestore_client=client):
                continue
            if composer.schedule(uid, episode_id, throttle=True, foreground=False, deletion_fence=True):
                _record(counts, 'scheduled')
            else:
                # The existing scheduler also returns false for its ten-minute
                # read throttle and an already-deferred settle. Both are in flight.
                _record(counts, 'skipped_inflight')
        except Exception as error:
            # A poison row must not trap the durable cursor. Log no content or ids.
            counts['errors'] += 1
            metrics.record_compose_sweep('error')
            logger.warning('event=episode_compose_sweep outcome=error exception_type=%s', type(error).__name__)

    @firestore.transactional
    def finish(transaction: Any) -> None:
        old = cursor_ref.get(transaction=transaction).to_dict() or {}
        if old.get('owner') != owner:
            return
        last = page[-1] if len(page) == COMPOSER_SWEEP_SCAN_LIMIT else None
        transaction.update(
            cursor_ref,
            {
                'lease_until': 0,
                'path': last.reference.path if last else None,
                'closed_at': (last.to_dict() or {}).get('closed_at') if last else None,
            },
        )

    finish(client.transaction())
    return counts
