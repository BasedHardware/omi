"""Exact per-stock counts and oldest-age readings for the batch census registry.

One pass over ``config.batch_census.ENTRIES``: each stock costs one ``count()``
aggregation and, when the entry has a clock, at most one oldest-row projection
read of that clock field. No document content, transcript, audio reference, uid
or email is read: the oldest read selects only the clock path.

A failure on one stock is isolated. The caller publishes the stocks that
succeeded and counts the failures; a stock that never sampled has no series, so
it can never read as a healthy zero.

This module never writes to Firestore, never transitions state and never creates
an index. Scheduled execution is the only caller.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from config.batch_census import COLLECTION_GROUP, COLLECTIONS, AgeCutoff, CensusEntry

logger = logging.getLogger(__name__)
DEFAULT_RPC_TIMEOUT_SECONDS = 60.0
MAX_RPC_TIMEOUT_SECONDS = 300.0
MAX_WORKERS = 4


@dataclass(frozen=True)
class StockSample:
    """One stock's fleet reading. ``oldest_at`` is None when no row carries the clock."""

    units: int
    oldest_at: float | None


def enabled() -> bool:
    return os.getenv('BATCH_CENSUS_EXPORT_ENABLED', 'true').strip().lower() not in {
        '0',
        'false',
        'off',
        'no',
        'disabled',
    }


def rpc_timeout_seconds() -> float:
    try:
        configured = float(os.getenv('BATCH_CENSUS_SNAPSHOT_TIMEOUT_SECONDS', '') or DEFAULT_RPC_TIMEOUT_SECONDS)
    except ValueError:
        configured = DEFAULT_RPC_TIMEOUT_SECONDS
    if not math.isfinite(configured):
        configured = DEFAULT_RPC_TIMEOUT_SECONDS
    return max(1.0, min(configured, MAX_RPC_TIMEOUT_SECONDS))


def collection_names(entry: CensusEntry) -> tuple[str, ...]:
    return COLLECTIONS[entry.collection]


def _scope(client: Any, entry: CensusEntry, name: str) -> Any:
    return client.collection_group(name) if entry.scope == COLLECTION_GROUP else client.collection(name)


def _resolved(value: object, now: float) -> object:
    return now - value.seconds if isinstance(value, AgeCutoff) else value


def _in_values(value: object) -> list[Any]:
    """A declared ``in`` filter is a literal sequence; anything else is one value."""
    if isinstance(value, (tuple, list, set, frozenset)):
        return list(value)
    return [value]


def _filtered(query: Any, entry: CensusEntry, now: float) -> Any:
    for field, operator, value in entry.filters:
        if operator == 'in':
            query = query.where(filter=FieldFilter(field, 'in', _in_values(value)))
        else:
            query = query.where(filter=FieldFilter(field, operator, _resolved(value, now)))
    return query


def _epoch(value: object) -> float | None:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def sample_entry(client: Any, entry: CensusEntry, *, now: float, timeout: float) -> StockSample:
    """Count and oldest clock for one stock across its stage-scoped collections."""
    units = 0
    oldest: float | None = None
    for name in collection_names(entry):
        query = _filtered(_scope(client, entry, name), entry, now)
        units += int(query.count().get(timeout=timeout)[0][0].value)
        if not entry.clock:
            continue
        # Projection read: the clock field only, never document content.
        rows = list(query.select([entry.clock]).order_by(entry.clock).limit(1).stream(timeout=timeout))
        if not rows:
            continue
        moment = _epoch((rows[0].to_dict() or {}).get(entry.clock))
        # A malformed clock is not a measured age; the sentinel covers it.
        if moment is not None:
            oldest = moment if oldest is None else min(oldest, moment)
    return StockSample(units=max(0, units), oldest_at=oldest)


__all__ = [
    'StockSample',
    'collection_names',
    'enabled',
    'rpc_timeout_seconds',
    'sample_entry',
]
