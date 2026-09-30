"""Hermetic resilience unit tests for backend/database/candidate_integration_outbox.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

import database.candidate_integration_outbox as outbox_db
from database.candidate_integration_outbox import (
    CANDIDATE_INTEGRATION_OUTBOX_COLLECTION,
    CANDIDATE_INTEGRATION_POLICY,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_QUERY_LIMIT,
    MAX_ERROR_TEXT_LENGTH,
    MAX_ID_LENGTH,
    MAX_LEASE_SECONDS,
    MAX_QUERY_LIMIT,
    MIN_LEASE_SECONDS,
    MIN_QUERY_LIMIT,
    TASK_INTELLIGENCE_CONTROL_COLLECTION,
    TASK_INTELLIGENCE_CONTROL_DOCUMENT,
    _clean_id,
    _ensure_utc,
    _integration_outbox_ref,
    _resolve_client,
    _task_control_ref,
    claim_candidate_integration_dispatch,
    complete_candidate_integration_dispatch,
    dead_letter_malformed_candidate_integration,
    list_candidate_integration_dispatches,
    redrive_candidate_integration_dead_letter,
)


def _make_mock_client():
    mock_client = MagicMock()
    mock_txn = MagicMock()
    mock_client.transaction.return_value = mock_txn

    outbox_doc = MagicMock()
    control_doc = MagicMock()
    outbox_coll = MagicMock(document=MagicMock(return_value=outbox_doc))

    # Default control doc exists and matches account_generation 1
    default_ctrl_snap = MagicMock(exists=True)
    default_ctrl_snap.to_dict.return_value = {'account_generation': 1}
    control_doc.get.return_value = default_ctrl_snap

    def mock_collection(coll_name: str):
        user_doc = MagicMock()

        def mock_subcoll(subcoll_name: str):
            if subcoll_name == CANDIDATE_INTEGRATION_OUTBOX_COLLECTION:
                return outbox_coll
            elif subcoll_name == TASK_INTELLIGENCE_CONTROL_COLLECTION:
                return MagicMock(document=MagicMock(return_value=control_doc))
            return MagicMock()

        user_doc.collection.side_effect = mock_subcoll
        return MagicMock(document=MagicMock(return_value=user_doc))

    mock_client.outbox_coll = outbox_coll
    mock_client.collection.side_effect = mock_collection
    return mock_client, mock_txn, outbox_doc, control_doc


def test_clean_id_validates_and_sanitizes():
    assert _clean_id('user_123') == 'user_123'
    assert _clean_id('  cand_abc-456  ') == 'cand_abc-456'
    assert _clean_id('') == ''
    assert _clean_id('   ') == ''
    assert _clean_id(None) == ''
    assert _clean_id(12345) == ''
    assert _clean_id({'id': 'u1'}) == ''
    # Path traversal and injection rejection
    assert _clean_id('../user') == ''
    assert _clean_id('user/sub') == ''
    assert _clean_id('user\\sub') == ''
    assert _clean_id('user\x00null') == ''
    # Length limits
    assert _clean_id('a' * MAX_ID_LENGTH) == 'a' * MAX_ID_LENGTH
    assert _clean_id('a' * (MAX_ID_LENGTH + 1)) == ''


def test_ensure_utc_normalizes_naive_and_aware():
    # Naive datetime
    naive = datetime(2026, 9, 30, 10, 0, 0)
    aware = _ensure_utc(naive)
    assert aware is not None
    assert aware.tzinfo == timezone.utc
    assert aware.year == 2026 and aware.month == 9 and aware.day == 30

    # Aware datetime in non-UTC timezone
    tz_plus_8 = timezone(timedelta(hours=8))
    dt_plus_8 = datetime(2026, 9, 30, 18, 0, 0, tzinfo=tz_plus_8)
    dt_utc = _ensure_utc(dt_plus_8)
    assert dt_utc is not None
    assert dt_utc.tzinfo == timezone.utc
    assert dt_utc.hour == 10

    # Non-datetime
    assert _ensure_utc(None) is None
    assert _ensure_utc('2026-09-30T10:00:00Z') is None
    assert _ensure_utc(123456789) is None


def test_integration_outbox_ref_validation_and_di():
    mock_client, _, outbox_doc, _ = _make_mock_client()
    ref = _integration_outbox_ref('u1', 'cand1', firestore_client=mock_client)
    assert ref is outbox_doc
    mock_client.collection.assert_called_with('users')

    # Path traversal validation
    with pytest.raises(ValueError, match='Invalid or missing uid'):
        _integration_outbox_ref('../u1', 'cand1', firestore_client=mock_client)

    with pytest.raises(ValueError, match='Invalid or missing candidate_id'):
        _integration_outbox_ref('u1', 'cand1/sub', firestore_client=mock_client)


def test_task_control_ref_validation_and_di():
    mock_client, _, _, control_doc = _make_mock_client()
    ref = _task_control_ref('u1', firestore_client=mock_client)
    assert ref is control_doc
    mock_client.collection.assert_called_with('users')

    with pytest.raises(ValueError, match='Invalid or missing uid'):
        _task_control_ref('..\\u1', firestore_client=mock_client)


def test_claim_candidate_integration_dispatch_not_found():
    mock_client, _, outbox_doc, _ = _make_mock_client()
    outbox_doc.get.return_value = MagicMock(exists=False)

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        firestore_client=mock_client,
    )
    assert token is None


def test_claim_candidate_integration_dispatch_generation_mismatch():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'pending',
        'account_generation': 2,  # mismatch with 1
    }
    outbox_doc.get.return_value = mock_snap

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        firestore_client=mock_client,
    )
    assert token is None
    # Verifies status is updated to suppressed via transaction
    mock_txn.update.assert_called_once()
    update_arg = mock_txn.update.call_args[0][1]
    assert update_arg['status'] == 'suppressed'
    assert update_arg['resolution_reason'] == 'account_generation_mismatch'


def test_claim_candidate_integration_dispatch_terminal_status():
    mock_client, _, outbox_doc, _ = _make_mock_client()
    for terminal_status in ['completed', 'suppressed', 'dead_letter']:
        mock_snap = MagicMock(exists=True)
        mock_snap.to_dict.return_value = {
            'status': terminal_status,
            'account_generation': 1,
        }
        outbox_doc.get.return_value = mock_snap

        token = claim_candidate_integration_dispatch(
            'u1',
            'cand1',
            account_generation=1,
            firestore_client=mock_client,
        )
        assert token is None


def test_claim_candidate_integration_dispatch_active_lease_prevents_claim():
    mock_client, _, outbox_doc, _ = _make_mock_client()
    now = datetime.now(timezone.utc)
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'claimed_at': now - timedelta(seconds=60),  # lease 300s, still active
    }
    outbox_doc.get.return_value = mock_snap

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        now=now,
        lease_seconds=300,
        firestore_client=mock_client,
    )
    assert token is None


def test_claim_candidate_integration_dispatch_expired_lease_allows_reclaim():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    now = datetime.now(timezone.utc)
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'attempt_count': 1,
        'claimed_at': now - timedelta(seconds=400),  # expired
    }
    outbox_doc.get.return_value = mock_snap

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        now=now,
        lease_seconds=300,
        firestore_client=mock_client,
    )
    assert token is not None
    assert len(token) == 32
    mock_txn.update.assert_called_once()
    update_arg = mock_txn.update.call_args[0][1]
    assert update_arg['status'] == 'processing'
    assert update_arg['attempt_count'] == 2
    assert update_arg['lease_token'] == token


def test_claim_candidate_integration_dispatch_naive_claimed_at_handled_safely():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    now = datetime.now(timezone.utc)
    naive_claimed_at = (now - timedelta(seconds=400)).replace(tzinfo=None)

    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'attempt_count': 1,
        'claimed_at': naive_claimed_at,
    }
    outbox_doc.get.return_value = mock_snap

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        now=now,
        lease_seconds=300,
        firestore_client=mock_client,
    )
    assert token is not None


def test_claim_candidate_integration_dispatch_invalid_ids():
    mock_client, _, _, _ = _make_mock_client()
    assert (
        claim_candidate_integration_dispatch(
            '../u1',
            'cand1',
            account_generation=1,
            firestore_client=mock_client,
        )
        is None
    )
    assert (
        claim_candidate_integration_dispatch(
            'u1',
            'cand1/path',
            account_generation=1,
            firestore_client=mock_client,
        )
        is None
    )


def test_complete_candidate_integration_dispatch_succeeded():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'lease_token': 'valid_token_123',
    }
    outbox_doc.get.return_value = mock_snap

    result = complete_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        lease_token='valid_token_123',
        succeeded=True,
        firestore_client=mock_client,
    )
    assert result is True
    mock_txn.update.assert_called_once()
    update_arg = mock_txn.update.call_args[0][1]
    assert update_arg['status'] == 'completed'
    assert update_arg['lease_token'] is None
    assert update_arg['last_error_text'] is None


def test_complete_candidate_integration_dispatch_lease_mismatch():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'lease_token': 'token_original',
    }
    outbox_doc.get.return_value = mock_snap

    result = complete_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        lease_token='wrong_token',
        succeeded=True,
        firestore_client=mock_client,
    )
    assert result is False
    mock_txn.update.assert_not_called()


def test_complete_candidate_integration_dispatch_failure_backoff_and_terminal():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()

    # Retryable attempt
    mock_snap1 = MagicMock(exists=True)
    mock_snap1.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'lease_token': 'token_1',
        'attempt_count': 1,
    }
    outbox_doc.get.return_value = mock_snap1

    res1 = complete_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        lease_token='token_1',
        succeeded=False,
        error_text='network_timeout',
        firestore_client=mock_client,
    )
    assert res1 is True
    update1 = mock_txn.update.call_args[0][1]
    assert update1['status'] == 'failed'
    assert update1['available_at'] is not None

    # Terminal attempt exceeding max attempts (5)
    mock_snap2 = MagicMock(exists=True)
    mock_snap2.to_dict.return_value = {
        'status': 'processing',
        'account_generation': 1,
        'lease_token': 'token_2',
        'attempt_count': 5,
    }
    outbox_doc.get.return_value = mock_snap2
    mock_txn.update.reset_mock()

    res2 = complete_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=1,
        lease_token='token_2',
        succeeded=False,
        error_text='fatal_transport_drop',
        firestore_client=mock_client,
    )
    assert res2 is True
    update2 = mock_txn.update.call_args[0][1]
    assert update2['status'] == 'dead_letter'
    assert update2['dead_letter_reason'] is not None


def test_redrive_candidate_integration_dead_letter():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()

    # Successful redrive from dead_letter
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'dead_letter',
        'account_generation': 1,
    }
    outbox_doc.get.return_value = mock_snap

    success = redrive_candidate_integration_dead_letter(
        'u1',
        'cand1',
        account_generation=1,
        firestore_client=mock_client,
    )
    assert success is True
    mock_txn.update.assert_called_once()

    # Ineligible because status is pending
    mock_snap.to_dict.return_value = {
        'status': 'pending',
        'account_generation': 1,
    }
    mock_txn.update.reset_mock()
    assert (
        redrive_candidate_integration_dead_letter(
            'u1',
            'cand1',
            account_generation=1,
            firestore_client=mock_client,
        )
        is False
    )
    mock_txn.update.assert_not_called()


def test_dead_letter_malformed_candidate_integration():
    mock_client, mock_txn, outbox_doc, _ = _make_mock_client()
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'pending',
        'account_generation': 1,
    }
    outbox_doc.get.return_value = mock_snap

    long_err = 'x' * 3000
    res = dead_letter_malformed_candidate_integration(
        'u1',
        'cand1',
        account_generation=1,
        error_text=long_err,
        firestore_client=mock_client,
    )
    assert res is True
    mock_txn.update.assert_called_once()
    update_arg = mock_txn.update.call_args[0][1]
    assert update_arg['status'] == 'dead_letter'
    assert update_arg['dead_letter_reason'] == 'malformed'
    assert len(update_arg['last_error_text']) == MAX_ERROR_TEXT_LENGTH


def test_list_candidate_integration_dispatches():
    mock_client, _, _, _ = _make_mock_client()
    now = datetime.now(timezone.utc)

    snap1 = MagicMock(exists=True)
    snap1.to_dict.return_value = {
        'id': 'cand1',
        'status': 'pending',
        'available_at': now - timedelta(minutes=5),  # eligible
    }

    snap2 = MagicMock(exists=True)
    snap2.to_dict.return_value = {
        'id': 'cand2',
        'status': 'failed',
        'available_at': now + timedelta(minutes=10),  # in future, backoff active
    }

    snap3 = MagicMock(exists=True)
    # Naive datetime in past
    snap3.to_dict.return_value = {
        'id': 'cand3',
        'status': 'processing',
        'available_at': (now - timedelta(minutes=1)).replace(tzinfo=None),
    }

    mock_client.outbox_coll.where.return_value = mock_client.outbox_coll
    mock_client.outbox_coll.limit.return_value.stream.return_value = [snap1, snap2, snap3]

    # Clamping negative limit to MIN_QUERY_LIMIT (1)
    results = list_candidate_integration_dispatches(
        'u1',
        account_generation=1,
        limit=-5,
        now=now,
        firestore_client=mock_client,
    )
    assert len(results) == 2
    assert results[0]['id'] == 'cand1'
    assert results[1]['id'] == 'cand3'
    # Verified query limit was clamped to MIN_QUERY_LIMIT
    mock_client.outbox_coll.limit.assert_called_with(MIN_QUERY_LIMIT)


def test_malformed_task_control_does_not_crash():
    mock_client, _, outbox_doc, control_doc = _make_mock_client()
    mock_snap = MagicMock(exists=True)
    mock_snap.to_dict.return_value = {
        'status': 'pending',
        'account_generation': 0,  # Matches default TaskWorkflowControl() generation
    }
    outbox_doc.get.return_value = mock_snap

    # Control snapshot is corrupt/unparseable
    mock_ctrl_snap = MagicMock(exists=True)
    mock_ctrl_snap.to_dict.side_effect = RuntimeError('Corrupt protobuf payload')
    control_doc.get.return_value = mock_ctrl_snap

    token = claim_candidate_integration_dispatch(
        'u1',
        'cand1',
        account_generation=0,
        firestore_client=mock_client,
    )
    assert token is not None


def test_snapshot_dict_without_exists_attribute():
    class PlainSnap:
        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return self.data

    snap = PlainSnap({'candidate_id': 'ready', 'status': 'pending'})
    res = outbox_db._snapshot_dict(snap)
    assert res == {'candidate_id': 'ready', 'status': 'pending'}
