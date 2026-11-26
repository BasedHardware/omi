"""Operation counts for one scenario run, and the scenario's ``budget`` checks.

What is counted (``result.json`` ``ops``; the verdict row's ``ops``; the web view's table under the verdict):

- **Firestore** document reads, writes and deletes, at the client seam the lab already patches: the emulator
  client ``database._client`` hands to the product (``stack/env.py``). :func:`install` wraps that client's
  GAPIC API (``client._firestore_api``), so every path the product takes (document gets, queries,
  transactions, batches, the bulk writer) is seen once, at the RPC. Reads are counted the way Firestore bills
  them: one per document a get or query returns, one for a get of a missing document, one for a query that
  returns nothing, one per aggregation query. A write is one ``Write`` in a successful commit or batch write
  (an update, a set, a transform); a delete is one delete ``Write``. A commit that fails (a contention
  retry) counts its writes when the retry succeeds, not before. Split by top-level collection
  (``by_collection``) and by collection path with the ids removed (``by_path``, e.g. ``users/conversations``).
- **No-op writes**: an update whose resulting document equals the previous one. Firestore (and the emulator,
  checked 2026-11-26) answers such a write with the document's *previous* ``update_time``, earlier than the
  commit time, so a write result older than its commit is a no-op. It is still billed as a write. Each no-op
  names its call site (``noop_sites``): the innermost three backend frames outside the lab, the libraries and
  the transaction plumbing (``_PLUMBING``), as ``path:line function``. Read a site against the lab clock: the
  scenario clock does not move inside one event, so a write of ``now``-derived values (a lease renewal's
  ``until``) repeats exactly where production's would move.
- **Vendor calls**: ``llm`` is every request the run's fake LLM gateway received (``by path``); ``stt`` is
  every STT request the run stood in for: each fast-finish provider call (``fast_finish._transcribe``) and
  each cassette played for an ``audio_file`` recording (``stt_by_site``). The canonical batch transcript of a
  scripted recording is a lab write (``batch_projection``), not an STT call, and is not counted.

Reads of a collection in :data:`WALL_CLOCK_COLLECTIONS` (a real-time TTL cache) are kept apart in
``wall_clock_reads``: shown, never totalled, budgeted or compared between repeats.

Scopes: ``pipeline`` (the product, and the lab stand-ins that write in its place), ``home`` (the Home route
calls of ``scenario/home.py``) and ``lab`` (the lab's own reads: snapshots, flags, the driver's pending
check). Totals are ``pipeline`` + ``home``; ``lab`` is shown in ``by_scope`` and never budgeted. Counting
starts after the reset and the account seed, when the first event runs.

The ``budget`` block of a scenario (``spec.py``) caps the totals; each key is one check, labelled
``budget_<key>`` (``budget_vendor_stt``, ``budget_vendor_llm`` for ``vendor_calls``), failing when the count
exceeds the cap, and nameable in ``expected_failure`` like any other check.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import threading
import traceback
from typing import Any, Iterable, Iterator, Mapping, Optional

SCOPES = ('pipeline', 'home', 'lab')
COUNTED_SCOPES = ('pipeline', 'home')
KINDS = ('reads', 'writes', 'deletes', 'noop_writes')
BUDGET_KEYS = ('reads', 'writes', 'deletes', 'noop_writes')
VENDOR_KEYS = ('stt', 'llm')
_SCOPE: ContextVar[str] = ContextVar('pipeline_lab_op_scope', default='pipeline')
BACKEND = Path(__file__).resolve().parents[3]
_LAB_DIR = str(BACKEND / 'testing' / 'pipeline_lab')
# Transaction plumbing: a frame here names how a write is retried, not who asked for it.
_PLUMBING = (
    ('database/_client.py', ''),
    ('database/firestore_transaction_retry.py', ''),
    ('database/transcript_pointer.py', 'run'),
    ('database/transcript_pointer.py', '<lambda>'),
)
SITE_FRAMES = 3
# Collections read through a real-time (``time.monotonic``) TTL cache: how often the cache expires depends on
# host speed, not on the scenario, so these reads are shown (``wall_clock_reads``) but never totalled,
# budgeted or compared between repeats (``determinism.WALL_CLOCK_FIELDS``).
WALL_CLOCK_COLLECTIONS = {
    'dream_control': 'config/dream_control.py: ten-second monotonic kill-switch cache',
}


def budget_label(key: str) -> str:
    return f'budget_vendor_{key}' if key in VENDOR_KEYS else f'budget_{key}'


@contextmanager
def scope(name: str) -> Iterator[None]:
    """Count Firestore operations started in this context (and threads that copy it) under ``name``."""
    token = _SCOPE.set(name)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def lab_io() -> Any:
    """The lab's own reads: shown under ``by_scope.lab``, never in the totals."""
    return scope('lab')


def collection_path(name: str) -> tuple[str, str]:
    """``(top-level collection, collection path without ids)`` of a document or parent resource name."""
    _, _, rest = str(name).partition('/documents/')
    parts = [p for p in rest.split('/') if p]
    if not parts:
        return '(root)', '(root)'
    collections = parts[0::2]
    return collections[0], '/'.join(collections)


def call_site(stack: Optional[list] = None, frames: int = SITE_FRAMES) -> str:
    """The innermost backend frames outside the lab and the libraries: ``path:line function <- ...``."""
    stack = traceback.extract_stack() if stack is None else stack
    out = []
    root = str(BACKEND) + os.sep
    for frame in reversed(stack):
        filename = str(frame.filename)
        if not filename.startswith(root) or filename.startswith(_LAB_DIR) or '/.venv/' in filename:
            continue
        relative = filename[len(root) :]
        if any(relative == path and str(frame.name).startswith(prefix) for path, prefix in _PLUMBING):
            continue
        out.append(f'{relative}:{frame.lineno} {frame.name}')
        if len(out) >= frames:
            break
    return ' <- '.join(out) or '(outside backend)'


class OpCounter:
    """Thread-safe Firestore operation counts by scope, kind, collection and path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = False
        self.counts: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
        self.noop_sites: dict[str, int] = {}
        self.wall_clock_reads: dict[str, int] = {}

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def add(self, kind: str, name: str, n: int = 1, *, site: Optional[str] = None) -> None:
        if not self.active or n <= 0:
            return
        top, path = collection_path(name)
        where = _SCOPE.get()
        if kind == 'reads' and top in WALL_CLOCK_COLLECTIONS:
            with self._lock:
                self.wall_clock_reads[top] = self.wall_clock_reads.get(top, 0) + n
            return
        with self._lock:
            by_kind = self.counts.setdefault(where, {}).setdefault(kind, {})
            by_kind.setdefault('by_collection', {})
            by_kind.setdefault('by_path', {})
            by_kind['by_collection'][top] = by_kind['by_collection'].get(top, 0) + n
            by_kind['by_path'][path] = by_kind['by_path'].get(path, 0) + n
            if site is not None and where in COUNTED_SCOPES:
                self.noop_sites[site] = self.noop_sites.get(site, 0) + n

    def total(self, kind: str, scopes: Iterable[str] = COUNTED_SCOPES) -> int:
        with self._lock:
            return sum(sum((self.counts.get(s, {}).get(kind, {}).get('by_path') or {}).values()) for s in scopes)

    def summary(self) -> dict[str, Any]:
        """``{"reads", "writes", "deletes", "noop_writes", "by_collection", "by_path", "by_scope", "noop_sites"}``."""
        out: dict[str, Any] = {kind: self.total(kind) for kind in KINDS}
        with self._lock:
            for split in ('by_collection', 'by_path'):
                merged: dict[str, dict[str, int]] = {}
                for where in COUNTED_SCOPES:
                    for kind in KINDS:
                        for key, n in (self.counts.get(where, {}).get(kind, {}).get(split) or {}).items():
                            merged.setdefault(key, {k: 0 for k in KINDS})[kind] += n
                out[split] = {key: merged[key] for key in sorted(merged)}
            out['by_scope'] = {
                where: {
                    kind: sum((self.counts.get(where, {}).get(kind, {}).get('by_path') or {}).values())
                    for kind in KINDS
                }
                for where in SCOPES
            }
            out['noop_sites'] = dict(sorted(self.noop_sites.items(), key=lambda kv: (-kv[1], kv[0])))
            out['wall_clock_reads'] = dict(sorted(self.wall_clock_reads.items()))
        return out


# ---- the GAPIC wrapper ------------------------------------------------------------------------------


def _request(args: tuple, kwargs: Mapping[str, Any]) -> Any:
    return kwargs.get('request', args[0] if args else None)


def _field(request: Any, name: str) -> Any:
    if request is None:
        return None
    if isinstance(request, Mapping):
        return request.get(name)
    return getattr(request, name, None)


def _pb(message: Any) -> Any:
    return getattr(message, '_pb', message)


def _query_parent(request: Any) -> str:
    """The queried collection: ``parent`` + the first ``from`` selector (proto-plus ``from_``)."""
    parent = str(_field(request, 'parent') or '')
    query = _field(request, 'structured_query')
    if query is None:  # an aggregation: the structured query inside it
        aggregation = _field(request, 'structured_aggregation_query')
        query = _field(aggregation, 'structured_query') if aggregation is not None else None
    if isinstance(query, Mapping):
        selectors = query.get('from_') or query.get('from') or ()
    else:
        selectors = getattr(query, 'from_', None) or ()
    for selector in selectors:
        collection = (
            selector.get('collection_id') if isinstance(selector, Mapping) else getattr(selector, 'collection_id', '')
        )
        if collection:
            return f'{parent}/{collection}'
    return parent


def _stamp(value: Any) -> tuple[int, int]:
    pb = _pb(value)
    if hasattr(pb, 'seconds'):
        return int(pb.seconds), int(pb.nanos)
    if hasattr(value, 'timestamp'):  # a datetime (proto-plus marshals Timestamp to DatetimeWithNanoseconds)
        nanos = getattr(value, 'nanosecond', value.microsecond * 1000)
        return int(value.replace(microsecond=0).timestamp()), int(nanos)
    return 0, 0


def _write_target(write: Any) -> tuple[str, str]:
    pb = _pb(write)
    op = pb.WhichOneof('operation') if hasattr(pb, 'WhichOneof') else None
    if op == 'update':
        return 'writes', pb.update.name
    if op == 'delete':
        return 'deletes', pb.delete
    if op == 'transform':
        return 'writes', pb.transform.document
    return 'writes', ''


class CountingFirestoreApi:
    """Delegates to the real GAPIC ``FirestoreClient``; counts the RPCs that read or write documents."""

    def __init__(self, inner: Any, counter: OpCounter):
        self._inner = inner
        self._counter = counter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def get_document(self, *args: Any, **kwargs: Any) -> Any:
        response = self._inner.get_document(*args, **kwargs)
        self._counter.add('reads', getattr(response, 'name', '') or str(_field(_request(args, kwargs), 'name')))
        return response

    def batch_get_documents(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        stream = self._inner.batch_get_documents(*args, **kwargs)
        counter = self._counter

        def counted() -> Iterator[Any]:
            for response in stream:
                pb = _pb(response)
                which = pb.WhichOneof('result') if hasattr(pb, 'WhichOneof') else None
                if which == 'found':
                    counter.add('reads', pb.found.name)
                elif which == 'missing':
                    counter.add('reads', pb.missing)
                yield response

        return _Stream(stream, counted())

    def run_query(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        request = _request(args, kwargs)
        stream = self._inner.run_query(*args, **kwargs)
        counter = self._counter

        def counted() -> Iterator[Any]:
            found = 0
            try:
                for response in stream:
                    pb = _pb(response)
                    if pb.HasField('document'):
                        found += 1
                        counter.add('reads', pb.document.name)
                    yield response
            finally:
                if found == 0:  # an empty result is billed one read
                    counter.add('reads', _query_parent(request))

        return _Stream(stream, counted())

    def run_aggregation_query(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        self._counter.add('reads', _query_parent(_request(args, kwargs)))
        return self._inner.run_aggregation_query(*args, **kwargs)

    def list_documents(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        pager = self._inner.list_documents(*args, **kwargs)
        counter = self._counter

        def counted() -> Iterator[Any]:
            for document in pager:
                counter.add('reads', getattr(document, 'name', ''))
                yield document

        return counted()

    def commit(self, *args: Any, **kwargs: Any) -> Any:
        request = _request(args, kwargs)
        response = self._inner.commit(*args, **kwargs)
        writes = list(_field(request, 'writes') or ())
        raw = _pb(response)
        results = list(getattr(raw, 'write_results', None) or ())
        committed = _stamp(raw.commit_time) if raw is not None and raw.HasField('commit_time') else (0, 0)
        site: Optional[str] = None
        for index, write in enumerate(writes):
            kind, name = _write_target(write)
            self._counter.add(kind, name)
            if kind != 'writes' or index >= len(results):
                continue
            result = results[index]
            if result.HasField('update_time') and committed != (0, 0) and _stamp(result.update_time) < committed:
                site = site or call_site()
                self._counter.add('noop_writes', name, site=site)
        return response

    def batch_write(self, *args: Any, **kwargs: Any) -> Any:
        request = _request(args, kwargs)
        response = self._inner.batch_write(*args, **kwargs)
        statuses = list(getattr(response, 'status', None) or ())
        for index, write in enumerate(_field(request, 'writes') or ()):
            if index < len(statuses) and int(getattr(_pb(statuses[index]), 'code', 0)) != 0:
                continue  # that write failed; the bulk writer retries it
            kind, name = _write_target(write)
            self._counter.add(kind, name)
        return response


class _Stream:
    """A counted iterator that still exposes the server stream's other members (``cancel``, ...)."""

    def __init__(self, stream: Any, counted: Iterator[Any]):
        self._stream = stream
        self._counted = counted

    def __iter__(self) -> Iterator[Any]:
        return self._counted

    def __next__(self) -> Any:
        return next(self._counted)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def install(stack: Any, client: Any, counter: OpCounter) -> OpCounter:
    """Wrap ``client``'s GAPIC API for the rest of ``stack`` (an ``ExitStack``)."""
    inner = client._firestore_api  # builds it once
    client._firestore_api_internal = CountingFirestoreApi(inner, counter)
    stack.callback(setattr, client, '_firestore_api_internal', inner)
    return counter


# ---- the budget ----------------------------------------------------------------------------------


def vendor_counts(*, transcribe_calls: int, cassette_plays: int, llm_paths: Iterable[str]) -> dict[str, Any]:
    by_path: dict[str, int] = {}
    for path in llm_paths:
        key = str(path).split('?', 1)[0]
        by_path[key] = by_path.get(key, 0) + 1
    return {
        'stt': transcribe_calls + cassette_plays,
        'llm': sum(by_path.values()),
        'stt_by_site': {'fast_finish': transcribe_calls, 'cassette': cassette_plays},
        'llm_by_path': dict(sorted(by_path.items())),
    }


def measured(ops: Mapping[str, Any], key: str) -> Optional[int]:
    """The run's count for a budget key (``vendor_calls`` keys by their own name), or None when not counted."""
    if key in VENDOR_KEYS:
        value = (ops.get('vendor_calls') or {}).get(key)
    else:
        value = ops.get(key)
    return None if value is None else int(value)


def evaluate_budget(key: str, cap: int, ops: Optional[Mapping[str, Any]]) -> tuple[bool, str, Optional[int]]:
    """``(ok, detail, count)`` for one budget key."""
    count = measured(ops or {}, key)
    if count is None:
        return False, f'{key} not counted', None
    if count > cap:
        return False, f'{key}={count} (budget {cap})', count
    return True, f'{key}={count} (budget {cap})', count


def table_rows(ops: Optional[Mapping[str, Any]], budget: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``[{"key", "count", "budget", "ok"}]`` for the web view and the text report."""
    if not ops:
        return []
    caps = dict(budget or {})
    vendor_caps = dict(caps.pop('vendor_calls', None) or {})
    rows = []
    for key in (*BUDGET_KEYS, *VENDOR_KEYS):
        count = measured(ops, key)
        cap = vendor_caps.get(key) if key in VENDOR_KEYS else caps.get(key)
        rows.append(
            {
                'key': key if key not in VENDOR_KEYS else f'vendor {key}',
                'count': count,
                'budget': cap,
                'ok': None if cap is None or count is None else count <= cap,
            }
        )
    return rows
