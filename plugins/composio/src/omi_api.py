import os
import json
import requests
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel
import logging
from dotenv import load_dotenv

from .db import get_pending_memories, update_memory_status, get_all_memories

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
APP_ID = os.getenv("OMI_APP_ID")
API_KEY = os.getenv("OMI_API_KEY")
API_BASE_URL = "https://api.omi.me/v2/integrations"

if not APP_ID or not API_KEY:
    logger.error("OMI credentials not found in environment variables")
    logger.error(f"APP_ID present: {'Yes' if APP_ID else 'No'}")
    logger.error(f"API_KEY present: {'Yes' if API_KEY else 'No'}")

# Initialize router
router = APIRouter(prefix="/api/omi", tags=["omi"])

# Models
class MemoryCreate(BaseModel):
    text: str
    text_source: str = "other"
    text_source_spec: Optional[str] = None

class MemoryBatch(BaseModel):
    uid: str
    memories: List[str]

# Helper function to create a fact in OMI
def create_fact(user_id: str, text: str, source: str = "other", source_spec: Optional[str] = None) -> bool:
    """
    Create a fact/memory in OMI using the API
    
    Args:
        user_id: OMI user ID
        text: Text content of the fact
        source: Source of the text (e.g., "email", "social_post", "other")
        source_spec: Additional specification about the source
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not APP_ID or not API_KEY:
        error_msg = "OMI_APP_ID and OMI_API_KEY must be set in environment variables"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    url = f"{API_BASE_URL}/{APP_ID}/user/facts?uid={user_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text,
        "text_source": source,
    }
    
    if source_spec:
        payload["text_source_spec"] = source_spec
    
    try:
        logger.info(f"Sending fact to OMI API - URL: {url}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info("Successfully created fact in OMI")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating fact: {e}")
        if 'response' in locals():
            logger.error(f"Response status: {response.status_code}")
            logger.error(f"Response text: {response.text}")
        return False

async def store_fact(uid: str, text: str, source_type: str = "notion", source_id: Optional[str] = None) -> bool:
    """
    Async wrapper for creating a fact in OMI
    
    Args:
        uid: User ID
        text: The text content to store
        source_type: The type of source (will be stored in source_spec)
        source_id: Optional source identifier
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Always use 'other' as text_source since we're using a custom integration
        # Include the actual source type in the source_spec
        source_spec_info = f"{source_type}"
        if source_id:
            source_spec_info += f":{source_id}"
            
        success = create_fact(
            user_id=uid,
            text=text,
            source="other",  # Must be one of: 'email', 'social_post', 'other'
            source_spec=source_spec_info
        )
        return success
    except Exception as e:
        logger.error(f"Error storing fact: {e}")
        return False

@router.post("/facts", status_code=status.HTTP_200_OK)
async def create_memory(memory: MemoryCreate, uid: str):
    """Create a single memory/fact in OMI"""
    success = create_fact(
        user_id=uid,
        text=memory.text,
        source=memory.text_source,
        source_spec=memory.text_source_spec
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create memory in OMI"
        )
    
    return {"success": True, "message": "Memory created successfully"}

@router.post("/facts/batch", status_code=status.HTTP_200_OK)
async def create_memories_batch(data: MemoryBatch):
    """Create multiple memories/facts in OMI"""
    results = []
    
    for memory_text in data.memories:
        success = create_fact(
            user_id=data.uid,
            text=memory_text,
            source="other",
            source_spec="notion"
        )
        results.append({"text": memory_text, "success": success})
    
    return {"results": results}

@router.post("/process-pending-memories/{uid}", status_code=status.HTTP_200_OK)
async def process_pending_memories(uid: str, limit: int = 10):
    """Process pending memories from the database and send to OMI"""
    pending_memories = get_pending_memories(uid, limit)
    results = []
    
    for memory in pending_memories:
        success = create_fact(
            user_id=uid,
            text=memory["memory_text"],
            source=memory["source"] or "other",
            source_spec="notion"
        )
        
        if success:
            update_memory_status(memory["id"], "completed")
            results.append({"id": memory["id"], "success": True})
        else:
            update_memory_status(memory["id"], "failed")
            results.append({"id": memory["id"], "success": False})
    
    return {
        "processed": len(results),
        "results": results
    }

@router.get("/memories/{uid}", status_code=status.HTTP_200_OK)
async def get_memories(uid: str, limit: int = 100, offset: int = 0):
    """Get all memories for a user"""
    memories = get_all_memories(uid, limit, offset)
    return {"memories": memories, "count": len(memories)} 