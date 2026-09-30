from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.firestore_v1 import FieldFilter

import database.candidate_integration_outbox as outbox_db


def test_coerce_timestamp_variants():
    """Verify _coerce_timestamp parses aware, naive, ISO strings, epoch, and malformed inputs."""
    aware_dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    parsed = outbox_db._coerce_timestamp(aware_dt)
    assert parsed == aware_dt
    assert parsed.tzinfo == timezone.utc

    # Naive datetime normalized to UTC
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    parsed_naive = outbox_db._coerce_timestamp(naive_dt)
    assert parsed_naive is not None
    assert parsed_naive.tzinfo == timezone.utc
    assert parsed_naive.year == 2026 and parsed_naive.hour == 12

    # ISO-8601 strings
    assert outbox_db._coerce_timestamp("2026-09-30T12:00:00Z") == aware_dt
    assert outbox_db._coerce_timestamp("2026-09-30T12:00:00+00:00") == aware_dt
    assert outbox_db._coerce_timestamp("2026-09-30T12:00:00") == aware_dt

    # Numeric epoch timestamps
    epoch_sec = 1790769600.0  # 2026-09-30 12:00:00 UTC
    assert outbox_db._coerce_timestamp(epoch_sec) == aware_dt
    assert outbox_db._coerce_timestamp(int(epoch_sec)) == aware_dt
    assert outbox_db._coerce_timestamp(str(epoch_sec)) == aware_dt

    # Malformed / boundary inputs
    assert outbox_db._coerce_timestamp(None) is None
    assert outbox_db._coerce_timestamp("") is None
    assert outbox_db._coerce_timestamp("   ") is None
    assert outbox_db._coerce_timestamp("not-a-date") is None
    assert outbox_db._coerce_timestamp(True) is None
    assert outbox_db._coerce_timestamp(False) is None
    assert outbox_db._coerce_timestamp(float("nan")) is None
    assert outbox_db._coerce_timestamp(float("inf")) is None
    assert outbox_db._coerce_timestamp(float("-inf")) is None
    assert outbox_db._coerce_timestamp(-100) is None
    assert outbox_db._coerce_timestamp(10**15) is None


def test_observed_now_variants():
    """Verify _observed_now produces aware UTC datetimes."""
    now_default = outbox_db._observed_now()
    assert now_default.tzinfo == timezone.utc

    naive_input = datetime(2026, 9, 30, 8, 30, 0)
    observed = outbox_db._observed_now(naive_input)
    assert observed.tzinfo == timezone.utc
    assert observed.hour == 8 and observed.minute == 30


def test_claim_candidate_integration_dispatch_naive_and_boundaries():
    """Verify claim_candidate_integration_dispatch handles naive claimed_at and clamps lease_seconds."""
    mock_db = MagicMock()
    mock_outbox_ref = MagicMock()
    mock_control_ref = MagicMock()

    mock_outbox_snap = MagicMock()
    mock_outbox_snap.exists = True
    # Naive timestamp in existing processing lease
    mock_outbox_snap.to_dict.return_value = {
        "status": "processing",
        "claimed_at": datetime(2026, 9, 30, 9, 50, 0),  # Naive!
        "account_generation": 1,
        "attempt_count": "invalid_num",  # Malformed attempt count
    }
    mock_outbox_ref.get.return_value = mock_outbox_snap

    mock_control_snap = MagicMock()
    mock_control_snap.exists = True
    mock_control_snap.to_dict.return_value = {"account_generation": 1}
    mock_control_ref.get.return_value = mock_control_snap

    with patch.object(outbox_db, "_integration_outbox_ref", return_value=mock_outbox_ref), \
         patch.object(outbox_db, "_task_control_ref", return_value=mock_control_ref), \
         patch.object(outbox_db, "db", mock_db):
        mock_db.transaction.return_value = MagicMock()

        # 1. Active lease under safe_lease_seconds (300s) -> should return None (still leased)
        now_within_lease = datetime(2026, 9, 30, 9, 52, 0, tzinfo=timezone.utc)
        res_leased = outbox_db.claim_candidate_integration_dispatch(
            uid="user-1",
            candidate_id="cand-1",
            account_generation=1,
            now=now_within_lease,
            lease_seconds=-50,  # Negative should be clamped to default
        )
        assert res_leased is None

        # 2. Expired lease past safe_lease_seconds -> should claim and return token
        now_expired_lease = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
        res_claimed = outbox_db.claim_candidate_integration_dispatch(
            uid="user-1",
            candidate_id="cand-1",
            account_generation=1,
            now=now_expired_lease,
        )
        assert res_claimed is not None
        assert isinstance(res_claimed, str)

        # 3. Invalid uid or candidate_id
        assert outbox_db.claim_candidate_integration_dispatch(uid="", candidate_id="cand-1", account_generation=1) is None
        assert outbox_db.claim_candidate_integration_dispatch(uid="user-1", candidate_id="", account_generation=1) is None


def test_complete_candidate_integration_dispatch_resilience():
    """Verify complete_candidate_integration_dispatch handles non-string errors and malformed attempts."""
    mock_db = MagicMock()
    mock_outbox_ref = MagicMock()
    mock_control_ref = MagicMock()

    mock_outbox_snap = MagicMock()
    mock_outbox_snap.exists = True
    mock_outbox_snap.to_dict.return_value = {
        "status": "processing",
        "lease_token": "token-123",
        "account_generation": 1,
        "attempt_count": "bad_attempt",
    }
    mock_outbox_ref.get.return_value = mock_outbox_snap

    mock_control_snap = MagicMock()
    mock_control_snap.exists = True
    mock_control_snap.to_dict.return_value = {"account_generation": 1}
    mock_control_ref.get.return_value = mock_control_snap

    with patch.object(outbox_db, "_integration_outbox_ref", return_value=mock_outbox_ref), \
         patch.object(outbox_db, "_task_control_ref", return_value=mock_control_ref), \
         patch.object(outbox_db, "db", mock_db):
        mock_db.transaction.return_value = MagicMock()

        # Failure path with None error_text and malformed attempt_count
        res_fail = outbox_db.complete_candidate_integration_dispatch(
            uid="user-1",
            candidate_id="cand-1",
            account_generation=1,
            lease_token="token-123",
            succeeded=False,
            error_text=None,
        )
        assert res_fail is True

        # Input validation
        assert not outbox_db.complete_candidate_integration_dispatch(
            uid="", candidate_id="cand-1", account_generation=1, lease_token="tok", succeeded=True
        )


def test_list_candidate_integration_dispatches_naive_and_clamping():
    """Verify list_candidate_integration_dispatches handles naive/ISO/epoch available_at and clamps limits."""
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_query = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_col
    mock_col.where.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query

    # Snapshot 1: Naive datetime in the past -> Ready
    snap1 = MagicMock()
    snap1.to_dict.return_value = {
        "candidate_id": "cand-past",
        "status": "pending",
        "available_at": datetime(2020, 1, 1, 0, 0, 0),  # Explicit naive past
    }

    # Snapshot 2: ISO string in the future -> Skipped
    snap2 = MagicMock()
    snap2.to_dict.return_value = {
        "candidate_id": "cand-future",
        "status": "failed",
        "available_at": "2026-10-01T12:00:00Z",  # Future ISO
    }

    # Snapshot 3: No available_at -> Ready
    snap3 = MagicMock()
    snap3.to_dict.return_value = {
        "candidate_id": "cand-immediate",
        "status": "pending",
        "available_at": None,
    }

    mock_query.stream.return_value = [snap1, snap2, snap3]

    with patch.object(outbox_db, "db", mock_db):
        res = outbox_db.list_candidate_integration_dispatches(
            uid="user-1",
            account_generation=1,
            limit=-5,  # Invalid limit should be clamped safely to default
            now=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert len(res) == 2
        cand_ids = {r["candidate_id"] for r in res}
        assert cand_ids == {"cand-past", "cand-immediate"}
        mock_query.limit.assert_called_with(100)

        # Invalid uid returns empty list
        assert outbox_db.list_candidate_integration_dispatches(uid="", account_generation=1) == []


def test_dead_letter_malformed_candidate_integration_resilience():
    """Verify dead_letter_malformed_candidate_integration handles non-string error_text safely."""
    mock_db = MagicMock()
    mock_outbox_ref = MagicMock()
    mock_snap = MagicMock()
    mock_snap.exists = True
    mock_snap.to_dict.return_value = {
        "status": "processing",
        "account_generation": 1,
    }
    mock_outbox_ref.get.return_value = mock_snap

    with patch.object(outbox_db, "_integration_outbox_ref", return_value=mock_outbox_ref), \
         patch.object(outbox_db, "db", mock_db):
        mock_db.transaction.return_value = MagicMock()

        # Non-string error_text (Exception instance)
        res = outbox_db.dead_letter_malformed_candidate_integration(
            uid="user-1",
            candidate_id="cand-1",
            account_generation=1,
            error_text=ValueError("Custom error"),
        )
        assert res is True

        # Invalid uid / candidate_id
        assert not outbox_db.dead_letter_malformed_candidate_integration(
            uid="", candidate_id="cand-1", account_generation=1, error_text="err"
        )
