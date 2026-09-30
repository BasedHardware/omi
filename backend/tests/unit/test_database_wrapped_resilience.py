import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import database.wrapped as wrapped_db
from database.wrapped import WrappedStatus


def _wrapped_db(existing=None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    collection_ref = user_ref.collection.return_value
    wrapped_ref = collection_ref.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing is not None
    snapshot.to_dict.return_value = existing
    wrapped_ref.get.return_value = snapshot
    return fake_db, user_ref, collection_ref, wrapped_ref


def test_validate_identifier_and_year():
    assert wrapped_db._validate_identifier("uid", "user_123") == "user_123"
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        wrapped_db._validate_identifier("uid", "")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        wrapped_db._validate_identifier("uid", 123)
    with pytest.raises(ValueError, match="Invalid character '/' in identifier uid"):
        wrapped_db._validate_identifier("uid", "user/hack")

    assert wrapped_db._validate_year(2025) == 2025
    with pytest.raises(ValueError, match="year must be an integer"):
        wrapped_db._validate_year(True)
    with pytest.raises(ValueError, match="year must be an integer"):
        wrapped_db._validate_year("2025")
    with pytest.raises(ValueError, match="year must be within 2000-2100"):
        wrapped_db._validate_year(1999)
    with pytest.raises(ValueError, match="year must be within 2000-2100"):
        wrapped_db._validate_year(2101)


def test_get_wrapped_returns_none_on_invalid_inputs():
    fake_db, _, _, _ = _wrapped_db()
    with patch.object(wrapped_db, 'db', fake_db):
        assert wrapped_db.get_wrapped("", 2025) is None
        assert wrapped_db.get_wrapped("uid", 1990) is None
        assert wrapped_db.get_wrapped("uid/bad", 2025) is None
        assert fake_db.collection.call_count == 0


def test_get_wrapped_success_and_coerces_timestamps():
    now = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    mock_data = {
        'year': 2025,
        'status': WrappedStatus.DONE,
        'started_at': now,
        'completed_at': now,
        'updated_at': now,
        'result': {'minutes': 100},
    }
    fake_db, user_ref, collection_ref, wrapped_ref = _wrapped_db(mock_data)
    with patch.object(wrapped_db, 'db', fake_db):
        res = wrapped_db.get_wrapped(" user1 ", 2025)
        assert res is not None
        assert res['year'] == 2025
        assert res['status'] == WrappedStatus.DONE
        assert res['result'] == {'minutes': 100}
        fake_db.collection.assert_called_with('users')
        user_ref.collection.assert_called_with('wrapped')
        collection_ref.document.assert_called_with('2025')


def test_create_wrapped_validates_inputs_and_writes():
    fake_db, user_ref, collection_ref, wrapped_ref = _wrapped_db()
    with patch.object(wrapped_db, 'db', fake_db):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            wrapped_db.create_wrapped("", 2025)
        with pytest.raises(ValueError, match="year must be within 2000-2100"):
            wrapped_db.create_wrapped("u1", 205)

        data = wrapped_db.create_wrapped("  u123  ", 2025)
        assert data['year'] == 2025
        assert data['status'] == WrappedStatus.PROCESSING
        wrapped_ref.set.assert_called_once()
        set_args = wrapped_ref.set.call_args[0][0]
        assert set_args['year'] == 2025
        assert set_args['status'] == WrappedStatus.PROCESSING


def test_update_wrapped_status_guards():
    fake_db, user_ref, collection_ref, wrapped_ref = _wrapped_db({'status': WrappedStatus.PROCESSING})
    with patch.object(wrapped_db, 'db', fake_db):
        # Invalid inputs return False safely without crashing
        assert not wrapped_db.update_wrapped_status("", 2025, WrappedStatus.DONE)
        assert not wrapped_db.update_wrapped_status("u1", 1990, WrappedStatus.DONE)
        assert not wrapped_db.update_wrapped_status("u1", 2025, "invalid_status")

        # Document exists -> successfully updates
        success = wrapped_db.update_wrapped_status("u1", 2025, WrappedStatus.DONE, result={'res': 1})
        assert success is True
        wrapped_ref.update.assert_called_once()
        update_args = wrapped_ref.update.call_args[0][0]
        assert update_args['status'] == WrappedStatus.DONE
        assert update_args['result'] == {'res': 1}
        assert update_args['completed_at'] is not None


def test_update_wrapped_status_document_missing_returns_false():
    fake_db, _, _, wrapped_ref = _wrapped_db(None)
    with patch.object(wrapped_db, 'db', fake_db):
        assert not wrapped_db.update_wrapped_status("u1", 2025, WrappedStatus.DONE)
        assert wrapped_ref.update.call_count == 0


def test_update_wrapped_progress_guards():
    fake_db, user_ref, collection_ref, wrapped_ref = _wrapped_db({'status': WrappedStatus.PROCESSING})
    with patch.object(wrapped_db, 'db', fake_db):
        assert not wrapped_db.update_wrapped_progress("", 2025, {'step': 'prep'})
        assert not wrapped_db.update_wrapped_progress("u1", 1999, {'step': 'prep'})
        assert not wrapped_db.update_wrapped_progress("u1", 2025, "not_a_dict")  # type: ignore

        assert wrapped_db.update_wrapped_progress("u1", 2025, {'pct': 50}) is True
        wrapped_ref.update.assert_called_once()
        progress_args = wrapped_ref.update.call_args[0][0]
        assert progress_args['progress'] == {'pct': 50}


def test_is_wrapped_stuck_handles_edge_cases():
    assert not wrapped_db.is_wrapped_stuck(None)  # type: ignore
    assert not wrapped_db.is_wrapped_stuck({})
    assert not wrapped_db.is_wrapped_stuck({'status': WrappedStatus.DONE})

    # Processing with no updated_at is considered stuck
    assert wrapped_db.is_wrapped_stuck({'status': WrappedStatus.PROCESSING})

    # Fresh timestamp is not stuck
    fresh_time = datetime.now(timezone.utc)
    assert not wrapped_db.is_wrapped_stuck(
        {'status': WrappedStatus.PROCESSING, 'updated_at': fresh_time}, stale_minutes=15
    )

    # Negative stale minutes safely handled
    assert not wrapped_db.is_wrapped_stuck(
        {'status': WrappedStatus.PROCESSING, 'updated_at': fresh_time}, stale_minutes=-5
    )
