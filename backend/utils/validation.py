import re
from typing import Optional
from fastapi import HTTPException

def validate_uid(uid: str) -> bool:
    """Validate Firebase UID format"""
    if not re.match(r'^[a-zA-Z0-9]{28}$', uid):
        raise HTTPException(status_code=400, detail="Invalid UID format")
    return True

def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filenames"""
    return re.sub(r'[^a-zA-Z0-9._-]', '', filename)

def validate_audio_file(file_content: bytes, max_size_mb: int = 10) -> bool:
    """Validate audio file content and size"""
    if len(file_content) > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    
    # Check WAV header
    if not file_content.startswith(b'RIFF') or b'WAVE' not in file_content[:12]:
        raise HTTPException(status_code=400, detail="Invalid audio file format")
    
    return True 