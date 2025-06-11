import uuid
import re
import base64
import time
import os
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from multipart.multipart import shutil
from pydantic import BaseModel

import database.conversations as conversations_db
import database.redis_db as redis_db
from models.conversation import ConversationSource, ConversationPhoto, Structured
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.other import endpoints as auth, storage

router = APIRouter()

# Response Models for API Documentation
class OpenGlassImageResponse(BaseModel):
    """Response model for processed OpenGlass image"""
    id: str
    name: str
    description: str
    mime_type: str
    created_at: str
    thumbnail: str
    url: str
    is_interesting: bool
    upload_success: bool
    linked_conversation_id: Optional[str] = None

class ErrorResponse(BaseModel):
    """Error response model"""
    detail: str

# Simple in-memory cache to prevent reprocessing the same images repeatedly
# Maps image_id -> (timestamp, description) to track recently processed images
_image_processing_cache = {}
_CACHE_DURATION_SECONDS = 300  # 5 minutes


def _is_image_recently_processed(image_id: str, description: str) -> bool:
    """Check if an image was recently processed with the same description"""
    if not image_id or not description:
        return False
    
    current_time = time.time()
    
    # Clean old cache entries first
    expired_keys = [key for key, (timestamp, _) in _image_processing_cache.items() 
                   if current_time - timestamp > _CACHE_DURATION_SECONDS]
    for key in expired_keys:
        del _image_processing_cache[key]
    
    # Check if this image was recently processed
    if image_id in _image_processing_cache:
        timestamp, cached_description = _image_processing_cache[image_id]
        
        # If processed recently with the same description, it's a duplicate
        if current_time - timestamp < _CACHE_DURATION_SECONDS:
            # Check if descriptions are similar
            if _descriptions_are_similar(description.lower().strip(), cached_description.lower().strip()):
                return True
    
    # Cache this image as recently processed
    _image_processing_cache[image_id] = (current_time, description)
    return False


def _descriptions_are_similar(desc1: str, desc2: str, threshold: float = 0.8) -> bool:
    """
    Check if two image descriptions are similar enough to be considered duplicates.
    Uses simple word overlap for similarity detection.
    """
    if not desc1 or not desc2:
        return False
    
    # Convert to sets of words for comparison
    words1 = set(desc1.split())
    words2 = set(desc2.split())
    
    if not words1 or not words2:
        return False
    
    # Calculate Jaccard similarity (intersection over union)
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    if union == 0:
        return False
    
    similarity = intersection / union
    
    # Also check if one description is a subset of another (for different length descriptions)
    smaller_set = words1 if len(words1) < len(words2) else words2
    larger_set = words2 if len(words1) < len(words2) else words1
    
    subset_ratio = len(smaller_set.intersection(larger_set)) / len(smaller_set) if smaller_set else 0
    
    # Consider similar if either high overall similarity or high subset similarity
    is_similar = similarity >= threshold or subset_ratio >= 0.9
    
    return is_similar


def get_openai_image_description(base64_image: str) -> str:
    """Get AI description for an image using OpenAI GPT-4o Vision"""
    try:
        from openai import OpenAI
        
        # Check if API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return "Image captured by OpenGlass (AI description unavailable)"
        
        client = OpenAI(
            api_key=api_key,
            timeout=30.0
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What's in this image? Describe in detail what you see. The camera quality may be low, but do your best to accurately describe what you see anyway. Do not comment on the image quality; only describe the content."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=150
        )
        
        description = response.choices[0].message.content
        
        if description and description.strip():
            return description.strip()
        else:
            return "Image captured by OpenGlass"
            
    except Exception as e:
        print(f"Error getting OpenAI image description: {e}")
        return "Image captured by OpenGlass (AI description failed)"


def is_image_interesting_for_summary(description: str) -> bool:
    """Determine if image is interesting enough for conversation summaries"""
    from openai import OpenAI
    
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        timeout=30.0
    )
    
    try:
        filter_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": f"Is this image interesting enough to save in a conversation summary? Only reject if the image is completely black, white, or extremely blurry with no discernible content. Description: {description}\n\nRespond with only 'INTERESTING: YES' or 'INTERESTING: NO'"
                }
            ],
            max_tokens=10
        )
        
        filter_result = filter_response.choices[0].message.content or "INTERESTING: YES"
        return "YES" in filter_result.upper()
    except Exception as e:
        print(f"Error in interesting filter: {e}")
        return True  # Default to interesting on error


def upload_image_to_bucket(image_data: bytes, uid: str, original_filename: str) -> str:
    """Upload image to cloud storage and return signed URL"""
    try:
        import tempfile
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(image_data)
            temp_file_path = temp_file.name
        
        try:
            # Use direct blob upload instead of transfer_manager to avoid FFI pickling issues
            bucket = storage._get_bucket_safely(storage.chat_files_bucket, "openglass image upload")
            if not bucket:
                return ""
            
            # Use original filename for blob name (matching upload_multi_chat_files structure)
            blob_name = f'{uid}/{original_filename}'
            blob = bucket.blob(blob_name)
            
            # Upload directly using blob
            blob.upload_from_filename(temp_file_path)
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Return signed URL for private bucket access (24 hour expiry)
            try:
                return storage._get_signed_url(blob, 1440)
            except Exception as url_error:
                print(f"Warning: Could not generate signed URL for full image: {url_error}")
                # Return empty string but don't fail - image still processed with description
                return ""
            
        except Exception as e:
            print(f"Warning: Could not upload image to cloud storage: {e}")
            # Clean up temp file even on error
            try:
                os.unlink(temp_file_path)
            except:
                pass
            return ""
            
    except Exception as e:
        print(f"Error in upload_image_to_bucket: {e}")
        return ""


def upload_thumbnail(image_bytes: bytes, image_name: str, uid: str) -> str:
    """Generate and upload thumbnail from image bytes"""
    try:
        from PIL import Image
        import tempfile
        import io
        
        # Create thumbnail from bytes directly
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.thumbnail((128, 128))
            
            # Save thumbnail to temporary file
            thumbnail_path = f"/tmp/{uuid.uuid4()}_thumb_{image_name}"
            img.save(thumbnail_path, format='JPEG')
            
            try:
                # Get bucket for direct upload (avoiding transfer_manager)
                bucket = storage._get_bucket_safely(storage.chat_files_bucket, "openglass thumbnail upload")
                if not bucket:
                    return ""
                
                # Create blob with proper path structure
                blob_name = f'{uid}/thumbnails/{os.path.basename(thumbnail_path)}'
                blob = bucket.blob(blob_name)
                
                # Upload directly
                blob.upload_from_filename(thumbnail_path)
                
                # Clean up local thumbnail file
                Path(thumbnail_path).unlink()
                
                # Return signed URL for private bucket access (24 hour expiry)
                try:
                    return storage._get_signed_url(blob, 1440)
                except Exception as url_error:
                    print(f"Warning: Could not generate signed URL for thumbnail: {url_error}")
                    return ""
                
            except Exception as upload_error:
                print(f"Warning: Could not upload thumbnail to cloud storage: {upload_error}")
                # Clean up local thumbnail file
                try:
                    Path(thumbnail_path).unlink()
                except:
                    pass
                return ""
            
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return ""


def upload_single_image_sync(image_data: dict, uid: str) -> dict:
    """Upload a single image synchronously - used within ThreadPoolExecutor"""
    try:
        image_bytes = image_data.pop('image_data', None)  # Remove from dict after use
        image_name = image_data.get('name', 'unknown.jpg')
        
        # Always determine if interesting for summaries first (regardless of upload success)
        is_interesting = is_image_interesting_for_summary(image_data.get('description', ''))
        
        # Set default values
        signed_url = ""
        thumbnail_url = ""
        
        # Attempt cloud storage upload only if we have image bytes
        if image_bytes:
            try:
                # Upload to cloud storage
                signed_url = upload_image_to_bucket(image_bytes, uid, image_name)
                
                # Generate and upload thumbnail from bytes (no temp file needed)
                thumbnail_url = upload_thumbnail(image_bytes, image_name, uid)
                
            except Exception as upload_error:
                print(f"Warning: Upload failed for image {image_name}: {upload_error}")
                # Continue processing - we still have the description
        
        # Update image data with upload results (empty strings if upload failed)
        image_data.update({
            'thumbnail': thumbnail_url,
            'url': signed_url,
            'is_interesting': is_interesting,
            'upload_success': bool(signed_url),  # Track upload status for debugging
        })
        
        return image_data
        
    except Exception as e:
        print(f"Error processing image {image_data.get('name', 'unknown')}: {e}")
        # Still return the image data with description, just mark upload as failed
        image_data.update({
            'thumbnail': '',
            'url': '',
            'is_interesting': True,  # Default to interesting
            'upload_success': False,
        })
        return image_data


def _integrate_with_existing_conversation(uid: str, images: List[dict]) -> Optional[str]:
    """
    ELEGANT: Single integration point that uses existing conversation architecture.
    Automatically handles all three scenarios without complex logic.
    """
    # Check if user has active conversation (recording or recent)
    active_conversation = retrieve_in_progress_conversation(uid)
    
    if active_conversation:
        # Check if this is an active recording session (phone mic recording in progress)
        if active_conversation.get('id', '').startswith('active_session_'):
            # SCENARIO: User is actively recording audio - hold images for the active session
            # Don't create a separate conversation, let the audio system handle integration
            print(f"🎤 User {uid} has active recording session - holding {len(images)} images for audio integration")
            
            # Store images temporarily linked to the active session
            # These will be picked up when the audio conversation is created
            return active_conversation['id']  # Return the active session ID for tracking
        else:
            # SCENARIO 1 & 2: Add to existing real conversation (audio+image or extending image session)
            conversation_id = active_conversation['id']
            conversation_photos = [
                ConversationPhoto(
                    id=img['id'],
                    url=img.get('url', ''),
                    thumbnail_url=img.get('thumbnail', ''),
                    description=img['description'],
                    created_at=img['created_at'],
                    added_at=datetime.now(timezone.utc).isoformat()
                ) for img in images
            ]
            
            conversations_db.add_photos_to_conversation(uid, conversation_id, conversation_photos)
            print(f"📸 Added {len(images)} images to existing conversation {conversation_id}")
            return conversation_id
    else:
        # SCENARIO 3: Create image-only conversation using intelligent timeout logic
        print(f"📷 Creating new image-only conversation for {len(images)} images")
        return _create_new_photo_conversation(uid, images)


def _create_new_photo_conversation(uid: str, images: List[dict]) -> Optional[str]:
    """
    Elegantly create a new conversation for photo-only sessions.
    SIMPLE: Create as in-progress, let stop button process it.
    """
    try:
        # Create conversation photos
        conversation_photos = []
        for image_data in images:
            conversation_photo = ConversationPhoto(
                id=image_data.get('id', 'unknown'),
                url=image_data.get('url', ''),
                thumbnail_url=image_data.get('thumbnail', ''),
                description=image_data.get('description', ''),
                created_at=image_data.get('created_at'),
                added_at=datetime.now(timezone.utc).isoformat()
            )
            conversation_photos.append(conversation_photo)
        
        # SIMPLE: Create conversation as in-progress with ALL required fields
        # Use exact same structure as audio+photo conversations
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        conversation_dict = {
            'id': conversation_id,
            'uid': uid,
            'structured': Structured().dict(),  # Required field - convert to dict
            'source': ConversationSource.openglass.value,  # Convert enum to string
            'language': 'en',
            'transcript_segments': [],  # Empty for photo-only
            'started_at': now,
            'finished_at': now,
            'created_at': now,
            'status': 'in_progress',  # String value, not enum
            'discarded': False,
            'deleted': False,
            'geolocation': None,
            'plugins_results': [],
            'processing_memory_id': None,
            'visibility': 'private'
        }
        
        # Save conversation to database (without photos - they'll be added separately)
        conversations_db.upsert_conversation(uid, conversation_dict)
        
        # CRITICAL: Save photos separately to database after conversation is created
        # This prevents photos from being deleted by upsert_conversation
        if conversation_photos:
            conversations_db.store_conversation_photos(uid, conversation_id, conversation_photos)
        
        # Set in Redis for stop button to find
        redis_db.set_in_progress_conversation_id(uid, conversation_id, ttl=3600)
        
        return conversation_id
            
    except Exception as e:
        print(f"Error creating in-progress photo conversation: {e}")
        import traceback
        traceback.print_exc()
        return None


def _handle_openglass_images(files: List[UploadFile], uid: str):
    """
    SIMPLIFIED: Handle OpenGlass images elegantly using existing conversation architecture.
    Supports all three scenarios: audio-only, image-only, audio+image without redundancy.
    """
    def process_single_image(file: UploadFile) -> dict:
        """Process a single image and return complete image data with description"""
        try:
            # Read and validate image
            image_data = file.file.read()
            if len(image_data) == 0:
                return None
            
            # Convert to base64 for processing
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Extract timestamp from filename for consistent ID
            timestamp_match = re.search(r'openglass_(\d+)', file.filename)
            if timestamp_match:
                consistent_id = f"openglass_{timestamp_match.group(1)}"
            else:
                consistent_id = f"openglass_{int(time.time() * 1000)}"
            
            # Get AI description
            description = get_openai_image_description(base64_image)
            
            result = {
                'id': consistent_id,
                'name': file.filename,
                'description': description,
                'mime_type': file.content_type or 'application/octet-stream',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'image_data': image_data  # Keep for upload
            }
            
            return result
            
        except Exception as e:
            print(f"Error processing OpenGlass image {file.filename}: {e}")
            return None

    # Process all images concurrently
    processed_images = []
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_file = {executor.submit(process_single_image, file): file for file in files}
            
            for future in concurrent.futures.as_completed(future_to_file, timeout=60):
                try:
                    result = future.result(timeout=30)
                    if result:
                        processed_images.append(result)
                except Exception as e:
                    file = future_to_file[future]
                    print(f"Error processing {file.filename}: {e}")
    except Exception as e:
        print(f"Error in concurrent processing: {e}")
    
    # Simple duplicate detection within current batch only
    unique_images = []
    for image in processed_images:
        is_duplicate = any(
            _descriptions_are_similar(image['description'], existing['description'], threshold=0.9)
            for existing in unique_images
        )
        if not is_duplicate:
            unique_images.append(image)
    
    # Upload unique images to cloud storage
    uploaded_images = []
    if unique_images:
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                upload_futures = [executor.submit(upload_single_image_sync, img.copy(), uid) for img in unique_images]
                
                for future in concurrent.futures.as_completed(upload_futures, timeout=60):
                    try:
                        result = future.result(timeout=30)
                        uploaded_images.append(result)
                    except Exception as e:
                        print(f"Error in upload future: {e}")
        
        except Exception as e:
            print(f"Error in concurrent upload processing: {e}")
    
    # ELEGANT: Use existing conversation architecture - much simpler!
    conversation_id = _integrate_with_existing_conversation(uid, uploaded_images)
    
    # Add conversation context to response
    for image in uploaded_images:
        image['linked_conversation_id'] = conversation_id
    
    return uploaded_images


@router.post(
    '/v1/images', 
    tags=['openglass'], 
    response_model=List[OpenGlassImageResponse],
    responses={
        200: {
            "description": "Successfully processed OpenGlass images",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "openglass_1703123456789",
                            "name": "openglass_1703123456789.jpg",
                            "description": "A person sitting at a desk with a laptop, typing in what appears to be an office environment. There are books visible on shelves in the background.",
                            "mime_type": "application/octet-stream",
                            "created_at": "2023-12-21T10:30:56.789Z",
                            "thumbnail": "https://storage.googleapis.com/...",
                            "url": "https://storage.googleapis.com/...",
                            "is_interesting": True,
                            "upload_success": True,
                            "linked_conversation_id": "conv_abc123"
                        }
                    ]
                }
            }
        },
        400: {
            "description": "Bad request - invalid files or non-OpenGlass images",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during image processing",
            "model": ErrorResponse
        }
    },
    summary="Upload and process OpenGlass images",
    description="""
    Process OpenGlass images with AI-powered description generation and conversation integration.
    
    **Features:**
    - 🤖 **AI Image Descriptions**: Uses GPT-4o Vision to generate detailed descriptions
    - 🚫 **Duplicate Detection**: Automatically identifies and removes duplicate images  
    - ☁️ **Cloud Storage**: Uploads images and generates thumbnails in cloud storage
    - 💬 **Conversation Integration**: Links images to existing conversations or creates new ones
    - ⚡ **Concurrent Processing**: Processes multiple images in parallel for performance
    
    **Scenarios Supported:**
    1. **Audio + Images**: Images are added to existing audio conversations
    2. **Image-only Sessions**: Creates new conversations for standalone image sessions  
    3. **Extended Sessions**: Adds images to existing image-only conversations
    
    **File Requirements:**
    - Files must have 'openglass' in the filename (case-insensitive)
    - Supported formats: JPEG, JPG, PNG
    - File size: Recommended < 10MB per image
    
    **Response:**
    Returns processed image data including AI descriptions, cloud URLs, thumbnails, 
    and conversation context for integration with the Omi platform.
    """,
)
def upload_openglass_images(
    files: List[UploadFile] = File(..., description="OpenGlass image files to process. Must contain 'openglass' in filename."), 
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    **OpenGlass Image Upload & Processing Endpoint**
    
    This endpoint is specifically designed for OpenGlass device images and provides:
    - AI-powered image descriptions using GPT-4o Vision
    - Intelligent duplicate detection and removal
    - Cloud storage with thumbnail generation  
    - Seamless conversation integration
    
    **Important**: For regular chat file uploads, use `/v2/files` instead.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Validate that all files are OpenGlass images
    non_openglass_files = [
        file.filename for file in files 
        if not (file.filename and 'openglass' in file.filename.lower())
    ]
    
    if non_openglass_files:
        raise HTTPException(
            status_code=400, 
            detail=f"Non-OpenGlass files detected: {non_openglass_files}. Use /v2/files for regular file uploads."
        )
    
    try:
        complete_images = _handle_openglass_images(files, uid)
        return complete_images
    except Exception as e:
        print(f"Error processing OpenGlass images: {e}")
        raise HTTPException(status_code=500, detail="Failed to process OpenGlass images") 