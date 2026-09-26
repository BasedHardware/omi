"""Contract and resilience tests for database.daily_summaries input guards, exception safety, and merge writes."""

from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import NotFound

import database.daily_summaries as ds_db


# ============================================================================
# Input Validation & Sanitization Tests
# ============================================================================

@pytest.mark.parametrize(
    'uid,date,device_id',
    [
        ('', '2026-09-26', 'device-1'),
        ('   ', '2026-09-26', 'device-1'),
        (None, '2026-09-26', 'device-1'),
        ('user-1', '', 'device-1'),
        ('user-1', '   ', 'device-1'),
        ('user-1', None, 'device-1'),
        ('user-1', '2026-09-26', ''),
        ('user-1', '2026-09-26', '   '),
        ('user-1', '2026-09-26', None),
    ],
)
def test_upsert_desktop_daily_usage_input_guards(uid, date, device_id):
    with pytest.raises(ValueError, match='uid, date, and client_device_id are required'):
        ds_db.upsert_desktop_daily_usage(uid, date, 'UTC', device_id, {})


def test_get_desktop_daily_usage_invalid_inputs_returns_zeroes():
    res = ds_db.get_desktop_daily_usage('', '2026-09-26')
    assert res == {field: 0 for field in ds_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS}

    res2 = ds_db.get_desktop_daily_usage('user-1', '   ')
    assert res2 == {field: 0 for field in ds_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS}


@pytest.mark.parametrize(
    'uid,summary_data',
    [
        ('', {'id': 'sum-1'}),
        ('   ', {'id': 'sum-1'}),
        (None, {'id': 'sum-1'}),
        ('user-1', 'not-a-dict'),
        ('user-1', {}),
        ('user-1', {'id': ''}),
        ('user-1', {'id': '   '}),
        ('user-1', {'id': None}),
    ],
)
def test_create_daily_summary_input_guards(uid, summary_data):
    with pytest.raises(ValueError):
        ds_db.create_daily_summary(uid, summary_data)


@pytest.mark.parametrize(
    'uid,summary_id',
    [
        ('', 'sum-1'),
        ('   ', 'sum-1'),
        (None, 'sum-1'),
        ('user-1', ''),
        ('user-1', '   '),
        ('user-1', None),
    ],
)
def test_get_daily_summary_invalid_inputs_returns_none(uid, summary_id):
    assert ds_db.get_daily_summary(uid, summary_id) is None


@pytest.mark.parametrize(
    'uid,date',
    [
        ('', '2026-09-26'),
        ('   ', '2026-09-26'),
        (None, '2026-09-26'),
        ('user-1', ''),
        ('user-1', '   '),
        ('user-1', None),
    ],
)
def test_get_daily_summary_by_date_invalid_inputs_returns_none(uid, date):
    assert ds_db.get_daily_summary_by_date(uid, date) is None


def test_get_daily_summaries_invalid_uid_returns_empty():
    assert ds_db.get_daily_summaries('') == []
    assert ds_db.get_daily_summaries('   ') == []


@pytest.mark.parametrize(
    'uid,summary_id,summary_data',
    [
        ('', 'sum-1', {'id': 'sum-1'}),
        ('   ', 'sum-1', {'id': 'sum-1'}),
        ('user-1', '', {'id': 'sum-1'}),
        ('user-1', '   ', {'id': 'sum-1'}),
        ('user-1', 'sum-1', 'not-a-dict'),
    ],
)
def test_update_daily_summary_input_guards(uid, summary_id, summary_data):
    with pytest.raises(ValueError):
        ds_db.update_daily_summary(uid, summary_id, summary_data)


def test_delete_daily_summary_invalid_inputs_returns_false():
    assert ds_db.delete_daily_summary('', 'sum-1') is False
    assert ds_db.delete_daily_summary('user-1', '   ') is False


@pytest.mark.parametrize(
    'uid,summary_id,visibility',
    [
        ('', 'sum-1', 'shared'),
        ('user-1', '', 'shared'),
        ('user-1', 'sum-1', ''),
        ('user-1', 'sum-1', '   '),
        ('user-1', 'sum-1', None),
    ],
)
def test_set_daily_summary_visibility_input_guards(uid, summary_id, visibility):
    with pytest.raises(ValueError):
        ds_db.set_daily_summary_visibility(uid, summary_id, visibility)


def test_get_summaries_count_invalid_uid_returns_zero():
    assert ds_db.get_summaries_count('') == 0
    assert ds_db.get_summaries_count('   ') == 0


# ============================================================================
# Resilience & Partial Payload Edge Case Tests
# ============================================================================

def test_upsert_desktop_daily_usage_partial_counters_safe(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_usage_coll = MagicMock()
    fake_usage_doc = MagicMock()
    fake_snapshot = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_usage_coll
    fake_usage_coll.document.return_value = fake_usage_doc
    fake_snapshot.exists = True
    fake_snapshot.to_dict.return_value = {
        'watching_seconds': 50,
        'listening_seconds': 30,
    }
    fake_usage_doc.get.return_value = fake_snapshot

    monkeypatch.setattr(ds_db, 'db', fake_db)
    monkeypatch.setattr(ds_db.firestore, 'transactional', lambda fn: fn)

    # Calling with partial dictionary (e.g. only watching_seconds provided, others omitted)
    ds_db.upsert_desktop_daily_usage(
        'user-1', '2026-09-26', 'America/New_York', 'device-1',
        {'watching_seconds': 100}
    )

    fake_tx = fake_db.transaction.return_value
    fake_tx.set.assert_called_once()
    payload = fake_tx.set.call_args[0][1]
    assert payload['watching_seconds'] == 100
    assert payload['listening_seconds'] == 30
    assert payload['proactive_cards_shown'] == 0
    assert payload['proactive_cards_acted'] == 0
    assert payload['ptt_turns'] == 0


def test_create_daily_summary_merge_writes(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_summary_coll = MagicMock()
    fake_summary_doc = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_summary_coll
    fake_summary_coll.document.return_value = fake_summary_doc
    monkeypatch.setattr(ds_db, 'db', fake_db)

    summary_payload = {'id': 'summary-123', 'headline': 'Great Day'}
    doc_id = ds_db.create_daily_summary('user-1', summary_payload)
    assert doc_id == 'summary-123'
    fake_summary_doc.set.assert_called_once_with(summary_payload, merge=True)


def test_delete_daily_summary_catches_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_summary_coll = MagicMock()
    fake_summary_doc = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_summary_coll
    fake_summary_coll.document.return_value = fake_summary_doc
    fake_summary_doc.delete.side_effect = NotFound('Document not found')

    fake_redis = MagicMock()
    monkeypatch.setattr(ds_db, 'db', fake_db)
    monkeypatch.setattr(ds_db, 'redis_db', fake_redis)

    result = ds_db.delete_daily_summary('user-1', 'summary-123')
    assert result is True
    fake_redis.remove_daily_summary_to_uid.assert_called_once_with('summary-123')


def test_set_daily_summary_visibility_catches_not_found(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_summary_coll = MagicMock()
    fake_summary_doc = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_summary_coll
    fake_summary_coll.document.return_value = fake_summary_doc
    fake_summary_doc.update.side_effect = NotFound('Document not found')

    monkeypatch.setattr(ds_db, 'db', fake_db)

    result = ds_db.set_daily_summary_visibility('user-1', 'summary-123', 'shared')
    assert result is False


def test_set_daily_summary_visibility_success(monkeypatch):
    fake_db = MagicMock()
    fake_user_doc = MagicMock()
    fake_summary_coll = MagicMock()
    fake_summary_doc = MagicMock()

    fake_db.collection.return_value.document.return_value = fake_user_doc
    fake_user_doc.collection.return_value = fake_summary_coll
    fake_summary_coll.document.return_value = fake_summary_doc

    monkeypatch.setattr(ds_db, 'db', fake_db)

    result = ds_db.set_daily_summary_visibility('user-1', 'summary-123', 'private')
    assert result is True
    fake_summary_doc.update.assert_called_once_with({'visibility': 'private'})
