from datetime import datetime, timezone
from models.conversation import Conversation
import database.conversations as conversations_db

MIN_CONVERSATION_DURATION = 30  # seconds


def check_and_auto_discard(uid: str, conversation: Conversation) -> Conversation:
    """
    Check if conversation should be auto-discarded based on duration.
    Returns the updated conversation.
    """
    # Only check completed conversations
    if conversation.status != 'completed':
        return conversation
    
    # Calculate duration if not set
    if not hasattr(conversation, 'duration') or conversation.duration == 0:
        if conversation.started_at and conversation.finished_at:
            duration = (conversation.finished_at - conversation.started_at).total_seconds()
            conversation.duration = duration
    
    # Auto-discard if too short
    if conversation.duration < MIN_CONVERSATION_DURATION:
        return discard_conversation_helper(uid, conversation.id, 'auto_short_duration')
    
    return conversation


def discard_conversation_helper(uid: str, conversation_id: str, reason: str = 'manual') -> Conversation:
    """Discard a conversation with the given reason"""
    now = datetime.now(timezone.utc)
    
    # Update in database
    conversations_db.update_conversation(uid, conversation_id, {
        'status': 'discarded',
        'discarded_reason': reason,
        'discarded_at': now,
        'updated_at': now
    })
    
    # Return updated conversation
    conversation = conversations_db.get_conversation(uid, conversation_id)
    return Conversation(**conversation)


def restore_conversation_helper(uid: str, conversation_id: str) -> Conversation:
    """Restore a discarded conversation"""
    now = datetime.now(timezone.utc)
    
    # Update in database
    conversations_db.update_conversation(uid, conversation_id, {
        'status': 'completed',
        'restored_at': now,
        'updated_at': now
    })
    
    # Return updated conversation
    conversation = conversations_db.get_conversation(uid, conversation_id)
    return Conversation(**conversation)