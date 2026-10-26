"""Shared-secret guard for the iq-rating service routes.

Data-plane routes in `plugins/iq_rating/` take `uid` and page through memories
and conversations with the app's secret, or expose/mutate private conversation-derived
IQ ratings. This guard requires callers to present `IQ_RATING_SECRET` either as an
`Authorization: Bearer <secret>` header or an `iq_rating_token` query parameter.

Fails closed (503) when IQ_RATING_SECRET is unset.
"""

import hmac
import os
from typing import Optional

try:
    from fastapi import HTTPException, Query, Request, status
except ImportError:  # pragma: no cover - defensive for minimal CI stub runners
    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None, headers=None, **kwargs):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    class status:
        HTTP_401_UNAUTHORIZED = 401
        HTTP_422_UNPROCESSABLE_ENTITY = 422
        HTTP_503_SERVICE_UNAVAILABLE = 503

    def Query(default=None, **kwargs):
        return default

    Request = object

_IQ_RATING_SECRET_ENV = "IQ_RATING_SECRET"
_QUERY_TOKEN_PARAM = "iq_rating_token"


def _configured_secret() -> Optional[str]:
    secret = os.getenv(_IQ_RATING_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> Optional[str]:
    headers = getattr(request, "headers", {})
    auth = headers.get("Authorization") if hasattr(headers, "get") else None
    if auth and isinstance(auth, str):
        scheme, _, credentials = auth.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()
    query_params = getattr(request, "query_params", {})
    query_token = query_params.get(_QUERY_TOKEN_PARAM) if hasattr(query_params, "get") else None
    if query_token and isinstance(query_token, str) and query_token.strip():
        return query_token.strip()
    return None


def _verify(request: Request) -> None:
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(
            status_code=getattr(status, "HTTP_503_SERVICE_UNAVAILABLE", 503),
            detail="iq rating auth is not configured",
        )

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        raise HTTPException(
            status_code=getattr(status, "HTTP_401_UNAUTHORIZED", 401),
            detail="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_iq_auth(
    request: Request,
    uid: str = Query(..., min_length=1),
) -> str:
    """Bind iq-rating data-plane routes to an authenticated caller and explicit uid."""
    _verify(request)

    trimmed_uid = uid.strip() if isinstance(uid, str) else ""
    if not trimmed_uid:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_ENTITY", 422),
            detail="uid must not be empty",
        )

    return trimmed_uid


def require_iq_auth_if_uid(
    request: Request,
    uid: Optional[str] = Query(None),
) -> Optional[str]:
    """Auth gate for the /iq page: uid-less requests only render the empty state."""
    if uid is None or (isinstance(uid, str) and not uid.strip()):
        return None
    _verify(request)
    return uid.strip()
