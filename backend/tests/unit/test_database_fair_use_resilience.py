"""Hermetic resilience tests for database.fair_use.

Covers identifier validation, caller-dictionary immutability, query-limit
clamping, and corrupt-timestamp tolerance. All Firestore access is mocked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

import pytest

import database.fair_use as fair_use_db


def _patch_db(monkeypatch) -> MagicMock:
    fake_db = MagicMock()
    monkeypatch.setattr(fair_use_db, 'db', fake_db)
    return fake_db


def _doc(data):
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.id = 'event-1'
    return doc


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('bad_uid', ['', '   ', '\t\n', None, 123, b'uid'])
def test_blank_uid_rejected_across_functions(monkeypatch, bad_uid):
    fake_db = _patch_db(monkeypatch)

    with pytest.raises(ValueError):
        fair_use_db.get_fair_use_state(bad_uid)
    with pytest.raises(ValueError):
        fair_use_db.update_fair_use_state(bad_uid, {'stage': 'warning'})
    with pytest.raises(ValueError):
        fair_use_db.set_fair_use_stage(bad_uid, 'warning')
    with pytest.raises(ValueError):
        fair_use_db.create_fair_use_event(bad_uid, {'reason': 'x'})
    with pytest.raises(ValueError):
        fair_use_db.get_fair_use_events(bad_uid)
    with pytest.raises(ValueError):
        fair_use_db.get_violation_counts(bad_uid)
    with pytest.raises(ValueError):
        fair_use_db.resolve_fair_use_event(bad_uid, 'evt', 'admin')
    with pytest.raises(ValueError):
        fair_use_db.reset_fair_use_state(bad_uid, 'admin')

    # Nothing should have reached Firestore.
    fake_db.collection.assert_not_called()
    fake_db.collection_group.assert_not_called()


def test_uid_is_trimmed(monkeypatch):
    fake_db = _patch_db(monkeypatch)

    fair_use_db.get_fair_use_state('  user-1  ')

    fake_db.collection.assert_called_once_with('users')
    fake_db.collection.return_value.document.assert_called_once_with('user-1')


def test_blank_event_and_admin_ids_rejected(monkeypatch):
    fake_db = _patch_db(monkeypatch)

    with pytest.raises(ValueError):
        fair_use_db.resolve_fair_use_event('user-1', '  ', 'admin-1')
    with pytest.raises(ValueError):
        fair_use_db.resolve_fair_use_event('user-1', 'evt-1', '   ')
    with pytest.raises(ValueError):
        fair_use_db.reset_fair_use_state('user-1', '   ')
    with pytest.raises(ValueError):
        fair_use_db.set_fair_use_stage('user-1', '   ')

    fake_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# Caller dictionary immutability
# ---------------------------------------------------------------------------


def test_update_fair_use_state_does_not_mutate_caller_dict(monkeypatch):
    fake_db = _patch_db(monkeypatch)
    updates = {'stage': 'warning', 'violation_count_7d': 3}

    fair_use_db.update_fair_use_state('user-1', updates)

    assert updates == {'stage': 'warning', 'violation_count_7d': 3}
    payload = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value.set.call_args.args[
        0
    ]
    assert payload['stage'] == 'warning'
    assert isinstance(payload['updated_at'], datetime)
    assert payload is not updates


def test_create_fair_use_event_does_not_mutate_caller_dict(monkeypatch):
    fake_db = _patch_db(monkeypatch)
    event_data = {'reason': 'rate_limit', 'details': {'count': 5}}

    fair_use_db.create_fair_use_event('user-1', event_data)

    assert event_data == {'reason': 'rate_limit', 'details': {'count': 5}}
    set_call = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value.set
    payload = set_call.call_args.args[0]
    assert payload['reason'] == 'rate_limit'
    assert isinstance(payload['created_at'], datetime)
    assert payload['case_ref'].startswith('FU-')
    assert payload is not event_data


# ---------------------------------------------------------------------------
# Query limit clamping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'requested, expected',
    [
        (-5, 1),
        (0, 1),
        (1, 1),
        (25, 25),
        (200, 200),
        (201, 200),
        (10_000, 200),
        (None, 50),
        ('abc', 50),
        ('12', 12),
        (float('inf'), 50),
        (float('nan'), 50),
    ],
)
def test_get_fair_use_events_clamps_limit(monkeypatch, requested, expected):
    fake_db = _patch_db(monkeypatch)
    ref = fake_db.collection.return_value.document.return_value.collection.return_value
    ref.order_by.return_value.limit.return_value.stream.return_value = []

    fair_use_db.get_fair_use_events('user-1', limit=requested)

    assert ref.order_by.return_value.limit.call_args == call(expected)


@pytest.mark.parametrize('requested, expected', [(-1, 1), (100_000, 200), (None, 100), (float('inf'), 100)])
def test_get_flagged_users_clamps_limit(monkeypatch, requested, expected):
    fake_db = _patch_db(monkeypatch)
    query = fake_db.collection_group.return_value
    limit_mock = query.where.return_value.order_by.return_value.limit
    limit_mock.return_value.stream.return_value = []

    fair_use_db.get_flagged_users(limit=requested)

    assert limit_mock.call_args == call(expected)


def test_get_flagged_users_blank_stage_filter_uses_default(monkeypatch):
    fake_db = _patch_db(monkeypatch)
    query = fake_db.collection_group.return_value
    query.where.return_value.order_by.return_value.limit.return_value.stream.return_value = []

    fair_use_db.get_flagged_users(stage_filter='   ')

    query.where.assert_called_once_with('stage', 'in', ['warning', 'throttle', 'restrict'])


# ---------------------------------------------------------------------------
# Corrupt timestamp tolerance
# ---------------------------------------------------------------------------


def test_get_violation_counts_skips_corrupt_timestamps(monkeypatch):
    fake_db = _patch_db(monkeypatch)
    ref = fake_db.collection.return_value.document.return_value.collection.return_value
    now = datetime.now(timezone.utc)
    ref.where.return_value.stream.return_value = [
        _doc({'created_at': now - timedelta(days=1)}),  # valid, within 7d
        _doc({'created_at': now - timedelta(days=10)}),  # valid, within 30d only
        _doc({'created_at': 'not-a-timestamp'}),  # corrupt string
        _doc({'created_at': {'nested': 'garbage'}}),  # corrupt type
        _doc({'created_at': None}),  # missing
        _doc({}),  # missing key
        _doc({'created_at': (now - timedelta(days=2)).timestamp()}),  # numeric epoch, within 7d
        _doc({'created_at': now.replace(tzinfo=None) - timedelta(days=3)}),  # naive datetime
    ]

    counts = fair_use_db.get_violation_counts('user-1')

    assert counts == {'violation_count_7d': 3, 'violation_count_30d': 4}


def test_get_violation_counts_handles_all_corrupt(monkeypatch):
    fake_db = _patch_db(monkeypatch)
    ref = fake_db.collection.return_value.document.return_value.collection.return_value
    ref.where.return_value.stream.return_value = [
        _doc({'created_at': 'x'}),
        _doc({'created_at': object()}),
    ]

    assert fair_use_db.get_violation_counts('user-1') == {'violation_count_7d': 0, 'violation_count_30d': 0}
