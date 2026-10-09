from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.cloud.firestore_v1 import FieldFilter

from database import conversation_finalization_jobs as cfj


def test_parse_timestamp_variants():
    """Verify _parse_timestamp handles aware, naive, ISO strings, epoch, and malformed inputs."""
    # Aware datetime
    aware_dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    parsed = cfj._parse_timestamp(aware_dt)
    assert parsed == aware_dt
    assert parsed.tzinfo == timezone.utc

    # Naive datetime
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    parsed_naive = cfj._parse_timestamp(naive_dt)
    assert parsed_naive is not None
    assert parsed_naive.tzinfo == timezone.utc
    assert parsed_naive.year == 2026 and parsed_naive.hour == 12

    # ISO-8601 strings
    assert cfj._parse_timestamp("2026-09-30T12:00:00Z") == aware_dt
    assert cfj._parse_timestamp("2026-09-30T12:00:00+00:00") == aware_dt
    assert cfj._parse_timestamp("2026-09-30T12:00:00") == aware_dt

    # Numeric epoch timestamps
    epoch_sec = 1790769600.0  # 2026-09-30 12:00:00 UTC
    assert cfj._parse_timestamp(epoch_sec) == aware_dt
    assert cfj._parse_timestamp(int(epoch_sec)) == aware_dt
    assert cfj._parse_timestamp(str(epoch_sec)) == aware_dt

    # Malformed / boundary inputs
    assert cfj._parse_timestamp(None) is None
    assert cfj._parse_timestamp("") is None
    assert cfj._parse_timestamp("   ") is None
    assert cfj._parse_timestamp("not-a-date") is None
    assert cfj._parse_timestamp(True) is None
    assert cfj._parse_timestamp(False) is None
    assert cfj._parse_timestamp(float("nan")) is None
    assert cfj._parse_timestamp(float("inf")) is None
    assert cfj._parse_timestamp(float("-inf")) is None
    assert cfj._parse_timestamp(-100) is None
    assert cfj._parse_timestamp(10**15) is None


def test_get_finalization_job_summary_naive_and_malformed():
    """Verify get_finalization_job_summary does not crash on naive created_at or NaN/Inf totals."""
    mock_client = MagicMock()
    mock_projection_col = MagicMock()
    mock_jobs_col = MagicMock()

    mock_client.collection.side_effect = lambda name: (
        mock_projection_col if name == cfj.FINALIZATION_PROJECTION_COLLECTION else mock_jobs_col
    )

    # Shard snapshot with NaN, Inf, and bool values
    mock_shard_doc = MagicMock()
    mock_shard_doc.exists = True
    mock_shard_doc.to_dict.return_value = {
        "generation": cfj.FINALIZATION_PROJECTION_GENERATION,
        "shard": 0,
        "accepted": 5,
        "success": float("nan"),
        "failure": float("inf"),
        "queued": True,  # Boolean should be ignored
        "leased": 2,
    }

    mock_doc_ref = MagicMock()
    mock_doc_ref.get.return_value = mock_shard_doc
    # For shards > 0, return exists=False
    mock_projection_col.document.side_effect = lambda shard_id: (
        mock_doc_ref if shard_id.endswith("-00") else MagicMock(get=MagicMock(return_value=MagicMock(exists=False)))
    )

    # Oldest nonterminal query returns naive datetime snapshot
    mock_query = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.to_dict.return_value = {"created_at": datetime(2026, 9, 29, 12, 0, 0)}  # offset-naive
    mock_query.stream.return_value = [mock_snapshot]
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_jobs_col.where.return_value = mock_query

    summary = cfj.get_finalization_job_summary(firestore_client=mock_client)
    assert summary["accepted"] == 5
    assert summary["success"] == 0
    assert summary["failure"] == 0
    assert summary["queued"] == 0
    assert summary["leased"] == 2
    assert summary["oldest_nonterminal_age_seconds"] > 0


def test_get_abandoned_byok_job_candidates_naive_and_clamping():
    """Verify get_abandoned_byok_job_candidates safely processes naive datetimes and clamps limits."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.collection.return_value = mock_collection

    mock_query = MagicMock()
    mock_collection.where.return_value = mock_query
    mock_query.limit.return_value = mock_query

    mock_snapshot = MagicMock()
    mock_snapshot.id = "job-123"
    mock_snapshot.reference.path = "conversation_finalization_jobs/job-123"
    mock_snapshot.to_dict.return_value = {
        "status": "leased",
        "requires_byok": True,
        "lease_expires_at": datetime(2026, 9, 29, 10, 0, 0),  # Naive expired lease
        "created_at": "2026-09-29T09:00:00Z",  # ISO string
    }
    mock_query.stream.return_value = [mock_snapshot]

    res = cfj.get_abandoned_byok_job_candidates(
        abandoned_after=timedelta(hours=1),
        limit=-5,  # Invalid limit should be clamped safely
        max_scan=999999,  # Oversized scan should be clamped
        firestore_client=mock_client,
    )
    assert len(res["candidates"]) == 1
    assert res["candidates"][0]["job_id"] == "job-123"
    assert res["candidates"][0]["last_activity_at"].tzinfo == timezone.utc


def test_get_stale_processing_orphan_candidates_naive_and_clamping():
    """Verify get_stale_processing_orphan_candidates safely parses naive timestamps and clamps limits."""
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_client.collection_group.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query

    mock_snapshot = MagicMock()
    mock_snapshot.id = "conv-123"
    mock_snapshot.reference.path = "users/test-uid/conversations/conv-123"
    mock_snapshot.to_dict.return_value = {
        "status": "processing",
        "processing_admitted_at": datetime(2026, 9, 29, 8, 0, 0),  # Naive
    }
    mock_query.stream.return_value = [mock_snapshot]

    res = cfj.get_stale_processing_orphan_candidates(
        stale_after=timedelta(hours=2),
        limit=-1,
        max_scan=0,
        firestore_client=mock_client,
    )
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert cand["conversation_id"] == "conv-123"
    assert cand["processing_admitted_at"].tzinfo == timezone.utc


def test_complete_orphan_conversation_naive_matching():
    """Verify _complete_orphan_conversation_txn matches naive and aware datetimes correctly."""
    mock_txn = MagicMock()
    mock_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    # Document has naive datetime
    mock_snapshot.to_dict.return_value = {
        "status": "processing",
        "processing_admitted_at": datetime(2026, 9, 29, 8, 0, 0),
    }
    mock_ref.get.return_value = mock_snapshot

    # Caller passes aware datetime
    expected_aware = datetime(2026, 9, 29, 8, 0, 0, tzinfo=timezone.utc)
    res = cfj._complete_orphan_conversation_txn(
        transaction=mock_txn,
        conversation_ref=mock_ref,
        expected_admitted_at=expected_aware,
        now=cfj._now(),
    )
    assert res is True
    mock_txn.update.assert_called_once_with(mock_ref, {"status": "completed"})


def test_complete_unstampable_orphan_conversation_naive_update_time():
    """Verify _complete_unstampable_orphan_conversation_txn handles naive update_time."""
    mock_txn = MagicMock()
    mock_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {
        "status": "processing",
        "processing_admitted_at": None,
    }
    # Naive update_time on snapshot
    mock_snapshot.update_time = datetime(2026, 9, 28, 12, 0, 0)
    mock_ref.get.return_value = mock_snapshot

    stale_before = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    res = cfj._complete_unstampable_orphan_conversation_txn(
        transaction=mock_txn,
        conversation_ref=mock_ref,
        stale_before=stale_before,
    )
    assert res is True
    mock_txn.update.assert_called_once_with(mock_ref, {"status": "completed"})


def test_abandon_byok_finalization_job_txn_naive_lease():
    """Verify _abandon_byok_finalization_job_txn handles naive lease_expires_at."""
    mock_txn = MagicMock()
    mock_job_ref = MagicMock()
    mock_job_ref.id = "job-456"
    mock_job_snapshot = MagicMock()
    mock_job_snapshot.exists = True
    mock_job_snapshot.to_dict.return_value = {
        "status": "leased",
        "requires_byok": True,
        "dispatch_generation": 1,
        "lease_epoch": 0,
        "lease_expires_at": datetime(2026, 9, 29, 10, 0, 0),  # Naive expired lease
        "updated_at": datetime(2026, 9, 29, 9, 0, 0),  # Naive
        "uid": "user-1",
        "conversation_id": "conv-1",
    }
    mock_job_ref.get.return_value = mock_job_snapshot

    mock_proj_col = MagicMock()
    mock_conv_ref = MagicMock()
    mock_conv_snapshot = MagicMock()
    mock_conv_snapshot.exists = True
    mock_conv_snapshot.to_dict.return_value = {
        "finalization_job_id": "job-456",
        "status": "processing",
    }
    mock_conv_ref.get.return_value = mock_conv_snapshot

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)

    abandonment = cfj._abandon_byok_finalization_job_txn(
        transaction=mock_txn,
        job_ref=mock_job_ref,
        expected_status="leased",
        expected_dispatch_generation=1,
        expected_lease_epoch=0,
        cutoff=cutoff,
        now=now,
        conversation_ref_for_job=lambda uid, cid: mock_conv_ref,
        projection_collection=mock_proj_col,
    )
    assert abandonment["status"] == "abandoned"
    assert abandonment["conversation_outcome"] == "closed"


def test_get_finalization_replay_candidates_limit_clamp():
    """Verify get_finalization_replay_candidates handles invalid limits safely."""
    mock_client = MagicMock()
    mock_col = MagicMock()
    mock_client.collection.return_value = mock_col
    mock_query = MagicMock()
    mock_col.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = []

    res = cfj.get_finalization_replay_candidates(limit=-10, firestore_client=mock_client)
    assert res == []
    mock_query.limit.assert_called_with(1)
