"""
Content preparation utilities for conversation processing.

This module contains utilities for preparing conversation content
(transcript + photos) for different processing contexts like apps,
summaries, and memory extraction.
"""

from typing import Union, Optional
from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
from .photo_processing import (
    has_photos_with_descriptions,
    photos_to_visual_context,
    photos_to_text_detailed,
    photos_to_memory_analysis
)


def get_conversation_transcript(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> str:
    """
    Safely extract transcript from conversation object.
    
    Args:
        conversation: Conversation object
        
    Returns:
        Transcript text or empty string
    """
    if hasattr(conversation, 'get_transcript'):
        return conversation.get_transcript(False) or ""
    return ""


def prepare_content_for_apps(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> str:
    """
    Prepare conversation content for app processing.
    
    This function creates unified content from transcript and photos,
    handling different combinations elegantly.
    
    Args:
        conversation: Conversation object with transcript and/or photos
        
    Returns:
        Prepared content string for app processing
    """
    transcript = get_conversation_transcript(conversation)
    has_transcript = transcript.strip()
    has_photos = has_photos_with_descriptions(conversation.photos)
    
    if has_transcript and has_photos:
        # Combined: transcript + visual context
        photos_text = photos_to_visual_context(conversation.photos)
        return transcript + photos_text
    elif has_transcript:
        # Transcript only
        return transcript
    elif has_photos:
        # Photos only - use detailed format with smart sampling
        return photos_to_text_detailed(conversation.photos, "Visual Experience Session")
    else:
        # No content
        return ""


def prepare_content_for_summary(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> str:
    """
    Prepare conversation content for summary generation.
    
    Args:
        conversation: Conversation object
        
    Returns:
        Content prepared for summary generation
    """
    transcript = get_conversation_transcript(conversation)
    has_transcript = transcript.strip()
    has_photos = has_photos_with_descriptions(conversation.photos)
    
    if has_transcript and has_photos:
        # Combined conversation: use transcript as base with photo context
        return transcript
    elif has_transcript:
        # Transcript-only conversation
        return transcript
    elif has_photos:
        # Photos-only conversation - use detailed text format for summary processing
        return photos_to_text_detailed(conversation.photos, "Visual Experience")
    else:
        # No content
        return ""


def prepare_content_for_memory_extraction(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> tuple[str, str]:
    """
    Prepare conversation content for memory extraction.
    
    Returns separate content for transcript-based and photo-based memory extraction.
    
    Args:
        conversation: Conversation object
        
    Returns:
        Tuple of (transcript_content, photo_content) for memory extraction
    """
    transcript = get_conversation_transcript(conversation)
    has_transcript = transcript.strip()
    has_photos = has_photos_with_descriptions(conversation.photos)
    
    transcript_content = ""
    photo_content = ""
    
    if has_transcript:
        transcript_content = transcript
    
    if has_photos:
        photo_content = photos_to_memory_analysis(conversation.photos)
    
    return transcript_content, photo_content


def has_meaningful_content(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> bool:
    """
    Check if conversation has meaningful content for processing.
    
    Args:
        conversation: Conversation object
        
    Returns:
        True if conversation has transcript or photos with descriptions
    """
    transcript = get_conversation_transcript(conversation)
    has_transcript = transcript.strip()
    has_photos = has_photos_with_descriptions(conversation.photos)
    
    return has_transcript or has_photos


def get_content_type_description(conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]) -> str:
    """
    Get a description of the content type for debugging/logging.
    
    Args:
        conversation: Conversation object
        
    Returns:
        Description like "transcript+photos", "photos-only", "transcript-only", or "no-content"
    """
    transcript = get_conversation_transcript(conversation)
    has_transcript = transcript.strip()
    has_photos = has_photos_with_descriptions(conversation.photos)
    
    if has_transcript and has_photos:
        return "transcript+photos"
    elif has_transcript:
        return "transcript-only" 
    elif has_photos:
        return "photos-only"
    else:
        return "no-content" 