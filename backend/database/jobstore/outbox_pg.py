"""Contract (b): the Postgres ``Outbox`` (one table, every ``OutboxKind``; see migration 0002).

The row is the source of truth; a Cloud Task is only a wake. Semantics (conformance-tested in
``tests/integration/test_outbox_conformance.py`` against the same invariants as the Firestore one):

- ``enqueue`` coalesces on an OPEN ``(kind, dedupe_key)`` row (partial unique index): version + 1 and
  ``available_at`` folds with min or max. It returns a fresh ``wake_token`` only when a task has to be
  (re)created, i.e. a new row or a moved ``available_at``; the old token then goes stale. With ``tx`` the
  row is written inside the caller's ``PostgresStore`` transaction, so it commits or rolls back with it.
- ``claim`` is ``FOR UPDATE SKIP LOCKED``; ``claim_key`` serves a task delivery (STALE on a wrong token,
  BUSY on a live foreign lease). Every later call carries the ``lease_token`` minted at claim.
- The outbox OWNS wake creation (lead ruling, 10-19): ``defer`` and a not-due ``claim_key`` re-arm the row
  under a new wake token, create the task through the injected ``create_wake`` hook after commit, and a
  not-due delivery returns ``Outcome.DEFERRED`` (``run_push`` maps that to 200). Transactional enqueuers call
  ``wake(row_id, wake_token)`` after their own commit; it is idempotent on ``(row_id, wake_token)``.
- A token stays ``wake_pending`` until its task create succeeded. ``enqueue`` without ``tx`` creates its own
  wake after commit. ``sweep`` pages only actionable rows: it re-arms expired leases under a new token,
  retries every pending wake, and closes the privacy-fenced rows among them. A hook error is counted, never
  raised, and leaves the row pending for the next sweep (invariant 4: durable before wake).

Time is always the caller's ``now`` (epoch seconds), never the database clock.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Literal, Mapping

from database.jobstore.postgres_store import PostgresStore, PostgresTransaction, jsonb
from database.outbox import Claim, EnqueueResult, OutboxKind, Outcome, SweepCounts

MAX_PAYLOAD_BYTES = 4096
PrivacyProbe = Callable[[str, Mapping[str, Any]], bool]  # (owner_id, payload) -> True when fenced
WakeHook = Callable[[str, str, float], None]  # create the Cloud Task: (row_id, wake_token, available_at)

_COLUMNS = 'id, owner_id, payload, policy_id, available_at, attempts, wake_token, lease_token, lease_until'


def _token() -> str:
    return uuid.uuid4().hex


class PostgresOutbox:
    def __init__(
        self,
        kind: OutboxKind,
        store: PostgresStore,
        *,
        privacy_blocked: PrivacyProbe | None = None,
        create_wake: WakeHook | None = None,
    ):
        self.kind = kind
        self.store = store
        self.privacy_blocked = privacy_blocked
        self.create_wake = create_wake

    # -- helpers --------------------------------------------------------------------------------
    def _claim_from(self, row: tuple, wake_token: str) -> Claim:
        row_id, owner_id, payload, policy_id, _available, attempts, _wake, lease_token, lease_until = row
        return Claim(
            kind=self.kind,
            row_id=str(row_id),
            lease_token=lease_token,
            wake_token=wake_token,
            attempt=attempts,
            lease_until=lease_until,
            owner_id=owner_id,
            payload=payload,
            policy_id=policy_id,
        )

    def _fenced(self, owner_id: str, payload: Mapping[str, Any]) -> bool:
        return bool(self.privacy_blocked and self.privacy_blocked(owner_id, payload))

    def _close(self, conn: Any, row_id: int, reason: str, now: float) -> None:
        conn.execute(
            'UPDATE outbox SET done_at = %s, done_reason = %s, lease_token = NULL, lease_until = 0 WHERE id = %s',
            (now, reason, row_id),
        )

    # -- Outbox ---------------------------------------------------------------------------------
    def enqueue(
        self,
        dedupe_key: str,
        owner_id: str,
        payload: Mapping[str, Any],
        available_at: float,
        *,
        policy_id: str | None = None,
        coalesce: Literal['min', 'max'] = 'max',
        tx: Any = None,
        now: float,
    ) -> EnqueueResult:
        if len(json.dumps(payload, separators=(',', ':')).encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError('outbox payload must be content-free and <= 4 KiB')
        if tx is not None:
            if not isinstance(tx, PostgresTransaction):
                raise TypeError('a Postgres outbox enqueues only inside a PostgresStore transaction')
            return self._enqueue(tx.conn, dedupe_key, owner_id, payload, available_at, policy_id, coalesce, now)
        with self.store.pool.connection() as conn, conn.transaction():
            result = self._enqueue(conn, dedupe_key, owner_id, payload, available_at, policy_id, coalesce, now)
        # Contract (b) invariant 4: without tx the outbox owns the wake. The row is committed first; a failed
        # task create leaves it wake_pending for the sweep, and callers never call wake() themselves.
        if result.wake_token is not None:
            self._try_wake(result.row_id, result.wake_token)
        return result

    def _enqueue(
        self, conn: Any, dedupe_key: str, owner_id: str, payload: Any, available_at: float, policy_id, coalesce, now
    ) -> EnqueueResult:
        namespace = self.store.namespace
        for _ in range(3):  # a concurrent insert of the same open key makes the INSERT a no-op: re-read
            row = conn.execute(
                'SELECT id, available_at FROM outbox WHERE namespace = %s AND kind = %s AND dedupe_key = %s '
                'AND done_at IS NULL FOR UPDATE',
                (namespace, self.kind.value, dedupe_key),
            ).fetchone()
            if row is not None:
                row_id, existing = row
                merged = min(existing, available_at) if coalesce == 'min' else max(existing, available_at)
                moved = merged != existing
                wake_token = _token() if moved else None
                conn.execute(
                    'UPDATE outbox SET version = version + 1, available_at = %s, wake_token = coalesce(%s, wake_token), '
                    'wake_pending = wake_pending OR %s, policy_id = coalesce(%s, policy_id) WHERE id = %s',
                    (merged, wake_token, moved, policy_id, row_id),
                )
                return EnqueueResult(row_id=str(row_id), coalesced=True, wake_token=wake_token)
            wake_token = _token()
            inserted = conn.execute(
                'INSERT INTO outbox (namespace, kind, dedupe_key, owner_id, payload, policy_id, available_at, '
                'wake_token, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) '
                'ON CONFLICT (namespace, kind, dedupe_key) WHERE done_at IS NULL DO NOTHING RETURNING id',
                (
                    namespace,
                    self.kind.value,
                    dedupe_key,
                    owner_id,
                    jsonb(dict(payload)),
                    policy_id,
                    available_at,
                    wake_token,
                    now,
                ),
            ).fetchone()
            if inserted is not None:
                return EnqueueResult(row_id=str(inserted[0]), coalesced=False, wake_token=wake_token)
        raise RuntimeError('outbox enqueue kept racing another writer')

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]:
        claims: list[Claim] = []
        with self.store.pool.connection() as conn, conn.transaction():
            while len(claims) < n:
                rows = conn.execute(
                    'SELECT id, owner_id, payload FROM outbox WHERE namespace = %s AND kind = %s AND done_at IS NULL '
                    'AND available_at <= %s AND lease_until <= %s ORDER BY available_at, id LIMIT %s '
                    'FOR UPDATE SKIP LOCKED',
                    (self.store.namespace, self.kind.value, now, now, n - len(claims)),
                ).fetchall()
                if not rows:
                    break
                for row_id, owner_id, payload in rows:
                    if self._fenced(owner_id, payload):
                        self._close(conn, row_id, 'privacy_fenced', now)
                        continue
                    taken = conn.execute(
                        f'UPDATE outbox SET lease_token = %s, lease_until = %s, attempts = attempts + 1, '
                        f'wake_pending = false WHERE id = %s RETURNING {_COLUMNS}',
                        (_token(), now + lease_seconds, row_id),
                    ).fetchone()
                    claims.append(self._claim_from(taken, ''))
        return claims

    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float) -> Claim | Outcome:
        try:
            numeric = int(row_id)
        except ValueError:
            return Outcome.STALE
        rearmed: tuple[str, float] | None = None
        taken: tuple | None = None
        with self.store.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                f'SELECT {_COLUMNS}, done_at FROM outbox WHERE id = %s AND namespace = %s AND kind = %s FOR UPDATE',
                (numeric, self.store.namespace, self.kind.value),
            ).fetchone()
            if row is None or row[-1] is not None or row[6] != wake_token:
                return Outcome.STALE
            if row[8] > now:
                return Outcome.BUSY
            if self._fenced(row[1], row[2]):
                self._close(conn, numeric, 'privacy_fenced', now)
                return Outcome.DISCARDED
            if row[4] > now:  # not due: this delivery is spent, re-arm under a new token
                fresh = _token()
                conn.execute('UPDATE outbox SET wake_token = %s, wake_pending = true WHERE id = %s', (fresh, numeric))
                rearmed = (fresh, row[4])
            else:
                taken = conn.execute(
                    f'UPDATE outbox SET lease_token = %s, lease_until = %s, attempts = attempts + 1, '
                    f'wake_pending = false WHERE id = %s RETURNING {_COLUMNS}',
                    (_token(), now + lease_seconds, numeric),
                ).fetchone()
        if rearmed is not None:
            self._try_wake(str(numeric), rearmed[0])
            return Outcome.DEFERRED
        assert taken is not None
        return self._claim_from(taken, wake_token)

    def wake(self, row_id: str, wake_token: str) -> None:
        """Create the task for ``(row_id, wake_token)``; idempotent, a no-op for a stale token or closed row.

        Callers that enqueue inside a store transaction call this after their commit. Errors propagate so the
        caller can log; the row stays ``wake_pending`` and ``sweep`` retries it.
        """
        if self.create_wake is None:
            return
        try:
            numeric = int(row_id)
        except ValueError:
            return
        # The task create is an RPC: never hold one of the pool's few connections across it.
        with self.store.pool.connection() as conn:
            row = conn.execute(
                'SELECT available_at FROM outbox WHERE id = %s AND namespace = %s AND kind = %s '
                'AND done_at IS NULL AND wake_token = %s',
                (numeric, self.store.namespace, self.kind.value, wake_token),
            ).fetchone()
        if row is None:
            return
        self.create_wake(row_id, wake_token, row[0])
        with self.store.pool.connection() as conn:
            conn.execute(
                'UPDATE outbox SET wake_pending = false WHERE id = %s AND wake_token = %s', (numeric, wake_token)
            )

    def _try_wake(self, row_id: str, wake_token: str) -> bool:
        try:
            self.wake(row_id, wake_token)
            return True
        except Exception:  # left wake_pending: the next sweep retries
            return False

    def _fenced_update(self, claim: Claim, sets: str, params: tuple, *, live: bool = False, now: float = 0.0) -> Any:
        """Run an UPDATE guarded by the claim's lease token; return the RETURNING row or None."""
        guard = 'AND lease_until > %s' if live else ''
        values = (*params, int(claim.row_id), self.store.namespace, claim.lease_token) + ((now,) if live else ())
        with self.store.pool.connection() as conn:
            return conn.execute(
                f'UPDATE outbox SET {sets} WHERE id = %s AND namespace = %s AND lease_token = %s '
                f'AND done_at IS NULL {guard} RETURNING id',
                values,
            ).fetchone()

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool:
        return self._fenced_update(claim, 'lease_until = %s', (now + lease_seconds,), live=True, now=now) is not None

    def ack(self, claim: Claim, reason: str, *, now: float) -> bool:
        return (
            self._fenced_update(
                claim, 'done_at = %s, done_reason = %s, lease_token = NULL, lease_until = 0', (now, reason)
            )
            is not None
        )

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:
        wake_token = _token()
        done = self._fenced_update(
            claim,
            'available_at = %s, wake_token = %s, wake_pending = true, lease_token = NULL, lease_until = 0, '
            'done_reason = %s',
            (available_at, wake_token, reason),
        )
        if done is None:
            return None
        self._try_wake(claim.row_id, wake_token)
        return wake_token

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        return (
            self._fenced_update(claim, 'lease_token = NULL, lease_until = 0, done_reason = %s', (reason,)) is not None
        )

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts:
        """Re-arm expired leases and retry pending wakes; privacy-fenced rows among them are closed instead.

        Only actionable rows fill the page: an expired lease, or an unleased row whose wake is still pending.
        A backlog of healthy, already-woken rows therefore cannot crowd them out (M1 L12-2); those rows are
        closed on delivery, where ``claim`` and ``claim_key`` run the same privacy probe. The probe runs before
        any row lock, and the locked pass re-checks the predicate, so claims never wait behind it.
        """
        discarded = expired = 0
        to_wake: list[tuple[str, str]] = []
        actionable = '((lease_until > 0 AND lease_until <= %s) OR (wake_pending AND lease_until <= %s))'
        with self.store.pool.connection() as conn:
            candidates = conn.execute(
                f'SELECT id, owner_id, payload FROM outbox WHERE namespace = %s AND kind = %s AND done_at IS NULL '
                f'AND {actionable} ORDER BY available_at, id LIMIT %s',
                (self.store.namespace, self.kind.value, now, now, limit),
            ).fetchall()
        if not candidates:
            return SweepCounts(rewoken=0, expired_leases=0, discarded=0, errors=0)
        fenced = {row_id for row_id, owner_id, payload in candidates if self._fenced(owner_id, payload)}
        with self.store.pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                f'SELECT id, lease_until, wake_token, wake_pending FROM outbox WHERE id = ANY(%s) '
                f'AND done_at IS NULL AND {actionable} ORDER BY id FOR UPDATE SKIP LOCKED',
                ([row_id for row_id, _, _ in candidates], now, now),
            ).fetchall()
            for row_id, lease_until, wake_token, pending in rows:
                if row_id in fenced:
                    self._close(conn, row_id, 'privacy_fenced', now)
                    discarded += 1
                elif 0 < lease_until <= now:
                    expired += 1
                    fresh = _token()
                    conn.execute(
                        'UPDATE outbox SET lease_token = NULL, lease_until = 0, wake_token = %s, wake_pending = true '
                        'WHERE id = %s',
                        (fresh, row_id),
                    )
                    to_wake.append((str(row_id), fresh))
                elif pending:
                    to_wake.append((str(row_id), wake_token))
        rewoken = errors = 0
        for row_id, wake_token in to_wake:
            if self.create_wake is None:
                rewoken += 1  # no task transport (pull-only): the row itself is re-armed
            elif self._try_wake(row_id, wake_token):
                rewoken += 1
            else:
                errors += 1
        return SweepCounts(rewoken=rewoken, expired_leases=expired, discarded=discarded, errors=errors)
