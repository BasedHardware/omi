"""Shared-secret auth guard for the iq-rating data-plane routes (#14430).

The iq_rating router trusts a client-supplied ``uid`` on every data-plane
route. Without a credential, one GET request converts a bare uid into a full
memory + conversation scrape (performed server-side with ``OMI_APP_SECRET``)
and then serves the derived data back to anyone. This module binds those
routes to an authenticated caller, mirroring the merged mentor webhook fix
(#13665) / ``basic/mentor_webhook_auth.py`` pattern:

- ``IQ_RATING_SECRET`` env secret (fail-closed: 503 when unconfigured/blank)
- ``Authorization: Bearer <token>`` header *or* ``iq_rating_token`` query param
- constant-time comparison via ``hmac.compare_digest``
- 401 on missing / mismatched token
"""

import hmac
import os

from fastapi import HTTPException, Query, Request

_IQ_RATING_SECRET_ENV = 'IQ_RATING_SECRET'
_QUERY_TOKEN_PARAM = 'iq_rating_token'


def _configured_secret() -> str | None:
    secret = os.getenv(_IQ_RATING_SECRET_ENV)
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


def require_iq_rating_auth(
    request: Request,
    uid: str = Query(..., min_length=1),
) -> str:
    """Bind an iq-rating data-plane route to an authenticated caller + explicit uid."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail='iq rating auth is not configured')

    token = _presented_token(request)
    # Compare UTF-8 encoded bytes: hmac.compare_digest raises TypeError on
    # non-ASCII str inputs, which would surface as an unhandled HTTP 500.
    # Encoding to bytes keeps the comparison constant-time AND lets any
    # non-ASCII token fail closed with 401 instead of crashing.
    if not token or not hmac.compare_digest(token.encode('utf-8'), secret.encode('utf-8')):
        raise HTTPException(status_code=401, detail='unauthorized')

    trimmed_uid = uid.strip()
    if not trimmed_uid:
        raise HTTPException(status_code=422, detail='uid must not be empty')

    return trimmed_uid