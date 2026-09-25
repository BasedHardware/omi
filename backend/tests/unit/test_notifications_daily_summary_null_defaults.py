from unittest.mock import MagicMock, patch

import database.notifications as notifications_db


def _mock_user_doc(data: dict, exists: bool = True):
    doc_snapshot = MagicMock()
    doc_snapshot.exists = exists
    doc_snapshot.to_dict.return_value = data
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc_snapshot
    users_col = MagicMock()
    users_col.document.return_value = doc_ref
    return users_col, doc_ref


def test_daily_summary_schedule_defaults_replaces_explicit_none_and_invalid_types():
    assert notifications_db.daily_summary_schedule_defaults(
        {'daily_summary_enabled': None, 'daily_summary_hour_local': None}
    ) == {
        'daily_summary_enabled': notifications_db.DEFAULT_DAILY_SUMMARY_ENABLED,
        'daily_summary_hour_local': notifications_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL,
    }
    assert (
        notifications_db.daily_summary_schedule_defaults(
            {'daily_summary_enabled': False, 'daily_summary_hour_local': 0}
        )
        == {}
    )
    assert notifications_db.daily_summary_schedule_defaults(
        {'daily_summary_enabled': True, 'daily_summary_hour_local': True}
    ) == {
        'daily_summary_hour_local': notifications_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL,
    }


def test_get_daily_summary_enabled_treats_explicit_none_as_default_true():
    users_col, _ = _mock_user_doc({'daily_summary_enabled': None})
    with patch.object(notifications_db, 'db', new=MagicMock()) as mock_db:
        mock_db.collection.return_value = users_col
        assert notifications_db.get_daily_summary_enabled('user-1') is True

    users_col_false, _ = _mock_user_doc({'daily_summary_enabled': False})
    with patch.object(notifications_db, 'db', new=MagicMock()) as mock_db:
        mock_db.collection.return_value = users_col_false
        assert notifications_db.get_daily_summary_enabled('user-1') is False


def test_get_daily_summary_hour_local_rejects_bool_and_none():
    users_col_bool, _ = _mock_user_doc({'daily_summary_hour_local': True})
    with patch.object(notifications_db, 'db', new=MagicMock()) as mock_db:
        mock_db.collection.return_value = users_col_bool
        assert notifications_db.get_daily_summary_hour_local('user-1') is None

    users_col_int, _ = _mock_user_doc({'daily_summary_hour_local': 21})
    with patch.object(notifications_db, 'db', new=MagicMock()) as mock_db:
        mock_db.collection.return_value = users_col_int
        assert notifications_db.get_daily_summary_hour_local('user-1') == 21
