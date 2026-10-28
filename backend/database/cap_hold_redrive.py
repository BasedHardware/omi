"""Rotating discovery of existing durable choices and unfinished live sources.

No intent is manufactured here. A cursor advances even past blocked owners so
repeated bounded pages eventually cover every pre-existing obligation.
"""

import os

from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client

PAGE = 5
# The held population spans millions of rows; fleet aggregations need a budget
# larger than a per-document RPC (a fleet count alone measured ~12 s in prod).
SNAPSHOT_RPC_TIMEOUT_SECONDS = 60.0
# Gauge population. Not the rotating sweep page: the scheduler snapshot counts these.
PENDING_STATES = ('held', 'staging', 'sealing', 'retained')
KINDS = {
    'choices': ('processing_backlog', 'processing'),
    'staging': ('stt_cap_holds', ['staging', 'sealing']),
    'cleanup': ('stt_cap_holds', True),
}


def _snapshot_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return timeout
    try:
        configured = float(os.getenv('CAP_HOLD_FLEET_SNAPSHOT_TIMEOUT_SECONDS', '') or SNAPSHOT_RPC_TIMEOUT_SECONDS)
    except ValueError:
        configured = SNAPSHOT_RPC_TIMEOUT_SECONDS
    return max(1.0, min(configured, 300.0))


def page(kind: str, *, after: str | None = None, firestore_client=None, limit: int | None = None):
    client = firestore_client or get_firestore_client()
    collection, state = KINDS[kind]
    field = 'staging_cleanup' if kind == 'cleanup' else 'state'
    query = client.collection_group(collection).where(
        filter=firestore.FieldFilter(field, 'in' if kind == 'staging' else '==', state)
    )
    query = query.order_by('__name__')
    if after:
        query = query.start_after({'__name__': client.document(after)})
    return list(query.limit(limit or PAGE).stream(timeout=10))


def discover(kind: str, *, limit: int | None = None):
    size = limit or PAGE
    client = get_firestore_client()
    cursor = client.collection('cap_hold_redrive').document(kind)
    after = (cursor.get(timeout=10).to_dict() or {}).get('after')
    rows = page(kind, after=after, firestore_client=client, limit=size)
    # Advance BEFORE awaited work. A killed sweep may revisit this owner on the
    # next rotation; it cannot pin discovery forever on a poison first page.
    cursor.set({'after': rows[-1].reference.path if len(rows) == size else None}, timeout=10)
    return rows


def _aggregation_map(results) -> dict:
    if not results:
        return {}
    row = results[0]
    if not isinstance(row, (list, tuple)):
        row = [row]
    values = {}
    for item in row:
        alias = getattr(item, 'alias', None)
        if alias:
            values[alias] = getattr(item, 'value', 0)
    return values


def _nonnegative(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, float(value))


def fleet_snapshot(firestore_client=None, timeout: float | None = None) -> dict:
    """Authoritative held and backlog totals for one redrive cadence.

    One holds aggregation (count and sum of seconds), one dated-hold count
    (``listed_at`` > 0, same index as the oldest row), one oldest ``limit(1)``,
    and one backlog sum. ``undated_pending`` is the pending count minus that
    dated count: holds with a missing, non-numeric, or non-positive
    ``listed_at``. The scheduler sweep is the only caller. An empty population
    is a real zero, not a missing sample. ``timeout`` bounds each RPC; the
    default is env-configurable because the fleet count outruns a per-document
    budget (a fixed 10 s budget failed every sweep with RetryError).
    """
    client = firestore_client or get_firestore_client()
    budget = _snapshot_timeout(timeout)
    pending = list(PENDING_STATES)
    holds = client.collection_group('stt_cap_holds').where(filter=firestore.FieldFilter('state', 'in', pending))
    totals = _aggregation_map(holds.count(alias='count').sum('seconds', alias='seconds').get(timeout=budget))
    dated_totals = _aggregation_map(
        client.collection_group('stt_cap_holds')
        .where(filter=firestore.FieldFilter('state', 'in', pending))
        .where(filter=firestore.FieldFilter('listed_at', '>', 0))
        .count(alias='dated')
        .get(timeout=budget)
    )
    oldest_rows = list(
        client.collection_group('stt_cap_holds')
        .where(filter=firestore.FieldFilter('state', 'in', pending))
        .where(filter=firestore.FieldFilter('listed_at', '>', 0))
        .order_by('listed_at')
        .limit(1)
        .stream(timeout=budget)
    )
    oldest = None
    if oldest_rows:
        listed = (oldest_rows[0].to_dict() or {}).get('listed_at')
        if not isinstance(listed, bool) and isinstance(listed, (int, float)) and listed > 0:
            oldest = float(listed)
    backlog = _aggregation_map(
        client.collection_group('processing_backlog')
        .where(filter=firestore.FieldFilter('state', '==', 'processing'))
        .sum('count', alias='items')
        .get(timeout=budget)
    )
    pending_count = int(_nonnegative(totals.get('count')))
    dated_count = int(_nonnegative(dated_totals.get('dated')))
    return {
        'pending_count': pending_count,
        'pending_seconds': _nonnegative(totals.get('seconds')),
        'oldest_listed_at': oldest,
        # Two aggregations are not one transaction. A hold that appears only in
        # the dated count cannot make this gauge negative.
        'undated_pending': max(0, pending_count - dated_count),
        'backlog_items': int(_nonnegative(backlog.get('items'))),
    }
