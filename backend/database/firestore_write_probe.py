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
(``database.list_projection`` rows and versions, ``database.memory_change_head``
heads). ``database._client`` installs this probe before those patches, so the
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
probe's plumbing rules plus the commit-boundary patches, and a separate cap
(``MAX_WRITE_CALLERS``) so write call sites never push read callers into
``other``. ``BulkWriter`` commits run on its own worker threads, so they carry
no product frame and are labelled ``other``. ``origin`` is the bounded
route/job origin the read probe uses. No uid, document id or field value is
ever a label. Recording never raises.
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
import re
import threading
from typing import Any, Callable, Iterable

from prometheus_client import Counter

from database.firestore_document_probe import collection_pattern, is_plumbing_module
from database.firestore_read_origin import current_read_origin

logger = logging.getLogger(__name__)

__all__ = [
    'FIRESTORE_AMBIGUOUS_COMMIT_WRITES',
    'FIRESTORE_BILLED_WRITES',
    'FIRESTORE_BILLED_WRITES_BY_CALLER',
    'FIRESTORE_BILLED_WRITES_BY_ORIGIN',
    'FIRESTORE_NOOP_WRITES_BY_CALLER',
    'FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW',
    'MAX_WRITE_CALLERS',
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


# An AST scan of backend/ (excluding tests and scripts) on 2026-11-01 found at
# most 1,324 functions that touch a document, batch or transaction and call
# set/update/create/delete/commit; that over-counts (dict.update matches too).
# 2048 is that bound plus headroom; the set fills on first observation.
MAX_WRITE_CALLERS = 2048

# Commit-boundary patches that sit between product code and the transport.
_WRITE_PLUMBING_MODULES = frozenset(
    {
        __name__,
        'database.list_projection',
        'database.memory_change_head',
        'database.action_item_write_fence',
        # The transactional callback has returned before the SDK commits, so the
        # retry helper would otherwise be the first frame for every caller of it
        # (~50% of Cloud Run writes on 2026-11-01).
        'database.firestore_transaction_retry',
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
    }
)
_CALLER_RE = re.compile(r'^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*){0,6}:[A-Za-z_][A-Za-z0-9_]{0,60}$')
_OTHER = 'other'
_UNKNOWN = 'unknown'
_PROBE_MARK = '_omi_write_probe'
_known_callers: set[str] = set()
_caller_lock = threading.Lock()


def _bound_caller(label: str) -> str:
    try:
        if len(label) > 96 or _CALLER_RE.match(label) is None:
            return _OTHER
        if label in _known_callers:
            return label
        with _caller_lock:
            if label in _known_callers:
                return label
            if len(_known_callers) >= MAX_WRITE_CALLERS:
                FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW.inc()
                return _OTHER
            _known_callers.add(label)
            return label
    except Exception:
        return _OTHER


def _call_site() -> str:
    """First product frame above the transport, as ``module:function``."""
    try:
        frame = inspect.currentframe()
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            module = frame.f_globals.get('__name__') or ''
            name = frame.f_code.co_name
            if (
                module in _WRITE_PLUMBING_MODULES
                or (module, name) in _WRITE_PLUMBING_FUNCTIONS
                or is_plumbing_module(module)
                or not name
                or name.startswith('<')
            ):
                frame = frame.f_back
                continue
            return _bound_caller(f'{module}:{name}')
    except Exception:
        return _OTHER
    return _OTHER


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
        origin = current_read_origin()
    except Exception:
        origin = 'unset'
    try:
        tally: dict[tuple[str, str, str], int] = {}
        for write in writes:
            op, database, parts = write_op(write)
            key = (collection_pattern(parts) if parts else _UNKNOWN, op, database)
            tally[key] = tally.get(key, 0) + 1
    except Exception:
        return
    for (collection, op, database), amount in tally.items():
        try:
            FIRESTORE_BILLED_WRITES.labels(collection=collection, op=op, database=database).inc(amount)
        except Exception:
            logger.warning('firestore write probe failed to record', exc_info=True)
        try:
            FIRESTORE_BILLED_WRITES_BY_CALLER.labels(collection=collection, op=op, caller=caller).inc(amount)
        except Exception:
            logger.warning('firestore write probe failed to record', exc_info=True)
        try:
            FIRESTORE_BILLED_WRITES_BY_ORIGIN.labels(origin=origin, collection=collection, op=op).inc(amount)
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
        return writes
    if len(statuses) != len(writes):
        return writes
    return [write for write, status in zip(writes, statuses) if not getattr(status, 'code', 0)]


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


def _after(writes: list, response: Any, caller: str, partial: bool) -> None:
    if partial:
        _record(_applied(writes, response), caller)
        return
    _record(writes, caller)
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
            caller = _call_site()
            writes = _request_writes(request, kwargs)
            try:
                response = await original(client, request, *args, **kwargs)
            except BaseException as error:
                _record_ambiguous(writes, error)
                raise
            _after(writes, response, caller, partial)
            return response

        return async_call

    @functools.wraps(original)
    def call(client: Any, request: Any = None, *args: Any, **kwargs: Any) -> Any:
        caller = _call_site()
        writes = _request_writes(request, kwargs)
        try:
            response = original(client, request, *args, **kwargs)
        except BaseException as error:
            _record_ambiguous(writes, error)
            raise
        _after(writes, response, caller, partial)
        return response

    return call


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


_installed = False


def probe_enabled() -> bool:
    """Kill switch, on unless the literal ``false``.

    Off means the transport is never wrapped, so the labelled write series are
    never created in that process. Set per service: a Cloud Run service close
    to its GMP sidecar ``samples`` limit (backend/deploy/cloud_run_gmp_sidecar.yaml)
    would otherwise lose its whole scrape, not just these series.
    """
    return os.getenv('OMI_FIRESTORE_WRITE_PROBE_ENABLED', 'true').strip().lower() != 'false'


def install_document_write_probe() -> None:
    """Wrap the transport's Commit and BatchWrite. Idempotent. ImportError or the kill switch skips the install."""
    global _installed
    if _installed or not probe_enabled():
        return
    try:
        from google.cloud.firestore_v1.services.firestore import FirestoreAsyncClient, FirestoreClient
    except ImportError:
        return
    for cls in (FirestoreClient, FirestoreAsyncClient):
        _patch(cls, 'commit', lambda original: _wrap(original, partial=False))
        _patch(cls, 'batch_write', lambda original: _wrap(original, partial=True))
    _installed = True
