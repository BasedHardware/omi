"""Consent, suppression, and sending for lifecycle (non-transactional) email.

Omi's only existing Resend integration is
``utils/conversations/share_email.py``: the user presses a button and their own
meeting summary goes to people they just met with. That is transactional mail,
and it needs no consent surface because the send *is* the user's action.

Lifecycle mail is the opposite: nobody asked for it. A day-3 re-engagement
nudge arrives unbidden, which changes the obligations rather than the plumbing.
Every send through this module therefore has to clear three gates that the
share path does not have:

1. **Suppression is re-read immediately before each send**, never cached across
   a batch. A user who unsubscribes at 09:00 must not receive the message a job
   selected them for at 08:59.
2. **Every message carries a working unsubscribe** — a one-click link and the
   ``List-Unsubscribe`` / ``List-Unsubscribe-Post`` headers that make Gmail and
   Apple Mail render their native unsubscribe control.
3. **A send is recorded before it is attempted**, so a retried job cannot mail
   the same person twice. Duplicate lifecycle mail is the failure users
   punish hardest, and a batch job is exactly the thing that retries.

Unsubscribe tokens are unexpiring by construction. An expiring unsubscribe link
is a dark pattern and an accessibility failure: mail lives in archives for
years, and the person clicking a two-year-old link is precisely the person most
entitled to be removed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from database._client import db

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'
LIFECYCLE_FROM_ADDRESS = os.getenv('LIFECYCLE_EMAIL_FROM_ADDRESS', 'hello@mail.omi.me')

# Token purpose is part of the signed input so a token minted to unsubscribe
# from lifecycle mail can never be replayed against a future category.
LIFECYCLE_PURPOSE = 'lifecycle'


class LifecycleEmailSuppressed(RuntimeError):
    """The recipient must not receive this message (opted out, or already sent)."""


class LifecycleEmailNotConfigured(RuntimeError):
    """Sending credentials or signing secret are absent."""


class LifecycleEmailDeliveryUnknown(RuntimeError):
    """The request reached the provider and the outcome was never read.

    Distinct from a plain failure because the claim must be treated
    differently: a caller may not release it, because the message may well have
    been sent. A miss is recoverable; a duplicate is not.
    """


def _signing_secret() -> str:
    secret = os.getenv('LIFECYCLE_EMAIL_SIGNING_SECRET')
    if not secret:
        raise LifecycleEmailNotConfigured('lifecycle email signing secret is not configured')
    return secret


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def mint_unsubscribe_token(uid: str, *, purpose: str = LIFECYCLE_PURPOSE) -> str:
    """Sign ``uid:purpose`` so the unsubscribe endpoint needs no session.

    Deliberately unexpiring: see the module docstring.
    """
    signature = hmac.new(_signing_secret().encode('utf-8'), f'{uid}:{purpose}'.encode('utf-8'), hashlib.sha256).digest()
    return f'{_b64url(uid.encode("utf-8"))}.{_b64url(signature)}'


def verify_unsubscribe_token(token: str, *, purpose: str = LIFECYCLE_PURPOSE) -> Optional[str]:
    """Return the uid a token authorizes, or None. Never raises on bad input."""
    try:
        # The signature half is deliberately unread — see the comparison below.
        # Splitting still does two jobs: it extracts the uid, and it rejects a
        # token with no dot at all.
        encoded_uid, _ = token.split('.', 1)
        padding = '=' * (-len(encoded_uid) % 4)
        uid = base64.urlsafe_b64decode(encoded_uid + padding).decode('utf-8')
    except Exception:
        return None
    if not uid:
        return None
    try:
        expected = mint_unsubscribe_token(uid, purpose=purpose)
    except LifecycleEmailNotConfigured:
        return None
    # compare_digest over the whole token keeps the comparison constant-time
    # across both components without branching on which half differed.
    return uid if hmac.compare_digest(token, expected) else None


def unsubscribe_url(uid: str, *, purpose: str = LIFECYCLE_PURPOSE) -> str:
    """Absolute URL of the unsubscribe endpoint, on the API that serves it.

    Deliberately ``BASE_API_URL`` and **not** ``share_base_url()``: the share
    origin (``h.omi.me``) is the conversation-share web frontend and has no
    ``/email/unsubscribe`` route, so a link built from it 404s — taking the
    ``List-Unsubscribe`` header down with it, since that carries the same URL.
    An unsubscribe that does not work is the one defect this whole module
    exists to prevent.

    Raises rather than defaulting: a lifecycle send with no working opt-out
    must not happen, so this failure has to reach ``send_lifecycle_email`` and
    stop it.
    """
    base = (os.getenv('BASE_API_URL') or '').strip().rstrip('/')
    if not base:
        raise LifecycleEmailNotConfigured('BASE_API_URL is not configured; cannot mint an unsubscribe link')
    return f'{base}/email/unsubscribe?token={mint_unsubscribe_token(uid, purpose=purpose)}'


def is_lifecycle_opted_out(uid: str, *, firestore_client: Any | None = None) -> bool:
    """True when the user has opted out. Fails **closed**: on any read error we
    decline to send, because an unwanted send is unrecoverable and a skipped
    one is merely a missed nudge."""
    client = firestore_client or db
    try:
        snapshot = client.collection('users').document(uid).get()
    except Exception:
        logger.warning('lifecycle email: opt-out read failed uid=%s; suppressing', uid)
        return True
    if not getattr(snapshot, 'exists', False):
        return True
    preferences = (snapshot.to_dict() or {}).get('email_preferences') or {}
    return bool(preferences.get('lifecycle_opted_out'))


def set_lifecycle_opted_out(uid: str, opted_out: bool, *, firestore_client: Any | None = None) -> None:
    client = firestore_client or db
    client.collection('users').document(uid).set(
        {
            'email_preferences': {
                'lifecycle_opted_out': opted_out,
                'lifecycle_opted_out_at': datetime.now(timezone.utc) if opted_out else None,
            }
        },
        merge=True,
    )


def _send_ledger_ref(client: Any, uid: str, campaign: str) -> Any:
    return client.collection('users').document(uid).collection('lifecycle_email_sends').document(campaign)


def claim_lifecycle_send(uid: str, campaign: str, *, firestore_client: Any | None = None) -> bool:
    """Reserve the one send of ``campaign`` for ``uid``.

    Uses ``create()``, which fails when the document already exists — so the
    claim is atomic against a concurrent or retried job run without needing a
    transaction. False means somebody already holds the claim.
    """
    client = firestore_client or db
    try:
        _send_ledger_ref(client, uid, campaign).create(
            {'campaign': campaign, 'claimed_at': datetime.now(timezone.utc), 'delivered': False}
        )
        return True
    except Exception:
        return False


def release_lifecycle_send(uid: str, campaign: str, *, firestore_client: Any | None = None) -> None:
    """Release a claim whose send definitively did not happen, so a later run
    can retry. Never called for an ambiguous delivery."""
    client = firestore_client or db
    try:
        _send_ledger_ref(client, uid, campaign).delete()
    except Exception:
        logger.exception('lifecycle email: failed to release send claim uid=%s campaign=%s', uid, campaign)


def mark_lifecycle_send_delivered(uid: str, campaign: str, *, firestore_client: Any | None = None) -> None:
    client = firestore_client or db
    try:
        _send_ledger_ref(client, uid, campaign).set(
            {'delivered': True, 'delivered_at': datetime.now(timezone.utc)}, merge=True
        )
    except Exception:
        logger.exception('lifecycle email: failed to mark delivery uid=%s campaign=%s', uid, campaign)


def send_lifecycle_email(
    *,
    uid: str,
    campaign: str,
    to_email: str,
    subject: str,
    html: str,
    firestore_client: Any | None = None,
) -> Dict[str, Any]:
    """Send one lifecycle message, re-checking consent at the last moment.

    Raises ``LifecycleEmailSuppressed`` when the user opted out. The caller is
    responsible for having claimed the send; this function marks it delivered
    on success and releases it on a definitive failure.
    """
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        raise LifecycleEmailNotConfigured('email sending is not configured')

    # Deliberately re-read rather than trusting the batch's selection snapshot.
    if is_lifecycle_opted_out(uid, firestore_client=firestore_client):
        raise LifecycleEmailSuppressed('recipient has opted out of lifecycle email')

    unsubscribe = unsubscribe_url(uid)
    payload: Dict[str, Any] = {
        'from': f'Omi <{LIFECYCLE_FROM_ADDRESS}>',
        'to': [to_email],
        'subject': subject,
        'html': html,
        'headers': {
            'List-Unsubscribe': f'<{unsubscribe}>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
        },
    }
    # One dispatch per (uid, campaign) even if a retry outruns the Firestore
    # claim — Resend dedupes on this key independently of our own ledger.
    idempotency_key = hashlib.sha256(f'lifecycle:{campaign}:{uid}'.encode()).hexdigest()
    try:
        response = httpx.post(
            RESEND_API_URL,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}', 'Idempotency-Key': idempotency_key},
            timeout=15.0,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # Never reached the provider: definitively not delivered, so the claim
        # is safe to release for a later retry.
        release_lifecycle_send(uid, campaign, firestore_client=firestore_client)
        raise RuntimeError('email provider unreachable') from exc
    except httpx.HTTPError as exc:
        # Request left, response never read. Delivery is unknown, so the claim
        # must STAND — releasing it risks a duplicate, which is worse than a
        # missed nudge. Typed so the caller cannot lump it in with the errors
        # that happened before anything was sent and release the claim.
        raise LifecycleEmailDeliveryUnknown('email delivery status unknown') from exc
    if response.status_code >= 400:
        logger.error('lifecycle email send failed uid=%s campaign=%s status=%s', uid, campaign, response.status_code)
        release_lifecycle_send(uid, campaign, firestore_client=firestore_client)
        raise RuntimeError('email provider rejected the send')
    mark_lifecycle_send_delivered(uid, campaign, firestore_client=firestore_client)
    return {'sent_to': to_email}
