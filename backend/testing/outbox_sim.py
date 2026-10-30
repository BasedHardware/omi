"""In-memory reference model of the contract (b) ``Outbox`` (the ``sim`` leg of the conformance suite).

Same observable semantics as ``database/jobstore/outbox_pg.py``; the point is that the contract is
executable in a form a reader can check without Postgres or Firestore. ``transaction()`` gives
all-or-nothing behaviour for the ``tx=`` enqueue path by snapshotting and restoring.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, Mapping

from database.outbox import Claim, EnqueueResult, OutboxKind, Outcome, SweepCounts


def _token() -> str:
    return uuid.uuid4().hex


class SimOutbox:
    def __init__(
        self,
        kind: OutboxKind,
        *,
        privacy_blocked: Callable[[str, Mapping[str, Any]], bool] | None = None,
        create_wake: Callable[[str, str, float], None] | None = None,
    ):
        self.kind = kind
        self.privacy_blocked = privacy_blocked
        self.create_wake = create_wake
        self.rows: dict[int, dict[str, Any]] = {}
        self._next = 1

    @contextmanager
    def transaction(self) -> Iterator[None]:
        snapshot = (deepcopy(self.rows), self._next)
        try:
            yield
        except BaseException:
            self.rows, self._next = snapshot
            raise

    def _open(self) -> list[dict[str, Any]]:
        return [r for r in self.rows.values() if r['done_at'] is None]

    def _fenced(self, row: dict[str, Any]) -> bool:
        return bool(self.privacy_blocked and self.privacy_blocked(row['owner_id'], row['payload']))

    @staticmethod
    def _close(row: dict[str, Any], reason: str, now: float) -> None:
        row.update(done_at=now, done_reason=reason, lease_token=None, lease_until=0.0)

    def _claim(self, row: dict[str, Any], lease_seconds: float, now: float, wake_token: str) -> Claim:
        row.update(
            lease_token=_token(), lease_until=now + lease_seconds, attempts=row['attempts'] + 1, wake_pending=False
        )
        return Claim(
            self.kind, str(row['id']), row['lease_token'], wake_token, row['attempts'], row['lease_until'],
            row['owner_id'], dict(row['payload']), row['policy_id'],
        )  # fmt: skip

    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, policy_id=None, coalesce='max', tx=None, now):
        result = self._enqueue(dedupe_key, owner_id, payload, available_at, policy_id, coalesce)
        if tx is None and result.wake_token is not None:  # invariant 4: without tx the outbox owns the wake
            self._try_wake(self.rows[int(result.row_id)])
        return result

    def _enqueue(self, dedupe_key, owner_id, payload, available_at, policy_id, coalesce):
        import json

        if len(json.dumps(payload, separators=(',', ':')).encode()) > 4096:
            raise ValueError('outbox payload must be content-free and <= 4 KiB')
        for row in self._open():
            if row['dedupe_key'] == dedupe_key:
                merged = (
                    min(row['available_at'], available_at)
                    if coalesce == 'min'
                    else max(row['available_at'], available_at)
                )
                moved = merged != row['available_at']
                row.update(version=row['version'] + 1, available_at=merged, policy_id=policy_id or row['policy_id'])
                if moved:
                    row.update(wake_token=_token(), wake_pending=True)
                return EnqueueResult(str(row['id']), True, row['wake_token'] if moved else None)
        row = dict(
            id=self._next, dedupe_key=dedupe_key, owner_id=owner_id, payload=dict(payload), policy_id=policy_id,
            available_at=available_at, version=1, attempts=0, wake_token=_token(), lease_token=None, lease_until=0.0,
            done_at=None, done_reason=None, wake_pending=True,
        )  # fmt: skip
        self.rows[self._next] = row
        self._next += 1
        return EnqueueResult(str(row['id']), False, str(row['wake_token']))

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]:
        claims: list[Claim] = []
        for row in sorted(self._open(), key=lambda r: (r['available_at'], r['id'])):
            if len(claims) >= n:
                break
            if row['available_at'] > now or row['lease_until'] > now:
                continue
            if self._fenced(row):
                self._close(row, 'privacy_fenced', now)
                continue
            claims.append(self._claim(row, lease_seconds, now, ''))
        return claims

    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float):
        row = self.rows.get(int(row_id)) if row_id.isdigit() else None
        if row is None or row['done_at'] is not None or row['wake_token'] != wake_token:
            return Outcome.STALE
        if row['lease_until'] > now:
            return Outcome.BUSY
        if self._fenced(row):
            self._close(row, 'privacy_fenced', now)
            return Outcome.DISCARDED
        if row['available_at'] > now:  # not due: this delivery is spent, re-arm under a new token
            row.update(wake_token=_token(), wake_pending=True)
            self._try_wake(row)
            return Outcome.DEFERRED
        return self._claim(row, lease_seconds, now, wake_token)

    def wake(self, row_id: str, wake_token: str) -> None:
        row = self.rows.get(int(row_id)) if row_id.isdigit() else None
        if self.create_wake is None or row is None or row['done_at'] is not None or row['wake_token'] != wake_token:
            return
        self.create_wake(str(row['id']), row['wake_token'], row['available_at'])
        row['wake_pending'] = False

    def _try_wake(self, row: dict[str, Any]) -> bool:
        try:
            self.wake(str(row['id']), row['wake_token'])
            return True
        except Exception:
            return False

    def _held(self, claim: Claim) -> dict[str, Any] | None:
        row = self.rows.get(int(claim.row_id))
        if row is None or row['done_at'] is not None or row['lease_token'] != claim.lease_token:
            return None
        return row

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool:
        row = self._held(claim)
        if row is None or row['lease_until'] <= now:
            return False
        row['lease_until'] = now + lease_seconds
        return True

    def ack(self, claim: Claim, reason: str, *, now: float) -> bool:
        row = self._held(claim)
        if row is None:
            return False
        self._close(row, reason, now)
        return True

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:
        row = self._held(claim)
        if row is None:
            return None
        row.update(
            available_at=available_at,
            wake_token=_token(),
            wake_pending=True,
            lease_token=None,
            lease_until=0.0,
            done_reason=reason,
        )
        self._try_wake(row)
        return row['wake_token']

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        row = self._held(claim)
        if row is None:
            return False
        row.update(lease_token=None, lease_until=0.0, done_reason=reason)
        return True

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts:
        discarded = expired = 0
        to_wake: list[dict[str, Any]] = []
        # Actionable rows only (same predicate as outbox_pg.sweep): healthy woken rows never fill the page.
        candidates = [
            r for r in self._open() if (0 < r['lease_until'] <= now) or (r['wake_pending'] and r['lease_until'] <= now)
        ]
        for row in sorted(candidates, key=lambda r: (r['available_at'], r['id']))[:limit]:
            if self._fenced(row):
                self._close(row, 'privacy_fenced', now)
                discarded += 1
            elif 0 < row['lease_until'] <= now:
                expired += 1
                row.update(lease_token=None, lease_until=0.0, wake_token=_token(), wake_pending=True)
                to_wake.append(row)
            elif row['wake_pending']:
                to_wake.append(row)
        rewoken = errors = 0
        for row in to_wake:
            if self.create_wake is None or self._try_wake(row):
                rewoken += 1
            else:
                errors += 1
        return SweepCounts(rewoken, expired, discarded, errors)
