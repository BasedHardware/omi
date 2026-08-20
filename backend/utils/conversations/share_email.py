"""Meeting-summary share email: recipient detection + one-click send.

Recipient detection mirrors Granola's follow-up-email rule: recipients come
from the calendar meeting context attached to the conversation (system
calendar / Google Calendar / on-device meeting identity), never from guessing
at transcript content. The proposal exists only when the meeting had at least
one participant with an email other than the owner's and no more than
MAX_MEETING_PARTICIPANTS people total.

Sending goes through Resend from Omi's verified domain with the owner's
address as reply-to; the recipient list a client may send to is validated
against the detected set so this endpoint can never relay to arbitrary
addresses.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

from database.auth import get_user_from_uid
from utils.share_links import build_share_url

logger = logging.getLogger(__name__)


class AmbiguousDeliveryError(RuntimeError):
    """Transport failed after the provider may have accepted the message.

    A read timeout (or any failure after the request body was sent) leaves
    delivery status unknown: the recipient may already hold the email, so the
    published link must stand — unpublishing could turn a delivered email into
    a dead link.
    """


# Granola gates follow-up drafts to meetings with <= 10 people; above that a
# blanket "send to everyone" proposal is more likely wrong than helpful.
MAX_MEETING_PARTICIPANTS = 10
MAX_RECIPIENTS = 5

RESEND_API_URL = 'https://api.resend.com/emails'
SHARE_EMAIL_FROM_ADDRESS = os.getenv('SHARE_EMAIL_FROM_ADDRESS', 'notes@mail.omi.me')

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _normalized_email(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if not _EMAIL_RE.match(email):
        return None
    return email


def normalized_recipient_emails(values: List[str]) -> List[str]:
    """Valid, lowercased, order-preserving, deduplicated recipient list.

    Request payloads can repeat an address; without dedup one request would
    send the same participant duplicate emails.
    """
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        email = _normalized_email(value)
        if email and email not in seen:
            seen.add(email)
            result.append(email)
    return result


def _participants_from_conversation(conversation: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    """All {name, email} pairs the calendar sources recorded for this conversation."""
    participants: List[Dict[str, Optional[str]]] = []

    external_data = conversation.get('external_data') or {}
    calendar_context = external_data.get('calendar_meeting_context') or conversation.get('calendar_meeting_context')
    if isinstance(calendar_context, dict):
        for participant in calendar_context.get('participants') or []:
            if isinstance(participant, dict):
                participants.append({'name': participant.get('name'), 'email': participant.get('email')})

    calendar_event = conversation.get('calendar_event')
    if isinstance(calendar_event, dict):
        names = calendar_event.get('attendees') or []
        emails = calendar_event.get('attendee_emails') or []
        for index, email in enumerate(emails):
            name = names[index] if index < len(names) and isinstance(names[index], str) else None
            participants.append({'name': name, 'email': email})

    return participants


def extract_share_recipients(conversation: Dict[str, Any], owner_emails: List[str]) -> List[Dict[str, Optional[str]]]:
    """Detected share recipients: meeting participants minus the owner.

    Pure so it is unit-testable; returns [] whenever the proposal should not
    exist (no calendar identity, owner-only meeting, or a meeting too large
    for a blanket proposal).
    """
    participants = _participants_from_conversation(conversation)
    if len(participants) > MAX_MEETING_PARTICIPANTS:
        return []

    owner_set = {email for email in (_normalized_email(e) for e in owner_emails) if email}
    recipients: List[Dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for participant in participants:
        email = _normalized_email(participant.get('email'))
        if not email or email in owner_set or email in seen:
            continue
        seen.add(email)
        name = participant.get('name')
        recipients.append({'name': name.strip() if isinstance(name, str) and name.strip() else None, 'email': email})
        if len(recipients) >= MAX_RECIPIENTS:
            break
    return recipients


def get_share_recipients(uid: str, conversation: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    owner = get_user_from_uid(uid) or {}
    owner_email = owner.get('email')
    owner_emails: List[str] = [owner_email] if isinstance(owner_email, str) and owner_email else []
    return extract_share_recipients(conversation, owner_emails)


def build_summary_email(
    *,
    sender_name: str,
    conversation_title: str,
    overview: str,
    share_url: str,
) -> Dict[str, str]:
    """Subject + HTML body for the shared-summary email. Pure for tests."""
    subject = f'Meeting notes: {conversation_title}' if conversation_title else 'Meeting notes'
    overview_html = '<br>'.join(_escape_html(line) for line in overview.splitlines()) if overview else ''
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;color:#111">'
        f'<p>{_escape_html(sender_name)} shared notes from your conversation'
        f'{": <strong>" + _escape_html(conversation_title) + "</strong>" if conversation_title else ""}.</p>'
        + (f'<p style="white-space:pre-wrap">{overview_html}</p>' if overview_html else '')
        + f'<p><a href="{_escape_html(share_url)}" '
        'style="display:inline-block;background:#111;color:#fff;text-decoration:none;'
        'padding:10px 18px;border-radius:8px">View the full notes</a></p>'
        f'<p style="color:#888;font-size:13px">Sent with <a href="https://omi.me" style="color:#888">Omi</a> — '
        f'reply to reach {_escape_html(sender_name)} directly.</p>'
        '</div>'
    )
    return {'subject': subject, 'html': html}


def _escape_html(value: str) -> str:
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def publish_then_send(
    *,
    publish: Any,
    unpublish: Any,
    send: Any,
) -> Dict[str, Any]:
    """Ordering contract for the one-click share email.

    The link must be live before the email can reach the recipient (no dead
    links), and a failed send must not leave a never-shared conversation
    publicly link-visible — so: publish, send, and roll the publish back if
    the send raises. Injected callables keep this unit-testable.
    """
    try:
        publish()
        return send()
    except AmbiguousDeliveryError:
        # Delivery status unknown — the recipient may already have the email,
        # so the published link stands rather than risking a dead link.
        raise
    except Exception:
        # publish() can fail after partially mutating state (e.g. the database
        # visibility write lands but the Redis registration raises), so the
        # rollback boundary covers it too; unpublish is idempotent for a
        # conversation that never became visible.
        try:
            unpublish()
        except Exception:
            logger.exception('share email: failed to roll back visibility after send failure')
        raise


def send_summary_email(
    *,
    uid: str,
    conversation: Dict[str, Any],
    recipient_emails: List[str],
) -> Dict[str, Any]:
    """Send the meeting summary to already-validated recipients via Resend.

    Callers must have validated `recipient_emails` against
    `get_share_recipients` — this function trusts its input on membership and
    only re-checks shape. Raises ValueError on config/shape problems and
    RuntimeError when the provider rejects the send.
    """
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        raise ValueError('email sending is not configured')

    normalized = normalized_recipient_emails(recipient_emails)
    if not normalized:
        raise ValueError('no valid recipients')

    owner = get_user_from_uid(uid) or {}
    sender_name = (owner.get('display_name') or '').strip() or 'Someone'
    structured = conversation.get('structured') or {}
    title = (structured.get('title') or '').strip()
    overview = (structured.get('overview') or '').strip()
    share_url = build_share_url(f"/conversations/{conversation.get('id')}")

    content = build_summary_email(
        sender_name=sender_name, conversation_title=title, overview=overview, share_url=share_url
    )
    payload: Dict[str, Any] = {
        'from': f'{sender_name} via Omi <{SHARE_EMAIL_FROM_ADDRESS}>',
        'to': normalized,
        'subject': content['subject'],
        'html': content['html'],
    }
    owner_email = _normalized_email(owner.get('email'))
    if owner_email:
        payload['reply_to'] = owner_email

    try:
        response = requests.post(
            RESEND_API_URL,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=15,
        )
    except (requests.ConnectionError, requests.exceptions.ConnectTimeout) as exc:
        # The request never reached the provider — definitively not delivered.
        raise RuntimeError('email provider unreachable') from exc
    except requests.RequestException as exc:
        # Sent but no response read (e.g. read timeout): delivery is unknown.
        raise AmbiguousDeliveryError('email delivery status unknown') from exc
    if response.status_code >= 400:
        logger.error('share email send failed uid=%s status=%s', uid, response.status_code)
        raise RuntimeError('email provider rejected the send')
    return {'sent_to': normalized}
