"""Shared validation helpers for memory-V3-F6 local contracts.

The helpers in this module intentionally preserve the existing fail-closed
exception classes, message text, and missing/unknown check order at call sites.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, TypeVar

_ErrorT = TypeVar("_ErrorT", bound=Exception)


def require_exact_fields(
    raw: Mapping[str, Any],
    expected: Collection[str],
    *,
    label: str,
    error_type: type[_ErrorT],
    missing_message_prefix: str | None = None,
    unknown_message_prefix: str | None = None,
    check_order: tuple[str, str] = ("missing", "unknown"),
) -> None:
    """Require an exact key set while preserving caller-specific messages.

    ``expected`` may be a frozenset/set as in the historical validators. The
    formatted field lists continue to use ``sorted(...)`` so messages remain
    byte-for-byte compatible with the old implementations.
    """

    expected_set = set(expected)
    actual_set = set(raw)
    missing = expected_set - actual_set
    unknown = actual_set - expected_set

    for check in check_order:
        if check == "missing" and missing:
            prefix = missing_message_prefix if missing_message_prefix is not None else f"{label} missing fields"
            raise error_type(f"{prefix}: {sorted(missing)}")
        if check == "unknown" and unknown:
            prefix = unknown_message_prefix if unknown_message_prefix is not None else f"{label} unknown fields"
            raise error_type(f"{prefix}: {sorted(unknown)}")
        if check not in {"missing", "unknown"}:
            raise ValueError(f"unsupported exact-field check: {check}")
