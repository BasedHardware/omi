import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import database.daily_summaries as daily_summaries_db


def _usage_db(existing=None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    collection_ref = user_ref.collection.return_value
    usage_ref = collection_ref.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing is not None
    snapshot.to_dict.return_value = existing
    usage_ref.get.return_value = snapshot
    return fake_db, collection_ref, usage_ref


def test_upsert_desktop_daily_usage_missing_counter_keys_safe_fallback():
    """Verify that partial or missing counters dict does not crash with KeyError."""
    fake_db, collection_ref, usage_ref = _usage_db({'watching_seconds': 100})
    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.firestore, 'transactional', side_effect=lambda fn: fn
    ):
        # counters only has 1 key instead of all 5 fields
        daily_summaries_db.upsert_desktop_daily_usage(
            'uid1',
            '2026-09-30',
            'UTC',
            'device123',
            {'watching_seconds': 150}  # missing listening_seconds, ptt_turns, etc.
        )

    payload = transaction.set.call_args.args[1]
    assert payload['watching_seconds'] == 150
    assert payload['listening_seconds'] == 0
    assert payload['proactive_cards_shown'] == 0
    assert payload['proactive_cards_acted'] == 0
    assert payload['ptt_turns'] == 0


def test_upsert_desktop_daily_usage_handles_invalid_counter_types_and_negatives():
    """Verify that non-int, negative, or bool counter values are sanitized to 0."""
    fake_db, collection_ref, usage_ref = _usage_db({'watching_seconds': 50})
    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.firestore, 'transactional', side_effect=lambda fn: fn
    ):
        daily_summaries_db.upsert_desktop_daily_usage(
            'uid1',
            '2026-09-30',
            'UTC',
            'device123',
            {
                'watching_seconds': 'not_an_int',
                'listening_seconds': -100,
                'proactive_cards_shown': True,  # bool is not int in clean counter terms
                'proactive_cards_acted': None,
                'ptt_turns': 10
            }
        )

    payload = transaction.set.call_args.args[1]
    assert payload['watching_seconds'] == 50  # preserved previous valid
    assert payload['listening_seconds'] == 0
    assert payload['proactive_cards_shown'] == 0
    assert payload['proactive_cards_acted'] == 0
    assert payload['ptt_turns'] == 10


def test_upsert_desktop_daily_usage_validates_identifiers():
    """Verify that empty or invalid uid/date/client_device_id raises ValueError."""
    fake_db, _, _ = _usage_db()

    with patch.object(daily_summaries_db, 'db', fake_db):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            daily_summaries_db.upsert_desktop_daily_usage('', '2026-09-30', 'UTC', 'dev1', {})

        with pytest.raises(ValueError, match="date must be a non-empty string"):
            daily_summaries_db.upsert_desktop_daily_usage('u1', '   ', 'UTC', 'dev1', {})

        with pytest.raises(ValueError, match="client_device_id must be a non-empty string"):
            daily_summaries_db.upsert_desktop_daily_usage('u1', '2026-09-30', 'UTC', '', {})

        with pytest.raises(ValueError, match="Invalid character '/' in identifier"):
            daily_summaries_db.upsert_desktop_daily_usage('u1', '2026/09/30', 'UTC', 'dev1', {})


def test_create_daily_summary_validates_inputs():
    """Verify create_daily_summary validates uid and id in summary_data."""
    fake_db = MagicMock()

    with patch.object(daily_summaries_db, 'db', fake_db):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            daily_summaries_db.create_daily_summary('', {'id': 'sum1'})

        with pytest.raises(ValueError, match="summary_data must be a dict"):
            daily_summaries_db.create_daily_summary('u1', 'invalid_data')  # type: ignore

        with pytest.raises(ValueError, match="summary_data must contain a non-empty 'id'"):
            daily_summaries_db.create_daily_summary('u1', {})

        with pytest.raises(ValueError, match="summary_data must contain a non-empty 'id'"):
            daily_summaries_db.create_daily_summary('u1', {'id': '   '})


def test_get_daily_summary_empty_identifier_fails_safe():
    """Verify get_daily_summary returns None if uid or summary_id is empty."""
    fake_db = MagicMock()
    with patch.object(daily_summaries_db, 'db', fake_db):
        assert daily_summaries_db.get_daily_summary('', 'sum1') is None
        assert daily_summaries_db.get_daily_summary('u1', '') is None
        assert daily_summaries_db.get_daily_summary('u1', '   ') is None
        assert fake_db.collection.call_count == 0


def test_get_desktop_daily_usage_empty_identifier_returns_zeroes():
    """Verify get_desktop_daily_usage returns zeroed counters for invalid inputs."""
    fake_db = MagicMock()
    with patch.object(daily_summaries_db, 'db', fake_db):
        res1 = daily_summaries_db.get_desktop_daily_usage('', '2026-09-30')
        assert res1 == {field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS}

        res2 = daily_summaries_db.get_desktop_daily_usage('u1', '')
        assert res2 == {field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS}

        res3 = daily_summaries_db.get_desktop_daily_usage('   ', '2026-09-30')
        assert res3 == {field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS}
        assert fake_db.collection.call_count == 0


def test_validate_identifier_direct_cases():
    """Directly test _validate_identifier behavior for various edge cases."""
    validate = daily_summaries_db._validate_identifier

    # Valid cases strip whitespace
    assert validate('key', ' abc ') == 'abc'
    assert validate('key', 'valid-id_123') == 'valid-id_123'

    # Non-string or empty strings raise ValueError
    with pytest.raises(ValueError, match="key must be a non-empty string"):
        validate('key', None)
    with pytest.raises(ValueError, match="key must be a non-empty string"):
        validate('key', 123)
    with pytest.raises(ValueError, match="key must be a non-empty string"):
        validate('key', '')
    with pytest.raises(ValueError, match="key must be a non-empty string"):
        validate('key', '   ')

    # Path traversal / separator check
    with pytest.raises(ValueError, match="Invalid character '/' in identifier key"):
        validate('key', 'foo/bar')
    with pytest.raises(ValueError, match="Invalid character '/' in identifier key"):
        validate('key', '/leading_slash')


def test_upsert_desktop_daily_usage_with_non_dict_counters():
    """Verify that passing non-dict counters safely defaults all fields to 0."""
    fake_db, _, _ = _usage_db()
    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.firestore, 'transactional', side_effect=lambda fn: fn
    ):
        daily_summaries_db.upsert_desktop_daily_usage(
            'uid1', '2026-09-30', 'UTC', 'dev1', None  # type: ignore
        )

    payload = transaction.set.call_args.args[1]
    for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS:
        assert payload[field] == 0


def test_create_daily_summary_valid_creation():
    """Verify create_daily_summary succeeds with valid id and uid."""
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    summary_ref = user_ref.collection.return_value.document.return_value

    with patch.object(daily_summaries_db, 'db', fake_db):
        res = daily_summaries_db.create_daily_summary(' user123 ', {'id': ' sum_abc ', 'headline': 'Great Day'})
        assert res == 'sum_abc'
        fake_db.collection.assert_called_with('users')
        user_ref.collection.assert_called_with('daily_summaries')
        summary_ref.set.assert_called_once_with({'id': ' sum_abc ', 'headline': 'Great Day'})
