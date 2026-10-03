from typing import Any


def clean_id(val: Any, field_name: str = "Identifier") -> str:
    """Sanitize identifier against path traversal, null bytes, empty strings, and length overruns."""
    if not isinstance(val, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = val.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if len(cleaned) > 256:
        raise ValueError(f"{field_name} exceeds maximum allowable length of 256 characters")
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned or '\x00' in cleaned:
        raise ValueError(f"{field_name} contains prohibited path-traversal or control characters")
    return cleaned
