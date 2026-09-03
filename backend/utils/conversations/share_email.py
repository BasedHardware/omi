"""Meeting-summary share email: recipient detection + one-click send.

Recipient detection mirrors Granola's follow-up-email rule: recipients come
from the calendar meeting context attached to the conversation (system
calendar / Google Calendar / on-device meeting identity), never from guessing
at transcript content. The proposal exists only when the owner's own address
is known (so it can be excluded), at least one other participant has both a
name and an email, and no more than MAX_MEETING_PARTICIPANTS people attended.

Sending goes through Resend from Omi's verified domain with the owner's
address as reply-to; the recipient list a client may send to is validated
against the detected set so this endpoint can never relay to arbitrary
addresses.
"""

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from database.auth import get_user_from_uid
from utils.conversations.overview_markdown import overview_to_email_html
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
# Sources that mean "the user actually has this event on a calendar, with these
# invitees". Anything else — screen-derived identity, or an unlabelled source we
# cannot attribute — is inference, and inference must not address an email.
CALENDAR_BACKED_SOURCES = frozenset(
    {'system_calendar', 'macos_calendar', 'google', 'google_calendar', 'outlook_calendar'}
)
# Attributable but still bounded: one authenticated user may relay at most
# this many summary emails per UTC day.
DAILY_SEND_QUOTA = 30

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
    """All {name, email} pairs a *calendar* recorded for this conversation.

    Screen-derived identity is excluded on purpose. It is inferred from whatever
    the conferencing window happened to show, which includes calendar tiles for
    other meetings — one such tile put a later meeting's guest on this card and
    offered to email him (issue #12036). An address the user actually invited is
    the only basis for a one-click send.
    """
    participants: List[Dict[str, Optional[str]]] = []

    external_data = conversation.get('external_data') or {}
    calendar_context = external_data.get('calendar_meeting_context') or conversation.get('calendar_meeting_context')
    if isinstance(calendar_context, dict) and calendar_context.get('calendar_source') in CALENDAR_BACKED_SOURCES:
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


def _attendee_count(participants: List[Dict[str, Optional[str]]]) -> int:
    """How many distinct people the sources describe.

    An address is the only stable identity here. The same meeting can arrive as
    both `calendar_meeting_context` and `calendar_event`, and each source may
    spell one person differently ("Nik" vs "Nik Shevchenko"), so counting names
    alongside addresses would make one attendee look like two. Conversations
    stored before attendees were paired also carry a person's name and address
    as separate entries, so names are counted only when no address accompanies
    them, and the two tallies are compared rather than summed.

    The gate errs toward proposing: it exists to stop a blanket proposal for a
    large meeting, and every proposed recipient still needs a name *and* an
    address, so a slight undercount cannot address anyone new — while an
    overcount silently drops a legitimate proposal.
    """
    emails: set[str] = set()
    unattached_names: set[str] = set()
    for participant in participants:
        email = _normalized_email(participant.get('email'))
        if email:
            emails.add(email)
            continue
        raw_name = participant.get('name')
        if isinstance(raw_name, str) and raw_name.strip():
            unattached_names.add(raw_name.strip().casefold())
    return max(len(emails), len(unattached_names))


def _is_captured_name(name: str, email: str) -> bool:
    """Whether `name` is a real captured name rather than a stand-in address.

    Google attendees without a `displayName` reach us as `name = email`
    (`calendar_utils.extract_attendees`), so a non-empty name alone does not
    prove we know who the person is.
    """
    if not name:
        return False
    normalized = name.strip().casefold()
    local_part = email.split('@', 1)[0]
    return normalized != email and normalized != local_part


def extract_share_recipients(conversation: Dict[str, Any], owner_emails: List[str]) -> List[Dict[str, Optional[str]]]:
    """Detected share recipients: meeting participants minus the owner.

    Only participants whose name *and* address the calendar actually recorded
    are proposed. A one-click send to a half-identified attendee is a mistake
    the user cannot take back, so an unnamed address is treated as an unknown
    person rather than a guess.

    Pure so it is unit-testable; returns [] whenever the proposal should not
    exist (no calendar identity, owner-only meeting, no fully identified
    participant, or a meeting too large for a blanket proposal).
    """
    participants = _participants_from_conversation(conversation)
    if _attendee_count(participants) > MAX_MEETING_PARTICIPANTS:
        return []

    owner_set = {email for email in (_normalized_email(e) for e in owner_emails) if email}
    recipients: List[Dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for participant in participants:
        email = _normalized_email(participant.get('email'))
        if not email or email in owner_set or email in seen:
            continue
        raw_name = participant.get('name')
        name = raw_name.strip() if isinstance(raw_name, str) else ''
        if not _is_captured_name(name, email):
            continue
        seen.add(email)
        recipients.append({'name': name, 'email': email})
        if len(recipients) >= MAX_RECIPIENTS:
            break
    return recipients


def get_share_recipients(uid: str, conversation: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    """Recipients to propose, or [] when the owner cannot be identified.

    Owner exclusion is what keeps the proposal from offering to mail the notes
    back to the person who just recorded them, so an unresolved owner address
    disqualifies the whole proposal instead of degrading it: without a known
    owner address every attendee — including the user — looks like a valid
    recipient (issue #12017).
    """
    owner = get_user_from_uid(uid) or {}
    owner_emails = normalized_recipient_emails([owner.get('email') or ''])
    if not owner_emails:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='other',
            from_mode='share_recipients_proposed',
            to_mode='share_recipients_suppressed',
            reason='auth',
            outcome='degraded',
            log=logger,
        )
        return []
    return extract_share_recipients(conversation, owner_emails)


def _sender_display_name(owner: Dict[str, Any]) -> str:
    """Who the recipient sees the notes came from.

    An account without a display name still has an address; showing its local
    part beats an anonymous "Someone", which reads like spam to the recipient.
    """
    display_name = (owner.get('display_name') or '').strip()
    if display_name:
        return display_name
    email = _normalized_email(owner.get('email'))
    local_part = email.split('@', 1)[0].strip() if email else ''
    return local_part or 'Someone'


def build_summary_email(
    *,
    sender_name: str,
    conversation_title: str,
    overview: str,
    share_url: str,
) -> Dict[str, str]:
    """Subject + HTML body for the shared-summary email. Pure for tests."""
    subject = f'Meeting notes: {conversation_title}' if conversation_title else 'Meeting notes'
    overview_html = overview_to_email_html(overview)
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;color:#111">'
        f'<p>{_escape_html(sender_name)} shared notes from your conversation'
        f'{": <strong>" + _escape_html(conversation_title) + "</strong>" if conversation_title else ""}.</p>'
        + (f'<div>{overview_html}</div>' if overview_html else '')
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


def consume_daily_send_quota(uid: str, recipient_count: int) -> bool:
    """Redis daily counter for outbound summary emails; False when exhausted."""
    from datetime import datetime, timezone

    from database.redis_db import r

    key = f"share_email_quota:{uid}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    try:
        total = r.incrby(key, recipient_count)
        if total == recipient_count:
            r.expire(key, 172800)
        if total > DAILY_SEND_QUOTA:
            r.incrby(key, -recipient_count)
            return False
        return True
    except Exception:
        # Fail-open: a Redis outage must not block the user's own share, but
        # the unenforced-quota window has to be observable.
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='other',
            from_mode='quota_enforced',
            to_mode='quota_bypassed',
            reason='provider_error',
            outcome='degraded',
            log=logger,
        )
        return True


def refund_daily_send_quota(uid: str, recipient_count: int) -> None:
    """Return quota consumed by a dispatch that definitively did not happen."""
    from datetime import datetime, timezone

    from database.redis_db import r

    key = f"share_email_quota:{uid}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    try:
        r.incrby(key, -recipient_count)
    except Exception:
        logger.exception('share email: quota refund failed')


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
    sender_name = _sender_display_name(owner)
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

    # Stable per-content idempotency key: even if a retry races past every
    # client-side guard, Resend dedupes the dispatch itself.
    idempotency_key = hashlib.sha256(
        f"{uid}:{conversation.get('id')}:{','.join(sorted(normalized))}".encode()
    ).hexdigest()
    try:
        response = httpx.post(
            RESEND_API_URL,
            json=payload,
            headers={'Authorization': f'Bearer {api_key}', 'Idempotency-Key': idempotency_key},
            timeout=15.0,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # The request never reached the provider — definitively not delivered.
        raise RuntimeError('email provider unreachable') from exc
    except httpx.HTTPError as exc:
        # Sent but no response read (e.g. read timeout): delivery is unknown.
        raise AmbiguousDeliveryError('email delivery status unknown') from exc
    if response.status_code >= 400:
        logger.error('share email send failed uid=%s status=%s', uid, response.status_code)
        raise RuntimeError('email provider rejected the send')
    return {'sent_to': normalized}
