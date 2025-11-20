"""
Conversation Auto-Discard Feature Implementation
File: backend/utils/conversation_helper.py

This module implements the core logic for automatically discarding
conversations based on their duration.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Configuration constants
MIN_CONVERSATION_DURATION = 30  # seconds
DISCARD_STATUS = 'discarded'
ACTIVE_STATUS = 'active'
ARCHIVED_STATUS = 'archived'

# Discard reasons
AUTO_SHORT_DURATION = 'auto_short_duration'
MANUAL = 'manual'
USER_REQUESTED = 'user_requested'


class ConversationDurationCalculator:
    """Handles calculation of conversation durations"""
    
    @staticmethod
    def calculate_duration(started_at: Optional[datetime], 
                          finished_at: Optional[datetime]) -> float:
        """
        Calculate conversation duration in seconds.
        
        Args:
            started_at: When the conversation started
            finished_at: When the conversation finished
            
        Returns:
            Duration in seconds, or 0 if timestamps are invalid
        """
        if not started_at or not finished_at:
            logger.warning("Missing timestamps for duration calculation")
            return 0.0
        
        try:
            # Ensure both timestamps are timezone-aware or naive
            duration = (finished_at - started_at).total_seconds()
            
            # Sanity check: duration should be positive and reasonable
            if duration < 0:
                logger.error(f"Negative duration detected: {duration}s")
                return 0.0
            
            # If duration > 24 hours, it's likely a timestamp error
            if duration > 86400:  # 24 hours in seconds
                logger.warning(f"Unusually long duration detected: {duration}s")
            
            return duration
            
        except Exception as e:
            logger.error(f"Error calculating duration: {e}")
            return 0.0


class ConversationAutoDiscardService:
    """Service for handling automatic conversation discarding"""
    
    def __init__(self, db_client):
        """
        Initialize the auto-discard service.
        
        Args:
            db_client: Database client (Firebase, etc.)
        """
        self.db = db_client
        self.duration_calculator = ConversationDurationCalculator()
    
    async def should_auto_discard(self, 
                                 conversation: Dict[str, Any], 
                                 user_settings: Dict[str, Any]) -> bool:
        """
        Determine if a conversation should be automatically discarded.
        
        Args:
            conversation: The conversation data
            user_settings: User's settings including auto-discard preferences
            
        Returns:
            True if conversation should be discarded, False otherwise
        """
        # Check if user has enabled auto-discard feature
        if not user_settings.get('auto_discard_short_conversations', True):
            logger.info(f"Auto-discard disabled for user {conversation.get('user_id')}")
            return False
        
        # Get user's custom minimum duration or use default
        min_duration = user_settings.get('min_conversation_duration', MIN_CONVERSATION_DURATION)
        
        # Calculate actual conversation duration
        duration = self.duration_calculator.calculate_duration(
            conversation.get('started_at'),
            conversation.get('finished_at')
        )
        
        # Store duration in conversation for future reference
        conversation['duration'] = duration
        
        should_discard = duration < min_duration and duration > 0
        
        if should_discard:
            logger.info(
                f"Conversation {conversation.get('id')} ({duration}s) "
                f"is below threshold ({min_duration}s) - will be discarded"
            )
        
        return should_discard
    
    async def discard_conversation(self, 
                                  conversation_id: str, 
                                  reason: str = AUTO_SHORT_DURATION) -> bool:
        """
        Move a conversation to discarded status.
        
        Args:
            conversation_id: ID of the conversation to discard
            reason: Reason for discarding
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'status': DISCARD_STATUS,
                'discarded_reason': reason,
                'discarded_at': datetime.utcnow()
            }
            
            await self._update_conversation(conversation_id, update_data)
            
            logger.info(f"Conversation {conversation_id} discarded (reason: {reason})")
            
            # Optional: Trigger webhook or notification
            await self._notify_conversation_discarded(conversation_id, reason)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to discard conversation {conversation_id}: {e}")
            return False
    
    async def restore_conversation(self, conversation_id: str) -> bool:
        """
        Restore a discarded conversation to active status.
        
        Args:
            conversation_id: ID of the conversation to restore
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {
                'status': ACTIVE_STATUS,
                'discarded_reason': None,
                'discarded_at': None,
                'restored_at': datetime.utcnow()
            }
            
            await self._update_conversation(conversation_id, update_data)
            
            logger.info(f"Conversation {conversation_id} restored")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore conversation {conversation_id}: {e}")
            return False
    
    async def process_conversation_completion(self, 
                                            conversation_id: str, 
                                            user_id: str) -> Dict[str, Any]:
        """
        Process a conversation when it's marked as complete.
        This is the main entry point for auto-discard logic.
        
        Args:
            conversation_id: ID of the completed conversation
            user_id: ID of the user who owns the conversation
            
        Returns:
            Dictionary with status and details
        """
        try:
            # Fetch conversation and user settings
            conversation = await self._get_conversation(conversation_id)
            user_settings = await self._get_user_settings(user_id)
            
            # Check if should be auto-discarded
            if await self.should_auto_discard(conversation, user_settings):
                success = await self.discard_conversation(
                    conversation_id, 
                    reason=AUTO_SHORT_DURATION
                )
                
                return {
                    'status': DISCARD_STATUS if success else 'error',
                    'reason': 'duration_too_short',
                    'duration': conversation.get('duration', 0)
                }
            
            return {
                'status': ACTIVE_STATUS,
                'reason': 'duration_sufficient',
                'duration': conversation.get('duration', 0)
            }
            
        except Exception as e:
            logger.error(f"Error processing conversation completion: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def get_discarded_conversations(self, 
                                        user_id: str, 
                                        limit: int = 50,
                                        offset: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch all discarded conversations for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of conversations to return
            offset: Pagination offset
            
        Returns:
            List of discarded conversations
        """
        try:
            query = self.db.collection('conversations') \
                .where('user_id', '==', user_id) \
                .where('status', '==', DISCARD_STATUS) \
                .order_by('discarded_at', direction='DESCENDING') \
                .limit(limit) \
                .offset(offset)
            
            conversations = []
            async for doc in query.stream():
                conv_data = doc.to_dict()
                conv_data['id'] = doc.id
                conversations.append(conv_data)
            
            return conversations
            
        except Exception as e:
            logger.error(f"Error fetching discarded conversations: {e}")
            return []
    
    async def bulk_delete_discarded(self, 
                                   user_id: str, 
                                   conversation_ids: Optional[List[str]] = None) -> int:
        """
        Permanently delete discarded conversations.
        
        Args:
            user_id: User ID
            conversation_ids: Optional list of specific conversation IDs to delete
                            If None, deletes all discarded conversations
            
        Returns:
            Number of conversations deleted
        """
        try:
            if conversation_ids:
                # Delete specific conversations
                deleted_count = 0
                for conv_id in conversation_ids:
                    # Verify ownership and status
                    conv = await self._get_conversation(conv_id)
                    if conv.get('user_id') == user_id and conv.get('status') == DISCARD_STATUS:
                        await self.db.collection('conversations').document(conv_id).delete()
                        deleted_count += 1
                        logger.info(f"Deleted conversation {conv_id}")
                
                return deleted_count
            else:
                # Delete all discarded conversations for user
                query = self.db.collection('conversations') \
                    .where('user_id', '==', user_id) \
                    .where('status', '==', DISCARD_STATUS)
                
                deleted_count = 0
                batch = self.db.batch()
                
                async for doc in query.stream():
                    batch.delete(doc.reference)
                    deleted_count += 1
                    
                    # Commit batch every 500 documents
                    if deleted_count % 500 == 0:
                        await batch.commit()
                        batch = self.db.batch()
                
                await batch.commit()
                logger.info(f"Deleted {deleted_count} discarded conversations for user {user_id}")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error bulk deleting discarded conversations: {e}")
            return 0
    
    # Private helper methods
    
    async def _get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Fetch a conversation from the database"""
        doc = await self.db.collection('conversations').document(conversation_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        raise ValueError(f"Conversation {conversation_id} not found")
    
    async def _update_conversation(self, conversation_id: str, update_data: Dict[str, Any]):
        """Update a conversation in the database"""
        await self.db.collection('conversations').document(conversation_id).update(update_data)
    
    async def _get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """Fetch user settings from the database"""
        doc = await self.db.collection('user_settings').document(user_id).get()
        if doc.exists:
            return doc.to_dict()
        # Return default settings if none exist
        return {
            'auto_discard_short_conversations': True,
            'min_conversation_duration': MIN_CONVERSATION_DURATION
        }
    
    async def _notify_conversation_discarded(self, conversation_id: str, reason: str):
        """
        Send notification that a conversation was discarded.
        This can be expanded to trigger webhooks, push notifications, etc.
        """
        # TODO: Implement notification logic
        pass


# Convenience functions for direct import

async def create_auto_discard_service(db_client):
    """Factory function to create an auto-discard service instance"""
    return ConversationAutoDiscardService(db_client)


async def process_completed_conversation(conversation_id: str, user_id: str, db_client):
    """
    Convenience function to process a completed conversation.
    This should be called when a conversation is marked as finished.
    """
    service = await create_auto_discard_service(db_client)
    return await service.process_conversation_completion(conversation_id, user_id)


# Example usage:
"""
from utils.conversation_helper import process_completed_conversation

# In your conversation completion handler:
result = await process_completed_conversation(
    conversation_id="conv-123",
    user_id="user-456",
    db_client=firestore_client
)

if result['status'] == 'discarded':
    print(f"Conversation auto-discarded: {result['duration']}s < 30s")
else:
    print(f"Conversation kept: {result['duration']}s")
"""