import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

import database.wrapped as wrapped_db
from database.wrapped import (
    WrappedStatus,
    VALID_WRAPPED_STATUSES,
    _validate_identifier,
    _validate_year,
    _coerce_timestamp,
    get_wrapped,
    create_wrapped,
    update_wrapped_status,
    update_wrapped_progress,
    reset_wrapped_for_regeneration,
    is_wrapped_stuck,
)


class TestValidateIdentifier:
    def test_valid_identifier(self):
        assert _validate_identifier("user123") == "user123"

    def test_whitespace_trimmed(self):
        assert _validate_identifier("  user123  ") == "user123"

    def test_empty_string_returns_none(self):
        assert _validate_identifier("") is None

    def test_whitespace_only_returns_none(self):
        assert _validate_identifier("   ") is None

    def test_non_string_returns_none(self):
        assert _validate_identifier(123) is None
        assert _validate_identifier(None) is None
        assert _validate_identifier({}) is None

    def test_path_separators_return_none(self):
        assert _validate_identifier("users/admin") is None
        assert _validate_identifier("users\\admin") is None


class TestValidateYear:
    def test_valid_int_year(self):
        assert _validate_year(2025) == 2025

    def test_valid_str_year(self):
        assert _validate_year("2025") == 2025

    def test_whitespace_str_year(self):
        assert _validate_year("  2024  ") == 2024

    def test_out_of_bounds_year(self):
        assert _validate_year(1999) is None
        assert _validate_year(2101) is None

    def test_non_integer_types(self):
        assert _validate_year(True) is None
        assert _validate_year(False) is None
        assert _validate_year("not_a_year") is None
        assert _validate_year(None) is None


def _mock_wrapped_db(exists=True, data=None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    wrapped_col = user_ref.collection.return_value
    wrapped_doc = wrapped_col.document.return_value
    snapshot = MagicMock()
    snapshot.exists = exists
    snapshot.to_dict.return_value = data or {}
    wrapped_doc.get.return_value = snapshot
    return fake_db, user_ref, wrapped_col, wrapped_doc


def test_get_wrapped_validation_and_coercion():
    # 1. Invalid args return None
    assert get_wrapped("", 2025) is None
    assert get_wrapped("uid", 1990) is None

    # 2. Document not found
    fake_db, _, _, _ = _mock_wrapped_db(exists=False)
    with patch.object(wrapped_db, 'db', fake_db):
        assert get_wrapped("uid1", 2025) is None

    # 3. Document found with timestamp coercion
    now = datetime.now(timezone.utc)
    fake_db, _, _, _ = _mock_wrapped_db(
        exists=True,
        data={
            'year': 2025,
            'status': WrappedStatus.PROCESSING,
            'started_at': now,
            'updated_at': now,
        },
    )
    with patch.object(wrapped_db, 'db', fake_db):
        res = get_wrapped("uid1", 2025)
        assert res is not None
        assert res['year'] == 2025
        assert res['status'] == WrappedStatus.PROCESSING
        assert res['started_at'] == now


def test_create_wrapped_full_schema():
    fake_db, user_ref, wrapped_col, wrapped_doc = _mock_wrapped_db()
    with patch.object(wrapped_db, 'db', fake_db):
        # Invalid input raises ValueError
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            create_wrapped("", 2025)
        with pytest.raises(ValueError, match="year must be a valid integer"):
            create_wrapped("uid1", 1999)

        # Valid creation
        doc = create_wrapped("uid1", 2025)
        assert doc['year'] == 2025
        assert doc['status'] == WrappedStatus.PROCESSING
        assert doc['schema_version'] == 1
        assert doc['completed_at'] is None
        assert doc['result'] is None
        assert doc['error'] is None
        wrapped_doc.set.assert_called_once()
        assert wrapped_doc.set.call_args.args[0]['year'] == 2025


def test_update_wrapped_status_contract():
    fake_db, _, _, wrapped_doc = _mock_wrapped_db(exists=True)
    with patch.object(wrapped_db, 'db', fake_db):
        # Invalid args return False
        assert update_wrapped_status("", 2025, WrappedStatus.DONE) is False
        assert update_wrapped_status("uid1", 1990, WrappedStatus.DONE) is False
        assert update_wrapped_status("uid1", 2025, "INVALID_STATUS") is False

        # Status DONE writes completed_at, result and clears error
        res = update_wrapped_status("uid1", 2025, WrappedStatus.DONE, result={"stats": 123})
        assert res is True
        update_call = wrapped_doc.update.call_args.args[0]
        assert update_call['status'] == WrappedStatus.DONE
        assert update_call['result'] == {"stats": 123}
        assert update_call['error'] is None
        assert 'completed_at' in update_call

        # Status ERROR writes error message and clears result
        res_err = update_wrapped_status("uid1", 2025, WrappedStatus.ERROR, error="Failed API")
        assert res_err is True
        update_err_call = wrapped_doc.update.call_args.args[0]
        assert update_err_call['status'] == WrappedStatus.ERROR
        assert update_err_call['error'] == "Failed API"
        assert update_err_call['result'] is None


def test_update_wrapped_progress_contract():
    fake_db, _, _, wrapped_doc = _mock_wrapped_db(exists=True)
    with patch.object(wrapped_db, 'db', fake_db):
        # Invalid args
        assert update_wrapped_progress("", 2025, {"step": 1}) is False
        assert update_wrapped_progress("uid1", 2025, "not_a_dict") is False

        # Valid progress
        res = update_wrapped_progress("uid1", 2025, {"step": "stats", "pct": 0.5})
        assert res is True
        call_arg = wrapped_doc.update.call_args.args[0]
        assert call_arg['progress'] == {"step": "stats", "pct": 0.5}
        assert 'updated_at' in call_arg


def test_reset_wrapped_for_regeneration():
    fake_db, _, _, wrapped_doc = _mock_wrapped_db(exists=True)
    with patch.object(wrapped_db, 'db', fake_db):
        doc = reset_wrapped_for_regeneration("uid1", 2025)
        assert doc['year'] == 2025
        assert doc['status'] == WrappedStatus.PROCESSING
        assert doc['result'] is None
        assert doc['error'] is None
        assert doc['progress'] is None
        wrapped_doc.set.assert_called_once()


def test_is_wrapped_stuck_fail_safe():
    # 1. Non-dict or None input
    assert is_wrapped_stuck(None) is False
    assert is_wrapped_stuck("invalid") is False

    # 2. Non-processing status is never stuck
    assert is_wrapped_stuck({'status': WrappedStatus.DONE}) is False
    assert is_wrapped_stuck({'status': WrappedStatus.ERROR}) is False
    assert is_wrapped_stuck({'status': WrappedStatus.NOT_GENERATED}) is False

    # 3. Processing with missing updated_at is stuck (fail-safe)
    assert is_wrapped_stuck({'status': WrappedStatus.PROCESSING}) is True
    assert is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': None}) is True

    # 4. Processing with unparseable updated_at is stuck (fail-safe)
    assert is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': 'unparseable'}) is True

    # 5. Processing with recent updated_at is NOT stuck
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': recent}) is False

    # 6. Processing with stale updated_at (> 15 min) IS stuck
    stale = datetime.now(timezone.utc) - timedelta(minutes=20)
    assert is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': stale}) is True