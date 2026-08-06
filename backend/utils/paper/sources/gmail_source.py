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
from datetime import date, timedelta
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
    'after:{after} before:{before} category:updates',
    'after:{after} before:{before} category:promotions',
    'after:{after} before:{before} category:forums',
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
    r'(?:\binvitation\s*:|\bcode\s*[:#]|\b('
    # Credentials. Providers phrase these a dozen ways and every one of them is
    # a subject that carries the secret in the subject line itself.
    r'(verification|security|confirmation|login|log-in|sign-in|signin|single[-\s]?use|'
    r'temporary|recovery|activation|authentication|access|one[-\s]?time|passcode|pass)\s*code|'
    r'your(?:\s+\w+){0,3}\s+code\b|code\s+is|otp|2fa|two[-\s]?factor|'
    r'verify\s+your|confirm\s+your\s+(email|account|identity)|confirm\s+it.?s\s+you|'
    r'magic\s+link|(sign|log)[-\s]?in\s+(to|link|request|attempt)|login\s+link|'
    r'password\s+(reset|changed)|reset\s+your\s+password|(reset|recover|recovery)\s+(instructions|link)|'
    r'unusual\s+(sign[-\s]?in|activity|login)|security\s+alert|'
    # Money. Worthless a day later, and private.
    r'your\s+(receipt|order|invoice|refund)|order\s+(confirmed|confirmation|shipped)|'
    r'payment\s+(received|failed|due|declined|sent|of|to)|you\s+(sent|received)|'
    r'invoice\s+\#?[\w-]*\d|statement\s+(is\s+)?(ready|available)|account\s+statement|'
    r'balance|available\s+(funds|balance)|account\s+value|deposit|withdraw(al)?|net\s+pay|'
    r'payout|payroll|purchase\s+(approved|declined)|overdraft|transaction\s+alert|'
    r'card\s+(ending|was\s+used)|process\s+your\s+card|'
    r'subscription\s+(renew|renewed|renewal|expiring)|billing|'
    # Machine noise.
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
#
# Anchored on `(?:^|[@.])` rather than `@`, because banks send from a sending
# subdomain: `alerts@notify.wellsfargo.com` never matches a bare `@wellsfargo.`.
_SENDER_BLOCKLIST = re.compile(
    r'(?:^|[@.])(?:'
    r'stripe\.com|paypal\.|chase\.|bankofamerica\.|wellsfargo\.|capitalone\.|'
    r'venmo\.|squareup\.|intuit\.|amazonses\.|zellepay\.|coinbase\.|robinhood\.|'
    r'fidelity\.|schwab\.|americanexpress\.|citi\.|discover\.|revolut\.|wise\.com|gusto\.'
    r')|notifications?@(github|gitlab)\.|ci_activity@',
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

# A credential anywhere in the scanned text, however the template lays it out.
#
# `[\s\S]` rather than `[^\n]` because every real provider puts the code on its
# own line ("Security code:\n\n7391042"), and the digit run allows separators
# because Slack sends `034-928`, Apple sends `483 920` and Google sends
# `G-123 456`. A `\d{4,8}` run bounded by \b matches none of those.
_CREDENTIAL = re.compile(
    r'\b(?:code|otp|passcode|pin|token|password)\b[\s\S]{0,60}?\b\d[\d\s\-]{2,10}\d\b'
    r'|\b\d[\d\s\-]{2,10}\d\b[\s\S]{0,60}?\b(?:is\s+your|to\s+(?:continue|verify|sign))\b'
    r'|\b\d[\d\s\-]{2,10}\d\b[\s\S]{0,40}?\b(?:code|otp|passcode|pin)\b'
    r'|https?://\S{0,120}?(?:token|magic|otp|one[-_]?time|reset|recover|verify|confirm|auth)\S{0,40}=',
    re.IGNORECASE,
)

# An amount tied to an account identifier. Deliberately NOT bare currency: real
# newsletters are full of dollar figures (Money Stuff, StockStory), and cutting
# on `$` alone would delete the best mail in the inbox. It is the pairing with
# an account, card or routing number that makes it the reader's own money.
_FINANCIAL_DETAIL = re.compile(
    r'\b(?:account|card|acct)\b[\s\S]{0,40}?\b(?:ending|number|no\.?)\b'
    r'|\brouting\b[\s\S]{0,20}?\d{6,}'
    r'|\b(?:available|current|remaining)\s+(?:balance|funds)\b'
    r'|\b(?:account\s+value|net\s+pay|direct\s+deposit)\b',
    re.IGNORECASE,
)


def scanned_text(message: dict[str, Any]) -> str:
    """Every field of a message that can reach a prompt.

    Checking `body` alone was a no-op on most real mail. `parse_gmail_message`
    only decodes a body for single-part text/plain or a top-level text part, so
    HTML-only and multipart/related messages — the dominant transactional
    shapes — parse to an empty body. Meanwhile the clustering prompt is handed
    `snippet`, which Gmail always populates with the stripped opening text, i.e.
    exactly the line the code sits on. The filter must read what the model reads.
    """
    return '\n'.join(
        part
        for part in (
            str(message.get('subject') or ''),
            str(message.get('snippet') or ''),
            str(message.get('body') or '')[:MAX_BODY_CHARS],
        )
        if part
    )


def exclusion_reason(message: dict[str, Any]) -> str | None:
    """Why this message must never be printed, or None if it may proceed.

    The category rules read the subject, because a body full of dollar figures
    is a normal newsletter and cutting on that would delete the best mail in the
    inbox. The credential and account-detail rules read **everything the model
    will be shown**, because that is where the secret actually sits.
    """
    subject = str(message.get('subject') or '')
    sender = str(message.get('from') or '')
    scanned = scanned_text(message)

    if _SUBJECT_BLOCKLIST.search(subject):
        return 'transactional, security or billing mail'
    if _SENDER_BLOCKLIST.search(sender):
        return 'automated sender on the exclusion list'
    if _CREDENTIAL.search(scanned):
        return 'contains what looks like a one-time code or sign-in link'
    if _FINANCIAL_DETAIL.search(scanned):
        return 'contains account or balance detail'
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
    """Read ``day``'s bulk mail, minus everything excluded.

    The window is bounded by date rather than `newer_than:`, so a historic
    edition prints the mail of the day it reports on instead of this morning's.

    Returns the survivors, the held-back entries describing what was cut, and
    the source health for this run.
    """
    if not integration or not access_token:
        return [], [], SourceHealth(source='gmail', ok=False, note='Google account not connected')

    after = (day - timedelta(days=max(0, days - 1))).strftime('%Y/%m/%d')
    before = (day + timedelta(days=1)).strftime('%Y/%m/%d')

    seen_ids: set[str] = set()
    parsed: list[dict[str, Any]] = []
    fetched = 0
    failures: list[str] = []

    for template in QUERIES:
        query = template.format(after=after, before=before)
        try:
            raw = await get_gmail_messages(access_token, query=query, max_results=MAX_MESSAGES)
        except Exception as e:  # noqa: BLE001 — one query failing must not lose the section.
            logger.warning('paper: gmail query %r failed: %s', query, sanitize(str(e)))
            failures.append(query)
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

    if len(failures) == len(QUERIES):
        # Every query failed. Reporting this as a quiet mailbox is the exact
        # failure the design exists to prevent: two weeks of a dead token would
        # look identical to two weeks with no newsletters.
        return (
            [],
            [],
            SourceHealth(source='gmail', ok=False, fetched=0, kept=0, note='every Gmail query failed'),
        )

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

    partial = f'{len(failures)} of {len(QUERIES)} Gmail queries failed' if failures else ''
    return (
        kept,
        held_back,
        SourceHealth(source='gmail', ok=True, fetched=fetched, kept=len(kept), note=partial),
    )


__all__ = ['GOOGLE_INTEGRATION_KEY', 'exclusion_reason', 'fetch_newsletters']
