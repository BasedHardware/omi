"""Collection- and caller-level accounting for every committed Firestore write.

Cloud Monitoring's ``firestore.googleapis.com/document/write_count`` has an
``op`` label and nothing else, and Firestore data-access audit logs are off, so
a write-volume step in the bill cannot be traced to code. This probe is the
write-side twin of ``database.firestore_document_probe``.

It wraps the GAPIC transport methods ``FirestoreClient.commit`` and
``batch_write`` (and the async twins). Every SDK write reaches one of them:
``WriteBatch.commit`` (which ``DocumentReference`` ``create`` / ``set`` /
``update`` use), ``Transaction._commit``, ``DocumentReference.delete`` and
``BulkWriter``. Counting at the transport means the probe sees the request as
sent, including writes that commit-boundary patches append to it
(such as the ``database.memory_change_head`` writes). ``database._client`` installs this probe before those patches, so the
change-head wrapper calls through it with its heads already appended.

Billing assumptions (Cloud Firestore Standard pricing, encoded, not measured):

* One billed write per ``Write`` in a successful Commit, whatever it carries.
  Field transforms such as ``SERVER_TIMESTAMP`` ride inside that write. A write
  that changes nothing is still billed; Cloud Monitoring calls it UPDATE_NOOP.
* A Commit that raises is not counted: Firestore applies none of its writes,
  and an aborted transaction attempt applies none. A transaction retried three
  times and then committed counts once. DeadlineExceeded / Unavailable may
  arrive after the server applied the writes; those go to
  ``omi_firestore_ambiguous_commit_writes_total`` instead, so the main counters
  stay exact for known outcomes and the ambiguity is still visible.
* BatchWrite is not atomic. Only writes whose status code is OK are counted.
* Deletes are counted with ``op="delete"``; billing prices them under their own
  SKU. Index-entry maintenance is not billed separately and is not counted.
* Writes to a named database are labelled ``database="named"``; billing prices
  them under their own "(named databases)" SKU.

``op`` is ``create`` (precondition exists=false), ``update`` (precondition
exists=true or a last-update-time precondition: ``update()``), ``merge`` (an update mask and no precondition, an
upsert: ``set(merge=True)``), ``set`` (whole-document replace), ``delete``, or
``transform`` (a transform-only write). ``update`` and ``merge`` are split
because commit-boundary fences treat an upsert as able to create a document.

Cardinality: collection patterns reuse the read probe's allowlist. The caller
label is ``module:function`` from the first product frame, with the read
probe's plumbing rules plus the commit-boundary patches, and the shared caller cap. BulkWriter
captures caller and origin when each operation is queued, and retains them
across worker threads and retries. The caller/origin counters fold merge into
set and transform into update. ``origin`` is the bounded route/job origin the
read probe uses. No uid, document id or field value is
ever a label. Recording never raises.
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterable
from threading import Lock

from prometheus_client import Counter

from database.firestore_document_probe import call_site, collection_pattern
from database.firestore_read_origin import current_read_origin
from database.plane_leak_probe import record_plane_leak

logger = logging.getLogger(__name__)

__all__ = [
    'FIRESTORE_AMBIGUOUS_COMMIT_WRITES',
    'FIRESTORE_BILLED_WRITES',
    'FIRESTORE_BILLED_WRITES_BY_CALLER',
    'FIRESTORE_BILLED_WRITES_BY_ORIGIN',
    'FIRESTORE_NOOP_WRITES_BY_CALLER',
    'FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW',
    'install_document_write_probe',
    'write_op',
]


FIRESTORE_BILLED_WRITES = Counter(
    'omi_firestore_billed_writes_total',
    'Billed-equivalent Firestore writes in successful commits by collection pattern, op, and database '
    '(default or named). Coverage numerator against firestore.googleapis.com/document/write_count.',
    ['collection', 'op', 'database'],
)


FIRESTORE_BILLED_WRITES_BY_CALLER = Counter(
    'omi_firestore_billed_writes_by_caller_total',
    'Billed-equivalent Firestore writes by collection, op, and bounded call site. '
    'caller is module:function or other; overflow increments omi_firestore_write_caller_label_overflow_total.',
    ['collection', 'op', 'caller'],
)


FIRESTORE_BILLED_WRITES_BY_ORIGIN = Counter(
    'omi_firestore_billed_writes_by_origin_total',
    'Billed-equivalent Firestore writes by bounded route template or job/task name, collection, and op.',
    ['origin', 'collection', 'op'],
)


# DeadlineExceeded / Unavailable can arrive after the server applied the Commit.
# Those writes are kept out of the counters above (which stay exact for known
# outcomes) and counted here, so the size of the ambiguity is visible.
FIRESTORE_AMBIGUOUS_COMMIT_WRITES = Counter(
    'omi_firestore_ambiguous_commit_writes_total',
    'Writes in Firestore Commit/BatchWrite calls that failed with DeadlineExceeded or Unavailable '
    'and may have been applied and billed.',
)


# Cloud Monitoring reports ~15-20% of writes as UPDATE_NOOP (billed, changed
# nothing) with no caller. A Commit's WriteResult.update_time is the document's
# previous update time when the write changed nothing, so it is earlier than the
# response's commit_time; a write that changed the document carries commit_time.
# Lower bound: when one Commit writes a document twice, the second write's
# "previous" time is this commit, whether or not it changed anything, so a
# repeated-document no-op is not counted (the response cannot tell them apart).
FIRESTORE_NOOP_WRITES_BY_CALLER = Counter(
    'omi_firestore_noop_writes_by_caller_total',
    'Committed Firestore writes that left the document unchanged (billed as writes), by collection and call site.',
    ['collection', 'caller'],
)


FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW = Counter(
    'omi_firestore_write_caller_label_overflow_total',
    'Firestore write caller labels dropped because the bounded write caller set is full.',
)


# Commit-boundary patches that sit between product code and the transport.
_WRITE_PLUMBING_MODULES = frozenset(
    {
        __name__,
        'database.firestore_bulk_attribution',
        'database.memory_change_head',
        'database.action_item_write_fence',
        'database.batch_privacy_write_fence',
        'database.home_feed_writer',
        # The transactional callback has returned before the SDK commits, so the
        # retry helper would otherwise be the first frame for every caller of it
        # (~50% of Cloud Run writes on 2026-11-01).
        'database.firestore_transaction_retry',
        # bind_firestore_client swaps the shared client's API methods for `bounded`,
        # so it was the first frame for ~42M writes/day (most of backend-sync) on 2026-11-25.
        'database.rpc_deadline',
    }
)
# Generic write helpers inside product modules: name the function that called them.
# The enrichment outbox CAS loop alone was ~3.1M writes/day on 2026-11-01.
_WRITE_PLUMBING_FUNCTIONS = frozenset(
    {
        ('utils.enrichment.outbox', '_cas'),
        ('utils.enrichment.outbox', '_mutate'),
        ('utils.enrichment.outbox', 'mutate_row'),
        # FirestoreEnrichmentOutbox's adapter in front of mutate_row.
        ('database.outbox_firestore', '_mutate'),
        # ProjectionStore's transaction runner: name the store method (ready, complete,
        # acknowledge, ...) instead of `run` (~32M writes/day on 2026-11-25).
        ('database.batch_pipeline_projection', 'run'),
    }
)
_OTHER = 'other'
_UNKNOWN = 'unknown'
_PROBE_MARK = '_omi_write_probe'
_ATTRIBUTION_OPS = {'merge': 'set', 'transform': 'update'}


WriteAttribution = tuple[str, str]
UNATTRIBUTED_WRITE = (_OTHER, 'unset')
bulk_write_attribution: ContextVar[dict[tuple[str, ...], WriteAttribution] | None] = ContextVar(
    'firestore_bulk_write_attribution', default=None
)


def _is_write_plumbing(module: str, function: str) -> bool:
    return module in _WRITE_PLUMBING_MODULES or (module, function) in _WRITE_PLUMBING_FUNCTIONS


def write_caller() -> str:
    return call_site(
        skip_frame=_is_write_plumbing, extra_overflow=FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW, use_privacy_caller=False
    )


def _wrap_bulk_init(original: Any) -> Any:
    @functools.wraps(original)
    def init(writer: Any, *args: Any, **kwargs: Any) -> None:
        # Only a process constructing a BulkWriter needs its metadata hooks.
        try:
            from database.firestore_bulk_attribution import install_bulk_attribution

            install_bulk_attribution()
        except Exception:
            logger.warning('firestore write probe failed to install BulkWriter attribution', exc_info=True)
        original(writer, *args, **kwargs)

    return init


def _split_name(name: str) -> tuple[str, tuple[str, ...]]:
    """``projects/p/databases/d/documents/a/b`` -> (``default``|``named``, (``a``, ``b``))."""
    head, sep, tail = name.partition('/documents/')
    if not sep:
        return _UNKNOWN, ()
    database = head.rpartition('/databases/')[2]
    return ('default' if database == '(default)' else 'named'), tuple(tail.split('/'))


def write_op(write: Any) -> tuple[str, str, tuple[str, ...]]:
    """(op, database, path parts) for one ``Write`` (proto-plus, raw pb or dict). Never raises."""
    try:
        from google.cloud.firestore_v1.types import Write

        pb = (
            Write.pb(write if isinstance(write, Write) else Write(write)) if not hasattr(write, 'WhichOneof') else write
        )
        kind = pb.WhichOneof('operation')
        if kind == 'update':
            if pb.HasField('current_document') and pb.current_document.HasField('exists'):
                op = 'update' if pb.current_document.exists else 'create'
            elif pb.HasField('current_document') and pb.current_document.HasField('update_time'):
                op = 'update'  # A last-update-time precondition requires the document to exist.
            else:
                op = 'merge' if pb.HasField('update_mask') else 'set'
            name = pb.update.name
        elif kind == 'delete':
            op, name = 'delete', pb.delete
        elif kind == 'transform':
            op, name = 'transform', pb.transform.document
        else:
            return _UNKNOWN, _UNKNOWN, ()
        database, parts = _split_name(name)
        return op, database, parts
    except Exception:
        return _UNKNOWN, _UNKNOWN, ()


def _record(writes: Iterable[Any], caller: str) -> None:
    """Count one successful commit's writes on every counter. Never raises."""
    try:
        bulk = bulk_write_attribution.get()
        if bulk is None:
            try:
                origin = current_read_origin()
            except Exception:
                origin = 'unset'
            fallback = (caller, origin)
        else:
            # Commit-boundary patches can append companion writes. Attribute
            # those to a common submitter when the entire batch has one.
            submitters = set(bulk.values())
            fallback = next(iter(submitters)) if len(submitters) == 1 else UNATTRIBUTED_WRITE
        tally: dict[tuple[str, str, str, WriteAttribution], int] = {}
        for write in writes:
            op, database, parts = write_op(write)
            record_plane_leak(parts, 'write')
            attribution = fallback if bulk is None else bulk.get(parts, fallback)
            key = (collection_pattern(parts) if parts else _UNKNOWN, op, database, attribution)
            tally[key] = tally.get(key, 0) + 1
    except Exception:
        return
    for (collection, op, database, (write_caller, origin)), amount in tally.items():
        try:
            FIRESTORE_BILLED_WRITES.labels(collection=collection, op=op, database=database).inc(amount)
        except Exception:
            logger.warning('firestore write probe failed to record', exc_info=True)
        attribution_op = _ATTRIBUTION_OPS.get(op, op)
        try:
            FIRESTORE_BILLED_WRITES_BY_CALLER.labels(collection=collection, op=attribution_op, caller=write_caller).inc(
                amount
            )
        except Exception:
            logger.warning('firestore write probe failed to record', exc_info=True)
        try:
            FIRESTORE_BILLED_WRITES_BY_ORIGIN.labels(origin=origin, collection=collection, op=attribution_op).inc(
                amount
            )
        except Exception:
            pass  # Attribution must never affect a write or the counters above.


def _request_writes(request: Any, kwargs: dict[str, Any]) -> list:
    try:
        if request is None:
            return list(kwargs.get('writes') or ())
        if isinstance(request, dict):
            return list(request.get('writes') or ())
        return list(getattr(request, 'writes', None) or ())
    except Exception:
        return []


def _applied(writes: list, response: Any) -> list:
    """BatchWrite: keep only writes whose per-write status is OK."""
    try:
        statuses = list(response.status)
    except Exception:
        return []
    if len(statuses) != len(writes):
        return []
    return [write for write, status in zip(writes, statuses) if getattr(status, 'code', None) == 0]


def _timestamp(value: Any) -> tuple[int, int]:
    return value.seconds, value.nanos


def _record_noops(writes: list, response: Any, caller: str) -> None:
    """Count Commit writes whose result update_time predates commit_time. Never raises."""
    try:
        pb = type(response).pb(response)
        results = list(pb.write_results)
        if len(results) != len(writes) or not pb.HasField('commit_time'):
            return
        committed = _timestamp(pb.commit_time)
        tally: dict[str, int] = {}
        for write, result in zip(writes, results):
            if not result.HasField('update_time') or _timestamp(result.update_time) >= committed:
                continue  # Deletes carry no update_time; a changed document carries commit_time.
            _, _, parts = write_op(write)
            collection = collection_pattern(parts) if parts else _UNKNOWN
            tally[collection] = tally.get(collection, 0) + 1
        for collection, amount in tally.items():
            FIRESTORE_NOOP_WRITES_BY_CALLER.labels(collection=collection, caller=caller).inc(amount)
    except Exception:
        pass  # Attribution must never affect a write.


class CommittedWrites:
    """Shared by the executor threads in one request context."""

    def __init__(self):
        self._total = 0
        self._lock = Lock()

    def add(self, count):
        with self._lock:
            self._total += count

    @property
    def total(self):
        with self._lock:
            return self._total


_committed_writes: ContextVar[CommittedWrites | None] = ContextVar('firestore_committed_writes', default=None)


@contextmanager
def count_committed_writes():
    counter = CommittedWrites()
    token = _committed_writes.set(counter)
    try:
        yield counter
    finally:
        _committed_writes.reset(token)


def _after(writes: list, response: Any, partial: bool) -> None:
    if partial:
        writes = _applied(writes, response)
    if not writes:
        return
    count = _committed_writes.get()
    if count is not None:
        count.add(len(writes))
    caller = write_caller() if bulk_write_attribution.get() is None else _OTHER
    _record(writes, caller)
    if not partial:
        _record_noops(writes, response, caller)


def _record_ambiguous(writes: list, error: BaseException) -> None:
    """A Commit whose outcome is unknown may still have applied. Count it apart. Never raises."""
    try:
        from google.api_core import exceptions

        if writes and isinstance(error, (exceptions.DeadlineExceeded, exceptions.ServiceUnavailable)):
            FIRESTORE_AMBIGUOUS_COMMIT_WRITES.inc(len(writes))
    except Exception:
        pass


def _wrap(original: Any, *, partial: bool) -> Any:
    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def async_call(client: Any, request: Any = None, *args: Any, **kwargs: Any) -> Any:
            writes = _request_writes(request, kwargs)
            try:
                response = await original(client, request, *args, **kwargs)
            except BaseException as error:
                _record_ambiguous(writes, error)
                raise
            _after(writes, response, partial)
            return response

        return async_call

    @functools.wraps(original)
    def call(client: Any, request: Any = None, *args: Any, **kwargs: Any) -> Any:
        writes = _request_writes(request, kwargs)
        try:
            response = original(client, request, *args, **kwargs)
        except BaseException as error:
            _record_ambiguous(writes, error)
            raise
        _after(writes, response, partial)
        return response

    return call


def patch_write_probe(cls: Any, name: str, factory: Callable[[Any], Any]) -> None:
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


_installed = False


def probe_enabled() -> bool:
    """Kill switch, on unless the literal ``false``.

    Off means the transport is never wrapped, so the labelled write series are
    never created in that process. Set per service: a Cloud Run service close
    to its GMP sidecar ``samples`` limit (backend/deploy/cloud_run_gmp_sidecar.yaml)
    would otherwise lose its whole scrape, not just these series.
    """
    return (
        os.getenv('FIRESTORE_WRITE_PROBE_ENABLED', 'true').strip().lower() != 'false'
        and os.getenv('OMI_FIRESTORE_WRITE_PROBE_ENABLED', 'true').strip().lower() != 'false'
    )


def install_document_write_probe() -> None:
    """Wrap the transport's Commit and BatchWrite. Idempotent. ImportError or the kill switch skips the install."""
    global _installed
    if _installed or not probe_enabled():
        return
    try:
        from google.cloud.firestore_v1.bulk_writer import BulkWriter
        from google.cloud.firestore_v1.services.firestore import FirestoreAsyncClient, FirestoreClient
    except ImportError:
        return
    for cls in (FirestoreClient, FirestoreAsyncClient):
        patch_write_probe(cls, 'commit', lambda original: _wrap(original, partial=False))
        patch_write_probe(cls, 'batch_write', lambda original: _wrap(original, partial=True))
    # In SDK 2.20 even AsyncClient.bulk_writer returns the synchronous writer.
    patch_write_probe(BulkWriter, '__init__', _wrap_bulk_init)
    _installed = True
