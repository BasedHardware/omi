"""
API Routes for Conversation Auto-Discard Feature
File: backend/routers/conversations_discard.py

This module defines the FastAPI routes for managing discarded conversations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db_client
from ..auth import get_current_user
from ..utils.conversations.conversation_helper import (
    ConversationAutoDiscardService,
    ACTIVE_STATUS,
    DISCARD_STATUS
)

router = APIRouter(
    prefix="/v1/conversations",
    tags=["conversations"]
)


# Request/Response Models

class DiscardRequest(BaseModel):
    reason: str = 'manual'
    
class BulkDeleteRequest(BaseModel):
    conversation_ids: Optional[List[str]] = None
    
class ConversationResponse(BaseModel):
    id: str
    user_id: str
    created_at: datetime
    finished_at: Optional[datetime]
    duration: float
    status: str
    discarded_reason: Optional[str] = None
    discarded_at: Optional[datetime] = None     # When it was discarded
    transcript: str
    started_at: Optional[datetime] = None       # When conversation started
    updated_at: Optional[datetime] = None       # Last modification time

    # OPTIONAL BUT RECOMMENDED ⬇️
    restored_at: Optional[datetime] = None      # If/when restored
    summary: Optional[str] = None               # AI summary
    title: Optional[str] = None 
    
class DiscardedConversationsResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int


# Endpoints

@router.get(
    "",
    response_model=List[ConversationResponse],
    summary="Get conversations",
    description="Retrieve conversations with optional status filtering"
)
async def get_conversations(
    status: str = Query(ACTIVE_STATUS, description="Filter by status: active, discarded, or archived"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of conversations to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Get conversations for the authenticated user.
    
    Query Parameters:
    - status: Filter by conversation status (default: active)
    - limit: Maximum number of results (1-100, default: 50)
    - offset: Pagination offset (default: 0)
    """
    try:
        query = db.collection('conversations') \
            .where('user_id', '==', user_id) \
            .where('status', '==', status) \
            .order_by('created_at', direction='DESCENDING') \
            .limit(limit) \
            .offset(offset)
        
        conversations = []
        async for doc in query.stream():
            conv_data = doc.to_dict()
            conv_data['id'] = doc.id
            conversations.append(conv_data)
        
        return conversations
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversations: {str(e)}")


@router.get(
    "/discarded",
    response_model=DiscardedConversationsResponse,
    summary="Get discarded conversations",
    description="Retrieve all discarded conversations for the authenticated user"
)
async def get_discarded_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Get all discarded conversations with pagination.
    
    Returns:
    - conversations: List of discarded conversations
    - total: Total number of discarded conversations
    - limit: Applied limit
    - offset: Applied offset
    """
    try:
        service = ConversationAutoDiscardService(db)
        
        # Get conversations
        conversations = await service.get_discarded_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        # Get total count
        count_query = db.collection('conversations') \
            .where('user_id', '==', user_id) \
            .where('status', '==', DISCARD_STATUS)
        
        total = 0
        async for _ in count_query.stream():
            total += 1
        
        return {
            'conversations': conversations,
            'total': total,
            'limit': limit,
            'offset': offset
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch discarded conversations: {str(e)}")


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get a single conversation",
    description="Retrieve a specific conversation by ID"
)
async def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """Get a specific conversation by ID"""
    try:
        doc = await db.collection('conversations').document(conversation_id).get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        conv_data = doc.to_dict()
        conv_data['id'] = doc.id
        
        # Verify ownership
        if conv_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return conv_data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversation: {str(e)}")


@router.post(
    "/{conversation_id}/discard",
    summary="Discard a conversation",
    description="Manually move a conversation to discarded status"
)
async def discard_conversation(
    conversation_id: str,
    request: DiscardRequest = Body(...),
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Manually discard a conversation.
    
    Body Parameters:
    - reason: Reason for discarding (default: 'manual')
    """
    try:
        # Verify conversation exists and user owns it
        doc = await db.collection('conversations').document(conversation_id).get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        conv_data = doc.to_dict()
        if conv_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Discard the conversation
        service = ConversationAutoDiscardService(db)
        success = await service.discard_conversation(conversation_id, reason=request.reason)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to discard conversation")
        
        return {
            "success": True,
            "message": "Conversation discarded successfully",
            "conversation_id": conversation_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discard conversation: {str(e)}")


@router.post(
    "/{conversation_id}/restore",
    summary="Restore a discarded conversation",
    description="Move a discarded conversation back to active status"
)
async def restore_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Restore a discarded conversation back to active status.
    """
    try:
        # Verify conversation exists and user owns it
        doc = await db.collection('conversations').document(conversation_id).get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        conv_data = doc.to_dict()
        if conv_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Verify it's actually discarded
        if conv_data.get('status') != DISCARD_STATUS:
            raise HTTPException(status_code=400, detail="Conversation is not discarded")
        
        # Restore the conversation
        service = ConversationAutoDiscardService(db)
        success = await service.restore_conversation(conversation_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to restore conversation")
        
        return {
            "success": True,
            "message": "Conversation restored successfully",
            "conversation_id": conversation_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore conversation: {str(e)}")


@router.post(
    "/discarded/bulk-delete",
    summary="Bulk delete discarded conversations",
    description="Permanently delete multiple or all discarded conversations"
)
async def bulk_delete_discarded(
    request: BulkDeleteRequest = Body(...),
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Permanently delete discarded conversations.
    
    Body Parameters:
    - conversation_ids: Optional list of specific conversation IDs to delete.
                       If omitted, all discarded conversations will be deleted.
    
    WARNING: This action cannot be undone!
    """
    try:
        service = ConversationAutoDiscardService(db)
        
        deleted_count = await service.bulk_delete_discarded(
            user_id=user_id,
            conversation_ids=request.conversation_ids
        )
        
        message = f"Successfully deleted {deleted_count} conversation(s)"
        if request.conversation_ids is None:
            message = f"Successfully deleted all {deleted_count} discarded conversation(s)"
        
        return {
            "success": True,
            "message": message,
            "deleted_count": deleted_count
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete conversations: {str(e)}")


@router.get(
    "/statistics/summary",
    summary="Get conversation statistics",
    description="Get summary statistics about conversations"
)
async def get_conversation_statistics(
    user_id: str = Depends(get_current_user),
    db = Depends(get_db_client)
):
    """
    Get summary statistics about user's conversations.
    
    Returns:
    - total_conversations: Total number of conversations
    - active_count: Number of active conversations
    - discarded_count: Number of discarded conversations
    - archived_count: Number of archived conversations
    - average_duration: Average duration of all conversations
    - auto_discarded_count: Number of auto-discarded conversations
    """
    try:
        stats = {
            'total_conversations': 0,
            'active_count': 0,
            'discarded_count': 0,
            'archived_count': 0,
            'average_duration': 0.0,
            'auto_discarded_count': 0
        }
        
        # Count by status
        for status in [ACTIVE_STATUS, DISCARD_STATUS, 'archived']:
            query = db.collection('conversations') \
                .where('user_id', '==', user_id) \
                .where('status', '==', status)
            
            count = 0
            total_duration = 0.0
            
            async for doc in query.stream():
                count += 1
                conv_data = doc.to_dict()
                duration = conv_data.get('duration', 0)
                total_duration += duration
                
                # Count auto-discarded
                if status == DISCARD_STATUS and conv_data.get('discarded_reason') == 'auto_short_duration':
                    stats['auto_discarded_count'] += 1
            
            stats[f'{status}_count'] = count
            stats['total_conversations'] += count
        
        # Calculate average duration
        if stats['total_conversations'] > 0:
            all_conversations = db.collection('conversations').where('user_id', '==', user_id)
            total_duration = 0.0
            count = 0
            
            async for doc in all_conversations.stream():
                conv_data = doc.to_dict()
                total_duration += conv_data.get('duration', 0)
                count += 1
            
            stats['average_duration'] = total_duration / count if count > 0 else 0.0
        
        return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch statistics: {str(e)}")


# Integration hook for conversation completion
# This should be called by the main conversation processing logic

async def on_conversation_completed(
    conversation_id: str,
    user_id: str,
    db
) -> dict:
    """
    Hook that should be called when a conversation is marked as complete.
    This triggers the auto-discard logic.
    
    Usage:
    from routers.conversations_discard import on_conversation_completed
    
    result = await on_conversation_completed(
        conversation_id=conv_id,
        user_id=user_id,
        db=db_client
    )
    """
    service = ConversationAutoDiscardService(db)
    return await service.process_conversation_completion(conversation_id, user_id)