import hmac
import os
from typing import Optional

from fastapi import HTTPException, Query, Request

_IQ_RATING_SECRET_ENV = 'IQ_RATING_SECRET'
_QUERY_TOKEN_PARAM = 'iq_rating_token'


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_IQ_RATING_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> Optional[str]:
    auth = request.headers.get('Authorization')
    if auth:
        scheme, _, credentials = auth.partition(' ')
        if scheme.lower() == 'bearer' and credentials.strip():
            return credentials.strip()
    query_token = request.query_params.get(_QUERY_TOKEN_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def _verify(request: Request) -> None:
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail='iq rating auth is not configured')

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail='unauthorized')


def require_iq_auth(
    request: Request,
    uid: str = Query(..., min_length=1),
) -> str:
    """Bind iq-rating data-plane routes to an authenticated caller and explicit uid."""
    _verify(request)

    trimmed_uid = uid.strip()
    if not trimmed_uid:
        raise HTTPException(status_code=422, detail='uid must not be empty')

    return trimmed_uid


def require_iq_auth_if_uid(
    request: Request,
    uid: Optional[str] = Query(None),
) -> Optional[str]:
    """Auth gate for the /iq page: uid-less requests only render the empty state."""
    if uid is None or not uid.strip():
        return None
    _verify(request)
    return uid.strip()
