"""Write-time defaults use the shared strict Firestore transaction fixture."""

from unittest.mock import MagicMock

import pytest

import database.notifications as notifications_module
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument


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


def _write(writer, store):
    if writer == 'enabled':
        return notifications_module.set_daily_summary_enabled('uid1', False, firestore_client=store)
    if writer == 'hour':
        return notifications_module.set_daily_summary_hour_local('uid1', 0, firestore_client=store)
    if writer == 'timezone_seed':
        return notifications_module.set_user_time_zone_if_missing('uid1', 'Asia/Kolkata', firestore_client=store)
    return notifications_module.set_user_time_zone('uid1', 'Asia/Kolkata', firestore_client=store)


@pytest.mark.parametrize('writer', ['enabled', 'hour', 'timezone', 'timezone_seed'])
@pytest.mark.parametrize('exists', [False, True])
def test_schedule_writers_fill_absent_defaults_without_replacing_other_fields(writer, exists):
    path = ('users', 'uid1')
    store = StrictFirestore({path: {'control': 'keep'}} if exists else {})
    _write(writer, store)
    saved = store.rows[path]
    assert saved['daily_summary_enabled'] is (writer != 'enabled')
    assert saved['daily_summary_hour_local'] == (0 if writer == 'hour' else 22)
    if exists:
        assert saved['control'] == 'keep'
    assert len(store.transactions) == 1
    assert len(store.transactions[0].updates if exists else store.transactions[0].creates) == 1


@pytest.mark.parametrize('writer', ['enabled', 'hour', 'timezone', 'timezone_seed'])
def test_schedule_writers_keep_present_opt_out_and_midnight(writer):
    path = ('users', 'uid1')
    store = StrictFirestore({path: {'daily_summary_enabled': False, 'daily_summary_hour_local': 0}})
    _write(writer, store)
    assert store.rows[path]['daily_summary_enabled'] is False
    assert store.rows[path]['daily_summary_hour_local'] == 0


def test_desktop_seed_preserves_existing_client_timezone():
    path = ('users', 'uid1')
    store = StrictFirestore({path: {'time_zone': 'Asia/Tokyo'}})
    assert _write('timezone_seed', store) is False
    assert store.rows[path] == {'time_zone': 'Asia/Tokyo'}
    assert not store.transactions[0].has_written


@pytest.mark.parametrize('writer', ['enabled', 'hour', 'timezone', 'timezone_seed'])
def test_schedule_writers_do_not_use_a_stale_snapshot_for_defaults(monkeypatch, writer):
    path = ('users', 'uid1')
    store = StrictFirestore({path: {'control': 'keep'}})
    original_get = StrictFirestoreDocument.get
    reads = []

    def get(document, transaction=None, **kwargs):
        reads.append(transaction)
        if transaction is None:
            snapshot = original_get(document, transaction=transaction, **kwargs)
            store.rows[path].update({'daily_summary_enabled': False, 'daily_summary_hour_local': 0})
            return snapshot
        store.rows[path].update({'daily_summary_enabled': False, 'daily_summary_hour_local': 0})
        return original_get(document, transaction=transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    _write(writer, store)
    assert store.rows[path]['daily_summary_enabled'] is False
    assert store.rows[path]['daily_summary_hour_local'] == 0
    assert reads and all(transaction is not None for transaction in reads)


def test_set_daily_summary_hour_local_rejects_out_of_range():
    with pytest.raises(ValueError, match='Invalid hour'):
        notifications_module.set_daily_summary_hour_local('uid1', 24)


@pytest.mark.parametrize('time_zone', [None, 'Asia/Kolkata'])
def test_token_registration_delegates_defaults_instead_of_reusing_its_migration_snapshot(monkeypatch, time_zone):
    # Token migration is not a transaction fake; only its delegation is under test.
    store = MagicMock()
    user = store.collection.return_value.document.return_value
    user.get.return_value.exists = False
    user.collection.return_value.document.return_value.get.return_value.exists = False
    schedule = MagicMock()
    monkeypatch.setattr(notifications_module, '_update_summary_schedule', schedule)
    notifications_module.save_token(
        'uid1',
        {'device_key': 'synthetic', 'fcm_token': 'not-a-real-token', 'time_zone': time_zone},
        firestore_client=store,
    )
    schedule.assert_called_once_with('uid1', {'time_zone': time_zone} if time_zone else {}, firestore_client=store)
    user.set.assert_not_called()
