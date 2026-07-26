"""
Conversation Merge Utilities (Simplified)

This module provides functions for merging multiple conversations into one.
1. Creates a NEW conversation with merged raw data
2. Calls process_conversation() to generate all derived data
3. Deletes ALL source conversations

"""

import copy
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import database.conversations as conversations_db
from database._client import db as firestore_db
from database.vector_db import delete_vector
from models.audio_file import AudioFile
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.structured import Structured
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.conversations.datetime_utils import coerce_utc_datetime
from utils.conversations import lifecycle as lifecycle_service
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import (
    compute_audio_files_fingerprint,
    delete_conversation_audio_files,
    enqueue_conversation_artifact_build,
    list_audio_chunks,
    _get_storage_client,
    private_cloud_sync_bucket,
    _get_extension_for_path,
)
import logging

logger = logging.getLogger(__name__)


def _coerce_dt(value):
    return coerce_utc_datetime(value)


_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _photo_created_at_sort_key(photo: Dict) -> datetime:
    created_at = coerce_utc_datetime(photo.get('created_at'))
    if created_at is None:
        logger.warning(
            'conversation_merge_photo_missing_or_invalid_created_at',
            extra={'photo_id': photo.get('id'), 'has_created_at': 'created_at' in photo},
        )
        return _UTC_MIN
    return created_at


# Timestamp fields touched by the merge pipeline. Coerced once at the entry
# point so every downstream caller (sort key, max(), .isoformat(), gap math
# in _merge_transcript_segments) can assume a uniform tz-aware datetime
# rather than re-checking the source type at each use site.
_TIMESTAMP_FIELDS = ('started_at', 'finished_at', 'created_at')


def _normalize_conversation_timestamps(conversations: List[Dict]) -> List[Dict]:
    """Return shallow-copied conversation dicts with timestamp fields coerced.

    Older conversation docs persisted ``started_at`` / ``finished_at`` /
    ``created_at`` as ISO strings while newer docs store them as Firestore
    ``Timestamp`` (deserialised to tz-aware ``datetime``). Mixed shapes break
    ``sorted()`` key comparisons, ``max()``, datetime subtraction in
    ``_merge_transcript_segments``, and ``.isoformat()`` calls in
    ``perform_merge_async`` — each of which would otherwise raise and trip
    the outer ``except`` in ``perform_merge_async``, silently failing the
    merge for the same user population fixed by ``_coerce_dt`` in the
    validation step.

    We shallow-copy each dict so the source row in the caller's list isn't
    mutated. Unparseable timestamps degrade to ``None``; downstream sites
    already guard against ``None`` (e.g. ``if prev_finished and curr_started``)
    so a single bad field does not abort the merge.
    """
    normalized = []
    for conv in conversations:
        c = dict(conv)
        for field in _TIMESTAMP_FIELDS:
            if field in c:
                c[field] = _coerce_dt(c[field])
        normalized.append(c)
    return normalized


def validate_merge_compatibility(
    conversations: List[Dict],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate if conversations can be merged.

    Args:
        conversations: List of conversation dictionaries

    Returns:
        Tuple of (is_valid, error_message, warning_message)

    Rejection criteria (hard failures):
    - Less than 2 conversations
    - Any conversation is a soft-deleted tombstone
    - Any conversation is locked
    - Any conversation is not completed (processing/merging/in_progress)

    Warning criteria (soft, user informed but not blocked):
    - Large time gaps between conversations (> 1 hour)
    """
    if len(conversations) < 2:
        return False, "At least 2 conversations required to merge", None

    # Check none are soft-deleted. A soft-deleted tombstone is invisible to the
    # user, so merging it resurrects deleted content into a new visible
    # conversation — the inverse of the tombstone contract the sync merge path
    # already enforces (see conversations_db.eligible_merge_target, #10119).
    # `get_conversation` returns tombstones unfiltered and the /merge endpoint
    # only 404s on a missing (None) doc, so a deleted id passed by an API client
    # or a delete-vs-merge race would otherwise flow straight through.
    for conv in conversations:
        if conv.get('deleted'):
            return False, "Cannot merge a deleted conversation.", None

    # Check none are locked
    for conv in conversations:
        if conv.get('is_locked', False):
            return False, "Cannot merge locked conversations. Please unlock them first.", None

    # Check all are completed
    for conv in conversations:
        status = conv.get('status', 'completed')
        if status != 'completed':
            return False, f"Conversation {conv['id']} is not ready (status: {status}). Wait for it to complete.", None

    # Generate warnings for large gaps (but don't reject)
    warnings = []
    _UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)
    sorted_convs = sorted(conversations, key=lambda c: _coerce_dt(c.get('started_at')) or _UTC_MIN)

    for i in range(1, len(sorted_convs)):
        prev_finished = _coerce_dt(sorted_convs[i - 1].get('finished_at'))
        curr_started = _coerce_dt(sorted_convs[i].get('started_at'))
        if prev_finished and curr_started:
            gap_hours = (curr_started - prev_finished).total_seconds() / 3600
            if gap_hours > 1:
                warnings.append(f"{gap_hours:.1f}h gap detected")

    warning_msg = "; ".join(warnings) if warnings else None
    return True, None, warning_msg


def perform_merge_async(
    uid: str,
    conversation_ids: List[str],
    reprocess: bool = True,
) -> None:
    """
    Background task to perform conversation merge.

    Simplified flow:
    1. Fetch all source conversations
    2. Merge raw data (transcripts, photos)
    3. Copy audio chunks with adjusted timestamps
    4. Create NEW conversation with merged raw data
    5. Process conversation (generates title, summary, action items, memories, etc.)
    6. Delete ALL source conversations
    7. Send FCM notification

    Args:
        uid: User ID
        conversation_ids: List of conversation IDs to merge
        reprocess: Whether to process merged conversation (generate summary, etc.)
    """
    from utils.conversations.process_conversation import process_conversation
    from utils.notifications import send_merge_completed_message

    try:
        # 1. Fetch all source conversations
        conversations = []
        for conv_id in conversation_ids:
            conv = conversations_db.get_conversation(uid, conv_id)
            if conv:
                conversations.append(conv)

        if len(conversations) < 2:
            logger.error(f"Merge failed: Not enough conversations found for uid={uid}")
            _handle_merge_failure(uid, conversation_ids)
            return

        # A source can be soft-deleted between admission (validate_merge_compatibility
        # at the endpoint) and this background re-fetch — the delete-vs-merge race. Re-check
        # here, before reading any content: merging a tombstone would resurrect its deleted
        # transcript/photos/audio into a new visible conversation. Abort rather than merge.
        if any(conv.get('deleted') for conv in conversations):
            logger.error(f"Merge aborted: a source was deleted after admission uid={uid}")
            _handle_merge_failure(uid, conversation_ids)
            return

        # Normalise timestamp fields once so the sort key, max() reducer,
        # .isoformat() metadata, and _merge_transcript_segments arithmetic
        # below can all assume tz-aware datetimes regardless of how each
        # source doc persisted its timestamps. See _coerce_dt for shape
        # details and rationale.
        conversations = _normalize_conversation_timestamps(conversations)

        # Sort by started_at (earliest first). _UTC_MIN keeps sort total even
        # if a doc has no (or an unparseable) started_at.
        _UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)
        sorted_convs = sorted(conversations, key=lambda c: c.get('started_at') or _UTC_MIN)

        # 2. Merge raw data
        merged_segments = _merge_transcript_segments(sorted_convs)
        merged_photos = _collect_all_photos(uid, sorted_convs)

        # 3. Generate new conversation ID and copy audio chunks
        new_conversation_id = str(uuid.uuid4())
        merged_audio_files = _copy_audio_chunks_for_merge(uid, sorted_convs, new_conversation_id)

        # 4. Determine basic fields from source conversations
        # Use earliest conversation's dates. created_at fallback uses
        # `or` (not `.get(..., default)`) so a present-but-None field still
        # falls back to "now" — the normaliser turns unparseable strings
        # into None.
        created_at = sorted_convs[0].get('created_at') or datetime.now(timezone.utc)
        started_at = sorted_convs[0].get('started_at')
        finished_at = max((c.get('finished_at') or _UTC_MIN) for c in sorted_convs)
        language = sorted_convs[0].get('language', 'en')
        source = sorted_convs[0].get('source', 'omi')

        # Visibility: most restrictive wins
        visibility = _determine_visibility(sorted_convs)

        # Private cloud sync: True if any has it
        private_cloud_sync_enabled = any(c.get('private_cloud_sync_enabled', False) for c in sorted_convs)

        # Discarded: only if ALL are discarded
        discarded = all(c.get('discarded', False) for c in sorted_convs)

        # Geolocation: use first conversation's
        geolocation = sorted_convs[0].get('geolocation')

        # Capture provenance is safe to retain only when every source came
        # from the same known device.
        client_device_id, client_platform = _shared_client_device_provenance(sorted_convs)

        # 5. Create merge metadata
        merge_metadata = {
            'merged_at': datetime.now(timezone.utc).isoformat(),
            'source_conversation_ids': conversation_ids,
            'source_details': [
                {
                    'id': c['id'],
                    'started_at': c.get('started_at').isoformat() if c.get('started_at') else None,
                    'finished_at': c.get('finished_at').isoformat() if c.get('finished_at') else None,
                    'source': c.get('source', 'unknown'),
                }
                for c in sorted_convs
            ],
        }

        # 6. Create new conversation object
        new_conversation = Conversation(
            id=new_conversation_id,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            structured=Structured(),  # Empty - will be generated by process_conversation
            language=language,
            source=source,
            transcript_segments=merged_segments,
            photos=merged_photos,
            audio_files=merged_audio_files,
            geolocation=geolocation,
            visibility=visibility,
            private_cloud_sync_enabled=private_cloud_sync_enabled,
            discarded=discarded,
            status=ConversationStatus.processing,
            client_device_id=client_device_id,
            client_platform=client_platform,
            external_data={'merge_metadata': merge_metadata},
        )

        # 7. Save stub conversation to database
        lifecycle_service.create_processing_conversation(uid, new_conversation.model_dump())

        # Build the conversation-level playback artifact for the merged conversation.
        # Fingerprint-named task: dedups with the enqueue process_conversation may
        # also fire on the reprocess path.
        if merged_audio_files and is_audio_merge_dispatch_enabled():
            files_payload = [af.model_dump() for af in merged_audio_files]
            enqueue_conversation_artifact_build(
                uid, new_conversation_id, compute_audio_files_fingerprint(files_payload), caller='merge_conversations'
            )

        # Store photos in subcollection if any
        if merged_photos:
            conversations_db.store_conversation_photos(uid, new_conversation_id, merged_photos)

        # 8. Process conversation to generate title, summary, action items, memories, etc.
        if reprocess:
            try:
                with lifecycle_service.processing_admission_guard(uid, new_conversation_id, rollback_on_failure=False):
                    processed_conversation = process_conversation(
                        uid,
                        new_conversation.language or 'en',
                        new_conversation,
                        force_process=True,
                        is_reprocess=False,  # Not a reprocess - this is a new conversation
                    )
            except Exception as e:
                logger.error(f"Error processing merged conversation: {e}")
                # Even if processing fails, continue with cleanup
                # Mark conversation as completed
                lifecycle_service.complete(uid, new_conversation_id)
        else:
            # If not reprocessing, just mark as completed
            lifecycle_service.complete(uid, new_conversation_id)

        # 9. Delete ALL source conversations and their related data
        for conv in sorted_convs:
            _delete_conversation_and_related_data(uid, conv['id'])

        # 10. Send FCM notification
        send_merge_completed_message(uid, new_conversation_id, conversation_ids)

        logger.info(
            f"Merge completed: uid={uid}, new_id={new_conversation_id}, merged={len(conversation_ids)} conversations"
        )

    except Exception as e:
        logger.error(f"Merge failed with exception: {e}")
        import traceback

        traceback.print_exc()
        _handle_merge_failure(uid, conversation_ids)


def _merge_transcript_segments(conversations: List[Dict]) -> List[Dict]:
    """
    Merge transcript segments from all conversations sequentially.

    Strategy:
    - Sort conversations by started_at
    - Append segments sequentially
    - Adjust timestamps to account for gaps between conversations

    Args:
        conversations: List of conversation dictionaries (already sorted by started_at)

    Returns:
        List of merged transcript segment dictionaries
    """
    merged = []
    cumulative_offset = 0.0

    for i, conv in enumerate(conversations):
        segments = conv.get('transcript_segments', [])

        if i == 0:
            # First conversation - use segments as-is
            merged.extend([copy.deepcopy(s) for s in segments])
            if segments:
                cumulative_offset = max(s.get('end', 0) for s in segments)
            elif conv.get('finished_at') and conv.get('started_at'):
                cumulative_offset = (conv['finished_at'] - conv['started_at']).total_seconds()
        else:
            # Calculate gap from previous conversation
            prev_finished = conversations[i - 1].get('finished_at')
            curr_started = conv.get('started_at')

            gap = 0.0
            if prev_finished and curr_started:
                gap = max(0, (curr_started - prev_finished).total_seconds())

            offset = cumulative_offset + gap

            # Adjust timestamps for this conversation's segments
            for seg in segments:
                seg_copy = copy.deepcopy(seg)
                seg_copy['start'] = seg.get('start', 0) + offset
                seg_copy['end'] = seg.get('end', 0) + offset
                merged.append(seg_copy)

            # Update cumulative offset for next conversation
            if segments:
                cumulative_offset = offset + max(s.get('end', 0) for s in segments)
            elif conv.get('finished_at') and conv.get('started_at'):
                duration = (conv['finished_at'] - conv['started_at']).total_seconds()
                cumulative_offset = offset + duration

    return merged


def _collect_all_photos(uid: str, conversations: List[Dict]) -> List[Dict]:
    """
    Fetch and merge photos from all conversation subcollections.

    Strategy:
    - Fetch photos from each conversation's subcollection
    - Deduplicate by photo ID
    - Sort by created_at

    Args:
        uid: User ID
        conversations: List of conversation dictionaries

    Returns:
        List of photo dictionaries
    """
    all_photos = []
    seen_ids = set()

    for conv in conversations:
        try:
            photos = conversations_db.get_conversation_photos(uid, conv['id'])
            for photo in photos:
                photo_id = photo.get('id')
                if photo_id and photo_id not in seen_ids:
                    all_photos.append(photo)
                    seen_ids.add(photo_id)
        except Exception as e:
            logger.error(f"Error fetching photos for {conv['id']}: {e}")

    # Sort by creation time with a uniform tz-aware UTC key. Missing or malformed
    # created_at values are retained and ordered first, with structured metrics.
    all_photos.sort(key=_photo_created_at_sort_key)
    return all_photos


def _copy_audio_chunks_for_merge(
    uid: str,
    conversations: List[Dict],
    new_conversation_id: str,
) -> List[AudioFile]:
    """
    Copy audio chunks from all source conversations to new conversation.

    Audio chunks are stored in GCS at:
        chunks/{uid}/{conversation_id}/{timestamp}.bin  (or .enc for encrypted)
        chunks/{uid}/{conversation_id}/{first_ts}-{last_ts}.batch.bin  (batch blobs)

    The filenames contain absolute Unix timestamps (when chunk was recorded).
    We preserve original filenames to maintain both single-chunk and batch blob naming.

    Strategy:
    - Copy all chunks from all conversations to new conversation path
    - Preserve original filenames (handles single and batch blobs)
    - Create AudioFile records from the copied chunks

    Args:
        uid: User ID
        conversations: List of conversation dictionaries (sorted by started_at)
        new_conversation_id: ID for the new merged conversation

    Returns:
        List of AudioFile objects
    """
    bucket = _get_storage_client().bucket(private_cloud_sync_bucket)
    has_chunks = False

    for conv in conversations:
        conv_id = conv['id']

        # A copy failure here must propagate, not be swallowed. perform_merge_async deletes every
        # source conversation's original audio chunks (step 9) after this returns, so a swallowed
        # failure — while has_chunks may already be True from an earlier source — would let that
        # deletion destroy audio that was never copied anywhere. Raising instead aborts the merge
        # into _handle_merge_failure, which runs before any source is deleted.
        chunks = list_audio_chunks(uid, conv_id)
        for chunk in chunks:
            has_chunks = True

            # Preserve original filename (handles both single and batch blob naming)
            original_filename = chunk['path'].split('/')[-1]
            new_path = f'chunks/{uid}/{new_conversation_id}/{original_filename}'
            source_blob = bucket.blob(chunk['path'])
            bucket.copy_blob(source_blob, bucket, new_path)

    # Create AudioFile records from copied chunks
    if has_chunks:
        try:
            return conversations_db.create_audio_files_from_chunks(uid, new_conversation_id)
        except Exception as e:
            logger.error(f"Error creating audio files: {e}")

    return []


def _determine_visibility(conversations: List[Dict]) -> str:
    """
    Determine visibility for merged conversation.

    Strategy: Most restrictive wins (private > shared > public)
    """
    visibility_priority = {'private': 0, 'shared': 1, 'public': 2}

    min_priority = 2  # Start with least restrictive (public)
    min_visibility = 'public'

    for conv in conversations:
        vis = conv.get('visibility', 'private')
        priority = visibility_priority.get(vis, 0)
        if priority < min_priority:
            min_priority = priority
            min_visibility = vis

    return min_visibility


def _shared_client_device_provenance(conversations: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
    """Return capture provenance only when every merged conversation agrees.

    A merged conversation can represent multiple devices. Assigning one source
    device to that output would make a cross-device capture appear in the wrong
    device-scoped memory view, so mixed or missing provenance stays unknown.
    """
    provenance = {
        (conversation.get('client_device_id'), conversation.get('client_platform')) for conversation in conversations
    }
    if len(provenance) != 1:
        return None, None
    client_device_id, client_platform = provenance.pop()
    if not client_device_id or not client_platform:
        return None, None
    return client_device_id, client_platform


def _delete_conversation_and_related_data(uid: str, conversation_id: str) -> None:
    """
    Delete a conversation and all its generated/related data.

    Deletes:
    - Memories linked to this conversation
    - Action items linked to this conversation (standalone collection)
    - Photos subcollection
    - Audio chunks in GCS
    - Vector embedding
    - Conversation document
    """
    # Import here to avoid circular imports
    import database.memories as memories_db
    import database.action_items as action_items_db

    memory_system: MemorySystem | None = None
    try:
        memory_system = pin_memory_system(uid, db_client=firestore_db)
        if memory_system == MemorySystem.CANONICAL:
            MemoryService(db_client=firestore_db).retract_conversation_memories(uid, conversation_id)
        else:
            memories_db.delete_memories_for_conversation(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting memories for {conversation_id}: {e}")
        # A canonical-selected account must retry the merge rather than delete
        # its source conversation while its canonical evidence retraction is
        # unavailable. Continuing here would silently leave active canonical
        # memories pointing at a deleted source.
        if memory_system == MemorySystem.CANONICAL:
            raise

    try:
        # Delete action items from standalone collection
        action_items_db.delete_action_items_for_conversation(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting action items for {conversation_id}: {e}")

    try:
        # Delete photos subcollection
        conversations_db.delete_conversation_photos(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting photos for {conversation_id}: {e}")

    try:
        # Delete audio chunks from GCS
        delete_conversation_audio_files(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting audio files for {conversation_id}: {e}")

    try:
        # Delete vector embedding
        delete_vector(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting vector for {conversation_id}: {e}")

    try:
        # Delete conversation document
        conversations_db.delete_conversation(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}")


def _handle_merge_failure(uid: str, conversation_ids: List[str]) -> None:
    """
    Handle merge failure by resetting conversation statuses.

    Since source conversations were set to 'merging' status, we need to
    reset them back to 'completed' so the user can try again or continue using them.
    """
    logger.error(f"Merge failed for conversations: {conversation_ids}")
    for conv_id in conversation_ids:
        try:
            lifecycle_service.complete(uid, conv_id)
        except Exception as e:
            logger.error(f"Error resetting status for {conv_id}: {e}")
