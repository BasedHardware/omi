"""
Conversation Merge Utilities

This module provides functions for merging multiple conversations into one.
The merge process is asynchronous - conversations are marked as 'merging'
and the actual merge happens in a background task.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import copy

import database.conversations as conversations_db
from database.vector_db import delete_vector
from utils.conversations.process_conversation import save_structured_vector
from models.conversation import (
    Conversation,
    ConversationStatus,
)


# Maximum allowed time gap between consecutive conversations (in minutes)
MAX_TIME_GAP_MINUTES = 15


def validate_merge_compatibility(
    conversations: List[Dict], max_time_gap_minutes: int = MAX_TIME_GAP_MINUTES
) -> Tuple[bool, Optional[str]]:
    """
    Validate if conversations can be merged.

    Args:
        conversations: List of conversation dictionaries
        max_time_gap_minutes: Maximum allowed gap between consecutive conversations

    Returns:
        Tuple of (is_valid, error_message)

    Validation rules:
    - At least 2 conversations
    - All conversations completed (not processing or merging)
    - None are locked
    - Time gaps between consecutive conversations ≤ max_time_gap_minutes
    """
    if len(conversations) < 2:
        return False, "At least 2 conversations required to merge"

    # Check all are completed
    for conv in conversations:
        status = conv.get('status', 'completed')
        if status != 'completed':
            return False, f"Conversation {conv['id']} is not ready (status: {status}). Wait for it to complete."

    # Check none are locked
    for conv in conversations:
        if conv.get('is_locked', False):
            return False, "Cannot merge locked conversations. Please unlock them first."

    # Sort by started_at
    sorted_convs = sorted(conversations, key=lambda c: c['started_at'])

    # Check time gaps between consecutive conversations
    max_gap_seconds = max_time_gap_minutes * 60
    for i in range(1, len(sorted_convs)):
        prev_conv = sorted_convs[i - 1]
        current_conv = sorted_convs[i]

        prev_finished = prev_conv.get('finished_at')
        current_started = current_conv.get('started_at')

        if prev_finished and current_started:
            time_gap = (current_started - prev_finished).total_seconds()

            if time_gap > max_gap_seconds:
                gap_minutes = time_gap / 60
                return (
                    False,
                    f"Time gap between conversations is {gap_minutes:.0f} minutes (max allowed: {max_time_gap_minutes} minutes)",
                )

    return True, None


def merge_transcript_segments_sequential(conversations: List[Dict]) -> List[Dict]:
    """
    Merge transcript segments from multiple conversations sequentially.

    Conversations are ordered by started_at, and each conversation's segments
    are appended after the previous conversation's segments with timestamp
    adjustments that preserve the actual timeline including gaps.

    Args:
        conversations: List of conversation dictionaries sorted by started_at

    Returns:
        List of merged transcript segment dictionaries
    """
    # Sort conversations by started_at (earliest first)
    sorted_conversations = sorted(conversations, key=lambda c: c.get('started_at', datetime.min))

    merged_segments = []
    cumulative_offset = 0.0

    for i, conversation in enumerate(sorted_conversations):
        segments = conversation.get('transcript_segments', [])

        if i == 0:
            # First conversation - use segments as-is
            merged_segments.extend(copy.deepcopy(segments))

            # Calculate where this conversation ended
            if segments:
                cumulative_offset = max(seg.get('end', 0) for seg in segments)
            elif conversation.get('finished_at') and conversation.get('started_at'):
                # No segments but have duration
                cumulative_offset = (conversation['finished_at'] - conversation['started_at']).total_seconds()
        else:
            # Calculate time gap between this and previous conversation
            prev_conversation = sorted_conversations[i - 1]
            prev_finished = prev_conversation.get('finished_at')
            current_started = conversation.get('started_at')

            time_gap = 0.0
            if prev_finished and current_started:
                time_gap = (current_started - prev_finished).total_seconds()
                time_gap = max(0, time_gap)  # Ensure non-negative

            # Offset includes both previous content and the gap
            offset = cumulative_offset + time_gap

            # Adjust all segments in this conversation
            for segment in segments:
                adjusted_segment = copy.deepcopy(segment)
                adjusted_segment['start'] = segment.get('start', 0) + offset
                adjusted_segment['end'] = segment.get('end', 0) + offset
                # Keep original segment.id (already unique)
                merged_segments.append(adjusted_segment)

            # Update cumulative offset for next conversation
            if segments:
                last_end = max(seg.get('end', 0) for seg in segments)
                cumulative_offset = offset + last_end
            elif conversation.get('finished_at') and conversation.get('started_at'):
                duration = (conversation['finished_at'] - conversation['started_at']).total_seconds()
                cumulative_offset = offset + duration

    return merged_segments


def merge_action_items(conversations: List[Dict], primary_id: str) -> List[Dict]:
    """
    Merge action items with deduplication.

    Deduplication Strategy:
    - Compare descriptions (case-insensitive, trimmed)
    - If duplicate found, keep the one with earliest created_at
    - Preserve completion status from most recent update

    Args:
        conversations: List of conversation dictionaries
        primary_id: ID of the primary (merged) conversation

    Returns:
        List of merged action item dictionaries
    """
    seen_descriptions = {}  # key -> action_item
    merged_items = []

    for conversation in sorted(conversations, key=lambda c: c.get('started_at', datetime.min)):
        structured = conversation.get('structured', {})
        action_items = structured.get('action_items', [])

        for item in action_items:
            description = item.get('description', '')
            key = description.lower().strip()

            if key not in seen_descriptions:
                # Update conversation_id to primary
                item_copy = copy.deepcopy(item)
                item_copy['conversation_id'] = primary_id
                seen_descriptions[key] = item_copy
                merged_items.append(item_copy)
            else:
                # Update if this one is completed and existing is not
                existing = seen_descriptions[key]
                if item.get('completed') and not existing.get('completed'):
                    existing['completed'] = True
                    existing['completed_at'] = item.get('completed_at')

    return merged_items


def merge_events(conversations: List[Dict]) -> List[Dict]:
    """
    Merge events with deduplication.

    Deduplication Strategy:
    - Compare title and start time (within 5 minute window)
    - If duplicate found, keep the one with more detailed description

    Args:
        conversations: List of conversation dictionaries

    Returns:
        List of merged event dictionaries
    """
    merged_events = []

    for conversation in conversations:
        structured = conversation.get('structured', {})
        events = structured.get('events', [])

        for event in events:
            # Check for duplicates
            is_duplicate = False
            for existing in merged_events:
                event_start = event.get('start')
                existing_start = existing.get('start')

                if event_start and existing_start:
                    time_diff = abs((event_start - existing_start).total_seconds())
                    if event.get('title') == existing.get('title') and time_diff < 300:  # 5 minutes
                        is_duplicate = True
                        # Update if this description is longer
                        if len(event.get('description', '')) > len(existing.get('description', '')):
                            existing['description'] = event.get('description', '')
                        # Update created status if any was created
                        if event.get('created'):
                            existing['created'] = True
                        break

            if not is_duplicate:
                merged_events.append(copy.deepcopy(event))

    return merged_events


def merge_photos(conversations: List[Dict]) -> List[Dict]:
    """
    Merge photos from all conversations.

    Strategy:
    - Collect all photos from all conversations
    - Sort by created_at
    - Keep unique IDs

    Args:
        conversations: List of conversation dictionaries

    Returns:
        List of merged photo dictionaries
    """
    all_photos = []
    seen_ids = set()

    for conversation in conversations:
        photos = conversation.get('photos', [])
        for photo in photos:
            photo_id = photo.get('id')
            if photo_id and photo_id not in seen_ids:
                all_photos.append(copy.deepcopy(photo))
                seen_ids.add(photo_id)

    # Sort by creation time
    all_photos.sort(key=lambda p: p.get('created_at', datetime.min))

    return all_photos


def merge_audio_files(conversations: List[Dict], primary_id: str) -> List[Dict]:
    """
    Merge audio files from all conversations.

    Strategy:
    - Collect all audio files from all conversations
    - Keep chunk references as-is (chunks stay at original GCS paths)
    - Update conversation_id metadata to point to merged conversation
    - Sort by started_at for chronological ordering

    Note: The physical audio chunks in GCS remain at their original paths
    (e.g., chunks/{uid}/{original_conversation_id}/{timestamp}.bin).
    Only the AudioFile metadata is updated.

    Args:
        conversations: List of conversation dictionaries
        primary_id: ID of the merged conversation

    Returns:
        List of merged audio file dictionaries
    """
    all_audio_files = []

    for conversation in sorted(conversations, key=lambda c: c.get('started_at', datetime.min)):
        audio_files = conversation.get('audio_files', [])
        for audio_file in audio_files:
            audio_copy = copy.deepcopy(audio_file)
            # Update metadata reference to merged conversation
            audio_copy['conversation_id'] = primary_id
            all_audio_files.append(audio_copy)

    # Sort by started_at for chronological ordering
    all_audio_files.sort(key=lambda af: af.get('started_at', datetime.min))

    return all_audio_files


def deep_merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Recursively merge dict2 into dict1."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def merge_external_data(conversations: List[Dict]) -> Optional[Dict]:
    """
    Deep merge external_data dictionaries from all conversations.

    Strategy:
    - Iterate through all conversations in chronological order
    - Merge dictionaries recursively
    - Later conversations' data overrides earlier ones for conflicting keys

    Args:
        conversations: List of conversation dictionaries

    Returns:
        Merged external_data dictionary or None if no data
    """
    # Sort conversations by started_at
    sorted_conversations = sorted(conversations, key=lambda c: c.get('started_at', datetime.min))

    merged_external_data = {}
    for conversation in sorted_conversations:
        external_data = conversation.get('external_data')
        if external_data:
            merged_external_data = deep_merge_dicts(merged_external_data, external_data)

    return merged_external_data if merged_external_data else None


def migrate_photos_to_primary(uid: str, primary_id: str, secondary_ids: List[str]) -> None:
    """
    Copy photos from secondary conversations to primary BEFORE deletion.

    Args:
        uid: User ID
        primary_id: Primary conversation ID
        secondary_ids: List of secondary conversation IDs
    """
    for secondary_id in secondary_ids:
        try:
            photos = conversations_db.get_conversation_photos(uid, secondary_id)
            if photos:
                # Store photos in primary conversation
                conversations_db.store_conversation_photos(uid, primary_id, photos)
        except Exception as e:
            print(f"Error migrating photos from {secondary_id}: {e}")


def determine_visibility(conversations: List[Dict]) -> str:
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


def perform_merge_async(
    uid: str,
    conversation_ids: List[str],
    primary_id: str,
    reprocess: bool = True,
) -> None:
    """
    Background task to perform the actual conversation merge.

    This function is called asynchronously after the API returns.
    On completion, it sends an FCM data message to notify the app.

    Args:
        uid: User ID
        conversation_ids: List of all conversation IDs to merge
        primary_id: ID of the primary conversation (earliest)
        reprocess: Whether to regenerate summary from merged content
    """
    from utils.notifications import send_merge_completed_message

    try:
        # Fetch all conversations with full data
        conversations = []
        for conv_id in conversation_ids:
            conv = conversations_db.get_conversation(uid, conv_id)
            if conv:
                conversations.append(conv)

        if len(conversations) < 2:
            print(f"Merge failed: Not enough conversations found for uid={uid}")
            _handle_merge_failure(uid, conversation_ids)
            return

        # Sort by started_at to determine order
        sorted_convs = sorted(conversations, key=lambda c: c.get('started_at', datetime.min))
        primary_conv = sorted_convs[0]
        secondary_ids = [c['id'] for c in sorted_convs[1:]]

        # 1. Migrate photos before we delete anything
        migrate_photos_to_primary(uid, primary_id, secondary_ids)

        # 2. Merge all data
        merged_segments = merge_transcript_segments_sequential(conversations)
        merged_action_items = merge_action_items(conversations, primary_id)
        merged_events = merge_events(conversations)
        merged_photos = merge_photos(conversations)
        merged_audio_files = merge_audio_files(conversations, primary_id)
        merged_external_data = merge_external_data(conversations)

        # 3. Determine merged field values
        finished_at = max(c.get('finished_at', datetime.min) for c in conversations)

        # visibility: most restrictive wins
        visibility = determine_visibility(conversations)

        # is_locked: True if any is locked (shouldn't happen, we validated)
        is_locked = any(c.get('is_locked', False) for c in conversations)

        # discarded: False if any is not discarded
        discarded = all(c.get('discarded', False) for c in conversations)

        # private_cloud_sync_enabled: True if any has it enabled
        private_cloud_sync_enabled = any(c.get('private_cloud_sync_enabled', False) for c in conversations)

        # 4. Build merged conversation data
        merged_data = {
            'finished_at': finished_at,
            'transcript_segments': merged_segments,
            'photos': merged_photos,
            'audio_files': merged_audio_files,
            'external_data': merged_external_data,
            'visibility': visibility,
            'is_locked': is_locked,
            'discarded': discarded,
            'private_cloud_sync_enabled': private_cloud_sync_enabled,
            'status': ConversationStatus.completed.value,
        }

        # Update structured data
        merged_structured = copy.deepcopy(primary_conv.get('structured', {}))
        merged_structured['action_items'] = merged_action_items
        merged_structured['events'] = merged_events
        merged_data['structured'] = merged_structured

        # Add merge metadata to external_data
        if merged_data['external_data'] is None:
            merged_data['external_data'] = {}
        merged_data['external_data']['merge_metadata'] = {
            'merged_at': datetime.now(timezone.utc).isoformat(),
            'source_conversation_ids': conversation_ids,
            'source_conversation_times': [
                {
                    'id': c['id'],
                    'started_at': c.get('started_at').isoformat() if c.get('started_at') else None,
                    'finished_at': c.get('finished_at').isoformat() if c.get('finished_at') else None,
                }
                for c in sorted_convs
            ],
        }

        # 5. Update primary conversation
        conversations_db.update_conversation_merged_data(uid, primary_id, merged_data)

        # 6. Delete secondary conversations
        for secondary_id in secondary_ids:
            try:
                # Delete photos subcollection first
                _delete_photos_subcollection(uid, secondary_id)
                # Delete the conversation document
                conversations_db.delete_conversation(uid, secondary_id)
                # Delete vector embedding
                delete_vector(uid, secondary_id)
            except Exception as e:
                print(f"Error deleting secondary conversation {secondary_id}: {e}")

        # 7. Update vector embedding for merged conversation
        try:
            merged_conv = conversations_db.get_conversation(uid, primary_id)
            if merged_conv:
                save_structured_vector(uid, Conversation(**merged_conv))
        except Exception as e:
            print(f"Error updating vector for merged conversation: {e}")

        # 8. Reprocess if requested (regenerate summary)
        if reprocess:
            try:
                from utils.conversations.process_conversation import process_conversation

                merged_conv = conversations_db.get_conversation(uid, primary_id)
                if merged_conv:
                    conversation_obj = Conversation(**merged_conv)
                    process_conversation(
                        uid, conversation_obj.language or 'en', conversation_obj, force_process=True, is_reprocess=True
                    )
            except Exception as e:
                print(f"Error reprocessing merged conversation: {e}")

        # 9. Send FCM notification
        send_merge_completed_message(uid, primary_id, secondary_ids)

        print(
            f"Merge completed successfully: uid={uid}, primary_id={primary_id}, merged={len(secondary_ids)} conversations"
        )

    except Exception as e:
        print(f"Merge failed with exception: {e}")
        _handle_merge_failure(uid, conversation_ids)


def _delete_photos_subcollection(uid: str, conversation_id: str) -> None:
    """Delete all photos in a conversation's photos subcollection."""
    try:
        deleted_count = conversations_db.delete_conversation_photos(uid, conversation_id)
        if deleted_count > 0:
            print(f"Deleted {deleted_count} photos from conversation {conversation_id}")
    except Exception as e:
        print(f"Error deleting photos subcollection for {conversation_id}: {e}")


def _handle_merge_failure(uid: str, conversation_ids: List[str]) -> None:
    """
    Handle merge failure by resetting conversation statuses.
    """
    for conv_id in conversation_ids:
        try:
            conversations_db.update_conversation_status(uid, conv_id, ConversationStatus.completed)
        except Exception as e:
            print(f"Error resetting status for {conv_id}: {e}")
