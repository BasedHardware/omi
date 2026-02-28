"""Log sanitization utilities.

Masks sensitive tokens and PII in log output while preserving enough context
for debugging.

- Token-like strings (8+ chars with digits): partially masked (first 4 + last 4 visible)
- Email addresses: local part masked, domain preserved (j***n@example.com)

Usage:
    from utils.log_sanitizer import sanitize, sanitize_pii

    logger.error(f"Token exchange failed: {sanitize(response.text)}")
    logger.info(f"Found contact: {sanitize_pii(name)} -> {sanitize_pii(email)}")
"""

import re
import logging

logger = logging.getLogger(__name__)

# Matches email addresses — mask local part, keep domain for debugging.
_EMAIL_PATTERN = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

# Matches continuous runs of 8+ chars from the token character set.
# Only masks runs that contain at least one digit or base64 char (+/),
# so regular words like "access_token" and "exchange" are preserved.
_TOKEN_CHARS = re.compile(r'[A-Za-z0-9+/_\-]{8,}')


def sanitize(value) -> str:
    """Mask token-like strings and emails while keeping enough for search.

    Tokens:
    - Pure-alpha strings (no digits) are kept as-is (JSON keys, error codes).
    - Strings 8-12 chars with digits: first 3 + *** + last 3.
    - Strings 13+ chars with digits: first 4 + *** + last 4.

    Emails:
    - Local part masked: john.doe@example.com -> j***e@example.com

    Preserves structure (JSON keys, punctuation, short values) so the log
    is still useful for debugging.
    """
    if value is None:
        return 'None'
    text = str(value)
    if len(text) > 2000:
        text = text[:2000] + '...[truncated]'
    # Mask emails first (before token regex can match parts of them)
    text = _EMAIL_PATTERN.sub(_mask_email, text)
    return _TOKEN_CHARS.sub(_mask_token, text)


def _mask_email(match: re.Match) -> str:
    """Mask email local part, keep domain: john.doe@example.com -> j***e@example.com."""
    email = match.group(0)
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return f'***@{domain}'
    return f'{local[0]}***{local[-1]}@{domain}'


def sanitize_pii(value) -> str:
    """Mask a known PII value (name, email, user text).

    Use this instead of sanitize() when the value is KNOWN to be personal data.
    Always masks regardless of content (unlike sanitize() which skips pure-alpha words).

    - Emails: local part masked, domain preserved.
    - Short values (<=4 chars): replaced with ***
    - Medium values (5-8 chars): first 1 + *** + last 1
    - Long values (9+ chars): first 2 + *** + last 2
    """
    if value is None:
        return 'None'
    text = str(value)
    truncated = len(text) > 200
    if truncated:
        text = text[:200]
    # Handle emails first, then mask remaining words
    text = _EMAIL_PATTERN.sub(_mask_email, text)
    # Mask each word in the text (skip already-masked email domains)
    words = text.split()
    masked = []
    for word in words:
        # Skip already-masked email addresses (contain @)
        if '@' in word:
            masked.append(word)
            continue
        n = len(word)
        if n <= 4:
            masked.append('***')
        elif n <= 8:
            masked.append(f'{word[0]}***{word[-1]}')
        else:
            masked.append(f'{word[:2]}***{word[-2:]}')
    result = ' '.join(masked)
    if truncated:
        result += '...'
    return result


def _mask_token(match: re.Match) -> str:
    """Replace the middle of a long token-like string with ***.

    Only masks strings that contain at least one digit or base64 special char (+/).
    Pure-alpha strings like 'access_token' or 'exchange' are left intact.
    """
    token = match.group(0)
    # Skip pure-alpha/underscore/hyphen words (no digits, no +/)
    if not any(c in token for c in '0123456789+/'):
        return token
    length = len(token)
    if length < 8:
        return token
    if length <= 12:
        return token[:3] + '***' + token[-3:]
    return token[:4] + '***' + token[-4:]
