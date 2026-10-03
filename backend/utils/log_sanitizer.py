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

import json
import logging
import re
from collections.abc import Mapping
from typing import Protocol, Sequence, cast

logger = logging.getLogger(__name__)

# Matches email addresses — mask local part, keep domain for debugging.
_EMAIL_PATTERN = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

# Matches continuous runs of 8+ chars from the token character set.
# Only masks runs that contain at least one digit or base64 char (+/),
# so regular words like "access_token" and "exchange" are preserved.
_TOKEN_CHARS = re.compile(r'[A-Za-z0-9+/_\-]{8,}')


class _ValidationErrorLike(Protocol):
    def errors(self, *, include_input: bool = True) -> Sequence[Mapping[str, object]]: ...


def sanitize(value: object) -> str:
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


def sanitize_validation_error(error: _ValidationErrorLike) -> str:
    """Return validation diagnostics without logging raw input values.

    Pydantic's default ``ValidationError.__str__`` includes ``input_value``;
    for LLM/user-derived payloads that can expose private text. Keep only the
    structural fields needed to debug malformed payloads.
    """
    safe_errors: list[dict[str, object | None]] = []
    for item in error.errors(include_input=False):
        safe_errors.append(
            {
                'type': item.get('type'),
                'loc': item.get('loc'),
                'msg': item.get('msg'),
            }
        )
    return sanitize(json.dumps(safe_errors, default=str))


_PROVIDER_DIAGNOSTIC_PHRASES = (
    'organization_balance_exhausted',
    'organization_monthly_budget_exhausted',
    'project_monthly_budget_exhausted',
    'invalid_api_key',
    'invalid language hint',
    'no audio received',
    'max_duration_reached',
    'request_timeout',
    'rate_limit_exceeded',
    'limit_exceeded',
    'internal server error',
    'unable to complete the request',
    'invalid input audio',
    'timeout',
    'timed out',
    'connection closed',
    'bounded connect retry window',
)

_PROVIDER_CODE_KEYS = ('error_code', 'status_code', 'code')
_PROVIDER_RESPONSE_CODE_KEYS = ('status_code', 'code', 'status')
_PROVIDER_DIAGNOSTIC_KEYS = ('message', 'error_message', 'error', 'description')
_PROVIDER_ERROR_MAX_LENGTH = 160
_PROVIDER_TEXT_SCAN_LENGTH = 2000

_PROVIDER_EXCEPTION_TYPE_NAMES = frozenset(
    {
        'RuntimeError',
        'ValueError',
        'TypeError',
        'KeyError',
        'IndexError',
        'AssertionError',
        'TimeoutError',
        'OSError',
        'ConnectionError',
        'HTTPStatusError',
        'ConnectError',
        'ReadError',
        'WriteError',
        'PoolTimeout',
        'ConnectTimeout',
        'ReadTimeout',
        'WriteTimeout',
        'ConnectionClosed',
        'ConnectionClosedError',
        'ConnectionClosedOK',
    }
)


def _provider_code(candidate: object) -> str:
    """Return a bounded numeric provider status, or '' when unusable."""
    if isinstance(candidate, bool):
        return ''
    if isinstance(candidate, int):
        number = candidate
    elif isinstance(candidate, str) and len(candidate) <= 4 and candidate.isascii() and candidate.isdigit():
        number = int(candidate)
    else:
        return ''
    if 100 <= number <= 599 or 1000 <= number <= 1015:
        return str(number)
    return ''


def _provider_field(value: object, key: str) -> object:
    try:
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value).get(key)
        return getattr(value, key, None)
    except Exception:
        return None


def _provider_code_candidate(value: object) -> object:
    for key in _PROVIDER_CODE_KEYS:
        candidate = _provider_field(value, key)
        if _provider_code(candidate):
            return candidate
    response = _provider_field(value, 'response')
    if response is not None:
        for key in _PROVIDER_RESPONSE_CODE_KEYS:
            candidate = _provider_field(response, key)
            if _provider_code(candidate):
                return candidate
    return None


def _provider_diagnostic_text(value: object) -> str:
    if isinstance(value, str):
        return value
    for key in _PROVIDER_DIAGNOSTIC_KEYS:
        candidate = _provider_field(value, key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    if isinstance(value, BaseException):
        try:
            return str(value)
        except Exception:
            return ''
    return ''


def _provider_normalized_text(text: str) -> str:
    return ' '.join(text.lower().replace('_', ' ').split())


def sanitize_provider_error(value: object, *, code: object = None) -> str:
    """Return a bounded diagnostic for a provider error without echoing raw text.

    Provider and user payloads can carry secrets, paths, or transcript text even
    when purely alphabetic, so nothing from ``value`` is copied to the output.
    Only a canonical diagnostic phrase matched against the provider text, a
    validated numeric status code, and a closed-set exception type name are
    emitted; anything else is redacted.
    """
    if code is None:
        code_text = _provider_code(_provider_code_candidate(value)) or 'unknown'
    else:
        code_text = _provider_code(code) or 'unknown'
    text = _provider_normalized_text(_provider_diagnostic_text(value)[:_PROVIDER_TEXT_SCAN_LENGTH])
    diagnostic = next(
        (phrase for phrase in _PROVIDER_DIAGNOSTIC_PHRASES if _provider_normalized_text(phrase) in text),
        '[redacted]',
    )
    result = f'code={code_text} diagnostic={diagnostic}'
    if isinstance(value, BaseException):
        name = type(value).__name__
        result += f' exception_type={name if name in _PROVIDER_EXCEPTION_TYPE_NAMES else "other"}'
    return sanitize(result)[:_PROVIDER_ERROR_MAX_LENGTH]


def _mask_email(match: re.Match[str]) -> str:
    """Mask email local part, keep domain: john.doe@example.com -> j***e@example.com."""
    email = match.group(0)
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return f'***@{domain}'
    return f'{local[0]}***{local[-1]}@{domain}'


def sanitize_pii(value: object) -> str:
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
    masked: list[str] = []
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


def _mask_token(match: re.Match[str]) -> str:
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
