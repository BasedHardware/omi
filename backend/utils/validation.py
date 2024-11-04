import re

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

def validate_email(email) -> bool:
    """
    Validate an email address.
    
    Args:
        email: The email address to validate
        
    Returns:
        bool: True if email is valid, False otherwise
    """
    if not isinstance(email, str):
        return False
        
    try:
        # Basic checks
        if not email or len(email) > 254:
            return False

        # Split into local and domain parts
        parts = email.split('@')
        if len(parts) != 2:  # Must have exactly one @
            return False
            
        local, domain = parts

        # Local part checks
        if not local or len(local) > 64 or ' ' in local:
            return False

        # Domain checks
        if not domain or '.' not in domain:
            return False

        domain_parts = domain.split('.')
        if len(domain_parts) < 2:
            return False

        # Each domain part must be valid
        for part in domain_parts:
            if not part or len(part) < 1:
                return False
            if part.startswith('-') or part.endswith('-'):
                return False
            if not re.match(r'^[a-zA-Z0-9-]+$', part):
                return False

        # Local part must contain only allowed characters
        if not re.match(r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+$', local):
            return False

        return True
        
    except Exception:
        return False