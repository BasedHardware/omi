"""Versioned raw-query projections; released read policy always runs afterwards.

The content-free head is authoritative for invalidation, never for access.
No head is cached. Missing coverage/head, bulk writers, faults and churn all
retain the existing query/lever path. A complete fill is published only if
its before/after heads match. No scan, backfill, polling cap or Redis is added.
"""

import copy
import functools
import hashlib
import os
import sys
import threading
import time
from collections import OrderedDict
from typing import Any, cast

from prometheus_client import REGISTRY, Counter

from database.firestore_read_origin import current_read_origin, read_origin
from database.memory_collections import RELEASED_MEMORY_CHANGE_HEAD as HEAD_DOCUMENT
from utils.observability.fallback import record_fallback
from utils.other.list_budget import (
    ListReadBudgetExhausted,
    budgeted_document_get,
    budgeted_stream_iter,
    budgeted_stream_list,
)


def _projection_events_counter() -> Counter:
    # Reuse the collector and its counts after import-isolated module eviction.
    try:
        return Counter(
            'omi_memory_released_projection_total',
            'Versioned released memory raw-query projection outcomes.',
            ['surface', 'outcome', 'origin'],
        )
    except ValueError:
        return cast(
            Counter,
            REGISTRY._names_to_collectors['omi_memory_released_projection_total'],  # type: ignore[attr-defined]
        )


EVENTS = _projection_events_counter()
SURFACES = frozenset({'canonical_scan', 'historical_scan', 'list_window', 'status_pairs', 'mcp_cards'})
MAX_ENTRIES = 128
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 2 * 1024 * 1024
TTL_SECONDS = 60
MIN_CACHE_ROWS = 3
_lock = threading.Lock()
_entries: OrderedDict[Any, Any] = OrderedDict()
_small_queries: OrderedDict[Any, Any] = OrderedDict()
_bytes = 0


def enabled() -> bool:
    coverage = os.environ.get('MEMORY_RELEASED_WRITERS_COVERED', '')
    return (
        os.environ.get('MEMORY_RELEASED_PROJECTION', '').strip().lower() not in {'off', 'false', '0', 'no'}
        and coverage.startswith('v1:')
        and bool(coverage[3:].strip())
    )


def _head(client: Any, uid: str, budget: Any, *, conversations: bool = False) -> str | None:
    path = (
        f'users/{uid}/list_serving_versions/conversations'
        if conversations
        else f'users/{uid}/memory_state/{HEAD_DOCUMENT}'
    )
    with read_origin('job:released_memory_projection'):
        reference = client.document(path)
        snap = (
            budgeted_document_get(reference, budget) if budget is not None else reference.get(timeout=1.0, retry=None)
        )
    if not getattr(snap, 'exists', False) and budget is not None:
        budget.charge(1)  # Missing head reads are billed too.
    data = snap.to_dict() if getattr(snap, 'exists', False) else {}
    if not isinstance(data, dict) or data.get('blocked') is not None:
        return None
    if conversations:
        version = data.get('version')
        return version if isinstance(version, str) and len(version) == 32 else None
    if data.get('schema') != 1:
        return None
    token = data.get('token')
    return token if isinstance(token, str) and token else None


def _pack(snapshots: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            'path': snap.reference.path,
            'id': snap.id,
            'data': snap.to_dict(),
            'exists': snap.exists,
            'read_time': snap.read_time,
            'create_time': snap.create_time,
            'update_time': snap.update_time,
        }
        for snap in snapshots
    ]


def _unpack(client: Any, records: Any) -> list[Any]:
    from google.cloud.firestore_v1.base_document import DocumentSnapshot

    return [
        DocumentSnapshot(
            reference=client.document(row['path']),
            data=row['data'],
            exists=row['exists'],
            read_time=row['read_time'],
            create_time=row['create_time'],
            update_time=row['update_time'],
        )
        for row in records
    ]


def _prune(now: float) -> None:
    global _bytes
    for key in list(_entries):
        if _entries[key][0] <= now:
            _bytes -= _entries.pop(key)[2]


def _source_read(query: Any, budget: Any) -> list[Any]:
    # Only cold/fallback queries incur Firestore's billed offset skips. MCP
    # callers formerly charged this before querying, which overcharged hits.
    offset = getattr(query, '_offset', 0)
    if budget is not None and isinstance(offset, int) and offset > 0:
        budget.charge(offset)
    return budgeted_stream_list(query, budget)


def projected_stream_list(query: Any, budget: Any = None, *, surface: str, _source: Any = None) -> list[Any]:
    """Reuse only exact, complete raw query snapshots under a fresh atomic head.

    Transactional and unknown query shapes never participate. Cache hits still
    check the request deadline, and charge only their actual head RPCs. Source
    query exceptions retain their original type/partial-snapshot semantics.
    """
    global _bytes
    source = _source or _source_read
    if surface not in SURFACES:
        raise ValueError('unregistered released memory projection surface')
    metric = EVENTS.labels(surface=surface, outcome='bypass', origin=current_read_origin())
    # Do not spend the last source-row allowance on an incomplete head pair.
    if not enabled() or (budget is not None and budget.remaining_documents < 2):
        metric.inc()
        return source(query, budget)
    try:
        client = query._client
        parent = list(query._parent._path)
        conversations = len(parent) == 3 and parent[2] == 'conversations' and surface == 'mcp_cards'
        card_coverage = bool(os.environ.get('OMI_LIST_VERSION_EPOCH', '').strip()) and os.environ.get(
            'OMI_LIST_PROJECTION_WRITER_ENABLED', 'true'
        ).strip().lower() not in {'0', 'false', 'off'}
        eligible = (
            len(parent) == 3
            and parent[0] == 'users'
            and (
                parent[2] in {'memories', 'memory_items', 'memory_historical_overrides'}
                or (conversations and card_coverage)
            )
        )
        shape = None
        if eligible:
            structured = query._to_protobuf()
            query_bytes = type(structured).serialize(structured)
            shape = (
                id(client),
                client._database_string,
                os.environ.get('MEMORY_RELEASED_WRITERS_COVERED'),
                os.environ.get('OMI_LIST_VERSION_EPOCH') if conversations else None,
                '/'.join(parent),
                hashlib.sha256(query_bytes).digest(),
            )
    except Exception:
        _unavailable(surface)
        return source(query, budget)
    if shape is None:
        metric.inc()
        return source(query, budget)
    with _lock:
        small = _small_queries.get(shape, (0, None))[0] > time.monotonic()
    if small:
        metric.inc()
        return source(query, budget)
    try:
        uid = parent[1]
        before = _head(client, uid, budget, conversations=conversations)
    except ListReadBudgetExhausted:
        raise
    except Exception:
        _unavailable(surface)
        return source(query, budget)
    if before is None:
        metric.inc()
        return source(query, budget)
    key = (*shape, before)
    with _lock:
        _prune(time.monotonic())
        entry = _entries.get(key)
        # SDK datetime subclasses carry nanoseconds outside deepcopy's state.
        # Keep immutable revision timestamps; copy only payload containers.
        cached = [{**row, 'data': copy.deepcopy(row['data'])} for row in entry[1]] if entry else None
        if entry:
            _entries.move_to_end(key)
    if cached is not None:
        try:
            if _head(client, uid, budget, conversations=conversations) == before:
                EVENTS.labels(surface=surface, outcome='hit', origin=current_read_origin()).inc()
                return _unpack(client, cached)
        except ListReadBudgetExhausted:
            raise
        except Exception:
            _unavailable(surface)
        else:
            EVENTS.labels(surface=surface, outcome='changed', origin=current_read_origin()).inc()
        return source(query, budget)

    # Query errors and partial results must never be cached or swallowed.
    snapshots = source(query, budget)
    EVENTS.labels(surface=surface, outcome='miss', origin=current_read_origin()).inc()
    if len(snapshots) < MIN_CACHE_ROWS:
        # Two head reads cannot beat a <=2-document query. This hint bypasses
        # reuse, never authority, and therefore need not be invalidated.
        with _lock:
            _small_queries[shape] = (time.monotonic() + TTL_SECONDS, client)
            while len(_small_queries) > MAX_ENTRIES:
                _small_queries.popitem(last=False)
        return snapshots
    try:
        if _head(client, uid, budget, conversations=conversations) != before:
            EVENTS.labels(surface=surface, outcome='changed', origin=current_read_origin()).inc()
            return snapshots
        records = _pack(snapshots)
        # The size bound includes Python containers, timestamps and byte payloads.
        size = _size(records)
        if size > MAX_ENTRY_BYTES:
            EVENTS.labels(surface=surface, outcome='oversized', origin=current_read_origin()).inc()
            return snapshots
        with _lock:
            _prune(time.monotonic())
            previous = _entries.pop(key, None)
            if previous:
                _bytes -= previous[2]
            while _entries and (len(_entries) >= MAX_ENTRIES or _bytes + size > MAX_BYTES):
                _bytes -= _entries.popitem(last=False)[1][2]
            # Retain the client with the entry so object id reuse cannot cross
            # credential/client boundaries before expiration.
            _entries[key] = (time.monotonic() + TTL_SECONDS, records, size, client)
            _bytes += size
    except ListReadBudgetExhausted:
        # The source scan completed; a failed optional publication cannot turn
        # that complete page into truncation. The budget remains exhausted.
        return snapshots
    except Exception:
        _unavailable(surface)
    return snapshots


def projected_stream_iter(query: Any, budget: Any = None, *, surface: str, offset_reads: int | None = None) -> Any:
    """Preserve MCP's verified partial prefix when a bounded stream times out."""
    try:
        snapshots = projected_stream_list(
            query,
            budget,
            surface=surface,
            _source=functools.partial(_source_iter_read, offset_reads=offset_reads),
        )
    except ListReadBudgetExhausted as exc:
        yield from getattr(exc, 'partial_snapshots', [])
        raise
    yield from snapshots


def _source_iter_read(query: Any, budget: Any, *, offset_reads: int | None = None) -> list[Any]:
    offset = getattr(query, '_offset', 0) if offset_reads is None else offset_reads
    if budget is not None and isinstance(offset, int) and offset > 0:
        budget.charge(offset)
    snapshots = []
    try:
        for snapshot in budgeted_stream_iter(query, budget):
            snapshots.append(snapshot)
    except ListReadBudgetExhausted as exc:
        setattr(exc, 'partial_snapshots', snapshots)
        raise
    return snapshots


def _size(value: Any) -> int:
    # No pickle/serialization of user-controlled objects. Payloads are SDK data.
    seen: set[int] = set()

    def size(item: Any) -> int:
        if id(item) in seen:
            return 0
        seen.add(id(item))
        total = sys.getsizeof(item)
        if isinstance(item, dict):
            total += sum(size(k) + size(v) for k, v in item.items())
        elif isinstance(item, (tuple, list)):
            total += sum(size(v) for v in item)
        return total

    return size(value)


def _unavailable(surface: str) -> None:
    EVENTS.labels(surface=surface, outcome='unavailable', origin=current_read_origin()).inc()
    record_fallback(
        component='firestore_read',
        from_mode='released_projection',
        to_mode='query',
        reason='other',
        outcome='recovered',
    )
