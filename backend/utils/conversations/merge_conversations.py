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
from database.vector_db import delete_vector
from models.conversation import (
    AudioFile,
    Conversation,
    ConversationStatus,
    Structured,
)
from utils.other.storage import (
    delete_conversation_audio_files,
    list_audio_chunks,
    storage_client,
    private_cloud_sync_bucket,
)
import logging

logger = logging.getLogger(__name__)


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
    - Any conversation is locked
    - Any conversation is not completed (processing/merging/in_progress)

    Warning criteria (soft, user informed but not blocked):
    - Large time gaps between conversations (> 1 hour)
    """
    if len(conversations) < 2:
        return False, "At least 2 conversations required to merge", None

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
    sorted_convs = sorted(conversations, key=lambda c: c.get('started_at', datetime.min))

    for i in range(1, len(sorted_convs)):
        prev_finished = sorted_convs[i - 1].get('finished_at')
        curr_started = sorted_convs[i].get('started_at')
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

        # Sort by started_at (earliest first)
        sorted_convs = sorted(conversations, key=lambda c: c.get('started_at', datetime.min))

        # 2. Merge raw data
        merged_segments = _merge_transcript_segments(sorted_convs)
        merged_photos = _collect_all_photos(uid, sorted_convs)

        # 3. Generate new conversation ID and copy audio chunks
        new_conversation_id = str(uuid.uuid4())
        merged_audio_files = _copy_audio_chunks_for_merge(uid, sorted_convs, new_conversation_id)

        # 4. Determine basic fields from source conversations
        # Use earliest conversation's dates
        created_at = sorted_convs[0].get('created_at', datetime.now(timezone.utc))
        started_at = sorted_convs[0].get('started_at')
        finished_at = max(c.get('finished_at', datetime.min) for c in sorted_convs)
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
            external_data={'merge_metadata': merge_metadata},
        )

        # 7. Save stub conversation to database
        conversations_db.upsert_conversation(uid, new_conversation.dict())

        # Store photos in subcollection if any
        if merged_photos:
            conversations_db.store_conversation_photos(uid, new_conversation_id, merged_photos)

        # 8. Process conversation to generate title, summary, action items, memories, etc.
        if reprocess:
            try:
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
                conversations_db.update_conversation_status(uid, new_conversation_id, ConversationStatus.completed)
        else:
            # If not reprocessing, just mark as completed
            conversations_db.update_conversation_status(uid, new_conversation_id, ConversationStatus.completed)

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

    # Sort by creation time
    all_photos.sort(key=lambda p: p.get('created_at', datetime.min))
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

    The timestamps in chunk filenames are absolute Unix timestamps (when chunk was recorded).
    We keep the original timestamps since they represent the actual recording time.

    Strategy:
    - Copy all chunks from all conversations to new conversation path
    - Keep original timestamps (they're absolute, not relative)
    - Create AudioFile records from the copied chunks

    Args:
        uid: User ID
        conversations: List of conversation dictionaries (sorted by started_at)
        new_conversation_id: ID for the new merged conversation

    Returns:
        List of AudioFile objects
    """
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    has_chunks = False

    for conv in conversations:
        conv_id = conv['id']

        # List and copy chunks for this conversation
        try:
            chunks = list_audio_chunks(uid, conv_id)
            for chunk in chunks:
                has_chunks = True
                original_ts = chunk['timestamp']

                # Determine extension from original path
                ext = 'enc' if chunk['path'].endswith('.enc') else 'bin'

                # Copy to new path with same timestamp (it's absolute Unix time)
                new_path = f'chunks/{uid}/{new_conversation_id}/{original_ts:.3f}.{ext}'
                source_blob = bucket.blob(chunk['path'])
                bucket.copy_blob(source_blob, bucket, new_path)

        except Exception as e:
            logger.error(f"Error copying chunks for {conv_id}: {e}")

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

    try:
        # Delete memories
        memories_db.delete_memories_for_conversation(uid, conversation_id)
    except Exception as e:
        logger.error(f"Error deleting memories for {conversation_id}: {e}")

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
            conversations_db.update_conversation_status(uid, conv_id, ConversationStatus.completed)
        except Exception as e:
            logger.error(f"Error resetting status for {conv_id}: {e}")
