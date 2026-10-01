"""Unit tests verifying resilience and policy invariants in account_deletion_policy."""

from __future__ import annotations

import pytest

from database.account_deletion_policy import (
    ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES,
    ACCOUNT_DELETION_INVALID_STATUS,
    MAX_ACCOUNT_DELETION_STATUS_CHARS,
    account_deletion_blocks_access,
    normalize_account_deletion_status,
)


def test_normalize_account_deletion_status_rejects_invalid_marker_types():
    """Verify normalize_account_deletion_status raises TypeError on non-bool marker_exists."""
    with pytest.raises(TypeError, match="marker_exists must be a boolean"):
        normalize_account_deletion_status(marker_exists="true", raw_status="active")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="marker_exists must be a boolean"):
        normalize_account_deletion_status(marker_exists=["true"], raw_status="active")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="marker_exists must be a boolean"):
        normalize_account_deletion_status(marker_exists={"exists": True}, raw_status="active")  # type: ignore[arg-type]


def test_normalize_account_deletion_status_handles_non_existent_marker():
    """Verify missing marker returns None regardless of raw_status."""
    assert normalize_account_deletion_status(marker_exists=False, raw_status="anything") is None
    assert normalize_account_deletion_status(marker_exists=False, raw_status=None) is None


def test_normalize_account_deletion_status_normalizes_valid_strings():
    """Verify valid statuses are trimmed properly."""
    assert normalize_account_deletion_status(marker_exists=True, raw_status="in_progress") == "in_progress"
    assert normalize_account_deletion_status(marker_exists=True, raw_status="  cancelled  ") == "cancelled"


def test_normalize_account_deletion_status_handles_empty_or_whitespace():
    """Verify empty/whitespace strings map to invalid status sentinel."""
    assert normalize_account_deletion_status(marker_exists=True, raw_status="") == ACCOUNT_DELETION_INVALID_STATUS
    assert normalize_account_deletion_status(marker_exists=True, raw_status="   ") == ACCOUNT_DELETION_INVALID_STATUS


def test_normalize_account_deletion_status_handles_non_string_raw_status():
    """Verify non-string values map to invalid status sentinel to avoid misinterpretation."""
    assert normalize_account_deletion_status(marker_exists=True, raw_status=None) == ACCOUNT_DELETION_INVALID_STATUS
    assert normalize_account_deletion_status(marker_exists=True, raw_status=12345) == ACCOUNT_DELETION_INVALID_STATUS
    assert normalize_account_deletion_status(marker_exists=True, raw_status={"status": "ok"}) == ACCOUNT_DELETION_INVALID_STATUS
    assert normalize_account_deletion_status(marker_exists=True, raw_status=["failed"]) == ACCOUNT_DELETION_INVALID_STATUS


def test_normalize_account_deletion_status_bounds_oversized_status():
    """Verify statuses exceeding MAX_ACCOUNT_DELETION_STATUS_CHARS map to invalid sentinel."""
    oversized = "a" * (MAX_ACCOUNT_DELETION_STATUS_CHARS + 1)
    assert normalize_account_deletion_status(marker_exists=True, raw_status=oversized) == ACCOUNT_DELETION_INVALID_STATUS


def test_account_deletion_blocks_access_allows_none():
    """Verify None status permits access (no marker exists)."""
    assert account_deletion_blocks_access(None) is False


def test_account_deletion_blocks_access_allows_whitelisted_statuses():
    """Verify cancelled and billing_failed explicitly allow access."""
    for allowed in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES:
        assert account_deletion_blocks_access(allowed) is False
        assert account_deletion_blocks_access(f"  {allowed}  ") is False


def test_account_deletion_blocks_access_blocks_all_other_statuses():
    """Verify all non-whitelisted statuses block access."""
    assert account_deletion_blocks_access("in_progress") is True
    assert account_deletion_blocks_access("completed") is True
    assert account_deletion_blocks_access("failed") is True
    assert account_deletion_blocks_access(ACCOUNT_DELETION_INVALID_STATUS) is True
    assert account_deletion_blocks_access("unknown_status") is True


def test_account_deletion_blocks_access_rejects_invalid_types():
    """Verify non-string non-None types raise TypeError."""
    with pytest.raises(TypeError, match="status must be a str or None"):
        account_deletion_blocks_access(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="status must be a str or None"):
        account_deletion_blocks_access({"status": "cancelled"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="status must be a str or None"):
        account_deletion_blocks_access(["cancelled"])  # type: ignore[arg-type]
