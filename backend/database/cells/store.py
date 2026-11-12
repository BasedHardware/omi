"""Doc-mode space transactions; adapted from jobstore/postgres_store.py strict 2PL.

Bodies are retried and must be pure: no external calls. The sole flush path holds
all document locks before allocating from the space head, which remains locked to
commit. Domain adapters register separately; this library has no serving callers.
"""

from __future__ import annotations

import random
import time
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Generic, TypeVar

from database.cells.errors import BaseRevisionMismatch, CellContentionExhausted, MutationIdReused
from database.cells.errors import CellWriteError as CellWriteError
from database.jobstore.codec import dumps
from database.jobstore.connection import Pool
from database.cells._validation import validate_address, validate_document, validate_id
from database.cells.feed import Feed
from database.cells.purge import Purge
from database.cells.purge import lock_writable_space
from database.cells.receipts import Receipts

T = TypeVar('T')
MAX_SERIALIZATION_RETRIES = 8
LOCK_TIMEOUT = '2s'


@dataclass
class RunResult(Generic[T]):
    value: T
    replayed: dict[str, int]


@dataclass
class _Mutation:
    entity: str
    entity_id: str
    doc: dict[str, Any] | None
    feed: bool
    expected_rev: int | None
    client_mutation_id: str | None
    fingerprint: str | None
    author_uid: str

    @property
    def op(self) -> str:
        return 'delete' if self.doc is None else 'upsert'

    @property
    def receipt_fingerprint(self) -> str:
        # Bind caller semantics to the address/op without retaining document content.
        return sha256(dumps((self.entity, self.entity_id, self.op, self.fingerprint)).encode()).hexdigest()


class CellTransaction:
    """Buffered, retried space view. Reads lock rows (or missing keys) to commit."""

    def __init__(self, conn: Any, space_id: str, actor_uid: str, now: float):
        self.conn = conn
        self.space_id = space_id
        self.actor_uid = actor_uid
        self.now = now
        self.cache: dict[tuple[str, str], tuple[int, dict[str, Any]] | None] = {}
        self.mutations: list[_Mutation] = []

    def _lock_read(self, entity: str, entity_id: str) -> tuple[int, dict[str, Any]] | None:
        address = (entity, entity_id)
        if address not in self.cache:
            args = (self.space_id, entity, entity_id)
            sql = 'SELECT rev, doc FROM cell_docs WHERE space_id=%s AND entity=%s AND entity_id=%s FOR UPDATE'
            row = self.conn.execute(sql, args).fetchone()
            if row is None:
                # Unambiguous tuple encoding: entity ids may contain slashes.
                self.conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (dumps(args),))
                row = self.conn.execute(sql, args).fetchone()
            self.cache[address] = row
        return self.cache[address]

    def get(self, entity: str, entity_id: str) -> dict[str, Any]:
        validate_address(entity, entity_id)
        row = self._lock_read(entity, entity_id)
        for mutation in reversed(self.mutations):
            if (mutation.entity, mutation.entity_id) == (entity, entity_id):
                return deepcopy(mutation.doc) if mutation.doc is not None else {}
        return deepcopy(row[1]) if row is not None else {}

    def get_with_rev(self, entity: str, entity_id: str) -> tuple[int, dict[str, Any]] | None:
        validate_address(entity, entity_id)
        return deepcopy(self._lock_read(entity, entity_id))

    def receipt_seq(self, client_mutation_id: str) -> int | None:
        if not client_mutation_id or '\x00' in client_mutation_id:
            raise ValueError('client_mutation_id must be nonempty without NUL')
        row = self.conn.execute(
            'SELECT seq FROM mutation_receipts WHERE space_id=%s AND client_mutation_id=%s',
            (self.space_id, client_mutation_id),
        ).fetchone()
        return row[0] if row else None

    def seq_as_of(self, entity: str, entity_id: str, ts: float) -> int | None:
        validate_address(entity, entity_id)
        return self.conn.execute(
            'SELECT max(seq) FROM change_log ' 'WHERE space_id=%s AND entity=%s AND entity_id=%s AND committed_at<=%s',
            (self.space_id, entity, entity_id, ts),
        ).fetchone()[0]

    def _buffer(
        self,
        entity: str,
        entity_id: str,
        doc: dict[str, Any] | None,
        *,
        feed: bool = True,
        expected_rev: int | None = None,
        client_mutation_id: str | None = None,
        fingerprint: str | None = None,
        author_uid: str | None = None,
    ) -> None:
        validate_address(entity, entity_id)
        author = self.actor_uid if author_uid is None else author_uid
        validate_id(author)
        if client_mutation_id is not None:
            if not client_mutation_id or '\x00' in client_mutation_id or fingerprint is None:
                raise ValueError('client_mutation_id requires a fingerprint and a nonempty id without NUL')
        self.mutations.append(
            _Mutation(
                entity,
                entity_id,
                deepcopy(doc),
                feed,
                expected_rev,
                client_mutation_id,
                fingerprint,
                author,
            )
        )

    def put(
        self,
        entity: str,
        entity_id: str,
        doc: dict[str, Any],
        *,
        feed: bool = True,
        expected_rev: int | None = None,
        client_mutation_id: str | None = None,
        fingerprint: str | None = None,
        author_uid: str | None = None,
    ) -> None:
        validate_document(doc)
        self._buffer(
            entity,
            entity_id,
            doc,
            feed=feed,
            expected_rev=expected_rev,
            client_mutation_id=client_mutation_id,
            fingerprint=fingerprint,
            author_uid=author_uid,
        )

    def delete(
        self,
        entity: str,
        entity_id: str,
        *,
        feed: bool = True,
        expected_rev: int | None = None,
        client_mutation_id: str | None = None,
        fingerprint: str | None = None,
        author_uid: str | None = None,
    ) -> None:
        self._buffer(
            entity,
            entity_id,
            None,
            feed=feed,
            expected_rev=expected_rev,
            client_mutation_id=client_mutation_id,
            fingerprint=fingerprint,
            author_uid=author_uid,
        )

    def flush(self) -> dict[str, int]:
        if self.mutations:
            # Match body reads (including typed adapters): document/missing-key
            # locks first, then the admission/sequence head through commit. Lock
            # buffered-only writes too, before replay checks take the head.
            for address in sorted({(m.entity, m.entity_id) for m in self.mutations}):
                self._lock_read(*address)
            # Also guard replay-only writes; no implicit enrollment on this path.
            lock_writable_space(self.conn, self.space_id)
        ids = [m.client_mutation_id for m in self.mutations if m.client_mutation_id is not None]
        receipts = {}
        if ids:
            receipts = {
                r[0]: r[1:]
                for r in self.conn.execute(
                    'SELECT client_mutation_id, seq, fingerprint FROM mutation_receipts '
                    'WHERE space_id=%s AND client_mutation_id=ANY(%s)',
                    (self.space_id, ids),
                ).fetchall()
            }
        replayed: dict[str, int] = {}
        pending: dict[tuple[str, str], _Mutation] = {}
        seen: dict[str, _Mutation] = {}
        for mutation in self.mutations:
            mid = mutation.client_mutation_id
            if mid is not None:
                if mid in receipts:
                    seq, fingerprint = receipts[mid]
                    if fingerprint != mutation.receipt_fingerprint:
                        raise MutationIdReused(self.space_id, mid)
                    replayed[mid] = seq
                    continue
                if mid in seen and seen[mid] != mutation:
                    raise MutationIdReused(self.space_id, mid)
                seen[mid] = mutation
            address = (mutation.entity, mutation.entity_id)
            previous = pending.get(address)
            # One log row cannot retain two different replay receipts. Refuse rather
            # than silently forgetting a mutation id while coalescing.
            if previous is not None and previous.client_mutation_id is not None and previous != mutation:
                raise ValueError('coalesced writes cannot discard a client mutation receipt')
            pending[address] = mutation
        for address in sorted(pending):
            row = self._lock_read(*address)
            expected = pending[address].expected_rev
            if expected is not None and (row is None or row[0] != expected):
                raise BaseRevisionMismatch(self.space_id, row[0] if row is not None else None)
        if not pending:
            return replayed
        count = len(pending)
        # flush already owns the space-head lock. Sample the database clock here,
        # after contention, and advance monotonically even if that clock recedes.
        # Caller `now` remains event/retention time, never revision authority.
        head, _epoch, revision_us = self.conn.execute(
            'UPDATE space_heads SET next_seq=next_seq+%s, updated_at=%s, '
            'revision_us=greatest((extract(epoch FROM clock_timestamp())*1000000)::bigint, revision_us+1) '
            'WHERE space_id=%s AND NOT tombstoned RETURNING next_seq, epoch, revision_us',
            (count, self.now, self.space_id),
        ).fetchone()
        # Integer microseconds round-trip through datetime tokens without
        # accumulating floating-point drift during logical clock advances.
        committed_at = revision_us / 1_000_000
        for seq, address in enumerate(sorted(pending), head - count + 1):
            mutation = pending[address]
            if mutation.doc is None:
                self.conn.execute(
                    'DELETE FROM cell_docs WHERE space_id=%s AND entity=%s AND entity_id=%s', (self.space_id, *address)
                )
            else:
                self.conn.execute(
                    'INSERT INTO cell_docs (space_id, entity, entity_id, author_id, rev, doc, updated_at) '
                    'VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT (space_id, entity, entity_id) DO UPDATE '
                    'SET author_id=EXCLUDED.author_id, rev=EXCLUDED.rev, doc=EXCLUDED.doc, '
                    'updated_at=EXCLUDED.updated_at',
                    (self.space_id, *address, mutation.author_uid, seq, dumps(mutation.doc), committed_at),
                )
            self.conn.execute(
                'INSERT INTO change_log (space_id, seq, entity, entity_id, op, rev, actor_uid, '
                'client_mutation_id, fingerprint, feed, ts, committed_at) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (
                    self.space_id,
                    seq,
                    *address,
                    mutation.op,
                    seq,
                    self.actor_uid,
                    mutation.client_mutation_id,
                    mutation.fingerprint,
                    mutation.feed,
                    self.now,
                    committed_at,
                ),
            )
            if mutation.client_mutation_id is not None:
                self.conn.execute(
                    'INSERT INTO mutation_receipts (space_id, client_mutation_id, seq, fingerprint, created_at) '
                    'VALUES (%s,%s,%s,%s,%s)',
                    (self.space_id, mutation.client_mutation_id, seq, mutation.receipt_fingerprint, self.now),
                )
        return replayed


class CellStore(Feed, Purge, Receipts):
    def __init__(self, pool: Pool):
        self.pool = pool

    def enroll_space(self, space_id: str, *, now: float) -> None:
        """Enrollment/backfill only. Never revive a previously wiped identity."""
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                'INSERT INTO space_heads (space_id, next_seq, epoch, updated_at) VALUES (%s,0,1,%s) '
                'ON CONFLICT (space_id) DO NOTHING',
                (space_id, now),
            )
            lock_writable_space(conn, space_id)

    def run(self, space_id: str, body: Callable[[CellTransaction], T], *, actor_uid: str, now: float) -> RunResult[T]:
        validate_id(space_id)
        validate_id(actor_uid)
        last: Exception | None = None
        for attempt in range(MAX_SERIALIZATION_RETRIES):
            if attempt:
                time.sleep(random.uniform(0, min(0.2, 0.005 * 2**attempt)))
            try:
                with self.pool.connection() as conn, conn.transaction():
                    conn.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                    conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                    tx = CellTransaction(conn, space_id, actor_uid, now)
                    value = body(tx)
                    replayed = tx.flush()
                    return RunResult(value, replayed)
            except Exception as exc:
                replay_race = (
                    getattr(exc, 'sqlstate', None) == '23505'
                    and getattr(getattr(exc, 'diag', None), 'constraint_name', None) == 'mutation_receipts_pkey'
                )
                if getattr(exc, 'sqlstate', None) not in {'40001', '40P01', '55P03'} and not replay_race:
                    raise
                last = exc
        raise CellContentionExhausted(space_id) from last

    def read_doc(self, space_id: str, entity: str, entity_id: str) -> dict[str, Any]:
        validate_id(space_id)
        validate_address(entity, entity_id)
        with self.pool.connection() as conn:
            row = conn.execute(
                'SELECT doc FROM cell_docs WHERE space_id=%s AND entity=%s AND entity_id=%s',
                (space_id, entity, entity_id),
            ).fetchone()
        return row[0] if row else {}

    def head(self, space_id: str) -> tuple[int, int]:
        validate_id(space_id)
        with self.pool.connection() as conn:
            row = conn.execute('SELECT next_seq, epoch FROM space_heads WHERE space_id=%s', (space_id,)).fetchone()
        return tuple(row) if row else (0, 0)

    def bump_epoch(self, space_id: str, *, now: float) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            lock_writable_space(conn, space_id)
            return conn.execute(
                'UPDATE space_heads SET epoch=epoch+1, updated_at=%s WHERE space_id=%s RETURNING epoch',
                (now, space_id),
            ).fetchone()[0]
