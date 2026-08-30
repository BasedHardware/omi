"""Unauthenticated lifecycle-email unsubscribe endpoints.

Reached from an email client, not the app, so neither route can require
``get_current_user_uid``: there is no session, and the whole point is that a
recipient who never signs in again can still opt out. Identity comes entirely
from the signed token minted by ``utils.email.lifecycle.mint_unsubscribe_token``.

Both routes must:
- Never reveal whether a uid exists (an invalid token and a token for a
  now-deleted account look identical to the caller).
- Never echo the token back into the response.
- Be idempotent — opting out twice is a success, not an error.

``POST`` exists for RFC 8058 one-click unsubscribe (``List-Unsubscribe-Post``),
which Gmail and Apple Mail send as a form-encoded body
(``List-Unsubscribe=One-Click``) to the same URL carried in the
``List-Unsubscribe`` header — i.e. the token arrives the same way as ``GET``,
in the query string. The body is never parsed: accepting whatever the client
sends without validating it is what makes the one-click contract one-click.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

from utils.email.lifecycle import set_lifecycle_opted_out, verify_unsubscribe_token

logger = logging.getLogger(__name__)

router = APIRouter()

_NEUTRAL_ERROR_HTML = (
    '<html><body><h1>This unsubscribe link is invalid or has expired.</h1>'
    '<p>If you followed a link from an email, please make sure you copied the whole address.</p>'
    '</body></html>'
)

_CONFIRMATION_HTML = (
    '<html><body><h1>You have been unsubscribed.</h1>'
    '<p>You will no longer receive this kind of email from Omi.</p>'
    '</body></html>'
)


def _opt_out_from_token(token: Optional[str]) -> bool:
    """Verify ``token`` and opt its owner out. Returns whether it succeeded.

    Never raises: a Firestore write failure here is logged and reported as a
    failed unsubscribe rather than surfaced with any detail that could
    distinguish "bad token" from "valid token, write failed".
    """
    if not token:
        return False
    uid = verify_unsubscribe_token(token)
    if not uid:
        return False
    try:
        set_lifecycle_opted_out(uid, True)
    except Exception:
        logger.exception('email preferences: opt-out write failed')
        return False
    return True


@router.get('/email/unsubscribe', tags=['email'], response_class=HTMLResponse)
def get_email_unsubscribe(token: Optional[str] = None):
    """Landing page a person reaches by clicking the link in a lifecycle email."""
    if not _opt_out_from_token(token):
        return HTMLResponse(_NEUTRAL_ERROR_HTML, status_code=400)
    return HTMLResponse(_CONFIRMATION_HTML, status_code=200)


@router.post('/email/unsubscribe', tags=['email'], response_class=PlainTextResponse)
def post_email_unsubscribe(token: Optional[str] = None):
    """RFC 8058 one-click unsubscribe target for ``List-Unsubscribe-Post``.

    The mail client's form body (``List-Unsubscribe=One-Click``) is
    intentionally not read — the token in the query string is the only input
    that matters, and requiring a specific body would break the one-click
    contract the RFC exists to guarantee.
    """
    if not _opt_out_from_token(token):
        return PlainTextResponse('', status_code=400)
    return PlainTextResponse('', status_code=200)
