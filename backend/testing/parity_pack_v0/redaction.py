"""Conservative redaction for cassette metadata, fingerprints, and reports."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|auths?|cookies?|tokens?|secrets?|api[_-]?keys?|"
    r"passwords?|passwd|pwd|signatures?|signed|private[_-]?keys?|access[_-]?keys?|"
    r"credentials?|bearer|jwts?)(?:$|[_-])",
    re.I,
)
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.+-])")
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{6,}\d)(?!\w)")
URL = re.compile(r"https?://[^\s\"']+", re.I)


def redact_text(value: str) -> str:
    """Strip URL query/fragment and mask common direct identifiers."""

    def clean_url(match: re.Match[str]) -> str:
        parsed = urlsplit(match.group(0))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")) + "[REDACTED_URL_PARAMS]"

    value = URL.sub(clean_url, value)
    value = EMAIL.sub("[REDACTED_EMAIL]", value)
    return PHONE.sub("[REDACTED_PHONE]", value)


def _is_sensitive_key(key_text: str) -> bool:
    """True when a mapping key names a credential-like field.

    Handles snake_case, kebab-case, and camelCase so keys like
    ``accessToken`` and ``clientSecret`` are caught alongside
    ``access_token`` and ``access-token``.
    """
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", key_text)
    return bool(SENSITIVE_KEY.search(normalized))


def redact_value(value: Any, *, drop_sensitive: bool = False) -> Any:
    """Return a structurally equivalent, safe-to-log representation.

    Sensitive mapping values are omitted when ``drop_sensitive`` is true (for
    fingerprints), otherwise replaced with a stable marker (for reports).
    """
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                if not drop_sensitive:
                    result[key_text] = "[REDACTED]"
            else:
                result[key_text] = redact_value(item, drop_sensitive=drop_sensitive)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_value(item, drop_sensitive=drop_sensitive) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
