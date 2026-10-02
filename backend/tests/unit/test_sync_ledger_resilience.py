from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import database.sync_ledger as sync_ledger


def test_coerce_timestamp_variants():
    """Verify _coerce_timestamp parses aware, naive, ISO strings, epoch, and malformed inputs."""
    aware_dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    assert sync_ledger._coerce_timestamp(aware_dt) == aware_dt

    # Naive datetime normalized to UTC
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    parsed_naive = sync_ledger._coerce_timestamp(naive_dt)
    assert parsed_naive is not None
    assert parsed_naive.tzinfo == timezone.utc
    assert parsed_naive.year == 2026 and parsed_naive.hour == 12

    # ISO-8601 strings
    assert sync_ledger._coerce_timestamp("2026-09-30T12:00:00Z") == aware_dt
    assert sync_ledger._coerce_timestamp("2026-09-30T12:00:00+00:00") == aware_dt
    assert sync_ledger._coerce_timestamp("2026-09-30T12:00:00") == aware_dt

    # Epoch numbers
    epoch_sec = 1790769600.0  # 2026-09-30 12:00:00 UTC
    assert sync_ledger._coerce_timestamp(epoch_sec) == aware_dt
    assert sync_ledger._coerce_timestamp(int(epoch_sec)) == aware_dt
    assert sync_ledger._coerce_timestamp(str(epoch_sec)) == aware_dt

    # Malformed / boundary inputs
    assert sync_ledger._coerce_timestamp(None) is None
    assert sync_ledger._coerce_timestamp("") is None
    assert sync_ledger._coerce_timestamp("   ") is None
    assert sync_ledger._coerce_timestamp("not-a-date") is None
    assert sync_ledger._coerce_timestamp(True) is None
    assert sync_ledger._coerce_timestamp(False) is None
    assert sync_ledger._coerce_timestamp(float("nan")) is None
    assert sync_ledger._coerce_timestamp(float("inf")) is None
    assert sync_ledger._coerce_timestamp(float("-inf")) is None
    assert sync_ledger._coerce_timestamp(-100) is None
    assert sync_ledger._coerce_timestamp(10**15) is None


def test_observed_now_variants():
    """Verify _observed_now produces aware UTC datetimes."""
    now_default = sync_ledger._observed_now()
    assert now_default.tzinfo == timezone.utc

    naive_input = datetime(2026, 9, 30, 8, 30, 0)
    observed = sync_ledger._observed_now(naive_input)
    assert observed.tzinfo == timezone.utc
    assert observed.hour == 8 and observed.minute == 30


def test_repeat_failure_capped_resilience():
    """Verify _repeat_failure_capped handles naive datetimes, ISO strings, and malformed inputs."""
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Naive future -> capped
    existing_naive_future = {"repeat_failure_pause_until": datetime(2026, 9, 30, 13, 0, 0)}
    assert sync_ledger._repeat_failure_capped(existing_naive_future, now) is True

    # 2. Naive past -> not capped
    existing_naive_past = {"repeat_failure_pause_until": datetime(2026, 9, 30, 11, 0, 0)}
    assert sync_ledger._repeat_failure_capped(existing_naive_past, now) is False

    # 3. ISO future -> capped
    existing_iso_future = {"repeat_failure_pause_until": "2026-09-30T13:00:00Z"}
    assert sync_ledger._repeat_failure_capped(existing_iso_future, now) is True

    # 4. None or malformed -> not capped
    assert sync_ledger._repeat_failure_capped({}, now) is False
    assert sync_ledger._repeat_failure_capped({"repeat_failure_pause_until": None}, now) is False
    assert sync_ledger._repeat_failure_capped({"repeat_failure_pause_until": "bad-date"}, now) is False


def test_repeat_failure_updates_resilience():
    """Verify _repeat_failure_updates handles naive first_at without TypeError."""
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    naive_first = datetime(2026, 9, 30, 10, 0, 0)  # Naive within 24h

    existing = {
        "repeat_failure_key": "invalid_audio",
        "repeat_failure_fingerprint": "decode:sync_invalid_audio",
        "repeat_failure_first_at": naive_first,
        "repeat_failure_count": 2,
    }

    updates = sync_ledger._repeat_failure_updates(
        existing, "invalid_audio", "decode:sync_invalid_audio", now
    )
    assert updates["repeat_failure_count"] == 3
    assert updates["repeat_failure_first_at"] == datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    assert updates["repeat_failure_pause_until"] == now + sync_ledger.REPEAT_FAILURE_PAUSE


def test_claim_sync_content_naive_and_boundaries():
    """Verify claim_sync_content handles naive pause_until and updated_at cleanly."""
    mock_client = MagicMock()
    mock_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Capped with naive repeat_failure_pause_until (1 hour remaining)
    mock_snapshot.to_dict.return_value = {
        "status": "retryable",
        "repeat_failure_key": "invalid_audio",
        "repeat_failure_pause_until": datetime(2026, 9, 30, 13, 0, 0),  # Naive future
    }
    mock_ref.get.return_value = mock_snapshot

    with patch.object(sync_ledger, "_ledger_ref", return_value=mock_ref), \
         patch.object(sync_ledger, "get_firestore_client", return_value=mock_client):
        mock_client.transaction.return_value = MagicMock()

        res_capped = sync_ledger.claim_sync_content(
            uid="user-1",
            content_id="content-1",
            job_id="job-1",
            lane="audio",
            now=now,
        )
        assert res_capped["outcome"] == "capped"
        assert res_capped["failure_key"] == "invalid_audio"
        assert res_capped["retry_after"] == 3601  # 3600 + 1

        # 2. Busy with naive updated_at within CLAIM_STALE_SECONDS
        mock_snapshot.to_dict.return_value = {
            "status": "processing",
            "job_id": "other-job",
            "updated_at": datetime(2026, 9, 30, 11, 0, 0),  # Naive 1 hr ago
        }
        res_busy = sync_ledger.claim_sync_content(
            uid="user-1",
            content_id="content-1",
            job_id="job-1",
            lane="audio",
            now=now,
        )
        assert res_busy["outcome"] == "busy"


def test_sync_ledger_input_validation():
    """Verify public entry points reject invalid identifiers gracefully."""
    mock_client = MagicMock()
    with patch.object(sync_ledger, "get_firestore_client", return_value=mock_client):
        # claim_sync_content
        assert sync_ledger.claim_sync_content("", "content-1", "job-1", "lane")["outcome"] == "invalid_arguments"
        assert sync_ledger.claim_sync_content("u1", "", "job-1", "lane")["outcome"] == "invalid_arguments"
        assert sync_ledger.claim_sync_content("u1", "c1", "", "lane")["outcome"] == "invalid_arguments"

        # mark_sync_content_completed
        assert not sync_ledger.mark_sync_content_completed("", "c1", "j1", {})
        assert not sync_ledger.mark_sync_content_completed("u1", "", "j1", {})
        assert not sync_ledger.mark_sync_content_completed("u1", "c1", "", {})

        # release_sync_content_claim
        assert not sync_ledger.release_sync_content_claim("", "c1", "j1")
        assert not sync_ledger.release_sync_content_claim("u1", "", "j1")
        assert not sync_ledger.release_sync_content_claim("u1", "c1", "")

        # release_sync_content_claim_after_job_retired
        assert not sync_ledger.release_sync_content_claim_after_job_retired("", "c1", "j1")
        assert not sync_ledger.release_sync_content_claim_after_job_retired("u1", "", "j1")
        assert not sync_ledger.release_sync_content_claim_after_job_retired("u1", "c1", "")

        # bind_sync_content_run_token
        res_bind = sync_ledger.bind_sync_content_run_token("", "c1", "j1", "tok", 1)
        assert res_bind.outcome == sync_ledger.SyncContentRunBindingOutcome.LOST
