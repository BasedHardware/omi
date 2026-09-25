"""Sanitization utilities for API responses and logs."""

import re
from typing import Any


def sanitize(text: str) -> str:
    """Sanitize sensitive information in error messages."""
    if not text:
        return text
    
    # Mask API keys and tokens
    text = re.sub(r'\b[a-f0-9]{32,}\b', '[MASKED]', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\w{8,}-[a-f0-9]{4,}-[a-f0-9]{4,}-[a-f0-9]{4,}-[a-f0-9]{12}\b', '[MASKED]', text, flags=re.IGNORECASE)
    
    # Mask user identifiers
    text = re.sub(r'user_id=\d+', 'user_id=[MASKED]', text)
    text = re.sub(r'user=\w+', 'user=[MASKED]', text)
    
    # Mask email addresses
    text = re.sub(r'\b[\w.-]+@[\w.-]+\b', '[MASKED]', text)
    
    return text


def sanitize_log_message(message: str, **kwargs) -> str:
    """Sanitize log messages with dynamic field masking."""
    sanitized = message
    for key, value in kwargs.items():
        if isinstance(value, str):
            sanitized = sanitized.replace(str(value), f'{key}=[MASKED]')
    return sanitized
