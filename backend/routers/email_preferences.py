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

## Why only ``POST`` writes

``GET`` renders a confirm page; ``POST`` performs the opt-out. That split is
not REST pedantry, it is the difference between a working guardrail and a
poisoned one.

Corporate mail security (Outlook/Defender Safe Links, and most scanning
gateways) fetches every ``https`` URL in a message body before the recipient
ever sees it. A ``GET`` that opted people out would therefore unsubscribe
recipients who never clicked anything — silently suppressing them, and
inflating the unsubscribe rate that EXP-001 pre-registers as its stop-for-harm
guardrail. A guardrail that fires on scanner traffic cannot tell you the email
is unwanted.

Scanners do not issue ``POST``, which is exactly why RFC 8058 one-click
unsubscribe (``List-Unsubscribe-Post``) is a POST. Gmail and Apple Mail send
``List-Unsubscribe=One-Click`` as a form-encoded body to the same URL carried
in the ``List-Unsubscribe`` header — the token arrives in the query string
either way. The body is never parsed: accepting whatever the client sends
without validating it is what makes the one-click contract one-click.

So the human path is two steps (click, then confirm) and the mail-client path
stays genuinely one-click. Both end at the same writer.
"""

from __future__ import annotations

import html
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


def _confirm_page_html(token: str) -> str:
    """One-button form that POSTs the token back to this same path.

    The token is echoed only into a form field of a page served to whoever
    already holds it, never into the response of a failed verification and
    never into a log. It is escaped because it reaches HTML, even though the
    minting alphabet is base64url.
    """
    safe_token = html.escape(token, quote=True)
    return (
        '<html><body><h1>Unsubscribe from Omi emails?</h1>'
        '<p>You will stop receiving onboarding and re-engagement email. '
        'This does not affect email you ask for, or your account.</p>'
        f'<form method="post" action="/email/unsubscribe?token={safe_token}">'
        '<button type="submit">Unsubscribe</button>'
        '</form>'
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
    """Confirm page for the link in a lifecycle email. Never writes.

    A link prefetch by a mail scanner lands here and changes nothing, which is
    the entire reason the write lives on ``POST``.
    """
    if not token or not verify_unsubscribe_token(token):
        return HTMLResponse(_NEUTRAL_ERROR_HTML, status_code=400)
    return HTMLResponse(_confirm_page_html(token), status_code=200)


@router.post('/email/unsubscribe', tags=['email'], response_class=PlainTextResponse)
def post_email_unsubscribe(token: Optional[str] = None):
    """The writer: RFC 8058 one-click target, and the confirm page's submit.

    The mail client's form body (``List-Unsubscribe=One-Click``) is
    intentionally not read — the token in the query string is the only input
    that matters, and requiring a specific body would break the one-click
    contract the RFC exists to guarantee.

    Returns HTML for a browser submitting the confirm form; a mail client
    ignores the body and reads only the status.
    """
    if not _opt_out_from_token(token):
        return HTMLResponse(_NEUTRAL_ERROR_HTML, status_code=400)
    return HTMLResponse(_CONFIRMATION_HTML, status_code=200)
