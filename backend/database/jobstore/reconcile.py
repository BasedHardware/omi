"""Bounded operator census/backfill and retirement of non-authoritative copies.

Each call visits one key-ordered page, never a whole-table key set. Run both
sources repeatedly: primary pages fill unchanged historical documents; copy
pages retire vanished/excluded documents, including copies that missed their
last TTL-stamping refresh. Expiry and lease clocks NEVER authorize deletion:
only a fresh primary absence or the shared cohort projection does. A present
legal hold therefore remains exactly as the authoritative primary represents it.

Cursors are sensitive operator state: URL-safe base64 JSON is opaque, NOT
encrypted. Persist privately; never include a cursor in public reports/logs.
Exceptions return no new checkpoint. Apply pages commit atomically and can be
retried idempotently from the previous cursor. An end-of-pass observation is
not a snapshot/coverage guarantee while writers are active; schedule rotations.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from google.cloud.firestore_v1.field_path import FieldPath

from database.jobstore.cohort import classify_document, project_document
from database.jobstore.dual_store import MIRRORED_TABLES, DualStore, ShadowParityOutcome, compare, mirrored
from database.jobstore.index_store import connection_deadline

_TYPED = frozenset({'jobs', 'results', 'control'})
_MAX_CURSOR_BYTES = 16384
_MAX_ROWS = 1000


@dataclass
class PageCounts:
    scanned: int = 0
    selected: int = 0
    excluded: int = 0
    unknown_owner: int = 0
    stale: int = 0
    deleted: int = 0  # would retire in dry-run; committed retirements in apply
    matched: int = 0
    copied: int = 0  # committed upserts only; always zero in dry-run
    primary_reads: int = 0
    statements: int = 0


@dataclass
class PageResult:
    counts: PageCounts
    end_of_pass: bool
    cursor: str | None = field(repr=False)

    def public_report(self) -> dict:
        """Counts/progress only, deliberately excluding the sensitive cursor."""
        return {'counts': asdict(self.counts), 'end_of_pass': self.end_of_pass}


def _encode_cursor(namespace: str, source: str, table: str, key: str) -> str:
    raw = json.dumps([1, namespace, source, table, key], separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode('ascii')


def decode_cursor(cursor: object, namespace: str, source: str, table: str) -> str | None:
    if cursor is None:
        return None
    try:
        if not isinstance(cursor, str) or len(cursor) > _MAX_CURSOR_BYTES:
            raise ValueError
        raw = base64.b64decode(cursor.encode('ascii'), altchars=b'-_', validate=True)
        value = json.loads(raw)
        if (
            not isinstance(value, list)
            or len(value) != 5
            or type(value[0]) is not int
            or value[:4] != [1, namespace, source, table]
            or not isinstance(value[4], str)
            or not value[4]
            or '/' in value[4]
            or '\x00' in value[4]
            or len(value[4].encode()) > 1500
        ):
            raise ValueError
        return value[4]
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        # Never echo either the cursor or a decoded customer identifier.
        raise ValueError('invalid reconciliation cursor or scope') from None


class _Budget:
    def __init__(self, seconds: float, primary_reads: int, statements: int, counts: PageCounts):
        self.deadline = time.monotonic() + seconds
        self.max_reads = primary_reads
        self.max_statements = statements
        self.counts = counts

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('reconciliation page deadline exceeded')
        return remaining

    def read(self, count: int) -> float:
        if self.counts.primary_reads + count > self.max_reads:
            raise RuntimeError('reconciliation primary-read budget exhausted')
        self.counts.primary_reads += count
        return self.remaining()

    def statement(self, count: int = 1) -> None:
        if self.counts.statements + count > self.max_statements:
            raise RuntimeError('reconciliation statement budget exhausted')
        self.counts.statements += count
        self.remaining()


class _BoundedConnection:
    """All called store SQL shares one absolute deadline and statement counter."""

    def __init__(self, conn: Any, budget: _Budget):
        self.conn, self.budget = conn, budget

    def execute(self, query, params=None):
        # Both settings are local to this transaction. Refresh before each SQL
        # operation, so N statements cannot each consume the original budget.
        self.budget.statement(2)
        milliseconds = max(1, int(self.budget.remaining() * 1000))
        self.conn.execute(
            "SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
            (str(milliseconds), str(milliseconds)),
        )
        self.budget.remaining()
        return self.conn.execute(query, params) if params is not None else self.conn.execute(query)


def _primary_keys(primary: Any, table: str, after: str | None, limit: int, budget: _Budget) -> list[str]:
    collection = primary.client.collection(f'{primary.namespace}_{table}')
    query = collection.order_by(FieldPath.document_id()).limit(limit)
    if after is not None:
        query = query.start_after({FieldPath.document_id(): collection.document(after)})
    # get() is a single bounded RPC (SDK retries are deliberately disabled).
    snapshots = query.get(timeout=budget.remaining(), retry=None)
    budget.read(len(snapshots))
    return [snapshot.id for snapshot in snapshots]


def _copy_keys(conn: Any, namespace: str, table: str, after: str | None, limit: int) -> list[str]:
    # Table is a closed enum before interpolation; all customer values are bound.
    if table in _TYPED:
        query = f'SELECT key FROM {table} WHERE namespace = %s'
        params: tuple = (namespace,)
    else:
        query = 'SELECT key FROM docs WHERE namespace = %s AND tbl = %s'
        params = (namespace, table)
    if after is not None:
        query += ' AND key COLLATE "C" > %s'
        params += (after,)
    query += ' ORDER BY key COLLATE "C" LIMIT %s'
    return [row[0] for row in conn.execute(query, params + (limit,)).fetchall()]


def _current(primary: Any, keys: list[tuple[str, str]], budget: _Budget) -> dict:
    refs = [primary.client.collection(f'{primary.namespace}_{table}').document(key) for table, key in keys]
    snapshots = primary.client.get_all(refs, timeout=budget.read(len(keys)), retry=None)
    found = {snapshot.reference.path: snapshot.to_dict() or {} for snapshot in snapshots if snapshot.exists}
    budget.remaining()
    return {address: found.get(ref.path, {}) for address, ref in zip(keys, refs)}


def process_page(
    dual: DualStore,
    *,
    source: str,
    table: str,
    cursor: str | None = None,
    max_rows: int = 100,
    max_primary_reads: int = 200,
    max_statements: int = 2000,
    budget_s: float = 10.0,
    apply: bool = False,
) -> PageResult:
    """Reconcile one bounded page; failures raise without publishing a cursor.

    ``source='primary'`` fills historical copies; ``source='copy'`` performs
    the rotating copy census, including vanished primaries and cohort shrink.
    Primary reads include discovery documents AND fresh exact-key rereads.
    Statements include timeout settings and reserved BEGIN/COMMIT controls.
    The caller must prewarm the target pool using its separately bounded
    connection setup; a page never starts credential refresh/cold connection IO.
    """
    if source not in {'primary', 'copy'} or table not in MIRRORED_TABLES:
        raise ValueError('explicit mirrored table and primary/copy source required')
    for value in (max_rows, max_primary_reads, max_statements):
        if type(value) is not int or value <= 0:
            raise ValueError('positive integer reconciliation budgets required')
    if max_rows > _MAX_ROWS or type(budget_s) not in (int, float) or not math.isfinite(budget_s) or budget_s <= 0:
        raise ValueError('invalid reconciliation row or deadline budget')
    namespace = dual.shadow.namespace
    if namespace != dual.primary.namespace:
        raise ValueError('primary and copy namespace mismatch')
    after = decode_cursor(cursor, namespace, source, table)
    counts = PageCounts()
    budget = _Budget(budget_s, max_primary_reads, max_statements, counts)
    limit = min(max_rows, max_primary_reads // (2 if source == 'primary' else 1))
    if limit < 1:
        raise ValueError('primary-read budget cannot cover one row')
    keys = _primary_keys(dual.primary, table, after, limit, budget) if source == 'primary' else None
    with dual.shadow.pool.connection(timeout=budget.remaining(), existing_only=True) as raw:
        with connection_deadline(raw, budget.deadline):
            budget.statement(2)  # reserve BEGIN and COMMIT (or rollback on failure)
            with raw.transaction():
                conn = _BoundedConnection(raw, budget)
                if keys is None:
                    keys = _copy_keys(conn, namespace, table, after, limit)
                if (
                    len(keys) > limit
                    or keys != sorted(set(keys))
                    or (after is not None and any(k <= after for k in keys))
                ):
                    raise RuntimeError('reconciliation source violated ordered page bound')

                def reader(primary, addresses):
                    docs = _current(primary, addresses, budget)
                    for (tbl, key), doc in docs.items():
                        counts.scanned += 1
                        projected = project_document(namespace, tbl, key, doc) if doc else None
                        if doc:
                            disposition = classify_document(namespace, tbl, key, doc)
                            if disposition not in {'selected', 'excluded', 'unknown_owner'}:
                                raise RuntimeError('unknown reconciliation cohort disposition')
                            setattr(counts, disposition, getattr(counts, disposition) + 1)
                        old = dual.shadow.read_doc(conn, tbl, key)
                        desired = mirrored(projected, tbl) if projected else {}
                        outcome = compare(desired, old, tbl)
                        if outcome == ShadowParityOutcome.UNCOMPARABLE:
                            raise ValueError('uncomparable reconciliation document')
                        if outcome == ShadowParityOutcome.MATCH:
                            counts.matched += 1
                        else:
                            counts.stale += 1
                        if not desired and old:
                            counts.deleted += 1
                        elif desired and apply:
                            counts.copied += 1
                    # Preserve authoritative document for copy_current's common
                    # projection boundary; never replace it with an old census image.
                    return docs

                for key in keys:
                    budget.remaining()
                    if apply:
                        dual.copy_current(conn, [(table, key)], reader=reader)
                    else:
                        reader(dual.primary, [(table, key)])
                budget.remaining()  # deadline failure rolls back the entire apply page
    budget.remaining()
    end = len(keys) < limit
    return PageResult(counts, end, None if end else _encode_cursor(namespace, source, table, keys[-1]))
