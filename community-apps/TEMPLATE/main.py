"""
Template for Omi Community App

This template demonstrates how to create a memory processing app
that triggers when a conversation finishes.

Replace this with your app's actual implementation.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

# Import Omi's base models
# Note: These are available when your app is integrated into Omi's backend
try:
    from plugins.example.models import (
        Conversation,
        TranscriptSegment,
        Memory,
        EndpointResponse,
        ProactiveNotificationEndpointResponse,
    )
except ImportError:
    # For local development/testing, define minimal models
    class TranscriptSegment(BaseModel):
        text: str
        speaker: str
        start: float
        end: float

    class Memory(BaseModel):
        id: str
        created_at: str
        structured: dict

    class Conversation(BaseModel):
        id: str
        transcript_segments: List[TranscriptSegment]
        memories: List[Memory]

    class EndpointResponse(BaseModel):
        message: str


# Create router for your app
router = APIRouter()


@router.post('/memory-created', response_model=EndpointResponse)
async def memory_created(conversation: Conversation) -> EndpointResponse:
    """
    Triggered when a new conversation finishes and memory is created.

    Args:
        conversation: The completed conversation with transcript and metadata

    Returns:
        EndpointResponse with a message to send to the user
    """
    try:
        # Extract transcript text
        transcript = " ".join([seg.text for seg in conversation.transcript_segments])

        # TODO: Implement your app logic here
        # Examples:
        # - Analyze conversation sentiment
        # - Extract action items
        # - Generate insights
        # - Send data to external service

        # For demo purposes, just count words
        word_count = len(transcript.split())

        return EndpointResponse(
            message=f"Conversation processed! Word count: {word_count}"
        )

    except Exception as e:
        # Log error and return helpful message
        print(f"Error processing conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/transcript-processed', response_model=ProactiveNotificationEndpointResponse)
async def transcript_processed(data: dict) -> ProactiveNotificationEndpointResponse:
    """
    Triggered in real-time as transcript segments arrive (every ~3 seconds).

    Use this for proactive notifications based on conversation context.

    Args:
        data: Real-time transcript data with session_id and segments

    Returns:
        ProactiveNotificationEndpointResponse with notification prompt
    """
    try:
        session_id = data.get('session_id')
        segments = data.get('segments', [])

        # TODO: Implement real-time processing logic
        # Examples:
        # - Detect keywords and send alerts
        # - Provide live coaching
        # - Track conversation metrics

        # Return empty response if no notification needed
        return ProactiveNotificationEndpointResponse(
            prompt=None,
            params=[],
            context={}
        )

    except Exception as e:
        print(f"Error processing transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Optional: Add health check endpoint
@router.get('/health')
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "app": "your-app-name"}
