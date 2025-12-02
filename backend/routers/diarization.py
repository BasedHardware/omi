"""
Diarization Refinement API Routes

Handles webhook callbacks from Modal diarization function
and provides status endpoints for diarization refinement.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from utils.stt.diarization_service import process_diarization_result, DiarizationStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class DiarizationResultPayload(BaseModel):
    """Payload from Modal diarization function."""
    recording_id: str
    words: list
    segments: list
    num_speakers: int
    status: str  # "success" or "error"
    error: Optional[str] = None


class DiarizationWebhookRequest(BaseModel):
    """Webhook request from Modal."""
    uid: str
    result: DiarizationResultPayload


@router.post("/v1/diarization/webhook")
async def diarization_webhook(
    request: DiarizationWebhookRequest,
    x_modal_secret: Optional[str] = Header(None)
):
    """
    Webhook endpoint for Modal diarization function to report results.

    Called when Pyannote diarization completes (success or failure).
    Updates the conversation with refined speaker labels.

    Security: Verify x-modal-secret header matches configured secret.
    """
    import os
    modal_secret = os.getenv("MODAL_WEBHOOK_SECRET")
    if modal_secret and x_modal_secret != modal_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    uid = request.uid
    result = request.result.model_dump()

    logger.info(f"[{result['recording_id']}] Received diarization webhook for user {uid}")

    # Process the result
    success = process_diarization_result(
        uid=uid,
        recording_id=result['recording_id'],
        result=result
    )

    if success:
        return {"status": "ok", "message": "Diarization result processed"}
    else:
        raise HTTPException(status_code=500, detail="Failed to process diarization result")


@router.get("/v1/diarization/status/{conversation_id}")
async def get_diarization_status(
    conversation_id: str,
    uid: str
):
    """
    Get the diarization refinement status for a conversation.

    Returns whether diarization has been refined and the current speaker count.
    """
    import database.conversations as conversations_db

    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    refined = conversation.get('diarization_refined', False)
    segments = conversation.get('transcript_segments', [])

    # Count unique speakers
    speakers = set()
    for seg in segments:
        if isinstance(seg, dict) and seg.get('speaker'):
            speakers.add(seg['speaker'])

    return {
        "conversation_id": conversation_id,
        "diarization_refined": refined,
        "num_speakers": len(speakers),
        "status": DiarizationStatus.COMPLETED if refined else DiarizationStatus.NOT_STARTED
    }
