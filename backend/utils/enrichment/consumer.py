"""``QueueConsumer`` for ``OutboxKind.ENRICHMENT`` (contract (a)), served at ``POST /v2/enrichment/run``.

Mirrors ``utils.enrichment.outbox.run`` outcome for outcome, with every settlement going through the
``Outbox`` calls instead of in-line CAS writes:

| ``run`` status | Result | row write (by ``run_push``'s settle, or the consumer where kind-specific) |
|---|---|---|
| processed | DONE processed | ``ack``: retire, dormant receipt (``record_summary``) or re-arm on a newer version |
| superseded, no revision | DISCARDED superseded | ``ack`` (same finish rules) |
| superseded, retry revision | STALE superseded | consumer: ``repair`` re-arms with the repair fence |
| deferred (live target, missing) | DEFERRED not_due | ``defer`` at +120s |
| redirected | STALE redirected | consumer: ``custody.transfer_redirect`` moved the obligation |
| blocked (empty budget spent) | STALE empty_output_blocked | consumer: ``record_empty_failure`` retired it |
| callback pending / empty output | RETRY callback_pending | ``release``: 409, the queue retry claims again |
| transient Firestore / gateway fault | RETRY dependency_warming | ``release``: 409, the queue retry claims again |

A consumer-side write leaves nothing for ``run_push`` to settle, so it reports STALE: this delivery no
longer owns a lease. Every lease heartbeats (120s lease, 30s beat), so a long summary never outlives it, up
to a 1500s hold cap after which a hung callback's lease lapses for the sweep to re-wake.
"""

from __future__ import annotations
from utils.observability.delivery import record_delivery

import logging
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, ClassVar, Iterator

from fastapi import HTTPException

from database.outbox import Claim, OutboxKind, Outcome
from utils.observability.reasons import ConsumerReason, RetryReason
from utils.workers.consumer import Result, Role
from utils.sync import processing_hold
from utils.enrichment import early_abort

logger = logging.getLogger(__name__)

_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


def _transient_dependency(error: BaseException) -> bool:
    """A Firestore or LLM-gateway transport fault (typed, never message text), anywhere in the cause chain.

    Prod 11-03: Firestore ``Aborted`` on the conversation claim and gateway embedding 503s/read timeouts
    answered 500. A 500 keeps the 120s lease, so the queue's own retry is consumed as BUSY and the
    obligation waits for the maintenance sweep; a 409 releases the lease and the retry claims again.
    """
    import httpx
    from google.api_core import exceptions as google_errors

    transient = (
        google_errors.Aborted,
        google_errors.DeadlineExceeded,
        google_errors.InternalServerError,
        google_errors.ServiceUnavailable,
        google_errors.TooManyRequests,
        httpx.TimeoutException,
        httpx.NetworkError,
    )
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, transient):
            return True
        if isinstance(current, httpx.HTTPStatusError):
            return current.response.status_code in _TRANSIENT_HTTP_STATUSES
        current = current.__cause__ or current.__context__
    return False


# Public name for the age-gate route's dependency-fault check.
transient_dependency = _transient_dependency


def _fenced_redirect(uid: str, conversation_id: str) -> tuple[str, str | None]:
    """How a fenced run with custody settles: ('superseded', None), ('transfer', canonical) or ('defer', None).

    Mirrors the callback's entry rule: a row a merge redirected moves its custody to the canonical conversation,
    and a redirect that cannot be resolved (broken topology, a failed read) keeps the row deferred, never retired.
    A live row or a plain user deletion stays superseded.
    """
    from config.sync_reprocess import fence_redirect_transfer_enabled
    from database import conversations as conversations_db

    if not fence_redirect_transfer_enabled():
        return 'superseded', None
    try:
        row = conversations_db.get_conversation_raw_snapshot(
            uid, conversation_id, field_paths=['deleted', 'sync_merged_into']
        )
        if not row or not (row.get('deleted') and row.get('sync_merged_into')):
            return 'superseded', None
        canonical = conversations_db.resolve_sync_conversation_redirect(uid, conversation_id)
    except Exception as error:
        if _transient_dependency(error):
            raise  # A transient Firestore fault keeps the consumer's quick retry, not the custody backoff.
        logger.warning('event=sync_reprocess outcome=fence_redirect_unresolved exception_type=%s', type(error).__name__)
        return 'defer', None
    if isinstance(canonical, str) and canonical and canonical != conversation_id:
        return 'transfer', canonical
    return 'defer', None


def _cause(error: BaseException) -> str:
    # FirstSummaryCallbackPending carries fixed literals ('redirect target changed'); keep a bounded token.
    return re.sub(r'[^a-z0-9]+', '_', str(error).lower()).strip('_')[:40] or 'unspecified'


def _callback_pending(cause: str, now: float) -> Result:
    """Every callback_pending 409 names its cause: one reason covers four different waits."""
    logger.info('event=enrichment_consumer outcome=retry reason=callback_pending cause=%s', cause)
    return Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=now)


@contextmanager
def _beating(
    heartbeat: Callable[[], bool], seconds: float, context: dict[str, Any] | None
) -> Iterator[threading.Event]:
    """Renew the lease until the block exits; ``lost`` is set when a renewal is refused.

    Renewal stops after ``max_hold_seconds``: a callback hung on a dependency then lets its lease lapse, so the
    maintenance sweep fences it and re-wakes the row, instead of heartbeating one obligation forever. A callback
    that finishes before the lease lapses still settles normally.
    """
    stopped, lost = threading.Event(), threading.Event()
    hold_until = time.monotonic() + EnrichmentConsumer.max_hold_seconds

    def renew() -> None:
        while not stopped.wait(seconds):
            if time.monotonic() >= hold_until:
                logger.warning(
                    'event=enrichment_heartbeat outcome=hold_cap max_hold_s=%.0f', EnrichmentConsumer.max_hold_seconds
                )
                return
            try:
                if not heartbeat():
                    lost.set()
                    return
                if context is not None:
                    context['lease_until'] = time.time() + EnrichmentConsumer.lease_seconds
            except Exception as error:
                logger.warning('event=enrichment_heartbeat outcome=error exception_type=%s', type(error).__name__)

    worker = threading.Thread(target=renew, name='enrichment-heartbeat', daemon=True)
    worker.start()
    try:
        yield lost
    finally:
        stopped.set()
        worker.join(timeout=2)


class EnrichmentConsumer:
    kind: ClassVar[OutboxKind] = OutboxKind.ENRICHMENT
    role: ClassVar[Role] = Role.WORKERS
    lease_seconds: ClassVar[float] = 120.0
    heartbeat_seconds: ClassVar[float] = 30.0
    # The 1500s dispatch deadline is the longest any wake may run; past it the callback is treated as hung.
    max_hold_seconds: ClassVar[float] = 1500.0

    def __init__(self, outbox: Any = None, process: Callable[[str, str, str], Any] | None = None):
        if outbox is None:
            from database.outbox_firestore import ENRICHMENT_OUTBOX

            outbox = ENRICHMENT_OUTBOX
        self.outbox = outbox
        self._process = process

    def _callback(self) -> Callable[[str, str, str], Any]:
        if self._process is not None:
            return self._process
        from utils.enrichment.callback import enrich_conversation

        return enrich_conversation

    def process(self, claim: Claim, heartbeat: Callable[[], bool]) -> Result:
        # Covers every store/gateway call below, including the effects-only path and the empty-output strike.
        # A consumer-side write that already moved ownership makes the release refuse, so that settles STALE.
        try:
            return self._deliver(claim, heartbeat)
        except Exception as error:
            if not _transient_dependency(error):
                raise
            logger.warning(
                'event=enrichment_consumer outcome=retry reason=dependency exception_type=%s', type(error).__name__
            )
            return Result(Outcome.RETRY, RetryReason.DEPENDENCY_WARMING, available_at=time.time())

    def _deliver(self, claim: Claim, heartbeat: Callable[[], bool]) -> Result:
        from config.summary_guarantee import ADMITTED_OWNER, preserves_admitted
        from database._client import get_firestore_client
        from database.summary_processing import record_empty_failure, EmptyFailureOutcome
        from utils.conversations import summary_delivery
        from utils.enrichment import outbox as rows
        from config.action_item_identity import enrichment_revision_race_retry_enabled
        from database.action_item_refresh import RefreshRevisionChanged
        from utils.enrichment.callback import SyncConversationPersistenceFenced

        now = time.time()
        row: dict[str, Any] = {**claim.payload, 'uid': claim.owner_id, 'document_id': claim.row_id}
        uid, conversation_id, language = claim.owner_id, row['conversation_id'], row['language']

        if row.get('effects_only'):
            from utils.conversations.lazy_enrichment import enrich_settled

            with _beating(heartbeat, self.heartbeat_seconds, None) as lost:
                try:
                    enrich_settled(uid, conversation_id, language)
                except processing_hold.ProcessingDeferred as error:
                    return Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE, available_at=error.available_at)
            if lost.is_set():
                return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
            return Result(Outcome.DONE, ConsumerReason.PROCESSED)

        summary_policy = rows.summary_policy_for(row)
        context: dict[str, Any] | None = (
            {'owner': claim.lease_token, 'lease_until': claim.lease_until}
            if (summary_policy and not row.get('summary_seen')) or row.get('sync_hold')
            else None
        )
        if context is not None:
            context.update(
                sync_hold=bool(row.get('sync_hold')),
                merge_hold=bool(row.get('merge_hold')),
                sync_hold_requested=bool(row.get('sync_hold_requested')),
                first_pending_at=row['first_pending_at'],
            )
        summary_seen = superseded = empty_blocked = False
        retry_revision = None
        lost = threading.Event()
        tokens = (
            summary_delivery.LANE_CONTEXT.set(row.get('summary_lane') or summary_delivery.lane({})),
            summary_delivery.PROCESS_CONTEXT.set(context),
            summary_delivery.ACCEPT_CONTEXT.set(row.get('first_pending_at')),
            summary_delivery.REPAIR_CONTEXT.set(row if row.get('summary_repair') else None),
            ADMITTED_OWNER.set(uid if preserves_admitted(row) else None),
        )
        try:
            with _beating(heartbeat, self.heartbeat_seconds, context) as lost:
                abort_token = early_abort.ACTIVE.set(True)
                try:
                    output = self._callback()(uid, conversation_id, language)
                finally:
                    early_abort.ACTIVE.reset(abort_token)
                if summary_policy:
                    summary_seen = output is not None and summary_delivery.present(
                        summary_delivery.field(output, 'structured')
                    )
                    discarded = (output is not None and summary_delivery.field(output, 'discarded', False)) or (
                        preserves_admitted(row) and bool(context and context.get('discarded'))
                    )
                    blocked = bool(context and context.get('blocked_reason'))
                    custody = bool(context and (context.get('redirect_to') or context.get('defer_reason')))
                    if context and context.get('hold_skipped'):
                        discarded = True
                    if output is None and preserves_admitted(row) and not discarded and not blocked and not custody:
                        return _callback_pending('admitted_no_output', now)
                    if output is not None and not summary_seen and not discarded and not blocked:
                        raise summary_delivery.SummaryOutputUnavailable('first-summary output is empty')
        except processing_hold.ProcessingDeferred as error:
            return Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE, available_at=error.available_at)
        except rows.FirstSummaryCallbackPending as error:
            return _callback_pending(_cause(error), now)
        except HTTPException as error:
            # Processing's HTTP contract for a failed LLM/provider/app step: retry without a fast 5xx.
            if not (error.status_code == 429 or error.status_code >= 500):
                raise
            logger.warning('event=enrichment_consumer outcome=retry reason=dependency status=%s', error.status_code)
            return Result(Outcome.RETRY, RetryReason.DEPENDENCY_WARMING, available_at=now)
        except summary_delivery.SummaryRepairSuperseded as error:
            superseded, retry_revision = True, error.retry_revision
        except RefreshRevisionChanged:
            # A sync write moved the conversation's revision while this run's LLM steps ran, so the action-item
            # refresh refused stale extraction. That is a correct race, not an unexpected failure. Keep the row
            # and its wake (not every revision bumper arms one) and rerun on the current revision.
            if not enrichment_revision_race_retry_enabled():
                raise
            logger.info('event=enrichment_consumer outcome=retry reason=persistence_fenced source=action_item_refresh')
            return Result(Outcome.RETRY, RetryReason.PERSISTENCE_FENCED, available_at=now)
        except SyncConversationPersistenceFenced:
            # #21968: the newer writer owns the conversation and marks its own obligation. A merge that
            # redirected this conversation while it ran is the exception: its custody (first summary, hold)
            # must move to the canonical conversation, exactly as before_notes' ConversationAbsorbed does.
            action, canonical = _fenced_redirect(uid, conversation_id) if context is not None else ('superseded', None)
            if context is not None and action == 'transfer':
                logger.info('event=sync_reprocess outcome=conversation_fenced redirect=transferred')
                context['redirect_to'] = canonical
            elif context is not None and action == 'defer':
                logger.info('event=sync_reprocess outcome=conversation_fenced redirect=unresolved')
                context['defer_reason'] = 'redirect_unresolved'
            else:
                logger.info('event=sync_reprocess outcome=conversation_fenced')
                superseded = True
        except summary_delivery.SummaryOutputUnavailable:
            if not context:
                return _callback_pending('empty_output_unrecorded', now)
            empty_outcome = record_empty_failure(
                get_firestore_client(), rows.COLLECTION, claim.row_id, claim.lease_token, claim.wake_token
            )
            if empty_outcome is EmptyFailureOutcome.STALE:
                return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
            if empty_outcome is EmptyFailureOutcome.OWNER_MISMATCH:
                return Result(
                    Outcome.DEFERRED,
                    ConsumerReason.NOT_DUE,
                    available_at=now + rows.LIVE_DEFER_SECONDS,
                    defer_cause='summary_owner_changed',
                )
            if empty_outcome is EmptyFailureOutcome.RETRY:
                return _callback_pending('empty_output', now)
            record_delivery('summary', 'failed')
            empty_blocked = True
        finally:
            ADMITTED_OWNER.reset(tokens[4])
            summary_delivery.REPAIR_CONTEXT.reset(tokens[3])
            summary_delivery.ACCEPT_CONTEXT.reset(tokens[2])
            summary_delivery.PROCESS_CONTEXT.reset(tokens[1])
            summary_delivery.LANE_CONTEXT.reset(tokens[0])

        if lost.is_set():
            return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
        if empty_blocked:
            return Result(Outcome.STALE, ConsumerReason.EMPTY_OUTPUT_BLOCKED)
        if context and context.get('redirect_to'):
            from utils.enrichment.custody import transfer_redirect

            try:
                pending = transfer_redirect(
                    claim.row_id, claim.wake_token, claim.lease_token, str(context['redirect_to']), now=now
                )
            except rows.FirstSummaryCallbackPending as error:
                return _callback_pending('redirect_' + _cause(error), now)
            if pending is not None:
                rows.wake_row(pending)  # Transactional custody survives a lost enqueue acknowledgement.
            return Result(Outcome.STALE, ConsumerReason.REDIRECTED)
        if context and context.get('defer_reason'):
            return Result(
                Outcome.DEFERRED,
                ConsumerReason.NOT_DUE,
                available_at=context.get('defer_until', now + rows.LIVE_DEFER_SECONDS),
                defer_cause=str(context['defer_reason']),
            )
        if superseded:
            if retry_revision is not None:
                self.outbox.repair(claim, retry_revision, now=now)
                return Result(Outcome.STALE, ConsumerReason.SUPERSEDED)
            return Result(Outcome.DISCARDED, ConsumerReason.SUPERSEDED)
        if summary_policy and summary_seen and not self.outbox.record_summary(claim):
            return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
        return Result(Outcome.DONE, ConsumerReason.PROCESSED)
