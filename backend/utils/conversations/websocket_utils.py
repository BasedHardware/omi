"""
WebSocket utilities for conversation processing.

This module contains utilities for WebSocket operations during transcription,
including Redis message handling and conversation transition logic.
"""

import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from database.redis_db import r
import database.conversations as conversations_db
from models.conversation import Conversation, ConversationPhoto, ConversationStatus, Structured, TranscriptSegment
import uuid


async def handle_clear_live_images_message(websocket, uid: str) -> None:
    """
    Check for and handle clear_live_images messages from Redis.
    
    This function checks Redis for pending clear_live_images messages
    and sends them to the WebSocket client if found.
    
    Args:
        websocket: The WebSocket connection
        uid: User ID
    """
    try:
        clear_images_key = f"clear_live_images:{uid}"
        clear_message_data = r.get(clear_images_key)
        
        if clear_message_data:
            # Send clear_live_images message to client
            clear_message = json.loads(clear_message_data)
            await websocket.send_json(clear_message)
            
            # Delete the message from Redis after sending
            r.delete(clear_images_key)
            
    except Exception as e:
        print(f"Error handling clear_live_images message: {e}")


def check_for_existing_image_conversation(uid: str) -> Tuple[List[Dict], Optional[str]]:
    """
    Check for existing image-only conversations that need to be merged with audio.
    
    This function looks for in-progress conversations that contain photos
    and returns the photo data for merging with new audio conversations.
    
    Args:
        uid: User ID
        
    Returns:
        Tuple of (existing_photos, existing_conversation_id)
    """
    existing_photos = []
    existing_conversation_id = None
    
    try:
        # Look for real in-progress conversations that might have photos
        real_existing = conversations_db.get_in_progress_conversation(uid)
        
        if real_existing and not real_existing.get('id', '').startswith('active_session_'):
            # Check if this existing conversation has photos
            try:
                photos = conversations_db.get_conversation_photos(uid, real_existing['id'])
                if photos and len(photos) > 0:
                    existing_photos = photos
                    existing_conversation_id = real_existing['id']
                    print(f"Found existing image-only conversation {existing_conversation_id} with {len(existing_photos)} photos - will merge with audio")
            except Exception as e:
                print(f"Error checking existing conversation photos: {e}")
    except Exception as e:
        print(f"Error looking for existing image conversations: {e}")
    
    return existing_photos, existing_conversation_id


def transfer_photos_to_conversation(
    uid: str, 
    target_conversation_id: str, 
    existing_photos: List[Dict], 
    source_conversation_id: str
) -> None:
    """
    Transfer photos from an existing conversation to a new conversation.
    
    This handles the critical edge case where users have captured photos
    and then start audio recording - we need to merge them into one conversation.
    
    Args:
        uid: User ID
        target_conversation_id: ID of conversation to transfer photos to
        existing_photos: List of photo data to transfer
        source_conversation_id: ID of conversation to transfer photos from
    """
    try:
        # Transfer photos to the new conversation
        conversation_photos = [ConversationPhoto(**photo) for photo in existing_photos]
        conversations_db.store_conversation_photos(uid, target_conversation_id, conversation_photos)
        print(f"Transferred {len(existing_photos)} photos from conversation {source_conversation_id} to new audio+image conversation {target_conversation_id}")
        
        # Mark the old image-only conversation as discarded to prevent duplicate processing
        conversations_db.set_conversation_as_discarded(uid, source_conversation_id)
        print(f"Marked old image-only conversation {source_conversation_id} as discarded")
        
    except Exception as e:
        print(f"Error transferring photos from existing conversation: {e}")


def create_new_audio_conversation(
    uid: str, 
    language: str, 
    segments: List[TranscriptSegment], 
    finished_at: datetime
) -> Conversation:
    """
    Create a new conversation for audio transcription.
    
    Args:
        uid: User ID
        language: Language code
        segments: Transcript segments
        finished_at: When the conversation finished
        
    Returns:
        New Conversation object
    """
    started_at = datetime.now(timezone.utc) - timedelta(seconds=segments[0].end - segments[0].start)
    conversation = Conversation(
        id=str(uuid.uuid4()),
        uid=uid,
        structured=Structured(),
        language=language,
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        transcript_segments=segments,
        status=ConversationStatus.in_progress,
    )
    return conversation


def ensure_conversation_fields(existing: Dict[str, Any], finished_at: datetime) -> Dict[str, Any]:
    """
    Ensure all required fields are present in conversation data.
    
    Args:
        existing: Existing conversation data
        finished_at: Fallback finished_at time
        
    Returns:
        Updated conversation data with all required fields
    """
    # Ensure all required fields are present before creating Conversation object
    if 'finished_at' not in existing or existing['finished_at'] is None:
        existing['finished_at'] = finished_at
    
    if 'created_at' not in existing or existing['created_at'] is None:
        existing['created_at'] = datetime.now(timezone.utc)
    
    if 'started_at' not in existing or existing['started_at'] is None:
        existing['started_at'] = datetime.now(timezone.utc)
    
    # Ensure status is set
    if 'status' not in existing:
        existing['status'] = ConversationStatus.in_progress
    
    return existing


def parse_datetime_safely(dt_value: Any) -> Optional[datetime]:
    """
    Safely parse datetime from various formats.
    
    Args:
        dt_value: DateTime value in string or datetime format
        
    Returns:
        Parsed datetime or None
    """
    if not dt_value:
        return None
        
    try:
        if isinstance(dt_value, str):
            return datetime.fromisoformat(dt_value)
        else:
            # Already a datetime object
            return dt_value
    except Exception:
        return None 