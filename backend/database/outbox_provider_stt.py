"""Firestore ``Outbox`` (contract (b)) for ``OutboxKind.PROVIDER_STT``; lane 8 owns it (lead ruling 10-19).

One row per provider unit, keyed by its batch segment id, in ``batch_pipeline_{stage}_provider_stt_outbox`` so
dev and prod (which share a Firestore project) never claim each other's rows. The row is the state; a Cloud Task
``pst-{row_id[:32]}-{wake_token}`` is only a wake. Behind ``database.outbox_firestore.FirestoreOutbox`` /
``firestore_outbox`` with the same seam as the enrichment outbox: ``client``, ``privacy_blocked`` and
``create_wake`` are injectable.

Invariants (contract (b)): every mutation after a claim is fenced by ``lease_token``; a stale wake token is
``STALE``; a live foreign lease is ``BUSY``; ``defer`` mints a new wake token; a transactional ``enqueue`` writes
in the caller's transaction and the caller wakes after commit; privacy-fenced rows are discarded at claim and
sweep. A provider unit is admitted exactly once, so a second ``enqueue`` of an open row coalesces with no new wake.
"""

from __future__ import annotations

import random
import re
import time
import uuid
from typing import Any, Callable, Literal, Mapping

from database.outbox import Claim, EnqueueResult, OutboxKind, Outcome, SweepCounts

Row = dict[str, Any]
_ROW_ID = re.compile('[0-9a-f]{64}')
_TOKEN = re.compile('[0-9a-f]{32}')
OPEN, CLOSED = 'open', 'closed'
TASK_PREFIX = 'pst'
# A wake younger than this may still be queued (Cloud Tasks backoff); the sweep leaves it alone.
REWAKE_AFTER_SECONDS = 600.0


def collection_name(stage: str | None = None) -> str:
    if stage is None:
        from utils.sync.stage import current_stage

        stage = current_stage()
    return f'batch_pipeline_{stage}_provider_stt_outbox'


def task_name(row_id: str, wake_token: str) -> str:
    return f'{TASK_PREFIX}-{row_id[:32]}-{wake_token}'


def _new_row(row_id: str, owner_id: str, available_at: float, policy_id: str | None, now: float) -> Row:
    return {
        'kind': OutboxKind.PROVIDER_STT.value,
        'segment_id': row_id,
        'owner_id': owner_id,
        'state': OPEN,
        'due_at': available_at,
        'task_token': uuid.uuid4().hex,
        'woken_at': now,
        'lease_token': None,
        'lease_until': 0.0,
        'attempts': 0,
        'policy_id': policy_id,
        'created_at': now,
        'closed_reason': None,
    }


def _claim(row: Mapping[str, Any]) -> Claim:
    return Claim(
        kind=OutboxKind.PROVIDER_STT,
        row_id=row['segment_id'],
        lease_token=row['lease_token'],
        wake_token=row['task_token'],
        attempt=int(row['attempts']),
        lease_until=float(row['lease_until']),
        owner_id=row['owner_id'],
        payload={'segment_id': row['segment_id']},
        policy_id=row.get('policy_id'),
    )


def _holds(row: Mapping[str, Any] | None, claim: Claim) -> bool:
    return bool(
        row
        and row.get('state') == OPEN
        and row.get('lease_token') == claim.lease_token
        and row.get('task_token') == claim.wake_token
    )


def _default_wake(row_id: str, wake_token: str, available_at: float) -> None:
    from utils.provider_stt_tasks import create_wake

    create_wake(row_id, wake_token, due_at=available_at)


class FirestoreProviderSttOutbox:
    kind = OutboxKind.PROVIDER_STT

    def __init__(
        self,
        client: Any = None,
        *,
        privacy_blocked: Callable[[str, Mapping[str, Any]], bool] | None = None,
        create_wake: Callable[[str, str, float], None] | None = None,
        collection: str | None = None,
    ):
        self._bound_client = client
        self._privacy_blocked = privacy_blocked
        self._create_wake = create_wake or _default_wake
        self._collection = collection

    # --- plumbing -------------------------------------------------------------------------------
    def _client(self) -> Any:
        if self._bound_client is not None:
            return self._bound_client
        from database._client import get_data_plane_firestore_client

        return get_data_plane_firestore_client()

    def _ref(self, row_id: str, client: Any = None) -> Any:
        return (client or self._client()).collection(self._collection or collection_name()).document(row_id)

    def _mutate(self, row_id: str, operation: Callable[[Row | None], tuple[Row | None, Any]]) -> Any:
        """Optimistic CAS on one document, as the enrichment outbox does (fenced by update time)."""
        from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
        from google.cloud import firestore

        ref = self._ref(row_id)
        for attempt in range(10):
            snapshot = ref.get()
            old = snapshot.to_dict() if snapshot.exists else None
            new, result = operation(old)
            if new == old:
                return result
            try:
                if old is None:
                    ref.create(new)
                else:
                    ref.update(new, option=firestore.LastUpdateOption(snapshot.update_time))
                return result
            except (AlreadyExists, FailedPrecondition, NotFound):
                if attempt == 9:
                    raise
                time.sleep(random.uniform(0.005, min(0.2, 0.01 * 2**attempt)))
        raise AssertionError('provider-stt outbox CAS must return or raise within its retry budget')

    def _wake(self, row: Mapping[str, Any]) -> None:
        self._create_wake(row['segment_id'], row['task_token'], float(row['due_at']))

    def _blocked(self, row_id: str, owner_id: str) -> bool:
        if self._privacy_blocked is not None:
            # Contract (b) seam: (owner_id, payload). Provider rows carry no conversation in the payload.
            return self._privacy_blocked(owner_id, {'segment_id': row_id})
        from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

        client = self._client()
        try:
            # Plain reads: an unstarted transaction raises 'Transaction not in progress' on real Firestore.
            assert_batch_write_allowed(client, None, owner_id)
        except BatchPrivacyBlocked:
            return True
        return False

    @staticmethod
    def _close(row: Mapping[str, Any], reason: str) -> Row:
        return {**row, 'state': CLOSED, 'closed_reason': reason, 'lease_token': None, 'lease_until': 0.0}

    # --- producers ------------------------------------------------------------------------------
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
        if not _ROW_ID.fullmatch(dedupe_key) or payload.get('segment_id') != dedupe_key:
            raise ValueError('provider-stt dedupe_key must be the batch segment id')

        def upsert(old: Row | None) -> tuple[Row | None, tuple[bool, Row]]:
            if old is not None and old.get('state') == OPEN:
                due = min(old['due_at'], available_at) if coalesce == 'min' else max(old['due_at'], available_at)
                return {**old, 'due_at': due}, (True, old)
            row = _new_row(dedupe_key, owner_id, available_at, policy_id, now)
            return row, (False, row)

        if tx is None:
            coalesced, row = self._mutate(dedupe_key, upsert)
        else:
            transaction = getattr(tx, 'transaction', tx)  # a batch FirestoreTransaction or a raw one
            ref = self._ref(dedupe_key, getattr(tx, 'client', None))
            snapshot = ref.get(transaction=transaction)
            old = snapshot.to_dict() if snapshot.exists else None
            new, (coalesced, row) = upsert(old)
            if new != old:
                transaction.set(ref, new)
        token = None if coalesced else row['task_token']
        if token and tx is None:
            try:
                self._wake(row)
            except Exception:
                pass  # The row is durable; sweep re-wakes it (invariant 4).
        return EnqueueResult(row_id=dedupe_key, coalesced=coalesced, wake_token=token)

    def wake(self, row_id: str, wake_token: str) -> None:
        snapshot = self._ref(row_id).get()
        row = snapshot.to_dict() if snapshot.exists else None
        if row and row.get('state') == OPEN and row.get('task_token') == wake_token:
            self._wake(row)  # Named task: AlreadyExists counts as success.

    # --- consumers ------------------------------------------------------------------------------
    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float) -> Claim | Outcome:
        if not _ROW_ID.fullmatch(row_id) or not _TOKEN.fullmatch(wake_token):
            raise ValueError('invalid provider-stt task binding')
        snapshot = self._ref(row_id).get()
        current = snapshot.to_dict() if snapshot.exists else None
        if current and current.get('state') == OPEN and self._blocked(row_id, current['owner_id']):
            self._mutate(row_id, lambda old: (self._close(old, 'privacy_blocked') if old else old, None))
            return Outcome.DISCARDED
        lease_token = uuid.uuid4().hex

        def claim(old: Row | None) -> tuple[Row | None, tuple[Outcome | None, Row | None]]:
            if old is None or old.get('state') != OPEN or old.get('task_token') != wake_token:
                return old, (Outcome.STALE, None)
            if old.get('lease_until', 0) > now:
                return old, (Outcome.BUSY, None)
            if old['due_at'] > now:
                row = {**old, 'task_token': uuid.uuid4().hex, 'woken_at': now}
                return row, (Outcome.DEFERRED, row)
            row = {
                **old,
                'lease_token': lease_token,
                'lease_until': now + lease_seconds,
                'attempts': old['attempts'] + 1,
            }
            return row, (None, row)

        outcome, row = self._mutate(row_id, claim)
        if outcome is Outcome.DEFERRED:
            self._wake(row)
            return outcome
        if outcome is not None:
            return outcome
        return _claim(row)

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]:
        """Pull: due, unleased open rows (single-field filter; lease checked by the CAS)."""
        from google.cloud.firestore_v1 import FieldFilter

        query = (
            self._client()
            .collection(self._collection or collection_name())
            .where(filter=FieldFilter('state', '==', OPEN))
            .limit(max(1, min(n * 4, 200)))
        )
        claims: list[Claim] = []
        for snapshot in query.stream():
            row = snapshot.to_dict() or {}
            if row.get('due_at', 0) > now or row.get('lease_until', 0) > now:
                continue
            claimed = self.claim_key(snapshot.id, row['task_token'], lease_seconds, now=now)
            if isinstance(claimed, Claim):
                claims.append(claimed)
                if len(claims) >= n:
                    break
        return claims

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool:
        def renew(old: Row | None) -> tuple[Row | None, bool]:
            if not _holds(old, claim) or old['lease_until'] <= now:  # type: ignore[index]
                return old, False
            return {**old, 'lease_until': now + lease_seconds}, True  # type: ignore[dict-item]

        return self._mutate(claim.row_id, renew)

    def ack(self, claim: Claim, reason: str, *, now: float) -> bool:
        def close(old: Row | None) -> tuple[Row | None, bool]:
            if not _holds(old, claim):
                return old, False
            return {**self._close(old, reason[:40]), 'closed_at': now}, True  # type: ignore[arg-type]

        return self._mutate(claim.row_id, close)

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:
        def rearm(old: Row | None) -> tuple[Row | None, Row | None]:
            if not _holds(old, claim):
                return old, None
            row = {
                **old,  # type: ignore[dict-item]
                'due_at': available_at,
                'task_token': uuid.uuid4().hex,
                'woken_at': now,
                'lease_token': None,
                'lease_until': 0.0,
                'deferred_reason': reason[:40],
            }
            return row, row

        row = self._mutate(claim.row_id, rearm)
        if row is None:
            return None
        self._wake(row)
        return row['task_token']

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        def drop(old: Row | None) -> tuple[Row | None, bool]:
            if not _holds(old, claim):
                return old, False
            return {**old, 'lease_token': None, 'lease_until': 0.0}, True  # type: ignore[dict-item]

        return self._mutate(claim.row_id, drop)

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts:
        """Re-wake due open rows whose lease is absent or expired; discard privacy-fenced rows."""
        from google.cloud.firestore_v1 import FieldFilter

        rewoken = expired = discarded = errors = 0
        query = (
            self._client()
            .collection(self._collection or collection_name())
            .where(filter=FieldFilter('state', '==', OPEN))
            .limit(max(1, min(limit, 500)))
        )
        for snapshot in query.stream():
            row = snapshot.to_dict() or {}
            try:
                if self._blocked(snapshot.id, row['owner_id']):
                    self._mutate(snapshot.id, lambda old: (self._close(old, 'privacy_blocked') if old else old, None))
                    discarded += 1
                    continue
                if (
                    row.get('due_at', 0) > now
                    or row.get('lease_until', 0) > now
                    or now - float(row.get('woken_at') or 0) < REWAKE_AFTER_SECONDS
                ):
                    continue
                if row.get('lease_token'):
                    expired += 1

                def rearm(old: Row | None) -> tuple[Row | None, Row | None]:
                    if not old or old.get('state') != OPEN or old.get('lease_until', 0) > now:
                        return old, None
                    fresh = {
                        **old,
                        'task_token': uuid.uuid4().hex,
                        'woken_at': now,
                        'lease_token': None,
                        'lease_until': 0.0,
                    }
                    return fresh, fresh

                fresh = self._mutate(snapshot.id, rearm)
                if fresh is not None:
                    self._wake(fresh)
                    rewoken += 1
            except Exception:
                errors += 1
        return SweepCounts(rewoken=rewoken, expired_leases=expired, discarded=discarded, errors=errors)
