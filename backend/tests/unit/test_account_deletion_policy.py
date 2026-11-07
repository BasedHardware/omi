"""Unit tests verifying boolean validation and status bounds in account_deletion_policy."""

from __future__ import annotations

from datetime import timedelta

import pytest

from database.account_deletion_policy import (
    ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES,
    ACCOUNT_DELETION_INVALID_STATUS,
    ACCOUNT_DELETION_RESTORABLE_STATUSES,
    MAX_ACCOUNT_DELETION_STATUS_CHARS,
    account_deletion_blocks_access,
    account_deletion_marker_blocks_access,
    account_deletion_restorable,
    deletion_wipe_retry_delay,
    normalize_account_deletion_status,
)


@pytest.mark.parametrize(
    'invalid_marker',
    ['true', 'false', '', ['true'], {'exists': True}, 0, 1, None, ()],
)
def test_normalize_account_deletion_status_rejects_non_bool_marker_exists(invalid_marker):
    """Verify normalize_account_deletion_status and marker helper reject non-boolean marker_exists."""
    with pytest.raises(TypeError, match='marker_exists must be a boolean'):
        normalize_account_deletion_status(
            marker_exists=invalid_marker,  # type: ignore[arg-type]
            raw_status='active',
        )
    with pytest.raises(TypeError, match='marker_exists must be a boolean'):
        account_deletion_marker_blocks_access(
            marker_exists=invalid_marker,  # type: ignore[arg-type]
            raw_status='active',
        )


def test_normalize_account_deletion_status_returns_none_when_marker_absent():
    """Verify missing marker returns None regardless of raw_status."""
    assert normalize_account_deletion_status(marker_exists=False, raw_status='anything') is None
    assert normalize_account_deletion_status(marker_exists=False, raw_status=None) is None
    assert account_deletion_marker_blocks_access(marker_exists=False, raw_status='in_progress') is False


def test_normalize_account_deletion_status_trims_valid_strings():
    """Verify valid status strings are trimmed and bounded up to MAX_ACCOUNT_DELETION_STATUS_CHARS."""
    assert normalize_account_deletion_status(marker_exists=True, raw_status='in_progress') == 'in_progress'
    assert normalize_account_deletion_status(marker_exists=True, raw_status='  cancelled  ') == 'cancelled'
    exact_max = 'a' * MAX_ACCOUNT_DELETION_STATUS_CHARS
    assert normalize_account_deletion_status(marker_exists=True, raw_status=f'  {exact_max}  ') == exact_max


@pytest.mark.parametrize('malformed', ['', '   ', None, 12345, {'status': 'ok'}, ['failed']])
def test_normalize_account_deletion_status_maps_malformed_or_empty_to_invalid_sentinel(malformed):
    """Verify empty, whitespace, or non-string values resolve to ACCOUNT_DELETION_INVALID_STATUS."""
    normalized = normalize_account_deletion_status(marker_exists=True, raw_status=malformed)
    assert normalized == ACCOUNT_DELETION_INVALID_STATUS
    assert account_deletion_marker_blocks_access(marker_exists=True, raw_status=malformed) is True


def test_normalize_account_deletion_status_bounds_oversized_status():
    """Verify statuses exceeding MAX_ACCOUNT_DELETION_STATUS_CHARS map to invalid sentinel."""
    oversized = 'a' * (MAX_ACCOUNT_DELETION_STATUS_CHARS + 1)
    normalized = normalize_account_deletion_status(marker_exists=True, raw_status=oversized)
    assert normalized == ACCOUNT_DELETION_INVALID_STATUS
    assert account_deletion_marker_blocks_access(marker_exists=True, raw_status=oversized) is True


def test_account_deletion_blocks_access_allows_none_and_whitelisted():
    """Verify None and whitelisted statuses allow access while trimming whitespace."""
    assert account_deletion_blocks_access(None) is False
    for allowed in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES:
        assert account_deletion_blocks_access(allowed) is False
        assert account_deletion_blocks_access(f'  {allowed}  ') is False


def test_account_deletion_marker_blocks_access_trims_padded_raw_status():
    """Verify account_deletion_marker_blocks_access trims whitespace-padded raw_status end-to-end."""
    for allowed in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES:
        assert account_deletion_marker_blocks_access(marker_exists=True, raw_status=f'  {allowed}  ') is False
    for blocked in ('in_progress', 'completed', 'failed', 'pending_deletion'):
        assert account_deletion_marker_blocks_access(marker_exists=True, raw_status=f'  {blocked}  ') is True


def test_account_deletion_blocks_access_blocks_non_whitelisted_empty_and_oversized():
    """Verify non-whitelisted, blank, and oversized statuses fail closed by blocking access."""
    assert account_deletion_blocks_access('in_progress') is True
    assert account_deletion_blocks_access('completed') is True
    assert account_deletion_blocks_access('failed') is True
    assert account_deletion_blocks_access('') is True
    assert account_deletion_blocks_access('   ') is True
    assert account_deletion_blocks_access(ACCOUNT_DELETION_INVALID_STATUS) is True
    assert account_deletion_blocks_access('a' * (MAX_ACCOUNT_DELETION_STATUS_CHARS + 1)) is True


@pytest.mark.parametrize('invalid_status', [123, True, False, {'status': 'cancelled'}, ['cancelled']])
def test_account_deletion_blocks_access_rejects_invalid_types(invalid_status):
    """Verify non-string non-None types raise TypeError."""
    with pytest.raises(TypeError, match='status must be a str or None'):
        account_deletion_blocks_access(invalid_status)  # type: ignore[arg-type]


def test_account_deletion_restorable_validates_types_and_bounds():
    """Verify account_deletion_restorable trims valid strings, rejects non-strings, and bounds length."""
    assert account_deletion_restorable(None) is False
    assert account_deletion_restorable('') is False
    assert account_deletion_restorable('   ') is False
    assert account_deletion_restorable('completed') is False
    assert account_deletion_restorable('a' * (MAX_ACCOUNT_DELETION_STATUS_CHARS + 1)) is False
    for restorable in ACCOUNT_DELETION_RESTORABLE_STATUSES:
        assert account_deletion_restorable(restorable) is True
        assert account_deletion_restorable(f'  {restorable}  ') is True
    for invalid_status in (123, True, False, {'status': 'pending'}, ['pending']):
        with pytest.raises(TypeError, match='status must be a str or None'):
            account_deletion_restorable(invalid_status)  # type: ignore[arg-type]


def test_deletion_wipe_retry_delay_rejects_non_int_or_bool():
    """Verify deletion_wipe_retry_delay rejects booleans and non-integers with TypeError."""
    assert deletion_wipe_retry_delay(0) == timedelta(0)
    assert deletion_wipe_retry_delay(1) == timedelta(0)
    for invalid_attempts in (True, False, '2', None, 2.5):
        with pytest.raises(TypeError, match='attempts must be an int'):
            deletion_wipe_retry_delay(invalid_attempts)  # type: ignore[arg-type]
