"""The pre-notes absorption boundary, shared by live, sync and recovery.

Relevance and paid-budget admission run before this boundary. Loading the merge
worker here avoids a process_conversation <-> smart_merge import cycle.
"""

import importlib
from typing import Any

from config.merge_before_processing import enabled
from config.conversation_smart_merge import MIN_WORDS
from utils.enrichment.admission import ConversationAbsorbed
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.sync import processing_hold


def before_notes(
    uid: str,
    conversation: Any,
    trigger: ProcessingTrigger,
    *,
    finalization_fence: tuple[str, int, int] | None = None,
) -> None:
    if not enabled() or trigger not in {
        ProcessingTrigger.CAPTURE_END,
        ProcessingTrigger.SYNC_UPDATE,
        ProcessingTrigger.SERVER_RECOVERY,
    }:
        return
    if getattr(conversation, 'source', None) != 'omi' or not getattr(conversation, 'id', None):
        return
    if getattr(conversation, 'record_lane_owner', None) in {'batch_live_v1', 'batch_sync_v1'}:
        return
    if sum(len(str(s.text or '').split()) for s in conversation.transcript_segments or []) < MIN_WORDS:
        return
    worker = importlib.import_module('utils.conversations.smart_merge')
    context = PROCESS_CONTEXT.get()
    owner = finalization_fence[0] if finalization_fence else (context or {}).get('owner', 'merge-before-notes')
    canonical = worker.absorb_before_notes(
        uid,
        conversation.id,
        trigger=trigger,
        owner=owner,
        finalization_fence=finalization_fence,
        donor_digest=processing_hold.content_snapshot(conversation.model_dump())['digest'],
    )
    if canonical:
        raise ConversationAbsorbed(canonical)
