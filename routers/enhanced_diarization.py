"""
Enhanced Diarization API Router

Simple API endpoint for monitoring enhanced speaker diarization status.
"""

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException

from utils.other import endpoints as auth
from utils.stt.enhanced_diarization import (
    is_enhanced_diarization_enabled,
    get_enhanced_diarization
)

router = APIRouter()


@router.get("/v1/enhanced-diarization/status", tags=['enhanced-diarization'])
def get_enhanced_diarization_status(uid: str = Depends(auth.get_current_user_uid)) -> Dict:
    """Get the current status of enhanced diarization system."""
    try:
        enabled = is_enhanced_diarization_enabled()
        
        if not enabled:
            return {"enabled": False, "available": False, "initialized": False}
        
        diarizer = get_enhanced_diarization()
        
        return {
            "enabled": True,
            "available": diarizer.is_initialized,
            "initialized": diarizer.is_initialized
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")
