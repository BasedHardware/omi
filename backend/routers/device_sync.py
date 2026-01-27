"""
Device Direct Sync API

Endpoints for device-initiated audio uploads over WiFi.
Uses device-specific tokens for authentication instead of Firebase user tokens.
"""

import os
import re
import shutil
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File

from database import device_tokens
from models.conversation import ConversationSource
from routers.sync import (
    decode_opus_file_to_wav,
    get_wav_duration,
    retrieve_vad_segments,
    process_segment,
    get_timestamp_from_path,
)
from utils.other import endpoints as auth

router = APIRouter(prefix="/v1/device", tags=["device"])


@router.post("/generate-sync-token")
def generate_device_sync_token(
    device_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Generate a device-specific token for direct WiFi sync.
    
    This token is tied to the user and device, allowing the device to upload
    audio directly to the backend without phone involvement.
    
    Called by the mobile app when configuring direct sync on a device.
    """
    device_tokens.revoke_device_sync_token(uid, device_id)
    
    token = device_tokens.create_device_sync_token(uid, device_id)
    
    return {
        "token": token,
        "expires_in_days": device_tokens.TOKEN_EXPIRY_DAYS,
    }


@router.post("/revoke-sync-token")
def revoke_device_sync_token(
    device_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Revoke device sync token.
    
    Called when user disables direct sync for a device.
    """
    count = device_tokens.revoke_device_sync_token(uid, device_id)
    return {"status": "revoked", "tokens_revoked": count}


@router.get("/sync-tokens")
def list_device_sync_tokens(
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    List all device sync tokens for the current user.
    
    Returns masked tokens for security.
    """
    tokens = device_tokens.get_user_device_tokens(uid)
    return {"tokens": tokens}


def _validate_device_auth(token: str, device_id: str) -> str:
    """Validate device token and return user ID."""
    token_data = device_tokens.validate_device_sync_token(token, device_id)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired device token")
    return token_data["uid"]


@router.post("/sync-audio")
def device_sync_audio(
    file: UploadFile = File(...),
    x_device_token: str = Header(..., alias="X-Device-Token"),
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_file_timestamp: Optional[str] = Header(None, alias="X-File-Timestamp"),
):
    """
    Receive audio upload directly from device.
    
    Uses device token for authentication instead of Firebase token.
    Processes audio similar to sync-local-files endpoint.
    
    Headers:
        X-Device-Token: Device-specific auth token
        X-Device-Id: Device ID (must match token)
        X-File-Timestamp: Unix timestamp of recording (optional, extracted from filename if not provided)
    
    Body:
        file: Opus-encoded audio file (.bin format)
    """
    uid = _validate_device_auth(x_device_token, x_device_id)
    
    filename = file.filename or "audio.bin"
    if not filename.endswith('.bin'):
        raise HTTPException(status_code=400, detail="Invalid file format, expected .bin")
    
    if x_file_timestamp:
        try:
            timestamp = int(x_file_timestamp)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-File-Timestamp header")
    else:
        try:
            timestamp = get_timestamp_from_path(filename)
        except (ValueError, IndexError):
            timestamp = int(datetime.now().timestamp())
    
    ts_datetime = datetime.fromtimestamp(timestamp)
    if ts_datetime > datetime.now() or ts_datetime < datetime(2024, 1, 1):
        raise HTTPException(status_code=400, detail="Invalid timestamp")
    
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    
    safe_filename = f"device_{x_device_id[-4:]}_{timestamp}.bin"
    bin_path = f"{directory}{safe_filename}"
    wav_path = bin_path.replace('.bin', '.wav')
    
    try:
        with open(bin_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        if os.path.exists(bin_path):
            os.remove(bin_path)
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")
    
    try:
        frame_size = 160
        match = re.search(r'_fs(\d+)', filename)
        if match:
            frame_size = int(match.group(1))
        
        success = decode_opus_file_to_wav(bin_path, wav_path, frame_size=frame_size)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to decode audio file")
        
        duration = get_wav_duration(wav_path)
        if duration < 1:
            return {"status": "skipped", "reason": "audio_too_short", "duration": duration}
        
        segmented_paths = set()
        errors = []
        retrieve_vad_segments(wav_path, segmented_paths, errors)
        
        if errors:
            print(f"VAD errors for device sync: {errors}")
        
        if not segmented_paths:
            return {"status": "skipped", "reason": "no_voice_detected"}
        
        response = {'updated_memories': set(), 'new_memories': set()}
        
        def chunk_threads(threads):
            chunk_size = 3
            for i in range(0, len(threads), chunk_size):
                [t.start() for t in threads[i:i + chunk_size]]
                [t.join() for t in threads[i:i + chunk_size]]
        
        threads = [
            threading.Thread(
                target=process_segment,
                args=(path, uid, response, ConversationSource.omi),
            )
            for path in segmented_paths
        ]
        chunk_threads(threads)
        
        return {
            "status": "success",
            "new_conversations": list(response['new_memories']),
            "updated_conversations": list(response['updated_memories']),
            "segments_processed": len(segmented_paths),
        }
        
    finally:
        if os.path.exists(bin_path):
            os.remove(bin_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)


@router.get("/sync-status")
def get_device_sync_status(
    x_device_token: str = Header(..., alias="X-Device-Token"),
    x_device_id: str = Header(..., alias="X-Device-Id"),
):
    """
    Check if device token is valid. Used by device to verify configuration.
    """
    uid = _validate_device_auth(x_device_token, x_device_id)
    return {"status": "ok", "uid_prefix": uid[:8] + "..."}
