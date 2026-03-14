"""
E2EE Access Verification
========================

Centralized helper that enforces E2EE key-hash verification on API endpoints
that return user data.

Architecture overview:
  - Enhanced: server-side AES-256-GCM encryption at rest. The server manages
    keys derived from ENCRYPTION_SECRET + uid, so it can read data internally.
  - E2EE: same server-side encryption at rest PLUS external API reads require
    the caller to prove possession of the user's client-side key by sending
    its SHA-256 hash. The server can still process data internally (e.g.
    transcript processing, LLM summarisation), but any client-facing read
    endpoint must include a valid key hash in the X-E2EE-Key-Hash header
    or the e2ee_key_hash query parameter.

Third-party apps and MCP integrations that access user data via API will
receive 403 responses when E2EE is active unless they supply the key hash.
Internal server-side processing (transcribe pipeline, background tasks)
bypasses this check because it calls database functions directly and never
goes through guarded router endpoints.
"""

from typing import Optional
from fastapi import HTTPException, Header, Query

import database.users as users_db


def verify_e2ee_access(
    uid: str,
    x_e2ee_key_hash: Optional[str] = None,
    e2ee_key_hash_param: Optional[str] = None,
):
    """Require valid E2EE key hash if user has E2EE enabled.

    Accepts the hash from either the X-E2EE-Key-Hash header or the
    ``e2ee_key_hash`` query parameter (for API-key based access).

    Args:
        uid: Authenticated user ID.
        x_e2ee_key_hash: Value from the X-E2EE-Key-Hash HTTP header.
        e2ee_key_hash_param: Value from the ?e2ee_key_hash query parameter.

    Raises:
        HTTPException 403: If E2EE is enabled and no valid hash is provided.
    """
    level = users_db.get_data_protection_level(uid)
    if level != 'e2ee':
        return

    provided_hash = x_e2ee_key_hash or e2ee_key_hash_param
    if not provided_hash:
        raise HTTPException(
            status_code=403,
            detail="E2EE is enabled. Provide X-E2EE-Key-Hash header or e2ee_key_hash query parameter.",
        )

    stored_hash = users_db.get_e2ee_key_hash(uid)
    if not stored_hash or provided_hash != stored_hash:
        raise HTTPException(
            status_code=403,
            detail="Invalid E2EE key hash. Pair your device using the QR code in the app.",
        )
