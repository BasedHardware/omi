"""Shared client-side validation for user-authored command arguments."""

from __future__ import annotations

from omi_cli.errors import UsageError


def bounded_text(value: str, *, label: str, max_length: int = 500) -> str:
    """Strip surrounding whitespace and enforce the documented 1-``max_length`` bounds.

    The API documents a 1-500 character bound for user-authored text fields
    (action item descriptions, goal titles). The raw value is measured before
    stripping so padded input cannot smuggle characters past the cap; the
    returned value is the stripped text that is safe to send.
    """
    if len(value) > max_length:
        raise UsageError(
            message=f"Invalid {label}",
            detail=f"{label.capitalize()} must be at most {max_length} characters (got {len(value)}).",
        )
    cleaned = value.strip()
    if not cleaned:
        raise UsageError(
            message=f"Invalid {label}",
            detail=f"{label.capitalize()} cannot be empty or whitespace.",
        )
    return cleaned
