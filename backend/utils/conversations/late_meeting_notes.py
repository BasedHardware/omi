"""Refresh only notes when approved screen evidence arrives after a blind note."""

import logging

from google.cloud.firestore_v1 import transactional

from database import conversations as conversations_db
from database import screen_frames as screen_frames_db
from database._client import get_firestore_client
from database.notes_identity import claim_late_evidence
from utils.conversations import lifecycle
from utils.conversations.factory import deserialize_conversation
from utils.conversations.meeting_notes_wiring import (
    meeting_notes_rich_context_enabled,
)
from utils.conversations.process_conversation import _get_structured
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.screen_content_window import selection_fingerprint, trusted_content_window
from utils.executors import db_executor, llm_executor, run_blocking
from utils.other.storage import configured_screen_frames_bucket
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _claim(uid, conversation_id, marker_at, fingerprint):
    client = get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    return transactional(claim_late_evidence)(client.transaction(), ref, marker_at=marker_at, fingerprint=fingerprint)


async def refresh_notes_after_evidence(uid: str, conversation_id: str) -> None:
    """No memory, app, embedding, enrollment, or learning work from this refresh."""
    if not meeting_notes_rich_context_enabled():
        return
    try:
        raw = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        window = trusted_content_window(raw) if raw else None
        bucket = configured_screen_frames_bucket()
        if not window or not bucket:
            return
        marker_at, fingerprint = await run_blocking(
            db_executor, screen_frames_db.get_conversation_screen_frames_marker, uid, conversation_id, bucket=bucket
        )
        if marker_at is None or fingerprint != selection_fingerprint(*window):
            return
        if not await run_blocking(db_executor, _claim, uid, conversation_id, marker_at, fingerprint):
            return
        conversation = deserialize_conversation(raw)
        structured, discarded = await run_blocking(
            llm_executor, _get_structured, uid, 'en', conversation, trigger=ProcessingTrigger.SCREEN_EVIDENCE
        )
        context = getattr(structured, '_notes_identity', None)
        if discarded or context is None:
            return
        payload = {
            'id': conversation_id,
            'status': 'completed',
            'structured': structured.model_dump(),
            'transcript_segments': [s.model_dump() for s in conversation.transcript_segments],
            'sync_content_revision': raw.get('sync_content_revision'),
            '_notes_identity': context,
            '_notes_evidence_reprocess': True,
        }
        await run_blocking(db_executor, lifecycle.persist_processed_conversation, uid, payload)
    except Exception as error:  # optional evidence must not fail screenshot egress
        logger.warning('late notes evidence refresh failed uid=%s error_type=%s', uid, type(error).__name__)
        record_fallback(
            component='conversation_finalization',
            from_mode='screen_evidence',
            to_mode='notes_without_evidence',
            reason='other',
            outcome='degraded',
            log=logger,
        )
