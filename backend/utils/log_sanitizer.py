"""Log sanitization utilities.

Masks sensitive tokens in log output while preserving enough context
for debugging. Any continuous alphanumeric string of 8+ characters
gets partially masked (first 4 + last 4 visible, middle replaced with ***).

Usage:
    from utils.log_sanitizer import sanitize

    logger.error(f"Token exchange failed: {sanitize(response.text)}")
"""

import re
import logging

logger = logging.getLogger(__name__)

# Matches continuous runs of 8+ chars from the token character set.
# Only masks runs that contain at least one digit or base64 special char (+/=),
# so regular words like "access_token" and "exchange" are preserved.
_TOKEN_CHARS = re.compile(r'[A-Za-z0-9+/=_\-]{8,}')


def sanitize(value) -> str:
    """Mask long token-like strings in a value while keeping enough for search.

    - Strings shorter than 8 chars are kept as-is.
    - Strings 8-12 chars: first 3 + *** + last 3.
    - Strings 13+ chars: first 4 + *** + last 4.

    Preserves structure (JSON keys, punctuation, short values) so the log
    is still useful for debugging.
    """
    if value is None:
        return 'None'
    text = str(value)
    if len(text) > 2000:
        text = text[:2000] + '...[truncated]'
    return _TOKEN_CHARS.sub(_mask_match, text)


def _mask_match(match: re.Match) -> str:
    """Replace the middle of a long token with ***.

    Only masks strings that contain at least one digit or base64 special char (+/=).
    Pure-alpha strings like 'access_token' or 'exchange' are left intact.
    """
    token = match.group(0)
    # Skip pure-alpha/underscore/hyphen words (no digits, no +/=)
    if not any(c in token for c in '0123456789+/='):
        return token
    length = len(token)
    if length < 8:
        return token
    if length <= 12:
        return token[:3] + '***' + token[-3:]
    return token[:4] + '***' + token[-4:]
