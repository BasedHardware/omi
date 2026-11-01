"""Shared deterministic secret patterns for ingestion and durable replacements."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretPattern:
    category: str
    placeholder: str
    regex: re.Pattern[str]


SECRET_PATTERNS = [
    SecretPattern(
        category="private_key",
        placeholder="[REDACTED_PRIVATE_KEY]",
        regex=re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    ),
    SecretPattern(
        category="private_key",
        placeholder="[REDACTED_PRIVATE_KEY]",
        regex=re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    SecretPattern(
        category="database_url",
        placeholder="[REDACTED_DATABASE_URL]",
        regex=re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@[^/\s]+[^\s]*", re.IGNORECASE),
    ),
    SecretPattern(
        category="api_key",
        placeholder="[REDACTED_API_KEY]",
        regex=re.compile(r"\b(?:sk[-_][A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"),
    ),
    SecretPattern(
        category="one_time_code",
        placeholder="[REDACTED_ONE_TIME_CODE]",
        regex=re.compile(
            r"\b(?:one[- ]?time code|verification code|2fa code|mfa code|otp)\s+(?:is\s+)?['\"]?([0-9]{4,8})\b",
            re.IGNORECASE,
        ),
    ),
    SecretPattern(
        category="token",
        placeholder="[REDACTED_TOKEN]",
        regex=re.compile(
            r"\b(?:token|auth[_-]?token|access[_-]?token|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9._~+/=-]{16,})",
            re.IGNORECASE,
        ),
    ),
    SecretPattern(
        category="password",
        placeholder="[REDACTED_PASSWORD]",
        regex=re.compile(r"\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^'\"\s]{8,})", re.IGNORECASE),
    ),
    SecretPattern(
        category="cookie",
        placeholder="[REDACTED_COOKIE]",
        regex=re.compile(r"\b(?:session|cookie)\s*[:=]\s*['\"]?([A-Za-z0-9._~+/=-]{16,})", re.IGNORECASE),
    ),
]
