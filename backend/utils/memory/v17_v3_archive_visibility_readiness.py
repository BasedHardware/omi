"""Backward-compatible shim — implementation lives in ``utils.memory.v3_archive_visibility_readiness`` (WS-G8b)."""

from utils.memory.v3_archive_visibility_readiness import (
    BLOCKED,
    decide_default_visibility,
    evaluate_archive_short_term_visibility_readiness,
    NOT_VISIBLE,
    VISIBLE,
    _ALLOWED_LIFECYCLES,
    _ALLOWED_SOURCE_FRESHNESS,
    _ALLOWED_VISIBILITIES,
    _drop_sensitive_fields,
    _safe_id,
    _sample_records,
    _sanitized_decision,
    _SENSITIVE_KEYS,
)

__all__ = [
    "BLOCKED",
    "decide_default_visibility",
    "evaluate_archive_short_term_visibility_readiness",
    "NOT_VISIBLE",
    "VISIBLE",
    "_ALLOWED_LIFECYCLES",
    "_ALLOWED_SOURCE_FRESHNESS",
    "_ALLOWED_VISIBILITIES",
    "_drop_sensitive_fields",
    "_safe_id",
    "_sample_records",
    "_sanitized_decision",
    "_SENSITIVE_KEYS",
]
