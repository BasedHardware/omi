"""Shared-secret guard for the Google Calendar chat-tool routes.

The /tools/* endpoints take uid from the JSON body and list/create/get/update/delete events and list calendars with that user's stored Google token —
with no caller authentication. This guard requires callers to present
the app-level shared secret via Authorization: Bearer <secret> or the
calendar_tools_token query param.

Fails closed (503) when GOOGLE_CALENDAR_TOOLS_SECRET is unset so the tool surface is never
silently unauthenticated in production.
"""

import hmac
import os

from fastapi import HTTPException, Request

_SECRET_ENV = "GOOGLE_CALENDAR_TOOLS_SECRET"
_QUERY_PARAM = "calendar_tools_token"


def require_calendar_tools_auth(request: Request) -> None:
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Google Calendar tools auth is not configured (GOOGLE_CALENDAR_TOOLS_SECRET unset)",
        )

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
    elif _QUERY_PARAM in request.query_params:
        token = request.query_params[_QUERY_PARAM]

    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
