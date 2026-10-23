"""Firestore ``Outbox`` (contract (b)) for ``OutboxKind.ENRICHMENT``, row-compatible with ``sync_reprocess_outbox``.

The row is the state; a Cloud Task is only a wake. Rows keep today's collection, document id
(``key(uid, conversation_id[+'\\0effects'])``), field names and ``sr-`` task names, so rows written by
``utils.enrichment.outbox.mark`` and rows written here are interchangeable, and in-flight rows drain.

Field mapping: ``Claim.lease_token`` is the row's ``owner`` (minted per claim, as ``run`` does today),
``Claim.wake_token`` is ``task_token`` ('' for pull claims), ``Claim.owner_id`` is ``uid``. ``claim_attempts``
and ``policy_id`` are additive fields. Post-claim calls are fenced on ``lease_token`` only (invariant 1): a
producer may rotate ``task_token`` under a live lease, and that must not strand the lease holder.

Wakes (lead ruling 10-19): this implementation creates Cloud Tasks itself through the existing
``_enqueue`` (binding checks, demand scheduling, eager effects recovery): after a non-transactional
``enqueue``, on ``defer``, on a not-due ``claim_key`` (returns ``Outcome.DEFERRED``) and on re-armed
``ack``. A transactional ``enqueue`` returns the wake token and the caller calls ``wake`` after commit.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable, Literal, Mapping

import dataclasses
import functools
import logging

from database.outbox import Claim, EnqueueResult, Outbox, OutboxKind, Outcome, SweepCounts

logger = logging.getLogger(__name__)

_DOCUMENT_ID = re.compile('[0-9a-f]{64}')
_TOKEN = re.compile('[0-9a-f]{32}')
_PAYLOAD_LIMIT = 4096  # contract (a): content-free, <= 4 KiB serialized
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
    'first_summary_policy',  # E1 snapshot; the consumer decides first summary from it
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
    # Invariant 1 fences on the lease token alone. ``mark_update``/``mark_effects`` may rotate ``task_token``
    # under a live lease; requiring it here would reject the live owner and lose that rotation's wake.
    return bool(row and not row.get('dormant') and row.get('owner') == claim.lease_token)


def _document_id(row: Mapping[str, Any]) -> str:
    return row.get('document_id') or _outbox().key(row['uid'], row['conversation_id'])


class FirestoreEnrichmentOutbox:
    kind = OutboxKind.ENRICHMENT

    def __init__(
        self,
        client: Any = None,
        *,
        privacy_blocked: Callable[[str, Mapping[str, Any]], bool] | None = None,
        create_wake: Callable[[str, str, float], None] | None = None,
    ):
        # Projection binds its own client so its transactional row and the post-commit wake read one store.
        # The conformance suite also injects the privacy check ``(owner_id, payload)`` and the task creator
        # ``(row_id, wake_token, available_at)`` (contract (b), testing/store_fixtures.py).
        self._bound_client = client
        self._privacy_blocked = privacy_blocked
        self._create_wake = create_wake

    def _client(self) -> Any:
        return self._bound_client or _outbox().get_firestore_client()

    def _mutate(self, row_id: str, operation):
        return _outbox().mutate_row(row_id, operation, client=self._bound_client)

    def _wake(self, row: Mapping[str, Any]) -> None:
        if self._create_wake is not None:
            self._create_wake(_document_id(row), row['task_token'], float(row.get('task_due_at') or row['due_at']))
        else:
            _outbox().wake_row(dict(row))

    def _rearmed(self, row: Mapping[str, Any]) -> None:
        """Wake a row this outbox just re-armed. The row is durable, so a failed create is left to the sweep
        (invariant 4) rather than failing the delivery, whose retry would only find a stale token."""
        try:
            self._wake(row)
        except Exception as error:
            logger.warning('event=enrichment_outbox action=wake outcome=error exception_type=%s', type(error).__name__)

    def _can_wake(self, row: Mapping[str, Any], *, effects: bool = False) -> bool:
        """An injected task creator stands in for the queue binding; otherwise the row must carry one."""
        if self._create_wake is not None:
            return True
        outbox = _outbox()
        return (
            outbox.valid_effects_binding(dict(row)) if effects else outbox.valid_dispatch_binding(row.get('dispatch'))
        )

    def _blocked(self, row_id: str) -> bool:
        """Discard the row when its owner is privacy-fenced (invariant 6); True when it was discarded."""
        if self._privacy_blocked is None:
            from utils.enrichment.custody import discard_blocked

            return discard_blocked(row_id)
        probe = self._privacy_blocked

        def discard(old):
            if not old or old.get('dormant') or not old.get('uid'):
                return old, False
            if not probe(old['uid'], {'conversation_id': old.get('conversation_id')}):
                return old, False
            return None, True

        return self._mutate(row_id, discard)

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
        snapshot_summary: bool = False,
    ) -> EnqueueResult:
        """``new_dispatch`` (Firestore enrichment only) supplies a new row's queue binding, e.g. backfill."""
        outbox = _outbox()
        if len(json.dumps(dict(payload), separators=(',', ':'), default=str).encode()) > _PAYLOAD_LIMIT:
            raise ValueError('outbox payload must be content-free and <= 4 KiB')
        conversation_id, language = payload['conversation_id'], payload['language']
        effects_only = bool(payload.get('effects_only'))
        if dedupe_key != outbox.key(owner_id, conversation_id + ('\0effects' if effects_only else '')):
            raise ValueError('enrichment dedupe_key must be the outbox key of (owner, conversation)')
        stamps: list[tuple[str, str]] = []
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
            snapshot_summary=snapshot_summary,
            stamps=stamps,
        )
        if tx is None:
            row, coalesced = self._mutate(dedupe_key, update)
        else:
            row, coalesced = self._mutate_in(tx, dedupe_key, update)
        outbox.record_summary_stamps(stamps)
        wake = bool(row.get('_wake', not coalesced)) and self._can_wake(row)
        if coalesced:
            outbox.COALESCED.inc()
        if not self._can_wake(row):
            outbox.UNBOUND.labels(action='mark').inc()
        token = row.get('task_token') if wake else None
        if wake and tx is None:
            self._wake(row)  # Failure leaves the obligation durable for the sweep.
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
        if self._can_wake(row, effects=True):
            self._wake(row)  # Named task: an existing wake answers AlreadyExists, which counts as success.

    # --- consumers ------------------------------------------------------------------------------
    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float) -> Claim | Outcome:
        if not _DOCUMENT_ID.fullmatch(row_id or '') or not _TOKEN.fullmatch(wake_token or ''):
            return Outcome.STALE  # No row can hold this binding (invariant 2: unknown rows are stale).
        from utils.conversations.demand_processing import admit
        from config.demand_processing import enabled

        if self._blocked(row_id):
            return Outcome.DISCARDED
        if not admit(row_id, now=now, token=wake_token):
            return Outcome.DEFERRED  # Demand processing owns this row's next wake.
        outbox = _outbox()
        owner = uuid.uuid4().hex
        cache: dict[str, Any] = {}
        stamps: list[tuple[str, str]] = []

        def claim(old):
            stamps.clear()
            if old is None or old.get('dormant') or old.get('task_token') != wake_token:
                return old, (Outcome.STALE, None)
            if old.get('lease_until', 0) > now:
                return old, (Outcome.BUSY, None)
            row = dict(old)
            outbox.stamp_claim_policy(row, cache, stamps)
            if row['due_at'] > now and (not row.get('effects_only') or not enabled(row['uid'])):
                row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
                return row, (Outcome.DEFERRED, row)
            row.update(
                lease_until=now + lease_seconds, owner=owner, claim_attempts=int(row.get('claim_attempts') or 0) + 1
            )
            return row, (None, row)

        outcome, row = self._mutate(row_id, claim)
        outbox.record_summary_stamps(stamps)
        if row is None:
            assert outcome is not None
            return outcome
        if outcome is Outcome.DEFERRED:
            self._rearmed(row)
            return outcome
        return _claim(row, row_id)

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]:
        """Pull: claim up to ``n`` due, unleased rows by their stored wake token.

        A pull claim was not delivered by a wake, so ``Claim.wake_token`` is '' (contract (a)).
        """
        claims: list[Claim] = []
        for row_id, row in _outbox().due_rows(now=now, limit=n * 4, client=self._bound_client):
            claimed = self.claim_key(row_id, row['task_token'], lease_seconds, now=now)
            if isinstance(claimed, Claim):
                claims.append(dataclasses.replace(claimed, wake_token=''))
                if len(claims) >= n:
                    break
        return claims

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool:
        def renew(old):
            if not _holds(old, claim) or old.get('lease_until', 0) <= now:
                return old, False
            return {**old, 'lease_until': now + lease_seconds}, True

        return self._mutate(claim.row_id, renew)

    def record_summary(self, claim: Claim) -> bool:
        """Enrichment-only: this lease delivered the first summary, so ``ack`` keeps a dormant receipt."""

        def seen(old):
            if not _holds(old, claim):
                return old, False
            return {**old, 'summary_seen_by': claim.lease_token}, True

        return self._mutate(claim.row_id, seen)

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

        settled, pending = self._mutate(claim.row_id, finish)
        if pending is not None:
            self._rearmed(pending)
        return settled

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:

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

        pending = self._mutate(claim.row_id, rearm)
        if pending is None:
            return None
        self._rearmed(pending)
        return pending['task_token']

    def repair(self, claim: Claim, retry_revision: int, *, now: float) -> str | None:
        """Enrichment-only: a repair lost its revision race; re-arm now behind the newer revision's fence."""

        def rearm(old):
            if not _holds(old, claim):
                return old, None
            pending = dict(old)
            pending.pop('summary_seen_by', None)
            due = min(now, pending['due_at'])
            pending.update(
                summary_repair=True,
                summary_expected_revision=retry_revision,
                lease_until=0,
                owner=None,
                task_token=uuid.uuid4().hex,
                task_due_at=due,
                due_at=due,
            )
            return pending, pending

        pending = self._mutate(claim.row_id, rearm)
        if pending is None:
            return None
        self._rearmed(pending)
        return pending['task_token']

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        """RETRY: drop the lease and keep the wake token, so the queue's own retry can claim again.

        If a producer rotated the wake token under this lease, the queue retries the old (now stale) task and
        the new wake may already have been answered BUSY. Then re-arm under a fresh token and wake it.
        """

        def drop(old):
            if not _holds(old, claim):
                return old, (False, None)
            row = {**old, 'lease_until': 0, 'owner': None}
            row.pop('summary_seen_by', None)
            if claim.wake_token and row.get('task_token') != claim.wake_token:
                row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
                return row, (True, row)
            return row, (True, None)

        released, rearmed = self._mutate(claim.row_id, drop)
        if rearmed is not None:
            self._rearmed(rearmed)
        return released

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts:
        # Invariant 8: no shared scan cursor; every pass starts at the oldest due row.
        counts = _outbox().sweep(
            now=now,
            limit=limit,
            discard=self._blocked,
            client=self._bound_client,
            wake=None if self._create_wake is None else self._wake,
            cursor=False,
        )
        return SweepCounts(
            rewoken=counts['repaired'],
            expired_leases=counts.get('expired', 0),
            discarded=counts.get('discarded', 0),
            errors=counts['error'],
        )


ENRICHMENT_OUTBOX = FirestoreEnrichmentOutbox()


def FirestoreOutbox(  # noqa: N802 (the conformance suite's factory name, contract (b))
    kind: OutboxKind,
    *,
    client: Any = None,
    privacy_blocked: Callable[[str, Mapping[str, Any]], bool] | None = None,
    create_wake: Callable[[str, str, float], None] | None = None,
) -> Outbox:
    """A Firestore outbox bound to ``client``; the conformance suite injects the privacy check and task creator."""
    if OutboxKind(kind) is OutboxKind.PROVIDER_STT:  # lane 8 (lead ruling 10-19)
        from database.outbox_provider_stt import FirestoreProviderSttOutbox

        return FirestoreProviderSttOutbox(client, privacy_blocked=privacy_blocked, create_wake=create_wake)
    if OutboxKind(kind) is not OutboxKind.ENRICHMENT:
        raise NotImplementedError(f'no Firestore outbox for {OutboxKind(kind).value} in this window')
    return FirestoreEnrichmentOutbox(client, privacy_blocked=privacy_blocked, create_wake=create_wake)


@functools.cache
def _provider_stt_outbox() -> Outbox:
    # Lazy so the selector stays import-light; cached so every caller shares one instance, like enrichment.
    from database.outbox_provider_stt import FirestoreProviderSttOutbox

    return FirestoreProviderSttOutbox()


def firestore_outbox(kind: OutboxKind) -> Outbox:
    """The Firestore implementation behind ``database.outbox.outbox_for`` in this window."""
    if OutboxKind(kind) is OutboxKind.ENRICHMENT:
        return ENRICHMENT_OUTBOX
    if OutboxKind(kind) is OutboxKind.PROVIDER_STT:  # lane 8 (lead ruling 10-19)
        return _provider_stt_outbox()
    raise NotImplementedError(f'no Firestore outbox for {OutboxKind(kind).value} in this window')
