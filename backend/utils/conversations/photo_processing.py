"""
Photo processing utilities for conversation handling.

This module contains utilities for processing photos in conversations,
including sampling large photo sets and converting photos to text format.
"""

from typing import List, Optional
from models.conversation import ConversationPhoto


def get_valid_photos(photos: List[ConversationPhoto]) -> List[ConversationPhoto]:
    """
    Filter photos to only include those with valid descriptions.
    
    Args:
        photos: List of photos to filter
        
    Returns:
        List of photos with valid, non-empty descriptions
    """
    return [
        photo for photo in photos 
        if photo.description and photo.description.strip()
    ]


def sample_large_photo_set(photos: List[ConversationPhoto], target_count: int = 15) -> List[ConversationPhoto]:
    """
    Sample a large photo set to a target number of key photos.
    
    For large photo sets (>20), this samples every nth photo to avoid
    overwhelming AI processing while maintaining representative coverage.
    
    Args:
        photos: List of photos to sample from
        target_count: Target number of photos to sample to (default: 15)
        
    Returns:
        Sampled list of photos
    """
    valid_photos = get_valid_photos(photos)
    
    if len(valid_photos) <= 20:
        return valid_photos
    
    # Calculate sampling step to get approximately target_count photos
    sample_step = max(2, len(valid_photos) // target_count)
    return valid_photos[::sample_step]


def photos_to_text_simple(photos: List[ConversationPhoto]) -> str:
    """
    Convert photos to simple text format for basic processing.
    
    Args:
        photos: List of photos to convert
        
    Returns:
        Text representation of photos
    """
    valid_photos = get_valid_photos(photos)
    
    if not valid_photos:
        return ""
    
    return "Visual Experience Description:\n" + "\n".join([
        f"Scene {i+1}: {photo.description}" 
        for i, photo in enumerate(valid_photos)
    ])


def photos_to_text_detailed(photos: List[ConversationPhoto], context_prefix: str = "Visual Experience") -> str:
    """
    Convert photos to detailed text format with smart sampling for large sets.
    
    Args:
        photos: List of photos to convert
        context_prefix: Prefix for the text context (e.g., "Visual Experience", "Visual Session")
        
    Returns:
        Text representation of photos with intelligent sampling for large sets
    """
    valid_photos = get_valid_photos(photos)
    
    if not valid_photos:
        return ""
    
    if len(valid_photos) > 20:
        # For large photo sets, create structured content with sampling
        sampled_photos = sample_large_photo_set(valid_photos)
        
        photos_text = f"{context_prefix} Session ({len(valid_photos)} images captured):\n\n"
        photos_text += "Key Visual Moments:\n" + "\n".join([
            f"Moment {i+1}: {photo.description}" 
            for i, photo in enumerate(sampled_photos)
        ])
        photos_text += f"\n\nVisual Session Context: Extended visual documentation session with {len(valid_photos)} total images captured."
        
        return photos_text
    else:
        # For smaller photo sets, use detailed scene-by-scene format
        return f"{context_prefix}:\n" + "\n".join([
            f"Scene {i+1}: {photo.description}" 
            for i, photo in enumerate(valid_photos)
        ])


def photos_to_visual_context(photos: List[ConversationPhoto]) -> str:
    """
    Convert photos to visual context format for combining with transcript.
    
    Args:
        photos: List of photos to convert
        
    Returns:
        Visual context text to append to transcript
    """
    valid_photos = get_valid_photos(photos)
    
    if not valid_photos:
        return ""
    
    return "\n\nVisual Context:\n" + "\n".join([
        f"- {photo.description}" 
        for photo in valid_photos
    ])


def photos_to_memory_analysis(photos: List[ConversationPhoto]) -> str:
    """
    Convert photos to memory analysis format for memory extraction.
    
    Args:
        photos: List of photos to convert
        
    Returns:
        Text format optimized for memory extraction
    """
    valid_photos = get_valid_photos(photos)
    
    if not valid_photos:
        return ""
    
    if len(valid_photos) > 20:
        # For large photo sets, create structured memory extraction content
        sampled_photos = sample_large_photo_set(valid_photos)
        
        photos_text = f"Visual Experience Analysis (from {len(valid_photos)} images):\n\n"
        photos_text += "Key Visual Moments:\n" + "\n".join([
            f"Scene {i+1}: {photo.description}" 
            for i, photo in enumerate(sampled_photos)
        ])
        photos_text += f"\n\nOverall Visual Context: Extended visual documentation session capturing diverse scenes and moments."
        
        return photos_text
    else:
        # For smaller photo sets, use detailed scene-by-scene format
        return "Visual Experience Analysis:\n" + "\n".join([
            f"Scene {i+1}: {photo.description}" 
            for i, photo in enumerate(valid_photos)
        ])


def create_photo_summary_title(photo_count: int) -> str:
    """
    Create a title suffix for photo summaries.
    
    Args:
        photo_count: Number of photos
        
    Returns:
        Title suffix like "(5 images)" or empty string for single photo
    """
    if photo_count > 1:
        return f"({photo_count} images)"
    return ""


def has_photos_with_descriptions(photos: Optional[List[ConversationPhoto]]) -> bool:
    """
    Check if there are any photos with valid descriptions.
    
    Args:
        photos: Optional list of photos to check
        
    Returns:
        True if there are photos with descriptions, False otherwise
    """
    if not photos:
        return False
    
    return any(
        photo.description and photo.description.strip() 
        for photo in photos
    ) 