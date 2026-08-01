"""Shared ADMIN_KEY authorization for admin-only HTTP routes.

Deliberately dependency-free (stdlib + fastapi only) so any router can import it
without pulling in the auth/Redis/Firestore surface of ``utils.other.endpoints``.

A bare ``secret_key != os.getenv('ADMIN_KEY')`` compare is not equivalent: an
unset ADMIN_KEY is safe (None never equals a str) but an ADMIN_KEY that
materialises as the empty string authenticates any empty header, and that state
is reachable (an ExternalSecret whose remote value is absent). This helper fails
closed on both, and compares in constant time.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException


def has_admin_authorization(secret_key: Optional[str]) -> bool:
    """True only when ADMIN_KEY is configured non-empty and *secret_key* matches it."""
    admin_key = os.getenv('ADMIN_KEY')
    if not admin_key or not secret_key:
        return False
    # compare_digest rejects str with non-ASCII code points, and Starlette decodes
    # headers as latin-1, so compare the encoded bytes instead of raising TypeError.
    return hmac.compare_digest(secret_key.encode('utf-8', 'surrogatepass'), admin_key.encode('utf-8', 'surrogatepass'))


def require_admin_authorization(secret_key: Optional[str]) -> None:
    """Raise 403 unless *secret_key* matches a configured non-empty ADMIN_KEY."""
    if not has_admin_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
