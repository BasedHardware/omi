"""Write-time defaults for always-present daily-summary schedule fields (#13210)."""

from unittest.mock import MagicMock

import pytest

import database.notifications as notifications_module


def _user_doc_db(existing_user: dict | None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing_user is not None
    snapshot.to_dict.return_value = existing_user
    user_ref.get.return_value = snapshot
    token_stream = user_ref.collection.return_value.stream
    token_stream.return_value = []
    unknown_doc = user_ref.collection.return_value.document.return_value.get.return_value
    unknown_doc.exists = False
    return fake_db, user_ref


@pytest.mark.parametrize(
    ('user_data', 'expected'),
    [
        ({}, {'daily_summary_enabled': True, 'daily_summary_hour_local': 22}),
        ({'daily_summary_enabled': False}, {'daily_summary_hour_local': 22}),
        ({'daily_summary_hour_local': 0}, {'daily_summary_enabled': True}),
        ({'daily_summary_enabled': True, 'daily_summary_hour_local': 8}, {}),
        ({'daily_summary_enabled': False, 'daily_summary_hour_local': 0}, {}),
    ],
)
def test_daily_summary_schedule_defaults_fills_only_absent_fields(user_data, expected):
    assert notifications_module.daily_summary_schedule_defaults(user_data) == expected


def test_set_daily_summary_enabled_fills_absent_hour(monkeypatch):
    fake_db, user_ref = _user_doc_db({'email': 'a@example.com'})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    assert notifications_module.set_daily_summary_enabled('uid1', False) is True

    user_ref.set.assert_called_once_with(
        {'daily_summary_hour_local': 22, 'daily_summary_enabled': False},
        merge=True,
    )


def test_set_daily_summary_enabled_does_not_override_present_hour(monkeypatch):
    fake_db, user_ref = _user_doc_db({'daily_summary_hour_local': 0})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    notifications_module.set_daily_summary_enabled('uid1', True)

    user_ref.set.assert_called_once_with({'daily_summary_enabled': True}, merge=True)


def test_set_daily_summary_hour_local_fills_absent_enabled(monkeypatch):
    fake_db, user_ref = _user_doc_db({})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    assert notifications_module.set_daily_summary_hour_local('uid1', 0) is True

    user_ref.set.assert_called_once_with(
        {'daily_summary_enabled': True, 'daily_summary_hour_local': 0},
        merge=True,
    )


def test_set_daily_summary_hour_local_does_not_override_present_enabled(monkeypatch):
    fake_db, user_ref = _user_doc_db({'daily_summary_enabled': False})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    notifications_module.set_daily_summary_hour_local('uid1', 9)

    user_ref.set.assert_called_once_with({'daily_summary_hour_local': 9}, merge=True)


def test_set_daily_summary_hour_local_rejects_out_of_range():
    with pytest.raises(ValueError, match='Invalid hour'):
        notifications_module.set_daily_summary_hour_local('uid1', 24)


def test_save_token_writes_defaults_alongside_time_zone(monkeypatch):
    fake_db, user_ref = _user_doc_db(None)
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    notifications_module.save_token(
        'uid1',
        {'device_key': 'ios_abc', 'fcm_token': 'tok', 'time_zone': 'America/New_York'},
    )

    user_ref.set.assert_called_once_with(
        {
            'time_zone': 'America/New_York',
            'daily_summary_enabled': True,
            'daily_summary_hour_local': 22,
        },
        merge=True,
    )


def test_save_token_preserves_present_schedule_fields(monkeypatch):
    fake_db, user_ref = _user_doc_db(
        {'daily_summary_enabled': False, 'daily_summary_hour_local': 0, 'time_zone': 'UTC'}
    )
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    notifications_module.save_token(
        'uid1',
        {'device_key': 'ios_abc', 'fcm_token': 'tok', 'time_zone': 'America/New_York'},
    )

    user_ref.set.assert_called_once_with({'time_zone': 'America/New_York'}, merge=True)


def test_set_user_time_zone_if_missing_writes_zone_and_defaults(monkeypatch):
    fake_db, user_ref = _user_doc_db({'email': 'desktop-only@example.com'})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    assert notifications_module.set_user_time_zone_if_missing('uid1', 'America/New_York') is True
    user_ref.set.assert_called_once_with(
        {
            'time_zone': 'America/New_York',
            'daily_summary_enabled': True,
            'daily_summary_hour_local': 22,
        },
        merge=True,
    )


def test_set_user_time_zone_if_missing_does_not_write_when_zone_exists(monkeypatch):
    fake_db, user_ref = _user_doc_db({'time_zone': 'Asia/Tokyo'})
    monkeypatch.setattr(notifications_module, 'db', fake_db)

    assert notifications_module.set_user_time_zone_if_missing('uid1', 'America/New_York') is False
    user_ref.set.assert_not_called()
