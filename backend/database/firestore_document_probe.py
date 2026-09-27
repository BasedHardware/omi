"""Collection-level accounting for every Firestore document read.

Cloud Monitoring's ``firestore.googleapis.com/document/read_count`` carries no
collection or caller dimension for server SDKs (``module="__unknown__"``), so a
read-volume regression is visible in the bill but not attributable. This probe
wraps the SDK methods that issue a read RPC. Methods that only delegate
(``Query.get`` → ``Query.stream``, ``Transaction.get`` → ``Client.get_all`` or
``Query.stream``, and the collection/async twins of those) are left alone:
wrapping them would count the same read twice.

Billing assumptions (Cloud Firestore Standard pricing, encoded here, not measured
per call):

* One read per document a lookup or query yields, including a NOT_FOUND lookup.
* A query that yields nothing bills one read. The same floor is applied when the
  caller closes the stream early or the stream raises before the first document.
  A transport failure that never reached Firestore is therefore over-counted by
  one; that is accepted so a dropped stream cannot hide a billed read.
* An ``offset`` is added once per query. Pricing charges one read per skipped
  document. The SDK does not say how many documents actually existed, so the
  configured offset is the count. A short collection over-states that offset.
* Aggregation ``count()`` bills one read per batch of up to 1000 index entries.
  The count value is treated as that entry count (the pricing-page example).
  ``sum()`` / ``avg()`` values are not entry counts; those bill the one-read
  minimum because the SDK does not expose entries read. Query Explain would,
  and turning it on changes the RPC, so it is not enabled.
* Queries with two or more range fields, and kNN vector search, also bill index
  entries the stream does not report. Those reads stay outside this probe.
* ``list_documents`` bills one read per yielded document name (a keys-only
  query), plus the empty-query minimum. ``DocumentReference.collections`` is
  ListCollectionIds: one read per RPC, not per id. ``get_partitions`` is not
  itemized on the pricing page; one read per yielded partition, else the
  one-read minimum. Product code does not call ``get_partitions``.
* Explain is not its own method on google-cloud-firestore 2.20.0. It is the
  ``explain_options`` argument of ``get`` / ``stream``. Explain-only (analyze
  off) yields no documents and bills one read, which the empty floor covers.
  Analyze bills the query itself and is counted from the documents yielded.

The class patch is installed when ``database._client`` is imported, before any
client is constructed. It patches the SDK classes, so every client created in
that process is covered, including a later ``firestore.Client()``. A process
that never imports ``database._client`` is not covered.

Cardinality: collection patterns are an allowlist (anything else is ``other``).
The caller label is ``module:function`` from the first product frame on the
stack. Plumbing frames (this probe, ``database._client``, ``database.helpers``,
``database.read_boundary``, ``utils.other.list_budget``, ``utils.executors``,
and ``google`` / ``asyncio`` / ``threading`` / ``contextlib`` /
``concurrent``) are skipped. The label matches a fixed grammar. At most
``MAX_CALLERS`` distinct values are kept; a later new label is ``other`` and
``omi_firestore_caller_label_overflow_total`` increments, so a full set is
visible instead of a silent collapse. No uid, document id, or query text is a
label. Recording never raises.
"""

from __future__ import annotations

import inspect
import logging
import math
import re
import threading
from typing import Any, Callable

from prometheus_client import Counter

from database.firestore_tier_context import current_tier

logger = logging.getLogger(__name__)

__all__ = [
    'FIRESTORE_BILLED_READS',
    'FIRESTORE_BILLED_READS_BY_CALLER',
    'FIRESTORE_CALLER_LABEL_OVERFLOW',
    'FIRESTORE_DOCUMENT_READS',
    'FIRESTORE_QUERY_OPERATIONS',
    'MAX_CALLERS',
    'SDK_READ_SURFACE',
    'bound_caller',
    'collection_pattern',
    'install_document_read_probe',
]


FIRESTORE_DOCUMENT_READS = Counter(
    'omi_firestore_document_reads_total',
    'Firestore document reads by collection pattern, outcome, and request-owner tier. '
    'outcome="hit" is a returned document, "miss" is a billed lookup or count that matched nothing, '
    'and "floor" is a billed read with no document (empty query, offset skip, or collection-id list). '
    'Pair with omi_firestore_billed_reads_total for the Cloud Monitoring type split.',
    ['collection', 'outcome', 'tier'],
)


FIRESTORE_QUERY_OPERATIONS = Counter(
    'omi_firestore_query_operations_total',
    'Firestore RunQuery operations by collection pattern and request-owner tier. '
    'One operation per stream, including streams closed early. Not itself a document-read count.',
    ['collection', 'tier'],
)


# Coverage numerator. ``kind`` maps onto firestore.googleapis.com/document/read_count's
# ``type`` label: lookup → LOOKUP, not_found → NOT_FOUND, query → QUERY.
# Aggregations, vector search, list_documents, partitions, offsets, and the empty
# minimum are QUERY. Do not add this counter to omi_firestore_document_reads_total.
FIRESTORE_BILLED_READS = Counter(
    'omi_firestore_billed_reads_total',
    'Billed-equivalent Firestore reads by collection, kind, and request-owner tier. '
    'kind is lookup, not_found, or query. This is the coverage numerator against '
    'stackdriver_firestore_instance_firestore_googleapis_com_document_read_count.',
    ['collection', 'kind', 'tier'],
)


# Same reads, split by calling module:function so a DATA_READ-style question is
# answerable without an audit log. No tier label: tier stays on the counter above.
FIRESTORE_BILLED_READS_BY_CALLER = Counter(
    'omi_firestore_billed_reads_by_caller_total',
    'Billed-equivalent Firestore reads by collection, kind, and bounded call site. '
    'caller is module:function or other. Distinct caller values are capped; '
    'overflow increments omi_firestore_caller_label_overflow_total.',
    ['collection', 'kind', 'caller'],
)


# Increments when a well-formed new caller is folded to ``other`` because the
# cap is full. Invalid labels do not increment it. A non-zero rate means the
# by-caller counter is no longer naming every product frame.
FIRESTORE_CALLER_LABEL_OVERFLOW = Counter(
    'omi_firestore_caller_label_overflow_total',
    'Firestore read caller labels dropped because the bounded caller set is full.',
)


# Firestore bills an aggregation one read per batch of up to this many index
# entries, not one read per matched document. count() values are treated as the
# index-entry count. See the module docstring for sum/avg.
_AGGREGATION_INDEX_ENTRIES_PER_READ = 1000

# AST scan of backend/database and backend/utils on 2026-09-23 found 921
# functions whose body calls a Firestore read (stream, get_all, list_documents,
# collections, get_partitions, on_snapshot, find_nearest, a document-shaped
# .get(), or .count()). 1536 is that count plus headroom for routers, services,
# and new call sites. The set is filled on first observation, not pre-created.
MAX_CALLERS = 1536

_CALLER_RE = re.compile(r'^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*){0,6}:[A-Za-z_][A-Za-z0-9_]{0,60}$')
_PLUMBING_MODULES = frozenset(
    {
        'database._client',
        'database.read_boundary',
        'database.helpers',
        'utils.other.list_budget',
        'utils.executors',
    }
)
_PLUMBING_PREFIXES = ('google.', 'concurrent.', 'asyncio.', 'threading.', 'contextlib.')
_PLUMBING_EXACT = frozenset({'asyncio', 'threading', 'contextlib'})
_known_callers: set[str] = set()
_caller_lock = threading.Lock()

# (qualified class, method, sync|async, wrapped|funnel|builder|unimplemented|absent)
# Funnel methods delegate to a wrapped method on google-cloud-firestore 2.20.0.
# Absent means the SDK has no such attribute. Unimplemented means the base class
# raises NotImplementedError and the concrete override (if any) is a separate row.
SDK_READ_SURFACE: tuple[tuple[str, str, str, str], ...] = (
    ('google.cloud.firestore_v1.document.DocumentReference', 'get', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.document.DocumentReference', 'collections', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.document.DocumentReference', 'on_snapshot', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.client.Client', 'get_all', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.transaction.Transaction', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.transaction.Transaction', 'get_all', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.query.Query', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.query.Query', 'stream', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.query.Query', 'on_snapshot', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.query.Query', 'find_nearest', 'sync', 'builder'),
    ('google.cloud.firestore_v1.query.Query', 'explain', 'sync', 'absent'),
    ('google.cloud.firestore_v1.query.Query', 'get_partitions', 'sync', 'absent'),
    ('google.cloud.firestore_v1.query.CollectionGroup', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.query.CollectionGroup', 'stream', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.query.CollectionGroup', 'get_partitions', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.collection.CollectionReference', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.collection.CollectionReference', 'stream', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.collection.CollectionReference', 'list_documents', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.collection.CollectionReference', 'on_snapshot', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.aggregation.AggregationQuery', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.aggregation.AggregationQuery', 'stream', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.vector_query.VectorQuery', 'get', 'sync', 'funnel'),
    ('google.cloud.firestore_v1.vector_query.VectorQuery', 'stream', 'sync', 'wrapped'),
    ('google.cloud.firestore_v1.async_document.AsyncDocumentReference', 'get', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_document.AsyncDocumentReference', 'collections', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_document.AsyncDocumentReference', 'on_snapshot', 'async', 'unimplemented'),
    ('google.cloud.firestore_v1.async_client.AsyncClient', 'get_all', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_transaction.AsyncTransaction', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_transaction.AsyncTransaction', 'get_all', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_query.AsyncQuery', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_query.AsyncQuery', 'stream', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_query.AsyncQuery', 'on_snapshot', 'async', 'unimplemented'),
    ('google.cloud.firestore_v1.async_query.AsyncCollectionGroup', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_query.AsyncCollectionGroup', 'stream', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_query.AsyncCollectionGroup', 'get_partitions', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_collection.AsyncCollectionReference', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_collection.AsyncCollectionReference', 'stream', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_collection.AsyncCollectionReference', 'list_documents', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_aggregation.AsyncAggregationQuery', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_aggregation.AsyncAggregationQuery', 'stream', 'async', 'wrapped'),
    ('google.cloud.firestore_v1.async_vector_query.AsyncVectorQuery', 'get', 'async', 'funnel'),
    ('google.cloud.firestore_v1.async_vector_query.AsyncVectorQuery', 'stream', 'async', 'wrapped'),
)


# Reviewed patterns. Anything else is folded into `other` so an unforeseen
# collection cannot expand the label space. Add a pattern here only after
# confirming it is a bounded, non-user-derived name.
_KNOWN_PATTERNS = frozenset(
    {
        'users',
        'users/conversations',
        'users/memory_items',
        'users/memory_outbox',
        'users/memory_historical_overrides',
        'users/memory_state',
        'users/memories',
        'users/candidates',
        'users/knowledge_nodes',
        'users/knowledge_edges',
        'users/task_intelligence_control',
        'users/recording_sessions',
        'users/conversation_finalization_jobs',
        'users/action_items',
        'users/photos',
        'users/conversations/photos',
        'users/hourly_usage',
        'users/messages',
        'users/fcm_tokens',
        'users/chat_messages',
        'users/people',
        'users/facts',
        'users/apps',
        'users/calendar_meetings',
        'users/payments',
        'users/usage',
        'account_deletions',
        'testers',
        'apps',
        'plugins',
        'migration_requests',
    }
)

_OTHER = 'other'
_UNKNOWN = 'unknown'
_PROBE_MARK = '_omi_read_probe'


def collection_pattern(path_parts: Any) -> str:
    """Reduce a Firestore document path to its collection pattern.

    ``('users', 'abc123', 'conversations', 'def456')`` -> ``'users/conversations'``.
    Document ids sit at the odd indices and are dropped, so no user-derived value
    survives into a label. A one-segment collection-group parent such as
    ``('memory_items',)`` maps to the single known pattern that ends with that
    segment; two matches (``photos``) stay ``other``.
    """
    try:
        parts = tuple(path_parts or ())
        if not parts:
            return _UNKNOWN
        pattern = '/'.join(str(parts[i]) for i in range(0, len(parts), 2))
    except Exception:
        return _UNKNOWN
    if pattern in _KNOWN_PATTERNS:
        return pattern
    if len(parts) == 1:
        token = str(parts[0])
        matches = [known for known in _KNOWN_PATTERNS if known == token or known.endswith('/' + token)]
        if len(matches) == 1:
            return matches[0]
    return _OTHER


def _is_plumbing_module(module: str) -> bool:
    if not module or module == __name__ or module in _PLUMBING_MODULES or module in _PLUMBING_EXACT:
        return True
    return module.startswith(_PLUMBING_PREFIXES)


def bound_caller(label: str) -> str:
    """Accept a ``module:function`` label, or ``other`` once the cap is full.

    A well-formed label that does not fit increments the overflow counter.
    A label that fails the grammar is ``other`` and does not, so garbage
    cannot page the saturation signal.
    """
    try:
        if len(label) > 96 or _CALLER_RE.match(label) is None:
            return _OTHER
        if label in _known_callers:
            return label
        with _caller_lock:
            if label in _known_callers:
                return label
            if len(_known_callers) >= MAX_CALLERS:
                FIRESTORE_CALLER_LABEL_OVERFLOW.inc()
                return _OTHER
            _known_callers.add(label)
            return label
    except Exception:
        return _OTHER


def call_site() -> str:
    """First product frame, as a bounded ``module:function`` label.

    Skips this probe, Firestore plumbing wrappers, and runtime frames so the
    label names the function that asked for the read.
    """
    try:
        frame = inspect.currentframe()
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            module = frame.f_globals.get('__name__') or ''
            name = frame.f_code.co_name
            if _is_plumbing_module(module) or not name or name.startswith('<'):
                frame = frame.f_back
                continue
            return bound_caller(f'{module}:{name}')
    except Exception:
        return _OTHER
    return _OTHER


def _record(
    path_parts: Any,
    exists: bool,
    amount: float = 1,
    *,
    kind: str | None = None,
    caller: str | None = None,
    outcome: str | None = None,
) -> None:
    """Count billed reads on every counter. Never raises."""
    if outcome is None:
        outcome = 'hit' if exists else 'miss'
    if kind is None:
        kind = 'not_found' if outcome == 'miss' else 'lookup'
    if caller is None:
        caller = 'unattributed'
    pattern = collection_pattern(path_parts)
    tier = current_tier()
    try:
        FIRESTORE_DOCUMENT_READS.labels(collection=pattern, outcome=outcome, tier=tier).inc(amount)
    except Exception:
        logger.warning('firestore document read probe failed to record', exc_info=True)
    try:
        FIRESTORE_BILLED_READS.labels(collection=pattern, kind=kind, tier=tier).inc(amount)
    except Exception:
        logger.warning('firestore document read probe failed to record', exc_info=True)
    try:
        FIRESTORE_BILLED_READS_BY_CALLER.labels(collection=pattern, kind=kind, caller=caller).inc(amount)
    except Exception:
        logger.warning('firestore document read probe failed to record', exc_info=True)


def _record_operation(path_parts: Any) -> None:
    """Count one RunQuery operation. Never raises."""
    try:
        FIRESTORE_QUERY_OPERATIONS.labels(collection=collection_pattern(path_parts), tier=current_tier()).inc()
    except Exception:
        logger.warning('firestore query operation probe failed to record', exc_info=True)


def _parent_path(query: Any) -> Any:
    parent = getattr(query, '_parent', None)
    if parent is None:
        nested = getattr(query, '_nested_query', None)
        parent = getattr(nested, '_parent', None)
    if parent is None:
        parent = getattr(query, '_collection_ref', None)
    return getattr(parent, '_path', ())


def _offset_of(query: Any) -> int:
    for obj in (query, getattr(query, '_nested_query', None)):
        if obj is None:
            continue
        raw = getattr(obj, '_offset', None)
        if not raw:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0
    return 0


def _counts_as_document(item: Any) -> bool:
    return hasattr(item, 'exists') or getattr(item, 'reference', None) is not None


def _snapshot_path(snapshot: Any, fallback: Any) -> Any:
    reference = getattr(snapshot, 'reference', None)
    path = getattr(reference, '_path', None)
    return path or fallback


def _finish_query(path: Any, caller: str, yielded: int, offset: int) -> None:
    # Offset skips are billed even when the client stops reading. Zero documents
    # and a zero offset still bill the one-read query minimum.
    extra = offset if offset > 0 else 0
    if yielded + extra == 0:
        extra = 1
    if extra:
        _record(path, False, amount=extra, kind='query', caller=caller, outcome='floor')
    _record_operation(path)


def _copy_explain(wrapper: Any, inner: Any) -> None:
    getter = getattr(inner, 'get_explain_metrics', None)
    if getter is not None:
        try:
            wrapper.get_explain_metrics = getter
        except Exception:
            return
    options = getattr(inner, 'explain_options', None)
    if options is not None:
        try:
            wrapper.explain_options = options
        except Exception:
            return


def _listen_documents(payload: Any) -> int:
    documents = getattr(payload, 'documents', None)
    if documents is not None:
        try:
            return len(documents)
        except TypeError:
            return 1
    if isinstance(payload, (list, tuple)):
        return len(payload)
    if payload is None:
        return 0
    return 1


def _aggregation_amount(query: Any, result: Any) -> list[tuple[int, int]]:
    """Return (matched, billed reads) per aggregation row.

    count() uses ceil(value/1000) with a floor of 1. sum/avg bill 1 because the
    numeric result is not an index-entry count.
    """
    aggregations = getattr(query, '_aggregations', None) or ()
    non_count = any(type(item).__name__ in ('SumAggregation', 'AvgAggregation') for item in aggregations)
    rows = result if isinstance(result, (list, tuple)) else (result,)
    billed_rows: list[tuple[int, int]] = []
    for row in rows:
        try:
            matched = int(getattr(row, 'value', 0) or 0)
        except (TypeError, ValueError):
            matched = 0
        if non_count:
            billed = 1
        else:
            billed = max(1, math.ceil(matched / _AGGREGATION_INDEX_ENTRIES_PER_READ))
        billed_rows.append((matched, billed))
    return billed_rows


def _patch(cls: Any, name: str, factory: Callable[[Any], Any]) -> None:
    try:
        current = getattr(cls, name)
    except AttributeError:
        return
    if getattr(current, _PROBE_MARK, False):
        return
    wrapper = factory(current)
    try:
        setattr(wrapper, _PROBE_MARK, True)
    except Exception:
        return
    setattr(cls, name, wrapper)


def _wrap_lookup_get(original: Any) -> Any:
    def get(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        snapshot = original(self, *args, **kwargs)
        _record(getattr(self, '_path', ()), bool(getattr(snapshot, 'exists', False)), caller=caller)
        return snapshot

    return get


def _wrap_async_lookup_get(original: Any) -> Any:
    async def get(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        snapshot = await original(self, *args, **kwargs)
        _record(getattr(self, '_path', ()), bool(getattr(snapshot, 'exists', False)), caller=caller)
        return snapshot

    return get


def _wrap_get_all(original: Any) -> Any:
    def get_all(self: Any, references: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        for snapshot in original(self, references, *args, **kwargs):
            reference = getattr(snapshot, 'reference', None)
            _record(getattr(reference, '_path', ()), bool(getattr(snapshot, 'exists', False)), caller=caller)
            yield snapshot

    return get_all


def _wrap_async_get_all(original: Any) -> Any:
    async def get_all(self: Any, references: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        async for snapshot in original(self, references, *args, **kwargs):
            reference = getattr(snapshot, 'reference', None)
            _record(getattr(reference, '_path', ()), bool(getattr(snapshot, 'exists', False)), caller=caller)
            yield snapshot

    return get_all


class _ObservedSync:
    """Iterator whose close() counts even when the caller never pulls a row.

    A fresh generator's close() does not run the generator body, so a stream
    abandoned before the first document would miss the empty-query read.
    Generators also cannot carry ``get_explain_metrics``.
    """

    def __init__(self, inner: Any, on_item: Callable[[Any], None], on_finish: Callable[[], None]) -> None:
        self._inner = inner
        self._on_item = on_item
        self._on_finish = on_finish
        self._done = False
        _copy_explain(self, inner)

    def __iter__(self) -> '_ObservedSync':
        return self

    def __next__(self) -> Any:
        try:
            item = next(self._inner)
        except BaseException:
            self._finish()
            raise
        self._on_item(item)
        return item

    def close(self) -> None:
        self._finish()
        closer = getattr(self._inner, 'close', None)
        if closer is not None:
            closer()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._on_finish()
        except Exception:
            logger.warning('firestore document read probe failed to record', exc_info=True)

    def __del__(self) -> None:
        try:
            self._finish()
        except Exception:
            return


class _ObservedAsync:
    """Async twin of ``_ObservedSync``. ``aclose`` counts an unpulled stream."""

    def __init__(self, inner: Any, on_item: Callable[[Any], None], on_finish: Callable[[], None]) -> None:
        self._inner = inner
        self._on_item = on_item
        self._on_finish = on_finish
        self._done = False
        _copy_explain(self, inner)

    def __aiter__(self) -> '_ObservedAsync':
        return self

    async def __anext__(self) -> Any:
        try:
            item = await self._inner.__anext__()
        except BaseException:
            self._finish()
            raise
        self._on_item(item)
        return item

    async def aclose(self) -> None:
        self._finish()
        closer = getattr(self._inner, 'aclose', None)
        if closer is not None:
            await closer()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._on_finish()
        except Exception:
            logger.warning('firestore document read probe failed to record', exc_info=True)

    def __del__(self) -> None:
        try:
            self._finish()
        except Exception:
            return


def _wrap_query_stream(original: Any) -> Any:
    def stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = _parent_path(self)
        offset = _offset_of(self)
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(snapshot: Any) -> None:
            nonlocal yielded
            if _counts_as_document(snapshot):
                yielded += 1
                _record(_snapshot_path(snapshot, path), True, kind='query', caller=caller)

        def on_finish() -> None:
            _finish_query(path, caller, yielded, offset)

        return _ObservedSync(inner, on_item, on_finish)

    return stream


def _wrap_async_query_stream(original: Any) -> Any:
    def stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = _parent_path(self)
        offset = _offset_of(self)
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(snapshot: Any) -> None:
            nonlocal yielded
            if _counts_as_document(snapshot):
                yielded += 1
                _record(_snapshot_path(snapshot, path), True, kind='query', caller=caller)

        def on_finish() -> None:
            _finish_query(path, caller, yielded, offset)

        return _ObservedAsync(inner, on_item, on_finish)

    return stream


def _wrap_aggregation_stream(original: Any) -> Any:
    def stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = _parent_path(self)
        inner = original(self, *args, **kwargs)
        saw_result = False

        def on_item(result: Any) -> None:
            nonlocal saw_result
            if not isinstance(result, (list, tuple)) and not hasattr(result, 'value'):
                return
            saw_result = True
            try:
                for matched, billed in _aggregation_amount(self, result):
                    _record(path, matched > 0, amount=billed, kind='query', caller=caller)
            except Exception:
                logger.warning('firestore document read probe failed to record', exc_info=True)

        def on_finish() -> None:
            if not saw_result:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedSync(inner, on_item, on_finish)

    return stream


def _wrap_async_aggregation_stream(original: Any) -> Any:
    def stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = _parent_path(self)
        inner = original(self, *args, **kwargs)
        saw_result = False

        def on_item(result: Any) -> None:
            nonlocal saw_result
            if not isinstance(result, (list, tuple)) and not hasattr(result, 'value'):
                return
            saw_result = True
            try:
                for matched, billed in _aggregation_amount(self, result):
                    _record(path, matched > 0, amount=billed, kind='query', caller=caller)
            except Exception:
                logger.warning('firestore document read probe failed to record', exc_info=True)

        def on_finish() -> None:
            if not saw_result:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedAsync(inner, on_item, on_finish)

    return stream


def _wrap_list_documents(original: Any) -> Any:
    def list_documents(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = getattr(self, '_path', ())
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(ref: Any) -> None:
            nonlocal yielded
            yielded += 1
            _record(getattr(ref, '_path', None) or path, True, kind='query', caller=caller)

        def on_finish() -> None:
            if yielded == 0:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedSync(inner, on_item, on_finish)

    return list_documents


def _wrap_async_list_documents(original: Any) -> Any:
    def list_documents(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = getattr(self, '_path', ())
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(ref: Any) -> None:
            nonlocal yielded
            yielded += 1
            _record(getattr(ref, '_path', None) or path, True, kind='query', caller=caller)

        def on_finish() -> None:
            if yielded == 0:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedAsync(inner, on_item, on_finish)

    return list_documents


def _wrap_collections(original: Any) -> Any:
    def collections(self: Any, *args: Any, **kwargs: Any) -> Any:
        # ListCollectionIds bills one read per request, not per collection id.
        caller = call_site()
        path = getattr(self, '_path', ())
        inner = original(self, *args, **kwargs)

        def on_finish() -> None:
            _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedSync(inner, lambda _item: None, on_finish)

    return collections


def _wrap_async_collections(original: Any) -> Any:
    def collections(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = getattr(self, '_path', ())
        inner = original(self, *args, **kwargs)

        def on_finish() -> None:
            _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedAsync(inner, lambda _item: None, on_finish)

    return collections


def _wrap_partitions(original: Any) -> Any:
    def get_partitions(self: Any, *args: Any, **kwargs: Any) -> Any:
        # PartitionQuery is not itemized on the pricing page. One read per
        # yielded cursor, or one if the call returns nothing.
        caller = call_site()
        path = _parent_path(self)
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(_part: Any) -> None:
            nonlocal yielded
            yielded += 1
            _record(path, True, kind='query', caller=caller)

        def on_finish() -> None:
            if yielded == 0:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedSync(inner, on_item, on_finish)

    return get_partitions


def _wrap_async_partitions(original: Any) -> Any:
    def get_partitions(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = _parent_path(self)
        inner = original(self, *args, **kwargs)
        yielded = 0

        def on_item(_part: Any) -> None:
            nonlocal yielded
            yielded += 1
            _record(path, True, kind='query', caller=caller)

        def on_finish() -> None:
            if yielded == 0:
                _record(path, False, kind='query', caller=caller, outcome='floor')

        return _ObservedAsync(inner, on_item, on_finish)

    return get_partitions


def _wrap_on_snapshot(original: Any, path_of: Callable[[Any], Any]) -> Any:
    def on_snapshot(self: Any, callback: Any, *args: Any, **kwargs: Any) -> Any:
        caller = call_site()
        path = path_of(self)

        def wrapped(payload: Any, changes: Any, read_time: Any) -> Any:
            try:
                amount = _listen_documents(payload)
                if amount <= 0:
                    _record(path, False, kind='query', caller=caller, outcome='floor')
                else:
                    _record(path, True, amount=amount, kind='query', caller=caller)
            except Exception:
                logger.warning('firestore document read probe failed to record', exc_info=True)
            return callback(payload, changes, read_time)

        return original(self, wrapped, *args, **kwargs)

    return on_snapshot


_installed = False


def install_document_read_probe() -> None:
    """Wrap SDK read entry points. Idempotent. ImportError skips the install.

    Unit-test harnesses stub the ``google`` namespace, so a missing SDK is not
    an error. A wrapper that is already installed is not wrapped again.
    """
    global _installed
    if _installed:
        return
    try:
        from google.cloud.firestore_v1.aggregation import AggregationQuery
        from google.cloud.firestore_v1.client import Client
        from google.cloud.firestore_v1.collection import CollectionReference
        from google.cloud.firestore_v1.document import DocumentReference
        from google.cloud.firestore_v1.query import CollectionGroup, Query
        from google.cloud.firestore_v1.vector_query import VectorQuery
    except ImportError:
        return

    _patch(DocumentReference, 'get', _wrap_lookup_get)
    _patch(Client, 'get_all', _wrap_get_all)
    _patch(Query, 'stream', _wrap_query_stream)
    _patch(AggregationQuery, 'stream', _wrap_aggregation_stream)
    _patch(VectorQuery, 'stream', _wrap_query_stream)
    _patch(CollectionReference, 'list_documents', _wrap_list_documents)
    _patch(CollectionGroup, 'get_partitions', _wrap_partitions)
    _patch(DocumentReference, 'collections', _wrap_collections)
    _patch(
        DocumentReference,
        'on_snapshot',
        lambda original: _wrap_on_snapshot(original, lambda self: getattr(self, '_path', ())),
    )
    _patch(
        Query,
        'on_snapshot',
        lambda original: _wrap_on_snapshot(original, _parent_path),
    )
    _patch(
        CollectionReference,
        'on_snapshot',
        lambda original: _wrap_on_snapshot(original, lambda self: getattr(self, '_path', ())),
    )

    try:
        from google.cloud.firestore_v1.async_aggregation import AsyncAggregationQuery
        from google.cloud.firestore_v1.async_client import AsyncClient
        from google.cloud.firestore_v1.async_collection import AsyncCollectionReference
        from google.cloud.firestore_v1.async_document import AsyncDocumentReference
        from google.cloud.firestore_v1.async_query import AsyncCollectionGroup, AsyncQuery
        from google.cloud.firestore_v1.async_vector_query import AsyncVectorQuery
    except ImportError:
        _installed = True
        return

    _patch(AsyncDocumentReference, 'get', _wrap_async_lookup_get)
    _patch(AsyncClient, 'get_all', _wrap_async_get_all)
    _patch(AsyncQuery, 'stream', _wrap_async_query_stream)
    _patch(AsyncAggregationQuery, 'stream', _wrap_async_aggregation_stream)
    _patch(AsyncVectorQuery, 'stream', _wrap_async_query_stream)
    _patch(AsyncCollectionReference, 'list_documents', _wrap_async_list_documents)
    _patch(AsyncCollectionGroup, 'get_partitions', _wrap_async_partitions)
    _patch(AsyncDocumentReference, 'collections', _wrap_async_collections)
    _installed = True
