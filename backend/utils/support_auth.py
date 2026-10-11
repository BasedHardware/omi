"""Firebase-only support authorization; no impersonation or activity writes."""

from datetime import datetime, timezone

from fastapi import Header, HTTPException
from firebase_admin import auth

from database.support import get_support_access


def get_support_caller_uid(authorization: str | None = Header(default=None)) -> str:
    parts = (authorization or '').split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(status_code=401, detail='Invalid support authentication')
    try:
        claims = auth.verify_id_token(parts[1])
        caller_uid = claims['uid']
        if not isinstance(caller_uid, str) or not caller_uid:
            raise ValueError('Missing caller identity')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid support authentication') from None

    try:
        access = get_support_access(caller_uid)
    except Exception:
        raise HTTPException(status_code=503, detail='Support authorization unavailable') from None
    if not access or access.get('role') != 'support:read':
        raise HTTPException(status_code=403, detail='Support access denied')
    if 'expires_at' in access:
        expires_at = access['expires_at']
        if (
            not isinstance(expires_at, datetime)
            or expires_at.tzinfo is None
            or expires_at.utcoffset() is None
            or expires_at <= datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=403, detail='Support access denied')
    return caller_uid
