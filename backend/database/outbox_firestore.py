"""Firestore ``Outbox`` (contract (b)) for ``OutboxKind.ENRICHMENT``, row-compatible with ``sync_reprocess_outbox``.

The row is the state; a Cloud Task is only a wake. Rows keep today's collection, document id
(``key(uid, conversation_id[+'\\0effects'])``), field names and ``sr-`` task names, so rows written by
``utils.enrichment.outbox.mark`` and rows written here are interchangeable, and in-flight rows drain.

Field mapping: ``Claim.lease_token`` is the row's ``owner`` (minted per claim, as ``run`` does today),
``Claim.wake_token`` is ``task_token``, ``Claim.owner_id`` is ``uid``. ``claim_attempts`` and ``policy_id``
are additive fields.

Wakes (lead ruling 10-19): this implementation creates Cloud Tasks itself through the existing
``_enqueue`` (binding checks, demand scheduling, eager effects recovery): after a non-transactional
``enqueue``, on ``defer``, on a not-due ``claim_key`` (returns ``Outcome.DEFERRED``) and on re-armed
``ack``. A transactional ``enqueue`` returns the wake token and the caller calls ``wake`` after commit.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Literal, Mapping

from database.outbox import Claim, EnqueueResult, OutboxKind, Outcome, SweepCounts

_DOCUMENT_ID = re.compile('[0-9a-f]{64}')
_TOKEN = re.compile('[0-9a-f]{32}')
# Scheduling metadata a consumer needs; never transcript or summary content.
_PAYLOAD_FIELDS = (
    'conversation_id',
    'language',
    'effects_only',
    'immediate',
    'version',
    'first_pending_at',
    'summary_deadline_at',
    'summary_lane',
    'summary_seen',
    'summary_repair',
    'summary_expected_revision',
)


def _outbox():
    from utils.enrichment import outbox

    return outbox


def _claim(row: Mapping[str, Any], row_id: str) -> Claim:
    return Claim(
        kind=OutboxKind.ENRICHMENT,
        row_id=row_id,
        lease_token=row['owner'],
        wake_token=row['task_token'],
        attempt=int(row.get('claim_attempts') or 1),
        lease_until=float(row['lease_until']),
        owner_id=row['uid'],
        payload={name: row.get(name) for name in _PAYLOAD_FIELDS},
        policy_id=row.get('policy_id'),
    )


def _holds(row: Mapping[str, Any] | None, claim: Claim) -> bool:
    return bool(
        row
        and not row.get('dormant')
        and row.get('owner') == claim.lease_token
        and row.get('task_token') == claim.wake_token
    )


class FirestoreEnrichmentOutbox:
    kind = OutboxKind.ENRICHMENT

    def __init__(self, client: Any = None):
        # Projection binds its own client so its transactional row and the post-commit wake read one store.
        self._bound_client = client

    def _client(self) -> Any:
        return self._bound_client or _outbox().get_firestore_client()

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
        new_dispatch: Callable[[], dict[str, str] | None] | None = None,
    ) -> EnqueueResult:
        """``new_dispatch`` (Firestore enrichment only) supplies a new row's queue binding, e.g. backfill."""
        outbox = _outbox()
        conversation_id, language = payload['conversation_id'], payload['language']
        effects_only = bool(payload.get('effects_only'))
        if dedupe_key != outbox.key(owner_id, conversation_id + ('\0effects' if effects_only else '')):
            raise ValueError('enrichment dedupe_key must be the outbox key of (owner, conversation)')
        update = outbox.mark_update(
            owner_id,
            conversation_id,
            language,
            current=now,
            settle_at=available_at,
            coalesce=coalesce,
            effects_only=effects_only,
            batch=tx is not None,
            policy_id=policy_id,
            new_dispatch=new_dispatch,
        )
        if tx is None:
            row, coalesced = outbox.mutate_row(dedupe_key, update)
        else:
            row, coalesced = self._mutate_in(tx, dedupe_key, update)
        wake = bool(row.get('_wake', not coalesced)) and outbox.valid_dispatch_binding(row.get('dispatch'))
        if coalesced:
            outbox.COALESCED.inc()
        if not outbox.valid_dispatch_binding(row.get('dispatch')):
            outbox.UNBOUND.labels(action='mark').inc()
        token = row.get('task_token') if wake else None
        if wake and tx is None:
            outbox.wake_row(row)  # Failure leaves the obligation durable for the sweep.
        return EnqueueResult(row_id=dedupe_key, coalesced=coalesced, wake_token=token)

    def _mutate_in(self, tx: Any, document_id: str, update):
        """Read and write the row inside the caller's Firestore transaction (contract (b) invariant 5)."""
        outbox = _outbox()
        transaction = getattr(tx, 'transaction', tx)  # a batch FirestoreTransaction or a raw one
        client = getattr(tx, 'client', None) or self._client()
        ref = client.collection(outbox.COLLECTION).document(document_id)
        snapshot = ref.get(transaction=transaction)
        old = snapshot.to_dict() if snapshot.exists else None
        new, result = update(old)
        if new != old:
            transaction.set(ref, new)
        return result

    def wake(self, row_id: str, wake_token: str) -> None:
        """Create the named task for ``wake_token`` if the row still wants it; repeat calls are harmless."""
        outbox = _outbox()
        snapshot = self._client().collection(outbox.COLLECTION).document(row_id).get()
        row = snapshot.to_dict() if snapshot.exists else None
        if not row or row.get('dormant') or row.get('task_token') != wake_token:
            return  # A newer wake or completion superseded this one.
        if outbox.valid_effects_binding(row):
            outbox.wake_row(row)  # Named task: an existing wake answers AlreadyExists, which counts as success.

    # --- consumers ------------------------------------------------------------------------------
    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float) -> Claim | Outcome:
        if not _DOCUMENT_ID.fullmatch(row_id) or not _TOKEN.fullmatch(wake_token):
            raise ValueError('invalid enrichment task binding')
        outbox = _outbox()
        from utils.enrichment.custody import discard_blocked
        from utils.conversations.demand_processing import admit
        from config.demand_processing import enabled

        if discard_blocked(row_id):
            return Outcome.DISCARDED
        if not admit(row_id, now=now, token=wake_token):
            return Outcome.DEFERRED  # Demand processing owns this row's next wake.
        owner = uuid.uuid4().hex

        def claim(old):
            if old is None or old.get('dormant') or old.get('task_token') != wake_token:
                return old, (Outcome.STALE, None)
            if old.get('lease_until', 0) > now:
                return old, (Outcome.BUSY, None)
            row = dict(old)
            if row['due_at'] > now and (not row.get('effects_only') or not enabled(row['uid'])):
                row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
                return row, (Outcome.DEFERRED, row)
            row.update(
                lease_until=now + lease_seconds, owner=owner, claim_attempts=int(row.get('claim_attempts') or 0) + 1
            )
            return row, (None, row)

        outcome, row = outbox.mutate_row(row_id, claim)
        if row is None:
            assert outcome is not None
            return outcome
        if outcome is Outcome.DEFERRED:
            outbox.wake_row(row)
            return outcome
        return _claim(row, row_id)

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]:
        """Pull: claim up to ``n`` due, unleased rows by their stored wake token."""
        claims: list[Claim] = []
        for row_id, row in _outbox().due_rows(now=now, limit=n * 4, client=self._bound_client):
            claimed = self.claim_key(row_id, row['task_token'], lease_seconds, now=now)
            if isinstance(claimed, Claim):
                claims.append(claimed)
                if len(claims) >= n:
                    break
        return claims

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool:
        def renew(old):
            if not _holds(old, claim) or old.get('lease_until', 0) <= now:
                return old, False
            return {**old, 'lease_until': now + lease_seconds}, True

        return _outbox().mutate_row(claim.row_id, renew)

    def record_summary(self, claim: Claim) -> bool:
        """Enrichment-only: this lease delivered the first summary, so ``ack`` keeps a dormant receipt."""

        def seen(old):
            if not _holds(old, claim):
                return old, False
            return {**old, 'summary_seen_by': claim.lease_token}, True

        return _outbox().mutate_row(claim.row_id, seen)

    def ack(self, claim: Claim, reason: str, *, now: float) -> bool:
        """Settle a processed lease with today's ``run`` completion rules (``finish``)."""
        outbox = _outbox()
        version = claim.payload.get('version')

        def finish(old):
            if not _holds(old, claim):
                return old, (False, None)
            summary_seen = old.get('summary_seen_by') == claim.lease_token
            if old['version'] == version:
                if summary_seen:
                    settled = dict(old)
                    settled.update(
                        summary_seen=True,
                        dormant=True,
                        due_at=None,
                        lease_until=0,
                        uid=None,
                        conversation_id=None,
                        language=None,
                        dispatch=None,
                        summary_repair=False,
                        summary_expected_revision=None,
                    )
                    settled.pop('summary_seen_by', None)
                    return settled, (True, None)
                return None, (True, None)
            pending = dict(old)
            pending.pop('summary_seen_by', None)
            if summary_seen:
                pending.update(
                    summary_seen=True,
                    first_pending_at=now,
                    summary_repair=False,
                    summary_expected_revision=None,
                    due_at=now + outbox.settle_seconds(),
                )
            pending.update(lease_until=0, owner=None, task_token=uuid.uuid4().hex, task_due_at=pending['due_at'])
            return pending, (True, pending)

        settled, pending = outbox.mutate_row(claim.row_id, finish)
        if pending is not None:
            outbox.wake_row(pending)
        return settled

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:
        outbox = _outbox()

        def rearm(old):
            if not _holds(old, claim):
                return old, None
            pending = dict(old)
            pending.pop('summary_seen_by', None)
            pending.update(
                deferred_reason=reason,
                due_at=available_at,
                task_due_at=available_at,
                task_token=uuid.uuid4().hex,
                lease_until=0,
                owner=None,
                wake_check_after=available_at,
            )
            return pending, pending

        pending = outbox.mutate_row(claim.row_id, rearm)
        if pending is None:
            return None
        outbox.wake_row(pending)
        return pending['task_token']

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        """RETRY: drop the lease and keep the wake token, so the queue's own retry can claim again."""

        def drop(old):
            if not _holds(old, claim):
                return old, False
            row = {**old, 'lease_until': 0, 'owner': None}
            row.pop('summary_seen_by', None)
            return row, True

        return _outbox().mutate_row(claim.row_id, drop)

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts:
        from utils.enrichment.custody import discard_blocked

        counts = _outbox().sweep(now=now, limit=limit, discard=discard_blocked)
        return SweepCounts(
            rewoken=counts['repaired'], expired_leases=0, discarded=counts.get('discarded', 0), errors=counts['error']
        )


ENRICHMENT_OUTBOX = FirestoreEnrichmentOutbox()


def firestore_outbox(kind: OutboxKind):
    """The Firestore implementation behind ``database.outbox.outbox_for`` in this window."""
    if OutboxKind(kind) is OutboxKind.ENRICHMENT:
        return ENRICHMENT_OUTBOX
    raise NotImplementedError(f'no Firestore outbox for {OutboxKind(kind).value} in this window')
