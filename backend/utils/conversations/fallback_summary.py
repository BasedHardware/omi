"""
Fallback summary generation utilities.

This module provides fallback summary generation when no apps are available
or when app processing fails. It ensures conversations always get basic
summaries even without configured apps.
"""

from typing import Union, Optional
from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation, AppResult
from .content_preparation import (
    get_conversation_transcript,
    has_meaningful_content,
    get_content_type_description
)
from .photo_processing import (
    has_photos_with_descriptions,
    get_valid_photos,
    create_photo_summary_title,
    photos_to_text_detailed
)


def generate_fallback_summary(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> Optional[AppResult]:
    """
    Generate a fallback summary when no apps are available.
    
    This function creates basic summaries for different conversation types
    using the conversation processing utilities directly.
    
    Args:
        conversation: Conversation object
        
    Returns:
        AppResult with fallback summary or None if no content available
    """
    if not has_meaningful_content(conversation):
        return None
    
    try:
        from utils.llm.conversation_processing import get_transcript_structure, get_combined_transcript_and_photos_structure
        import database.notifications as notification_db
        
        transcript = get_conversation_transcript(conversation)
        has_transcript = transcript.strip()
        has_photos = has_photos_with_descriptions(conversation.photos)
        
        if has_transcript and has_photos:
            # Combined conversation: transcript + photos
            tz = notification_db.get_user_time_zone(conversation.uid if hasattr(conversation, 'uid') else 'default')
            basic_summary = get_combined_transcript_and_photos_structure(
                transcript, conversation.photos, conversation.started_at, 'en', tz
            )
            
            return AppResult(
                app_id='fallback_combined_summary',
                content=f"**Summary:** {basic_summary.overview}\n\n**Key Points:** Generated from combined conversation and visual analysis."
            )
            
        elif has_transcript:
            # Transcript-only conversation
            tz = notification_db.get_user_time_zone(conversation.uid if hasattr(conversation, 'uid') else 'default')
            basic_summary = get_transcript_structure(transcript, conversation.started_at, 'en', tz)
            
            return AppResult(
                app_id='fallback_summary',
                content=f"**Summary:** {basic_summary.overview}\n\n**Key Points:** Generated from conversation analysis."
            )
            
        elif has_photos:
            # Photos-only conversation - handle large numbers of images efficiently
            valid_photos = get_valid_photos(conversation.photos)
            
            # Use the smart photo processing utility
            photos_as_transcript = photos_to_text_detailed(valid_photos, "Visual Experience")
            
            tz = notification_db.get_user_time_zone(conversation.uid if hasattr(conversation, 'uid') else 'default')
            basic_summary = get_transcript_structure(photos_as_transcript, conversation.started_at, 'en', tz)
            
            # Enhance the summary for photo-only conversations
            photo_count_text = create_photo_summary_title(len(valid_photos))
            return AppResult(
                app_id='fallback_photos_summary',
                content=f"**Visual Session Summary {photo_count_text}:** {basic_summary.overview}\n\n**Key Visual Elements:** Generated from comprehensive visual analysis."
            )
        else:
            # Should not reach here due to has_meaningful_content check
            return None
            
    except Exception as e:
        # Log error for debugging but don't fail completely
        print(f"Error generating fallback summary: {e}")
        
        # Create a minimal fallback summary
        content_type = get_content_type_description(conversation)
        return AppResult(
            app_id='fallback_minimal',
            content=f"**Summary:** Conversation processed ({content_type})\n\n**Note:** Basic summary generated due to processing limitations."
        )


def apply_fallback_summary(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> None:
    """
    Apply fallback summary to conversation if no apps generated results.
    
    Args:
        conversation: Conversation object to apply fallback summary to
    """
    if not hasattr(conversation, 'apps_results'):
        conversation.apps_results = []
    
    # Only apply fallback if no existing results
    if not conversation.apps_results:
        fallback_result = generate_fallback_summary(conversation)
        if fallback_result:
            conversation.apps_results = [fallback_result] 