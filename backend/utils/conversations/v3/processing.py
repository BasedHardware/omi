"""Fenced v3 reprocess/merge lifecycle; explicit Retry always owns its copied window."""

import logging
from datetime import datetime, timedelta, timezone
from time import monotonic

from database import conversations_v3_fence as fence, conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from models.finalization_owner import FinalizationOwnedElsewhere
from utils.conversations.processing_retry import ProcessingNotCompleted
from utils.conversations.v3 import models, policy
from utils.conversations.v3.triggers import enqueue
from utils.llm.notes_observability import notes_stage
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _not_completed_stage(persisted) -> str:
    """The bounded point that stopped completion, for the one refusal line."""
    decline = fence.persistence_declined()
    if decline is not None:
        return decline.reason
    if not persisted or not persisted[-1]:
        return 'summary_not_persisted'
    return 'status_not_completed'


def _not_completed(persisted, elapsed_seconds: float) -> ProcessingNotCompleted:
    stage = _not_completed_stage(persisted)
    lane = notes_stage()
    logger.warning(
        'event=v3_processing_not_completed stage=%s notes_stage=%s elapsed_seconds=%.3f',
        stage,
        lane,
        elapsed_seconds,
    )
    return ProcessingNotCompleted(stage, elapsed_seconds=elapsed_seconds, notes_stage=lane)


def run_external(fn, uid, language, conversation, *args, **kwargs):
    started = monotonic()
    token = leases.acquire(uid, 'summary-' + conversation.id)
    if not token:
        raise RuntimeError('v3_summary_busy')
    row = conversation.model_dump()
    revision, content_hash = row.get('sync_content_revision'), writers.processing_hash(row)
    backfilled = bool(row.get('backfilled'))
    backfill_prior: dict | None = {} if backfilled else None
    persisted = []
    armed = False
    observer = kwargs.pop('persistence_observer', None)

    def observed(current):
        persisted.append(current)
        if observer:
            observer(current)

    try:
        retry = policy.explicit_retry(row, kwargs.get('trigger'))
        with leases.keepalive(uid, 'summary-' + conversation.id, token), fence.writer(uid, conversation.id, token):
            outcome = writers.begin_processing(uid, row, token, force=retry, backfill_prior=backfill_prior)
            if outcome is not True:
                # A locked row is owned elsewhere and an exhausted row is already terminal: both are
                # settled no-ops, so the outbox acknowledges them instead of looping on a 500.
                if conversation.is_locked or outcome is writers.TERMINAL:
                    return conversation
                raise RuntimeError('v3_processing_unavailable')
            conversation.tile_state = 'writing'
            conversation.summary_retryable = False
            try:
                with models.notes_mode(uid, foreground=retry, backfilled=backfilled):
                    result = fn(uid, language, conversation, *args, persistence_observer=observed, **kwargs)
                if not persisted or not persisted[-1] or getattr(result.status, 'value', result.status) != 'completed':
                    raise _not_completed(persisted, monotonic() - started)
            except (models.BackfillNotesDeletionBlocked, models.BackfillNotesAdmissionTimeout):
                if backfill_prior is not None:
                    writers.park_backfill_processing(uid, conversation.id, token, backfill_prior)
                raise
            except FinalizationOwnedElsewhere:
                raise
            except Exception:
                writers.fail_processing(uid, conversation.id, token, revision, content_hash=content_hash)
                raise
            armed = writers.settle_processing(
                uid, conversation.id, token, revision, conversation.finished_at, notes=True, content_hash=content_hash
            )
            result.tile_state = 'done'
            if not result.home_hidden and result.structured.title:
                result.title_locked = True
            result.summary_retryable = False
            return result
    finally:
        leases.release(uid, 'summary-' + conversation.id, token)
        if armed:
            # Retry/reprocess settles outside the builder's drain: wake the owner so the drain delivers
            # the conversation-created fanout. A lost wake waits for the owner's next reconcile.
            try:
                enqueue(uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
            except Exception as error:
                logger.warning('event=v3_created_wake outcome=deferred exception_type=%s', type(error).__name__)
                record_fallback(
                    component='other', from_mode='dispatch', to_mode='none', reason='enqueue_failed', outcome='degraded'
                )
