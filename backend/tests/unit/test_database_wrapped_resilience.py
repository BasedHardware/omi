"""Tests for database.wrapped resilience, input validation, and merge writes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound, ServiceUnavailable

import database.wrapped as wrapped_db
from database.wrapped import WrappedStatus


def test_get_wrapped_returns_data(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot

    fake_snapshot.exists = True
    now = datetime.now(timezone.utc)
    fake_snapshot.to_dict.return_value = {
        'year': 2025,
        'status': WrappedStatus.DONE,
        'started_at': now,
        'completed_at': now,
        'updated_at': now,
        'result': {'total_memories': 100},
    }
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    result = wrapped_db.get_wrapped('user-123', 2025)
    assert result is not None
    assert result['status'] == WrappedStatus.DONE
    assert result['result'] == {'total_memories': 100}
    fake_user_coll.document.assert_called_once_with('user-123')
    fake_wrapped_coll.document.assert_called_once_with('2025')


def test_get_wrapped_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = False
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    result = wrapped_db.get_wrapped('user-123', 2025)
    assert result is None


def test_get_wrapped_invalid_inputs(monkeypatch):
    assert wrapped_db.get_wrapped('', 2025) is None
    assert wrapped_db.get_wrapped('   ', 2025) is None
    assert wrapped_db.get_wrapped('user-123', 0) is None
    assert wrapped_db.get_wrapped('user-123', -1) is None
    assert wrapped_db.get_wrapped(None, 2025) is None


def test_create_wrapped_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    data = wrapped_db.create_wrapped('user-123', 2025)

    assert data['year'] == 2025
    assert data['status'] == WrappedStatus.PROCESSING
    assert data['schema_version'] == 1
    fake_wrapped_doc.set.assert_called_once()
    args, kwargs = fake_wrapped_doc.set.call_args
    assert kwargs.get('merge') is True
    assert args[0]['year'] == 2025
    assert args[0]['status'] == WrappedStatus.PROCESSING


def test_create_wrapped_invalid_inputs(monkeypatch):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        wrapped_db.create_wrapped('', 2025)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        wrapped_db.create_wrapped('   ', 2025)

    with pytest.raises(ValueError, match="year must be a positive integer"):
        wrapped_db.create_wrapped('user-123', 0)

    with pytest.raises(ValueError, match="year must be a positive integer"):
        wrapped_db.create_wrapped('user-123', -2025)


def test_update_wrapped_status_done(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    result_payload = {'recap': 'great year'}
    success = wrapped_db.update_wrapped_status('user-123', 2025, WrappedStatus.DONE, result=result_payload)

    assert success is True
    fake_wrapped_doc.update.assert_called_once()
    payload = fake_wrapped_doc.update.call_args[0][0]
    assert payload['status'] == WrappedStatus.DONE
    assert payload['result'] == result_payload
    assert payload['error'] is None
    assert isinstance(payload['completed_at'], datetime)


def test_update_wrapped_status_error(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    success = wrapped_db.update_wrapped_status('user-123', 2025, WrappedStatus.ERROR, error="Quota exceeded")

    assert success is True
    fake_wrapped_doc.update.assert_called_once()
    payload = fake_wrapped_doc.update.call_args[0][0]
    assert payload['status'] == WrappedStatus.ERROR
    assert payload['error'] == "Quota exceeded"
    assert payload['result'] is None


def test_update_wrapped_status_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = False
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    success = wrapped_db.update_wrapped_status('user-123', 2025, WrappedStatus.DONE)
    assert success is False
    fake_wrapped_doc.update.assert_not_called()


def test_update_wrapped_status_concurrent_exception(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_wrapped_doc.update.side_effect = NotFound("document deleted concurrently")
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    success = wrapped_db.update_wrapped_status('user-123', 2025, WrappedStatus.DONE)
    assert success is False


def test_update_wrapped_status_invalid_inputs():
    assert wrapped_db.update_wrapped_status('', 2025, WrappedStatus.DONE) is False
    assert wrapped_db.update_wrapped_status('user-123', 0, WrappedStatus.DONE) is False


def test_update_wrapped_progress_valid(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    progress = {'step': 'fetching_stats', 'pct': 0.3}
    success = wrapped_db.update_wrapped_progress('user-123', 2025, progress)

    assert success is True
    fake_wrapped_doc.update.assert_called_once()
    payload = fake_wrapped_doc.update.call_args[0][0]
    assert payload['progress'] == progress
    assert isinstance(payload['updated_at'], datetime)


def test_update_wrapped_progress_concurrent_exception(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    fake_wrapped_doc.get.return_value = fake_snapshot
    fake_snapshot.exists = True
    fake_wrapped_doc.update.side_effect = NotFound("document deleted concurrently")
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    success = wrapped_db.update_wrapped_progress('user-123', 2025, {'pct': 0.5})
    assert success is False


def test_reset_wrapped_for_regeneration_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_user_coll = MagicMock()
    fake_user_doc = MagicMock()
    fake_wrapped_coll = MagicMock()
    fake_wrapped_doc = MagicMock()

    fake_db.collection.return_value = fake_user_coll
    fake_user_coll.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_wrapped_coll
    fake_wrapped_coll.document.return_value = fake_wrapped_doc
    monkeypatch.setattr(wrapped_db, 'db', fake_db)

    data = wrapped_db.reset_wrapped_for_regeneration('user-123', 2025)

    assert data['year'] == 2025
    assert data['status'] == WrappedStatus.PROCESSING
    assert data['progress'] is None
    fake_wrapped_doc.set.assert_called_once()
    args, kwargs = fake_wrapped_doc.set.call_args
    assert kwargs.get('merge') is True
    assert args[0]['year'] == 2025


def test_reset_wrapped_for_regeneration_invalid_inputs():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        wrapped_db.reset_wrapped_for_regeneration('', 2025)

    with pytest.raises(ValueError, match="year must be a positive integer"):
        wrapped_db.reset_wrapped_for_regeneration('user-123', 0)


def test_is_wrapped_stuck_scenarios():
    # Not a dict
    assert wrapped_db.is_wrapped_stuck(None) is False
    assert wrapped_db.is_wrapped_stuck("invalid") is False

    # Status not processing
    assert wrapped_db.is_wrapped_stuck({'status': WrappedStatus.DONE}) is False
    assert wrapped_db.is_wrapped_stuck({'status': WrappedStatus.ERROR}) is False

    # Processing but missing or invalid updated_at -> stuck
    assert wrapped_db.is_wrapped_stuck({'status': WrappedStatus.PROCESSING}) is True
    assert wrapped_db.is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': 'invalid_date'}) is True

    # Processing and old timestamp -> stuck
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    assert (
        wrapped_db.is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': old_time}, stale_minutes=15)
        is True
    )

    # Processing and recent timestamp -> not stuck
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert (
        wrapped_db.is_wrapped_stuck({'status': WrappedStatus.PROCESSING, 'updated_at': recent_time}, stale_minutes=15)
        is False
    )


@pytest.mark.parametrize("operation", ["status", "progress"])
@pytest.mark.parametrize("error_type", [NotFound, ServiceUnavailable])
def test_wrapped_updates_keep_api_failures_fail_soft(monkeypatch, operation, error_type):
    fake_db = MagicMock()
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = True
    ref.update.side_effect = error_type("synthetic provider failure")
    monkeypatch.setattr(wrapped_db, "db", fake_db)

    if operation == "status":
        result = wrapped_db.update_wrapped_status("user-123", 2025, WrappedStatus.DONE)
    else:
        result = wrapped_db.update_wrapped_progress("user-123", 2025, {"pct": 0.5})

    assert result is False
    ref.update.assert_called_once()
    ref.set.assert_not_called()


@pytest.mark.parametrize("operation", ["status", "progress"])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, TypeError])
def test_wrapped_updates_preserve_unexpected_errors(monkeypatch, operation, error_type):
    fake_db = MagicMock()
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = True
    error = error_type("synthetic programming or serialization failure")
    ref.update.side_effect = error
    monkeypatch.setattr(wrapped_db, "db", fake_db)

    with pytest.raises(error_type) as raised:
        if operation == "status":
            wrapped_db.update_wrapped_status("user-123", 2025, WrappedStatus.DONE)
        else:
            wrapped_db.update_wrapped_progress("user-123", 2025, {"pct": 0.5})

    assert raised.value is error
    ref.update.assert_called_once()
    ref.set.assert_not_called()
