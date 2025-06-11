from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from utils.other import endpoints as auth
from utils.other.omiglass import handle_omiglass_images

router = APIRouter()

# Response Models for API Documentation
class OmiGlassImageResponse(BaseModel):
    """Response model for processed OmiGlass image"""
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




@router.post(
    '/v1/images', 
    tags=['omiglass'], 
    response_model=List[OmiGlassImageResponse],
    responses={
        200: {
            "description": "Successfully processed OmiGlass images",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "omiglass_1703123456789",
                            "name": "omiglass_1703123456789.jpg",
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
            "description": "Bad request - invalid files or non-OmiGlass images",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during image processing",
            "model": ErrorResponse
        }
    },
    summary="Upload and process OmiGlass images",
    description="""
    Process OmiGlass images with AI-powered description generation and conversation integration.
    
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
    - Files must have 'omiglass' in the filename (case-insensitive)
    - Supported formats: JPEG, JPG, PNG
    - File size: Recommended < 10MB per image
    
    **Response:**
    Returns processed image data including AI descriptions, cloud URLs, thumbnails, 
    and conversation context for integration with the Omi platform.
    """,
)
def upload_omiglass_images(
    files: List[UploadFile] = File(..., description="OmiGlass image files to process. Must contain 'omiglass' in filename."), 
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    **OmiGlass Image Upload & Processing Endpoint**
    
    This endpoint is specifically designed for OmiGlass device images and provides:
    - AI-powered image descriptions using GPT-4o Vision
    - Intelligent duplicate detection and removal
    - Cloud storage with thumbnail generation  
    - Seamless conversation integration
    
    **Important**: For regular chat file uploads, use `/v2/files` instead.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Validate that all files are OmiGlass images
    non_omiglass_files = [
        file.filename for file in files 
        if not (file.filename and 'omiglass' in file.filename.lower())
    ]
    
    if non_omiglass_files:
        raise HTTPException(
            status_code=400, 
            detail=f"Non-OmiGlass files detected: {non_omiglass_files}. Use /v2/files for regular file uploads."
        )
    
    try:
        complete_images = handle_omiglass_images(files, uid)
        return complete_images
    except Exception as e:
        print(f"Error processing OmiGlass images: {e}")
        raise HTTPException(status_code=500, detail="Failed to process OmiGlass images") 