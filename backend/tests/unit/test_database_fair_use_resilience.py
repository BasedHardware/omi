import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest

# Ensure mocked environment
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from backend.database import fair_use


def test_clean_uid_valid():
    assert fair_use._clean_uid('  user_123  ') == 'user_123'


@pytest.mark.parametrize('invalid_uid', ['', '   ', None, 123, []])
def test_clean_uid_invalid(invalid_uid):
    with pytest.raises(ValueError, match='uid must be a non-empty string'):
        fair_use._clean_uid(invalid_uid)


def test_clean_id_valid():
    assert fair_use._clean_id('  event_abc  ', 'event_id') == 'event_abc'


@pytest.mark.parametrize('invalid_id', ['', '   ', None, 456, {}])
def test_clean_id_invalid(invalid_id):
    with pytest.raises(ValueError, match='custom_id must be a non-empty string'):
        fair_use._clean_id(invalid_id, 'custom_id')


def test_get_fair_use_state_empty_uid():
    with pytest.raises(ValueError, match='uid must be a non-empty string'):
        fair_use.get_fair_use_state('')


def test_get_fair_use_state_exists():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {'stage': 'warning', 'violation_count_7d': 1}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        mock_doc
    )

    with patch.object(fair_use, 'db', mock_db):
        res = fair_use.get_fair_use_state('test_user')
        assert res == {'stage': 'warning', 'violation_count_7d': 1}


def test_get_fair_use_state_not_found():
    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        mock_doc
    )

    with patch.object(fair_use, 'db', mock_db):
        res = fair_use.get_fair_use_state('test_user')
        assert res == {}


def test_update_fair_use_state_invalid_args():
    with pytest.raises(ValueError, match='uid must be a non-empty string'):
        fair_use.update_fair_use_state('   ', {'stage': 'warning'})

    with pytest.raises(ValueError, match='updates must be a dictionary'):
        fair_use.update_fair_use_state('user_1', 'not_a_dict')  # type: ignore[arg-type]


def test_update_fair_use_state_does_not_mutate_caller():
    mock_doc_ref = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

    updates = {'stage': 'throttle'}
    with patch.object(fair_use, 'db', mock_db):
        fair_use.update_fair_use_state('user_1', updates)

    assert 'updated_at' not in updates
    assert mock_doc_ref.set.called
    saved_payload, kwargs = mock_doc_ref.set.call_args
    assert saved_payload[0]['stage'] == 'throttle'
    assert 'updated_at' in saved_payload[0]
    assert kwargs.get('merge') is True


def test_set_fair_use_stage_invalid():
    with pytest.raises(ValueError, match='stage must be a non-empty string'):
        fair_use.set_fair_use_stage('user_1', '   ')


def test_set_fair_use_stage_valid():
    with patch.object(fair_use, 'update_fair_use_state') as mock_update:
        fair_use.set_fair_use_stage('user_1', ' warning ', reason='rate_limit')
        mock_update.assert_called_once_with('user_1', {'stage': 'warning', 'reason': 'rate_limit'})


def test_create_fair_use_event_invalid():
    with pytest.raises(ValueError, match='uid must be a non-empty string'):
        fair_use.create_fair_use_event('', {'type': 'overflow'})

    with pytest.raises(ValueError, match='event_data must be a dictionary'):
        fair_use.create_fair_use_event('user_1', None)  # type: ignore[arg-type]


def test_create_fair_use_event_success_immutability():
    mock_doc_ref = MagicMock()
    mock_doc_ref.id = 'event_999'
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

    caller_dict = {'type': 'rate_limit_exceeded'}
    with patch.object(fair_use, 'db', mock_db):
        event_id = fair_use.create_fair_use_event('user_1', caller_dict)

    assert event_id == 'event_999'
    assert 'created_at' not in caller_dict
    assert 'case_ref' not in caller_dict

    saved_data = mock_doc_ref.set.call_args[0][0]
    assert saved_data['type'] == 'rate_limit_exceeded'
    assert saved_data['case_ref'].startswith('FU-')
    assert len(saved_data['case_ref']) == 15  # 'FU-' + 12 chars
    assert isinstance(saved_data['created_at'], datetime)


def test_get_fair_use_events_clamped_limits():
    mock_query = MagicMock()
    mock_query.stream.return_value = []
    mock_coll = MagicMock()
    mock_coll.order_by.return_value.limit.return_value = mock_query
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll

    with patch.object(fair_use, 'db', mock_db):
        fair_use.get_fair_use_events('user_1', limit=-10)
        mock_coll.order_by.return_value.limit.assert_called_with(1)

        fair_use.get_fair_use_events('user_1', limit=1000)
        mock_coll.order_by.return_value.limit.assert_called_with(200)


def test_get_violation_counts_handles_corrupt_and_valid_timestamps():
    now = datetime.now(timezone.utc)
    ts_3d = now - timedelta(days=3)
    ts_15d = now - timedelta(days=15)
    ts_naive = (now - timedelta(days=2)).replace(tzinfo=None)

    doc_recent = MagicMock()
    doc_recent.to_dict.return_value = {'created_at': ts_3d}

    doc_mid = MagicMock()
    doc_mid.to_dict.return_value = {'created_at': ts_15d}

    doc_naive = MagicMock()
    doc_naive.to_dict.return_value = {'created_at': ts_naive}

    doc_corrupt = MagicMock()
    doc_corrupt.to_dict.return_value = {'created_at': 'corrupt_string_timestamp'}

    doc_none = MagicMock()
    doc_none.to_dict.return_value = {'created_at': None}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = [
        doc_recent,
        doc_mid,
        doc_naive,
        doc_corrupt,
        doc_none,
    ]

    with patch.object(fair_use, 'db', mock_db):
        counts = fair_use.get_violation_counts('user_1')
        assert counts['violation_count_7d'] == 2  # ts_3d and ts_naive
        assert counts['violation_count_30d'] == 3  # ts_3d, ts_15d, and ts_naive


def test_resolve_fair_use_event_validation_and_update():
    with pytest.raises(ValueError, match='event_id must be a non-empty string'):
        fair_use.resolve_fair_use_event('user_1', '', 'admin_1')

    with pytest.raises(ValueError, match='admin_uid must be a non-empty string'):
        fair_use.resolve_fair_use_event('user_1', 'evt_1', '   ')

    mock_doc = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

    with patch.object(fair_use, 'db', mock_db):
        fair_use.resolve_fair_use_event('user_1', 'evt_1', 'admin_1', notes='resolved by customer request')
        mock_doc.update.assert_called_once()
        update_args = mock_doc.update.call_args[0][0]
        assert update_args['resolved'] is True
        assert update_args['resolved_by'] == 'admin_1'
        assert update_args['admin_notes'] == 'resolved by customer request'


def test_reset_fair_use_state():
    with pytest.raises(ValueError, match='admin_uid must be a non-empty string'):
        fair_use.reset_fair_use_state('user_1', '')

    with patch.object(fair_use, 'update_fair_use_state') as mock_update:
        fair_use.reset_fair_use_state('user_1', 'admin_boss')
        mock_update.assert_called_once()
        uid, payload = mock_update.call_args[0]
        assert uid == 'user_1'
        assert payload['stage'] == 'none'
        assert payload['violation_count_7d'] == 0
        assert payload['violation_count_30d'] == 0
        assert payload['reset_by'] == 'admin_boss'


def test_get_flagged_users_clamping_and_filtering():
    mock_query = MagicMock()
    mock_query.stream.return_value = []
    mock_coll_group = MagicMock()
    mock_coll_group.where.return_value.order_by.return_value.limit.return_value = mock_query
    mock_db = MagicMock()
    mock_db.collection_group.return_value = mock_coll_group

    with patch.object(fair_use, 'db', mock_db):
        # 1. Default stages and clamped high limit
        fair_use.get_flagged_users(limit=500)
        mock_coll_group.where.assert_called_with('stage', 'in', ['warning', 'throttle', 'restrict'])
        mock_coll_group.where.return_value.order_by.return_value.limit.assert_called_with(200)

        # 2. Specific stage filter
        fair_use.get_flagged_users(stage_filter=' throttle ', limit=10)
        mock_coll_group.where.assert_called_with('stage', '==', 'throttle')
        mock_coll_group.where.return_value.order_by.return_value.limit.assert_called_with(10)
