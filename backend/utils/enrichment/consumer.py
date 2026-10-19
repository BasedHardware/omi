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

A consumer-side write leaves nothing for ``run_push`` to settle, so it reports STALE: this delivery no
longer owns a lease. Every lease heartbeats (120s lease, 30s beat), so a long summary never outlives it.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, ClassVar, Iterator

from fastapi import HTTPException

from database.outbox import Claim, OutboxKind, Outcome
from utils.observability.reasons import ConsumerReason, RetryReason
from utils.workers.consumer import Result, Role

logger = logging.getLogger(__name__)


@contextmanager
def _beating(
    heartbeat: Callable[[], bool], seconds: float, context: dict[str, Any] | None
) -> Iterator[threading.Event]:
    """Renew the lease until the block exits; ``lost`` is set when a renewal is refused."""
    stopped, lost = threading.Event(), threading.Event()

    def renew() -> None:
        while not stopped.wait(seconds):
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
        from config.summary_guarantee import ADMITTED_OWNER, preserves_admitted
        from database._client import get_firestore_client
        from database.summary_processing import record_empty_failure
        from utils.conversations import summary_delivery
        from utils.enrichment import outbox as rows
        from utils.enrichment.callback import SyncConversationPersistenceFenced

        now = time.time()
        row: dict[str, Any] = {**claim.payload, 'uid': claim.owner_id, 'document_id': claim.row_id}
        uid, conversation_id, language = claim.owner_id, row['conversation_id'], row['language']

        if row.get('effects_only'):
            from utils.conversations.lazy_enrichment import enrich_settled

            with _beating(heartbeat, self.heartbeat_seconds, None) as lost:
                enrich_settled(uid, conversation_id, language)
            if lost.is_set():
                return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
            return Result(Outcome.DONE, ConsumerReason.PROCESSED)

        summary_policy = rows.summary_policy_for(row)
        context = (
            {'owner': claim.lease_token, 'lease_until': claim.lease_until}
            if summary_policy and not row.get('summary_seen')
            else None
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
                output = self._callback()(uid, conversation_id, language)
                if summary_policy:
                    summary_seen = output is not None and summary_delivery.present(
                        summary_delivery.field(output, 'structured')
                    )
                    discarded = (output is not None and summary_delivery.field(output, 'discarded', False)) or (
                        preserves_admitted(row) and bool(context and context.get('discarded'))
                    )
                    blocked = bool(context and context.get('blocked_reason'))
                    custody = bool(context and (context.get('redirect_to') or context.get('defer_reason')))
                    if output is None and preserves_admitted(row) and not discarded and not blocked and not custody:
                        return Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=now)
                    if output is not None and not summary_seen and not discarded and not blocked:
                        raise summary_delivery.SummaryOutputUnavailable('first-summary output is empty')
        except rows.FirstSummaryCallbackPending:
            return Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=now)
        except HTTPException as error:
            # Processing's HTTP contract for a failed LLM/provider/app step: retry without a fast 5xx.
            if not (error.status_code == 429 or error.status_code >= 500):
                raise
            logger.warning('event=enrichment_consumer outcome=retry reason=dependency status=%s', error.status_code)
            return Result(Outcome.RETRY, RetryReason.DEPENDENCY_WARMING, available_at=now)
        except summary_delivery.SummaryRepairSuperseded as error:
            superseded, retry_revision = True, error.retry_revision
        except SyncConversationPersistenceFenced:
            # #21968: the newer writer owns the conversation and marks its own obligation.
            logger.info('event=sync_reprocess outcome=conversation_fenced')
            superseded = True
        except summary_delivery.SummaryOutputUnavailable:
            if not context or not record_empty_failure(
                get_firestore_client(), rows.COLLECTION, claim.row_id, claim.lease_token, claim.wake_token
            ):
                return Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=now)
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
            except rows.FirstSummaryCallbackPending:
                return Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=now)
            if pending is not None:
                rows.wake_row(pending)  # Transactional custody survives a lost enqueue acknowledgement.
            return Result(Outcome.STALE, ConsumerReason.REDIRECTED)
        if context and context.get('defer_reason'):
            return Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE, available_at=now + rows.LIVE_DEFER_SECONDS)
        if superseded:
            if retry_revision is not None:
                self.outbox.repair(claim, retry_revision, now=now)
                return Result(Outcome.STALE, ConsumerReason.SUPERSEDED)
            return Result(Outcome.DISCARDED, ConsumerReason.SUPERSEDED)
        if summary_policy and summary_seen and not self.outbox.record_summary(claim):
            return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)
        return Result(Outcome.DONE, ConsumerReason.PROCESSED)
