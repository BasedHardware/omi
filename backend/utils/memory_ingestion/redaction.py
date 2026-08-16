from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from utils.memory_ingestion.ids import StableIdFactory, stable_hmac
from utils.memory_ingestion.models import RedactionRecord


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


def redact_text(
    text: str,
    *,
    source_event_id: str,
    id_factory: StableIdFactory,
    hmac_key: str | None,
    payload_path: str | None = None,
) -> tuple[str, list[RedactionRecord]]:
    redactions: list[RedactionRecord] = []
    redacted = text
    offset = 0
    for pattern in SECRET_PATTERNS:
        replacements: list[tuple[int, int, str, str]] = []
        for match in pattern.regex.finditer(redacted):
            secret_value = match.group(1) if match.groups() else match.group(0)
            replacements.append((match.start(), match.end(), pattern.placeholder, secret_value))
        for start, end, placeholder, secret_value in reversed(replacements):
            absolute_start = start + offset
            absolute_end = end + offset
            value_hash = stable_hmac(hmac_key, secret_value) if hmac_key else None
            redactions.append(
                RedactionRecord(
                    redaction_id=id_factory.new_id(
                        "redaction", source_event_id, payload_path, absolute_start, pattern.category
                    ),
                    source_event_id=source_event_id,
                    category=pattern.category,  # type: ignore[arg-type]
                    placeholder=placeholder,
                    char_start=absolute_start,
                    char_end=absolute_end,
                    payload_path=payload_path,
                    value_hash=value_hash,
                )
            )
            redacted = redacted[:start] + placeholder + redacted[end:]
    return redacted, redactions


def redact_payload(
    value: Any,
    *,
    source_event_id: str,
    id_factory: StableIdFactory,
    hmac_key: str | None,
    path: str = "$",
) -> tuple[Any, list[RedactionRecord]]:
    if isinstance(value, str):
        return redact_text(
            value, source_event_id=source_event_id, id_factory=id_factory, hmac_key=hmac_key, payload_path=path
        )
    if isinstance(value, list):
        items: list[Any] = cast(list[Any], value)
        out: list[Any] = []
        redactions: list[RedactionRecord] = []
        for index, item in enumerate(items):
            redacted_item, item_redactions = redact_payload(
                item,
                source_event_id=source_event_id,
                id_factory=id_factory,
                hmac_key=hmac_key,
                path=f"{path}[{index}]",
            )
            out.append(redacted_item)
            redactions.extend(item_redactions)
        return out, redactions
    if isinstance(value, dict):
        items_dict: dict[Any, Any] = cast(dict[Any, Any], value)
        out_dict: dict[Any, Any] = {}
        redactions = []
        for key, item in items_dict.items():
            redacted_item, item_redactions = redact_payload(
                item,
                source_event_id=source_event_id,
                id_factory=id_factory,
                hmac_key=hmac_key,
                path=f"{path}.{key}",
            )
            out_dict[key] = redacted_item
            redactions.extend(item_redactions)
        return out_dict, redactions
    return value, []
