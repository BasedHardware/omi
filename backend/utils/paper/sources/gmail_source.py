"""Newsletters, read and deduplicated to one line per story.

Gmail's `category:updates` carries newsletters and security mail in the same
bucket. The edition becomes something the reader may forward or print, so
reproducing a login code inside it is a security hole, not a formatting flaw.

That is why exclusion here is **deterministic and runs before any model sees a
message**. A regex that drops a real newsletter costs one bullet. A model that
decides a verification code is newsworthy costs an account. The asymmetry
decides the design: rules first, model only on what survives.
"""

import logging
import re
from datetime import date
from typing import Any

from models.paper import HeldBack, SourceHealth
from utils.log_sanitizer import sanitize
from utils.retrieval.tools.gmail_tools import get_gmail_messages, parse_gmail_message
from utils.retrieval.tools.google_utils import GOOGLE_INTEGRATION_KEY

logger = logging.getLogger(__name__)

MAX_MESSAGES = 60
MAX_BODY_CHARS = 2000

# Queries that between them cover bulk mail without touching the primary inbox,
# where personal correspondence lives. The edition never reads personal mail.
QUERIES = (
    'newer_than:{days}d category:updates',
    'newer_than:{days}d category:promotions',
    'newer_than:{days}d category:forums',
)

# ---------------------------------------------------------------------------
# The hard exclusion list. Never printed, in any form, even summarized.
#
# Ported from a rule set that has run daily against this same mailbox. Each
# entry is here because that category is either dangerous to reproduce (codes,
# balances) or worthless a day later (receipts, shipping, CI).
# ---------------------------------------------------------------------------

_SUBJECT_BLOCKLIST = re.compile(
    # The trailing \b cannot follow a literal ending in punctuation, so patterns
    # like "invitation:" are held in their own alternative outside the group.
    r'(?:\binvitation\s*:|\b('
    r'verification\s+code|verify\s+your|confirm\s+your\s+(email|account)|'
    r'security\s+(code|alert)|one[-\s]?time\s+(code|password|passcode)|otp|2fa|'
    r'two[-\s]?factor|magic\s+link|sign[-\s]?in\s+(code|link)|login\s+code|'
    r'password\s+(reset|changed)|reset\s+your\s+password|'
    r'authentication\s+code|access\s+code|'
    r'your\s+(receipt|order|invoice|refund)|order\s+(confirmed|confirmation|shipped)|'
    r'payment\s+(received|failed|due|declined)|invoice\s+\#?\d|'
    r'statement\s+(is\s+)?(ready|available)|account\s+statement|'
    r'balance|overdraft|transaction\s+alert|card\s+(ending|was\s+used)|'
    r'subscription\s+(renew|renewed|renewal|expiring)|billing|'
    r'build\s+(failed|passed|succeeded)|ci\s+(failed|passed)|'
    r'pull\s+request|workflow\s+run|deployment\s+(failed|succeeded)|'
    r'calendar\s+invite|has\s+(accepted|declined)\s+your\s+invitation'
    r')\b)',
    re.IGNORECASE,
)

# Only senders that are *never* a newsletter belong here.
#
# `noreply@` deliberately does NOT: running this against a real inbox showed it
# cutting Bloomberg's Money Stuff, John Authers and the Evening Briefing, which
# all send from noreply@news.bloomberg.com. Sending bulk mail from an unmonitored
# address is the norm for publications, not a signal of transactional mail.
# Category is decided by subject and body instead, which is where the danger is.
_SENDER_BLOCKLIST = re.compile(
    r'('
    r'notifications?@github\.|notifications?@gitlab\.|ci_activity@|'
    r'@stripe\.com|@paypal\.|@chase\.|@bankofamerica\.|@wellsfargo\.|@capitalone\.|'
    r'@venmo\.|@squareup\.|@intuit\.|@amazonses\.'
    r')',
    re.IGNORECASE,
)

# Sending subdomains sit in front of the real publication name.
_MAIL_SUBDOMAINS = {'news', 'info', 'mail', 'email', 'e', 'm', 'em', 'go', 'link', 'send', 'notifications'}

# Domains whose second-level label is not what the publication is called.
_PUBLICATION_NAMES = {
    'ycombinator': 'Y Combinator',
    'wsj': 'WSJ',
    'nytimes': 'The New York Times',
    'gatesnotes': 'Gates Notes',
    'digitalocean': 'DigitalOcean',
    'stockstory': 'StockStory',
    'posthog': 'PostHog',
    'higgsfield': 'Higgsfield',
    'producthunt': 'Product Hunt',
}

# A body containing a bare 4-8 digit code next to code-ish words is a credential,
# whatever the subject says.
_CODE_IN_BODY = re.compile(
    r'\b(code|otp|passcode|pin)\b[^\n]{0,40}?\b\d{4,8}\b|\b\d{4,8}\b[^\n]{0,40}?\bis\s+your\b',
    re.IGNORECASE,
)


def exclusion_reason(message: dict[str, Any]) -> str | None:
    """Why this message must never be printed, or None if it may proceed.

    Checked against subject, sender and body. Returns the reason so the cut can
    be shown in Held Back — the reader sees that mail was excluded without
    seeing its contents.
    """
    subject = str(message.get('subject') or '')
    sender = str(message.get('from') or '')
    body = str(message.get('body') or '')[:MAX_BODY_CHARS]

    if _SUBJECT_BLOCKLIST.search(subject):
        return 'transactional, security or billing mail'
    if _SENDER_BLOCKLIST.search(sender):
        return 'automated sender on the exclusion list'
    if _CODE_IN_BODY.search(body):
        return 'contains what looks like a one-time code'
    return None


def _sender_name(raw: str) -> str:
    """The publication behind a From header.

    Prefers the display name. Falls back to the **domain**, never the local
    part: a bare `noreply@news.bloomberg.com` is Bloomberg, and rendering it as
    "noreply" makes the sources line useless. That line is what lets a reader
    check a story, so getting it wrong breaks the rule the section rests on.
    """
    text = str(raw or '').strip()

    match = re.match(r'^\s*"?([^"<]+?)"?\s*<', text)
    if match and match.group(1).strip():
        return match.group(1).strip()

    address = text.split('<')[-1].strip('> ')
    if '@' not in address:
        return text or 'Unknown'

    labels = [part for part in address.split('@')[-1].lower().split('.') if part]
    # Drop the TLD, then any sending subdomain in front of the real name.
    if len(labels) > 1:
        labels = labels[:-1]
        if labels[-1] in {'co', 'com', 'org', 'net', 'ac'} and len(labels) > 1:
            labels = labels[:-1]
    while len(labels) > 1 and labels[0] in _MAIL_SUBDOMAINS:
        labels = labels[1:]

    name = labels[-1] if labels else ''
    if not name:
        return 'Unknown'
    return _PUBLICATION_NAMES.get(name, name.replace('-', ' ').title())


async def fetch_newsletters(
    uid: str,
    integration: dict[str, Any] | None,
    access_token: str | None,
    day: date,
    days: int = 1,
) -> tuple[list[dict[str, Any]], list[HeldBack], SourceHealth]:
    """Read the last ``days`` of bulk mail, minus everything excluded.

    Returns the survivors, the held-back entries describing what was cut, and
    the source health for this run.
    """
    if not integration or not access_token:
        return [], [], SourceHealth(source='gmail', ok=False, note='Google account not connected')

    seen_ids: set[str] = set()
    parsed: list[dict[str, Any]] = []
    fetched = 0

    for template in QUERIES:
        query = template.format(days=max(1, days))
        try:
            raw = await get_gmail_messages(access_token, query=query, max_results=MAX_MESSAGES)
        except Exception as e:  # noqa: BLE001 — one query failing must not lose the section.
            logger.warning('paper: gmail query %r failed: %s', query, sanitize(str(e)))
            continue
        fetched += len(raw or [])
        for message in raw or []:
            message_id = str(message.get('id') or '')
            if not message_id or message_id in seen_ids:
                continue
            seen_ids.add(message_id)
            try:
                parsed.append(parse_gmail_message(message))
            except Exception as e:  # noqa: BLE001
                logger.info('paper: could not parse a gmail message: %s', sanitize(str(e)))

    if fetched == 0 and not parsed:
        return (
            [],
            [],
            SourceHealth(source='gmail', ok=True, fetched=0, kept=0, note='no bulk mail in the window'),
        )

    kept: list[dict[str, Any]] = []
    cut_reasons: dict[str, int] = {}
    for message in parsed:
        reason = exclusion_reason(message)
        if reason:
            cut_reasons[reason] = cut_reasons.get(reason, 0) + 1
            continue
        message['publication'] = _sender_name(message.get('from', ''))
        message['body'] = str(message.get('body') or '')[:MAX_BODY_CHARS]
        kept.append(message)

    held_back = [
        HeldBack(item=f'{count} message{"" if count == 1 else "s"}', reason=reason)
        for reason, count in sorted(cut_reasons.items(), key=lambda pair: -pair[1])
    ]

    return (
        kept,
        held_back,
        SourceHealth(source='gmail', ok=True, fetched=fetched, kept=len(kept)),
    )


__all__ = ['GOOGLE_INTEGRATION_KEY', 'exclusion_reason', 'fetch_newsletters']
