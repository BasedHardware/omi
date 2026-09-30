import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from types import SimpleNamespace

import database.daily_summaries as daily_summaries_db
from database.daily_summaries import (
    upsert_desktop_daily_usage,
    get_desktop_daily_usage,
    create_daily_summary,
    get_daily_summary,
    get_daily_summary_by_date,
    get_daily_summaries,
    update_daily_summary,
    delete_daily_summary,
    set_daily_summary_visibility,
    get_summaries_count,
    _validate_identifier,
    _validate_and_get_counter,
    DESKTOP_DAILY_USAGE_COUNTER_FIELDS,
)


class TestValidateIdentifier:
    def test_valid_identifier(self):
        assert _validate_identifier("valid_id", "test_field") == "valid_id"

    def test_whitespace_trimmed(self):
        assert _validate_identifier("  valid_id  ", "test_field") == "valid_id"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="test_field cannot be empty"):
            _validate_identifier("", "test_field")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="test_field cannot be empty"):
            _validate_identifier("   ", "test_field")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="test_field must be a string"):
            _validate_identifier(123, "test_field")

    def test_path_separator_slash_raises(self):
        with pytest.raises(ValueError, match="test_field cannot contain path separators"):
            _validate_identifier("invalid/id", "test_field")

    def test_path_separator_backslash_raises(self):
        with pytest.raises(ValueError, match="test_field cannot contain path separators"):
            _validate_identifier("invalid\\id", "test_field")


class TestValidateAndGetCounter:
    def test_valid_positive_int(self):
        assert _validate_and_get_counter(42, "test_field") == 42

    def test_zero(self):
        assert _validate_and_get_counter(0, "test_field") == 0

    def test_negative_int(self):
        assert _validate_and_get_counter(-10, "test_field") == 0

    def test_boolean_false(self):
        assert _validate_and_get_counter(False, "test_field") == 0

    def test_boolean_true(self):
        assert _validate_and_get_counter(True, "test_field") == 0

    def test_non_int_type(self):
        assert _validate_and_get_counter("not_an_int", "test_field") == 0

    def test_none(self):
        assert _validate_and_get_counter(None, "test_field") == 0


def _mock_usage_db(existing=None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    collection_ref = user_ref.collection.return_value
    usage_ref = collection_ref.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing is not None
    snapshot.to_dict.return_value = existing
    usage_ref.get.return_value = snapshot
    return fake_db, collection_ref, usage_ref


def test_upsert_desktop_daily_usage_partial_counters_prevents_keyerror():
    """Verify partial counter dictionary does not crash with KeyError (#19955)."""
    fake_db, collection_ref, usage_ref = _mock_usage_db(
        {
            'watching_seconds': 100,
            'listening_seconds': 50,
        }
    )
    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.firestore, 'transactional', side_effect=lambda fn: fn
    ):
        # Only pass watching_seconds, omitting all other 4 counter fields
        daily_summaries_db.upsert_desktop_daily_usage(
            'uid_user',
            '2026-09-30',
            'UTC',
            'device_123',
            {'watching_seconds': 250},
        )

    collection_ref.document.assert_called_once_with('2026-09-30__device_123')
    payload = transaction.set.call_args.args[1]
    assert payload['watching_seconds'] == 250
    assert payload['listening_seconds'] == 50  # preserved from existing
    assert payload['proactive_cards_shown'] == 0  # defaulted safely
    assert payload['proactive_cards_acted'] == 0
    assert payload['ptt_turns'] == 0
    assert payload['date'] == '2026-09-30'
    assert payload['timezone'] == 'UTC'
    assert payload['client_device_id'] == 'device_123'
    assert payload['updated_at'].tzinfo is not None


def test_upsert_desktop_daily_usage_invalid_identifiers_raise():
    fake_db, _, _ = _mock_usage_db()
    with patch.object(daily_summaries_db, 'db', fake_db):
        with pytest.raises(ValueError, match="uid cannot be empty"):
            daily_summaries_db.upsert_desktop_daily_usage(
                "", "2026-09-30", "UTC", "dev1", {}
            )
        with pytest.raises(ValueError, match="date cannot be empty"):
            daily_summaries_db.upsert_desktop_daily_usage(
                "uid1", "   ", "UTC", "dev1", {}
            )
        with pytest.raises(ValueError, match="client_device_id cannot be empty"):
            daily_summaries_db.upsert_desktop_daily_usage(
                "uid1", "2026-09-30", "UTC", "", {}
            )


def test_get_desktop_daily_usage_handles_malformed_docs():
    fake_db, collection_ref, _ = _mock_usage_db()
    query = collection_ref.where.return_value
    query.stream.return_value = [
        SimpleNamespace(to_dict=lambda: "not_a_dict"),
        SimpleNamespace(
            to_dict=lambda: {
                'watching_seconds': 100,
                'listening_seconds': -5,  # negative should be 0
                'proactive_cards_shown': True,  # bool should be 0
                'proactive_cards_acted': 'invalid',  # non-int should be 0
                'ptt_turns': 5,
            }
        ),
    ]

    with patch.object(daily_summaries_db, 'db', fake_db):
        totals = daily_summaries_db.get_desktop_daily_usage('uid1', '2026-09-30')

    assert totals == {
        'watching_seconds': 100,
        'listening_seconds': 0,
        'proactive_cards_shown': 0,
        'proactive_cards_acted': 0,
        'ptt_turns': 5,
    }


def test_public_summary_crud_operations():
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    summaries_col = user_ref.collection.return_value
    summary_doc = summaries_col.document.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.redis_db, 'remove_daily_summary_to_uid'
    ) as mock_redis:
        # 1. create_daily_summary
        sid = daily_summaries_db.create_daily_summary('uid1', {'id': 'sum_123', 'headline': 'Great Day'})
        assert sid == 'sum_123'
        summary_doc.set.assert_called_with({'id': 'sum_123', 'headline': 'Great Day'})

        # 2. get_daily_summary (found)
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'id': 'sum_123', 'headline': 'Great Day'}
        summary_doc.get.return_value = mock_doc
        res = daily_summaries_db.get_daily_summary('uid1', 'sum_123')
        assert res == {'id': 'sum_123', 'headline': 'Great Day'}

        # 3. update_daily_summary (preserves id)
        daily_summaries_db.update_daily_summary('uid1', 'sum_123', {'headline': 'Updated'})
        summary_doc.set.assert_called_with({'headline': 'Updated', 'id': 'sum_123'})

        # 4. delete_daily_summary (calls redis)
        del_res = daily_summaries_db.delete_daily_summary('uid1', 'sum_123')
        assert del_res is True
        summary_doc.delete.assert_called_once()
        mock_redis.assert_called_once_with('sum_123')

        # 5. set_daily_summary_visibility
        daily_summaries_db.set_daily_summary_visibility('uid1', 'sum_123', 'private')
        summary_doc.update.assert_called_once_with({'visibility': 'private'})

        # 6. get_summaries_count
        count_mock = summaries_col.count.return_value
        count_res_item = MagicMock()
        count_res_item.value = 7
        count_mock.get.return_value = [[count_res_item]]
        count = daily_summaries_db.get_summaries_count('uid1')
        assert count == 7
