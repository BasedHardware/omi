"""
Conversation merge endpoints.

Endpoints:
1. POST /v1/conversations/merge/preview - Preview merge without committing
2. POST /v1/conversations/merge - Execute merge operation
3. POST /v1/conversations/merge/{merge_id}/rollback - Rollback a merge

Dependencies:
- backend/models/conversation.py (MergePreviewRequest, etc.)
- backend/utils/conversations/merge_utils.py (validation & combining)
- backend/database/merge_history.py (rollback tracking)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

import database.conversations as conversations_db
import database.action_items as action_items_db
from database import merge_history as merge_history_db
from database._client import db
from database.vector_db import delete_vector, upsert_vector
from models.conversation import (
    Conversation,
    ConversationStatus,
    MergePreviewRequest,
    MergePreviewResponse,
    MergeConversationsRequest,
    MergeConversationsResponse,
    RollbackMergeResponse,
    MergeMetadata,
)
from utils.conversations.merge_utils import (
    validate_conversations_for_merge,
    validate_chronological_adjacency,
    combine_conversation_data,
    generate_merge_id,
    generate_merged_conversation_id,
)
from utils.conversations.process_conversation import get_transcript_structure
from utils.other import endpoints as auth

router = APIRouter()


@router.post("/v1/conversations/merge/preview", response_model=MergePreviewResponse, tags=['conversations', 'merge'])
def preview_merge(
    request: MergePreviewRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Generate preview of merged conversation without committing changes.

    Validates conversations, combines data, generates AI summary preview.
    Does NOT create any database records - read-only operation.

    Args:
        request: MergePreviewRequest with conversation_ids (min 2)
        uid: Current user ID (from auth)

    Returns:
        MergePreviewResponse with preview conversation, metadata, warnings

    Raises:
        HTTPException 400: Invalid merge (non-adjacent, locked, discarded, etc.)
        HTTPException 404: Conversation not found
    """
    # 1. Validate conversations
    conversations = validate_conversations_for_merge(uid, request.conversation_ids)

    # 2. Validate chronological adjacency (1-hour gap max, no convs in between)
    validate_chronological_adjacency(uid, conversations, max_gap_seconds=3600)

    # 3. Combine data from all source conversations
    merged_data = combine_conversation_data(conversations, include_photos=True)

    # 4. Generate AI-powered structured preview (title, overview, emoji, action items)
    # Note: Using synchronous call - will be converted to async if needed
    try:
        structured = get_transcript_structure(
            transcript=merged_data['combined_transcript'],
            started_at=merged_data['earliest_start'],
            language_code='en',
            timezone='UTC',
            photos=[],  # Photos already in combined_data
            existing_action_items=[],  # Preview doesn't need deduplication
        )
    except Exception as e:
        # Fallback if LLM fails
        from models.conversation import Structured, CategoryEnum
        structured = Structured(
            title="Merged Conversation",
            overview="Preview unavailable - LLM processing failed",
            emoji="🔗",
            category=CategoryEnum.other,
            action_items=[],
            events=[]
        )

    # 5. Calculate metadata
    metadata = MergeMetadata(
        total_segments=len(merged_data['transcript_segments']),
        total_duration_seconds=merged_data['total_duration_seconds'],
        action_items_combined=len(merged_data['all_action_items']),
        action_items_deduplicated=len(structured.action_items),
        events_combined=len(merged_data['all_events']),
        photos_combined=len(merged_data['combined_photos']),
        audio_files_combined=len(merged_data['combined_audio']),
        estimated_processing_time_seconds=5  # Estimated
    )

    # 6. Build preview conversation (not persisted)
    preview_conversation = {
        'id': 'preview-temp',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'started_at': merged_data['earliest_start'].isoformat(),
        'finished_at': merged_data['latest_finish'].isoformat(),
        'structured': structured.dict() if hasattr(structured, 'dict') else structured,
        'transcript_segments': [seg for seg in merged_data['transcript_segments']],
        'photos': merged_data['combined_photos'],
        'audio_files': merged_data['combined_audio'],
        'is_merged': True,
        'source_conversation_ids': request.conversation_ids,
        'status': 'completed'
    }

    # 7. Check for warnings
    warnings = []
    if len(conversations) > 10:
        warnings.append(f"Merging {len(conversations)} conversations - this may take longer to process")

    if metadata.total_segments > 500:
        warnings.append(f"Large merge ({metadata.total_segments} segments) - AI summary may be truncated")

    return MergePreviewResponse(
        preview_conversation=preview_conversation,
        source_conversations=conversations,
        merge_metadata=metadata,
        warnings=warnings
    )


@router.post("/v1/conversations/merge", response_model=MergeConversationsResponse, tags=['conversations', 'merge'])
def merge_conversations(
    request: MergeConversationsRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Execute conversation merge with full rollback capability.

    Creates merged conversation, marks sources as merged, stores rollback snapshot.

    Args:
        request: MergeConversationsRequest with conversation_ids, optional custom_title
        uid: Current user ID (from auth)

    Returns:
        MergeConversationsResponse with merged conversation, merge_id, rollback deadline

    Raises:
        HTTPException 400: Invalid merge
        HTTPException 404: Conversation not found
        HTTPException 500: Merge operation failed
    """
    # 1. Validate (same as preview)
    conversations = validate_conversations_for_merge(uid, request.conversation_ids)
    validate_chronological_adjacency(uid, conversations, max_gap_seconds=3600)

    # 2. Generate IDs and timestamps
    merge_id = generate_merge_id()
    merged_conversation_id = generate_merged_conversation_id()
    merge_time = datetime.now(timezone.utc)
    rollback_expiration = merge_time + timedelta(hours=24)

    # 3. Create rollback snapshot BEFORE any changes
    merge_history_data = {
        'merge_id': merge_id,
        'uid': uid,
        'merged_conversation_id': merged_conversation_id,
        'source_conversations': conversations,  # Full snapshots
        'merge_time': merge_time,
        'rollback_expiration': rollback_expiration,
        'rolled_back': False,
        'rollback_time': None,
        'rollback_reason': None,
        'merge_metadata': {
            'source_count': len(conversations),
            'conversation_ids': request.conversation_ids
        },
        'user_agent': None  # Could extract from headers if needed
    }

    try:
        merge_history_db.create_merge_history(uid, merge_history_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create rollback snapshot: {str(e)}")

    # 4. Combine data
    merged_data = combine_conversation_data(conversations, include_photos=True)

    # 5. Generate AI summary with action item deduplication (Gotcha 6)
    existing_action_items = action_items_db.get_action_items_from_last_n_days(uid, days=2)

    try:
        structured = get_transcript_structure(
            transcript=merged_data['combined_transcript'],
            started_at=merged_data['earliest_start'],
            language_code='en',
            timezone='UTC',
            photos=merged_data['combined_photos'],
            existing_action_items=existing_action_items  # For deduplication
        )

        # Override title if custom title provided
        if request.custom_title:
            structured.title = request.custom_title

    except Exception as e:
        # Rollback on LLM failure
        merge_history_db.update_merge_history(uid, merge_id, {
            'rolled_back': True,
            'rollback_reason': f'LLM processing failed: {str(e)}',
            'rollback_time': datetime.now(timezone.utc)
        })
        raise HTTPException(status_code=500, detail=f"AI summary generation failed: {str(e)}")

    # 6. Create merged conversation
    # Gotcha 3: Preserve highest data protection level
    max_protection_level = 'standard'
    for conv in conversations:
        level = conv.get('data_protection_level', 'standard')
        if level == 'enhanced':
            max_protection_level = 'enhanced'
            break

    merged_conversation_dict = {
        'id': merged_conversation_id,
        'created_at': merge_time,
        'started_at': merged_data['earliest_start'],
        'finished_at': merged_data['latest_finish'],
        'source': conversations[0].get('source', 'omi'),  # Use first conv's source
        'language': conversations[0].get('language'),
        'structured': structured.dict() if hasattr(structured, 'dict') else structured,
        'transcript_segments': merged_data['transcript_segments'],
        'transcript_segments_compressed': False,  # Will be compressed by DB layer
        'geolocation': conversations[0].get('geolocation'),  # Use first conv's location
        'photos': merged_data['combined_photos'],
        'audio_files': merged_data['combined_audio'],
        'private_cloud_sync_enabled': False,
        'apps_results': [],
        'suggested_summarization_apps': [],
        'plugins_results': [],
        'external_data': None,
        'app_id': None,
        'discarded': False,
        'visibility': 'private',
        'processing_memory_id': None,
        'processing_conversation_id': None,
        'status': ConversationStatus.completed,
        'is_locked': False,
        'data_protection_level': max_protection_level,
        # Merge-specific fields
        'is_merged': True,
        'source_conversation_ids': request.conversation_ids,
        'merge_id': merge_id,
        'merged_into_id': None,
        'merge_time': None
    }

    # 7. Execute database operations atomically using batch writes
    try:
        batch = db.batch()

        # Create merged conversation
        merged_conv_ref = db.collection('users').document(uid).collection('conversations').document(merged_conversation_id)
        batch.set(merged_conv_ref, merged_conversation_dict)

        # Mark source conversations as merged (soft delete via discarded flag - Gotcha 8)
        for conv in conversations:
            conv_ref = db.collection('users').document(uid).collection('conversations').document(conv['id'])
            batch.update(conv_ref, {
                'discarded': True,
                'merged_into_id': merged_conversation_id,
                'merge_time': merge_time
            })

        # Commit all changes atomically
        batch.commit()

        # Update vector database (Gotcha 2: use full {uid}-{id} format)
        # Note: Vector operations are outside the batch as they use a different DB
        for conv in conversations:
            try:
                delete_vector(f"{uid}-{conv['id']}")
            except Exception as e:
                # Non-blocking - log warning
                print(f"Warning: Vector delete failed for {conv['id']}: {e}")

        # Create vector for merged conversation
        # (Simplified - actual implementation would generate embedding)
        # upsert_vector(uid, merged_conversation_dict)

    except Exception as e:
        # Rollback on database failure
        merge_history_db.update_merge_history(uid, merge_id, {
            'rolled_back': True,
            'rollback_reason': f'Database operation failed: {str(e)}',
            'rollback_time': datetime.now(timezone.utc)
        })
        raise HTTPException(status_code=500, detail=f"Merge operation failed: {str(e)}")

    # 8. Build response with metadata
    metadata = MergeMetadata(
        total_segments=len(merged_data['transcript_segments']),
        total_duration_seconds=merged_data['total_duration_seconds'],
        action_items_combined=len(merged_data['all_action_items']),
        action_items_deduplicated=len(structured.action_items) if hasattr(structured, 'action_items') else 0,
        events_combined=len(merged_data['all_events']),
        photos_combined=len(merged_data['combined_photos']),
        audio_files_combined=len(merged_data['combined_audio']),
        estimated_processing_time_seconds=5
    )

    merged_conversation = Conversation(**merged_conversation_dict)

    return MergeConversationsResponse(
        merged_conversation=merged_conversation,
        merge_id=merge_id,
        rollback_available_until=rollback_expiration,
        merge_metadata=metadata
    )


@router.post(
    "/v1/conversations/merge/{merge_id}/rollback",
    response_model=RollbackMergeResponse,
    tags=['conversations', 'merge']
)
def rollback_merge(
    merge_id: str,
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Rollback a conversation merge within 24-hour window.

    Restores source conversations, deletes merged conversation, marks merge as rolled back.

    Args:
        merge_id: Merge operation ID to rollback
        uid: Current user ID (from auth)

    Returns:
        RollbackMergeResponse with restored conversations, rollback time

    Raises:
        HTTPException 404: Merge history not found
        HTTPException 400: Rollback window expired or already rolled back
        HTTPException 500: Rollback operation failed
    """
    # 1. Get merge history
    merge_history = merge_history_db.get_merge_history(uid, merge_id)
    if not merge_history:
        raise HTTPException(status_code=404, detail=f"Merge history not found: {merge_id}")

    # 2. Check rollback eligibility
    is_available, reason = merge_history_db.check_rollback_available(uid, merge_id)
    if not is_available:
        raise HTTPException(status_code=400, detail=f"Rollback not available: {reason}")

    # 3. Get source conversations from snapshot
    source_conversations = merge_history['source_conversations']
    merged_conversation_id = merge_history['merged_conversation_id']
    rollback_time = datetime.now(timezone.utc)

    # 4. Execute rollback atomically using batch writes
    try:
        batch = db.batch()

        # Restore source conversations (clear merged flags)
        for conv in source_conversations:
            # Remove merge tracking fields
            conv['discarded'] = False
            conv['merged_into_id'] = None
            conv['merge_time'] = None

            # Restore conversation
            conv_ref = db.collection('users').document(uid).collection('conversations').document(conv['id'])
            batch.set(conv_ref, conv)

        # Delete merged conversation (hard delete this time)
        merged_conv_ref = db.collection('users').document(uid).collection('conversations').document(merged_conversation_id)
        batch.delete(merged_conv_ref)

        # Mark merge as rolled back
        merge_history_ref = db.collection('users').document(uid).collection('merge_history').document(merge_id)
        batch.update(merge_history_ref, {
            'rolled_back': True,
            'rollback_time': rollback_time,
            'rollback_reason': 'User requested rollback'
        })

        # Commit all changes atomically
        batch.commit()

        # Delete merged conversation vector (outside batch - different DB)
        try:
            delete_vector(f"{uid}-{merged_conversation_id}")
        except Exception as e:
            print(f"Warning: Vector delete failed for merged conversation: {e}")

        # Restore source conversation vectors (if they were deleted)
        # (Simplified - actual implementation would regenerate embeddings)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback operation failed: {str(e)}")

    # 5. Build response
    restored_conversations = [Conversation(**conv) for conv in source_conversations]

    return RollbackMergeResponse(
        restored_conversations=restored_conversations,
        merge_id=merge_id,
        rollback_time=rollback_time
    )
