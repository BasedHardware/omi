"""Publish deferred recording memories before the chat retrieval scope opens."""

import asyncio
import logging
from time import monotonic, sleep

from config.transcript_publication import pre_chat_memory_catch_up_enabled
from database._client import get_data_plane_firestore_client
from database.recording_memory_catch_up import RecordingMemoryChanged, claim_recording, pending_recordings
from utils.executors import postprocess_executor, run_blocking

logger = logging.getLogger(__name__)

CHAT_CATCH_UP_SECONDS = 12


def _publish_claim(claim):
    from database.conversations import prepare_conversation_for_read
    from utils.conversations.factory import deserialize_conversation
    from utils.conversations.process_conversation import extract_published_memories
    from utils.conversations.minimum_derived import intentional_short_clip_minimum
    from utils.memory.memory_service import MemoryService

    row = prepare_conversation_for_read(claim.row, claim.uid, firestore_client=claim.client, strict_transcript=True)
    if not row:
        return False
    if intentional_short_clip_minimum(row):
        claim.complete_empty()
        return True
    settled = False

    def publish(items):
        nonlocal settled
        if items:
            MemoryService(db_client=claim.client).replace_conversation_memories(
                claim.uid, row['id'], items, prepare_publication=claim.prepare_commit
            )
        else:
            claim.complete_empty()
        settled = True

    extract_published_memories(
        claim.uid, deserialize_conversation(row), db_client=claim.client, publish_memories=publish
    )
    return settled


def _catch_up(uid, recording_id, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    deadline = monotonic() + CHAT_CATCH_UP_SECONDS
    observed_pending = False

    def finish_recording(source):
        nonlocal observed_pending
        target = None
        while monotonic() < deadline:
            target, busy, claim = claim_recording(client, uid, source)
            if busy:
                observed_pending = True
                sleep(0.2)
                continue
            if claim is None:
                break
            observed_pending = True
            settled = False
            try:
                settled = _publish_claim(claim)
            except RecordingMemoryChanged:
                # Re-resolve the recording. A newer publication can be available already.
                continue
            except Exception as error:
                logger.warning('recording memory extraction unavailable error_type=%s', type(error).__name__)
            finally:
                if not settled:
                    claim.release()
            break
        return target

    try:
        if recording_id:
            resolved = finish_recording(recording_id)
            if resolved:
                return resolved
        for source in pending_recordings(client, uid, destination=recording_id):
            if source != recording_id:
                finish_recording(source)
    finally:
        if observed_pending:
            from utils.llms.memory import clear_prompt_data_cache

            clear_prompt_data_cache(uid)
    return None


async def before_chat(uid, context=None):
    if not pre_chat_memory_catch_up_enabled():
        return context
    recording_id = context.id if context and context.type == 'conversation' else None
    if recording_id:
        from utils.mcp_server.handlers.conversations import is_safe_conversation_id

        if not is_safe_conversation_id(recording_id):
            return context
    try:
        async with asyncio.timeout(CHAT_CATCH_UP_SECONDS):
            resolved = await run_blocking(postprocess_executor, _catch_up, uid, recording_id)
    except Exception as error:
        logger.warning('pre-chat recording memory catch-up unavailable error_type=%s', type(error).__name__)
        return context
    if resolved and recording_id and resolved != recording_id:
        return context.model_copy(update={'id': resolved})
    return context
