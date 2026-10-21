import hmac
import os

from fastapi import HTTPException, Query, Request

_MENTOR_WEBHOOK_SECRET_ENV = 'BASIC_MENTOR_WEBHOOK_SECRET'
_QUERY_TOKEN_PARAM = 'mentor_webhook_token'


def _configured_secret() -> str | None:
    secret = os.getenv(_MENTOR_WEBHOOK_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get('Authorization')
    if auth:
        scheme, _, credentials = auth.partition(' ')
        if scheme.lower() == 'bearer' and credentials.strip():
            return credentials.strip()
    query_token = request.query_params.get(_QUERY_TOKEN_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def require_mentor_webhook_auth(
    request: Request,
    uid: str = Query(..., min_length=1),
) -> str:
    """Bind mentor realtime webhooks to an authenticated caller and explicit uid."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail='mentor webhook auth is not configured')

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail='unauthorized')

    trimmed_uid = uid.strip()
    if not trimmed_uid:
        raise HTTPException(status_code=422, detail='uid must not be empty')

    return trimmed_uid
