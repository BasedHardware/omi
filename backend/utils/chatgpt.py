"""Per-request ChatGPT / Codex tier fingerprint plumbing.

Desktop sends ``X-ChatGPT-Fingerprint`` (SHA-256 of Codex account_id) on requests
while Codex is active. Quota and subscription bypass require a matching enrolled
fingerprint on the same request — enrollment alone is not enough (mirrors BYOK).
"""

import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import database.users as users_db

logger = logging.getLogger('chatgpt')

CHATGPT_FINGERPRINT_HEADER = 'x-chatgpt-fingerprint'
_SHA256_HEX_RE = re.compile(r'^[a-f0-9]{64}$')
# Refresh Firestore heartbeat at most once per day when desktop sends a valid fingerprint.
_HEARTBEAT_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60

_chatgpt_fp_ctx: ContextVar[Optional[str]] = ContextVar('chatgpt_fingerprint', default=None)


def get_chatgpt_fingerprint() -> Optional[str]:
    return _chatgpt_fp_ctx.get()


def has_chatgpt_fingerprint() -> bool:
    """True if the current request carries a ChatGPT enrollment fingerprint header."""
    return bool(_chatgpt_fp_ctx.get())


def chatgpt_request_grants_bypass(uid: str) -> bool:
    """True when enrolled and this request's fingerprint matches Firestore enrollment.

    Refreshes ``last_seen_at`` on success so desktop enrollment stays alive without
    re-posting to ``/chatgpt-active`` every week.
    """
    fp = _chatgpt_fp_ctx.get()
    if not fp or not _SHA256_HEX_RE.match(fp):
        return False
    if not users_db.is_chatgpt_active(uid):
        return False
    state = users_db.get_chatgpt_state(uid)
    if state.get('fingerprint') != fp:
        return False
    last_seen = state.get('last_seen_at')
    if not isinstance(last_seen, datetime):
        users_db.touch_chatgpt_heartbeat(uid)
    else:
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
        if age >= _HEARTBEAT_REFRESH_INTERVAL_SECONDS:
            users_db.touch_chatgpt_heartbeat(uid)
    return True


class ChatGPTMiddleware(BaseHTTPMiddleware):
    """Extract ChatGPT fingerprint header into a per-request contextvar."""

    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get(CHATGPT_FINGERPRINT_HEADER)
        fp = raw.strip() if raw else None
        if fp and not _SHA256_HEX_RE.match(fp):
            fp = None
        token = _chatgpt_fp_ctx.set(fp)
        try:
            return await call_next(request)
        finally:
            _chatgpt_fp_ctx.reset(token)
