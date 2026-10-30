"""Enrichment callback: re-run conversation processing after new segments land (plan C2).

Extracted verbatim from ``utils/sync/pipeline.py:_reprocess_conversation_after_update`` so the
``sr-`` outbox no longer imports legacy transcription. The legacy copy stays for the non-coalescing
direct path until pipeline.py is unfrozen (#21932/#20662) or deleted (C11);
``tests/unit/test_enrichment_callback_parity.py`` keeps the two bodies identical until then.
"""

from __future__ import annotations

from utils.enrichment.admission import SyncConversationPersistenceFenced
from utils.enrichment.admission import require_current_persistence as _require_current_conversation_persistence
from utils.enrichment.admission import run_created_webhook as _run_conversation_created_webhook

import logging
import time

from config.occasion_relevance import enabled as occasion_relevance_enabled
from database import conversations as conversations_db
from database._client import get_firestore_client
from database.summary_processing import claim_from_snapshot
from models.conversation_enums import ConversationSource
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.factory import deserialize_conversation
from utils.conversations.fragment_visibility import is_user_curated
from utils.conversations.process_conversation import process_conversation
from utils.sync import processing_hold
from utils.enrichment.smart_refresh import settle_survivor
from utils.conversations.smart_merge_policy import refresh_owed
from utils.enrichment.admission import ConversationAbsorbed
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.silent_redrive import is_silent_redrive
from utils.conversations.relevance import sync_intake_decision
from utils.conversations.summary_delivery import (
    PROCESS_CONTEXT,
    REPAIR_CONTEXT,
    SummaryRepairSuperseded,
    present as summary_output_present,
    refusal as summary_repair_refusal,
    repair_fenced,
)
from utils.episodes.finalize import schedule_after_finalization
from utils.executors import postprocess_executor, submit_with_context
from utils.journey_metrics_contract import resolve_client_kind
from utils.metrics import record_conversation_relevance
from utils.observability.journeys import record_client_journey_accepted, record_client_journey_terminal
from utils.sync.assignment import fragment_rule

logger = logging.getLogger(__name__)

# Shared with legacy sync's lineage retry intents; the stored row's language wins.
_LINEAGE_RETRY_LANGUAGE = '__stored_conversation_language__'


def enrich_conversation(uid: str, conversation_id: str, language: str):
    """
    Reprocess a conversation after new segments have been added.
    This checks if the conversation should still be discarded and regenerates
    the summary/structured data if it now has sufficient content.
    """
    # Fetch the updated conversation with all segments
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    context = PROCESS_CONTEXT.get()
    if conversation_data and conversation_data.get('deleted') and conversation_data.get('sync_merged_into'):
        if context is not None:
            canonical = conversations_db.resolve_sync_conversation_redirect(uid, conversation_id)
            # The outbox transfers custody atomically before acknowledging this donor.
            context['redirect_to' if canonical else 'defer_reason'] = canonical or 'redirect_unresolved'
            return
        conversation_data = conversations_db.get_sync_redirected_conversation(uid, conversation_id)
        if conversation_data:
            conversation_id = conversation_data['id']
    if not conversation_data or conversation_data.get('deleted'):
        if context is not None:
            if conversation_data and conversation_data.get('deleted'):
                context['discarded'] = True  # A real deletion is terminal, never regenerated.
            else:
                context['defer_reason'] = 'conversation_missing'
        logger.info('event=sync_reprocess_callback outcome=unavailable')
        return

    if repair_fenced(conversation_data):
        raise SummaryRepairSuperseded(
            'summary repair ownership changed',
            retry_revision=(
                conversation_data.get('sync_content_revision')
                if summary_repair_refusal(conversation_data) is None
                else None
            ),
        )
    if conversation_data.get('sync_live_target') and conversation_data.get('status') == 'in_progress':
        # Live finalization owns the open row. SYNC_UPDATE would mark it
        # completed while the socket is still adding speech, after which the
        # finalizer skips processing that later content.
        if context is not None:
            context['defer_reason'] = 'open_live_target'
        return

    if context is not None and (context.get('sync_hold') or processing_hold.FIELD in conversation_data):
        context['sync_hold'] = True
        # Rollback bypasses admission, but still settles stored hold metadata
        # after success so lazy effects do not remain fenced indefinitely.
        outcome, due = (
            processing_hold.admission(conversation_data, context, now=time.time())
            if processing_hold.enabled_for(context)
            else ('ready', None)
        )
        processing_hold.record(outcome)
        context['hold_outcome'] = outcome
        if due is not None:
            context.update(defer_reason=outcome, defer_until=due)
            return
        if outcome in {'unchanged', 'late_cap', 'immaterial'}:
            if (conversation_data.get('smart_merge') or {}).get('role') == 'survivor' and refresh_owed(
                conversation_data
            ):
                settle_survivor(uid, conversation_id, owner=context['owner'], skip_processing=True)
            if not conversations_db.complete_sync_processing_hold(
                uid, conversation_id, conversation_data.get('sync_content_revision'), None
            ):
                raise SyncConversationPersistenceFenced('hold completion snapshot changed')
            context['hold_skipped'] = True
            return
        context['hold_snapshot'] = processing_hold.content_snapshot(conversation_data)

    # Intake already discarded a rule-settled fragment; skip the processing
    # spend. Everything else goes through the relevance step (SYNC_UPDATE),
    # which reassesses the whole merged transcript, so later speech promotes it.
    segments = conversation_data.get('transcript_segments', [])
    status = getattr(conversation_data.get('status'), 'value', conversation_data.get('status'))
    if (
        status == 'completed'
        and not occasion_relevance_enabled()
        and conversation_data.get('sync_relevance') == 'review'
        and not is_user_curated(conversation_data)
    ):
        verdict, rule = fragment_rule(segments)
        if verdict == 'discard':
            outcome = lifecycle_service.rule_discard_outcome(
                uid,
                conversation_id,
                sync_intake_decision(rule),
                expected_sync_content_revision=conversation_data.get('sync_content_revision'),
            )
            if outcome == 'discarded':
                record_conversation_relevance(trigger='sync_intake', verdict='discard', decided_by='rule', reason=rule)
            if outcome in ('discarded', 'already_discarded'):
                # The read predicate derives `discarded` for review rows, so only
                # the write's outcome can tell a stored discard from a refused one.
                context = PROCESS_CONTEXT.get()
                if context is not None:
                    context['discarded'] = True
            return

    if PROCESS_CONTEXT.get() is not None and not claim_from_snapshot(
        get_firestore_client(), uid, conversation_id, conversation_data
    ):
        raise SyncConversationPersistenceFenced('summary processing snapshot changed')

    if (
        context is not None
        and context.get('sync_hold')
        and (conversation_data.get('smart_merge') or {}).get('role') == 'survivor'
        and refresh_owed(conversation_data)
    ):
        # Preserve the smart-merge refresh lease/checkpoints and its vector work.
        settle_survivor(uid, conversation_id, owner=context['owner'])
        if context.get('hold_budget_denied_at_max'):
            if not conversations_db.complete_sync_processing_hold(
                uid, conversation_id, conversation_data.get('sync_content_revision'), None
            ):
                raise SyncConversationPersistenceFenced('hold completion snapshot changed')
            context['hold_skipped'] = True
            return
        refreshed = conversations_db.get_conversation(uid, conversation_id)
        if (
            refreshed
            and (refreshed.get('discarded') or summary_output_present(refreshed.get('structured')))
            and context.get('hold_snapshot') is not None
            and not conversations_db.complete_sync_processing_hold(
                uid,
                conversation_id,
                conversation_data.get('sync_content_revision'),
                context['hold_snapshot'] if summary_output_present(refreshed.get('structured')) else None,
            )
        ):
            raise SyncConversationPersistenceFenced('hold completion snapshot changed')
        return deserialize_conversation(refreshed) if refreshed else None

    # Convert to Conversation object
    conversation = deserialize_conversation(conversation_data)
    if language == _LINEAGE_RETRY_LANGUAGE:
        language = conversation.language or 'en'

    silent_redrive = is_silent_redrive(conversation_data)
    was_discarded = conversation.discarded
    prior_decision = conversation_data.get('relevance_decision')
    # process_conversation persists relevance_decision.trigger == 'sync_update'.
    # Intake only writes 'sync_intake' (or nothing). A later WAL segment re-enters
    # this function; that stored trigger is the already-processed signal.
    already_sync_processed = (
        isinstance(prior_decision, dict) and prior_decision.get('trigger') == ProcessingTrigger.SYNC_UPDATE.value
    )
    # Visible rows must not accept again. A prior discard is not a visible
    # finalization, so discarded -> visible still accepts once.
    already_visible_finalized = already_sync_processed and not was_discarded
    started = time.monotonic()
    try:
        processed_conversation = process_conversation(
            uid=uid,
            language_code=language or 'en',
            conversation=conversation,
            trigger=ProcessingTrigger.SYNC_UPDATE,
            defer_derived_effects=silent_redrive,
            user_kept=is_user_curated(conversation_data) or REPAIR_CONTEXT.get() is not None,
            persistence_observer=_require_current_conversation_persistence,
            # Deserialize drops relevance_decision. The raw row still has it:
            # sync_update means a previous enrichment, sync_intake or absence does not.
            prior_relevance_decision=prior_decision if isinstance(prior_decision, dict) else None,
        )
    except ConversationAbsorbed as absorbed:
        if context is not None:
            context['redirect_to'] = absorbed.canonical_id
            return
        canonical = conversations_db.get_sync_redirected_conversation(uid, conversation_id)
        return deserialize_conversation(canonical) if canonical else None

    if context is not None and context.get('hold_budget_denied_at_max'):
        if not conversations_db.complete_sync_processing_hold(
            uid, conversation_id, conversation_data.get('sync_content_revision'), None
        ):
            raise SyncConversationPersistenceFenced('hold completion snapshot changed')
        context['hold_skipped'] = True
        return None

    if (
        context is not None
        and context.get('hold_snapshot') is not None
        and (processed_conversation.discarded or summary_output_present(processed_conversation.structured))
        and not conversations_db.complete_sync_processing_hold(
            uid,
            conversation_id,
            conversation_data.get('sync_content_revision'),
            context['hold_snapshot'] if summary_output_present(processed_conversation.structured) else None,
        )
    ):
        raise SyncConversationPersistenceFenced('hold completion snapshot changed')
    elapsed = time.monotonic() - started
    # Persistence is guaranteed here: a fenced write raises before return.
    # client_platform is the Conversation field set at sync intake; None -> unknown.
    client_kind = resolve_client_kind(x_app_platform=getattr(conversation, 'client_platform', None), user_agent=None)
    if processed_conversation.discarded:
        if not already_sync_processed:
            record_client_journey_terminal('conversation_finalization', client_kind, 'cancelled', elapsed)
    elif not already_visible_finalized:
        record_client_journey_accepted('conversation_finalization', client_kind)
        record_client_journey_terminal('conversation_finalization', client_kind, 'success', elapsed)

    # Limitless uploads commonly begin as a short discarded fragment and only
    # become a real conversation after later WAL segments are merged. The
    # initial discarded pass is not a useful creation event, while the generic
    # reprocess path deliberately suppresses webhooks. Emit exactly at the
    # discarded -> visible transition so pendant conversations reach developer
    # integrations without duplicating events on ordinary later reprocessing.
    if (
        not silent_redrive
        and conversation.source == ConversationSource.limitless
        and was_discarded
        and not processed_conversation.discarded
    ):
        submit_with_context(postprocess_executor, _run_conversation_created_webhook, uid, processed_conversation)

    # Episodes: the WAL row joins the live episode covering it, so Home folds it under the
    # live row instead of a second capture's fragment. Off this lane, fail-open; a later
    # WAL append re-runs it and is a no-op once joined.
    schedule_after_finalization(uid, conversation_id, ProcessingTrigger.SYNC_UPDATE)

    logger.info('event=sync_reprocess_callback outcome=processed')
    return processed_conversation
