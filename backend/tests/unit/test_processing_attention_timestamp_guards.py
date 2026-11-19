from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from database.processing_attention import (
    _coerce_utc_datetime,
    timing,
    lease_live,
    now_utc,
    claim_in_transaction,
    list_items,
    RETRY_LEASE_SECONDS,
)


def test_coerce_utc_datetime():
    # 1. Naive datetime
    naive = datetime(2026, 10, 28, 12, 0, 0)
    res = _coerce_utc_datetime(naive)
    assert res is not None
    assert res.tzinfo == timezone.utc
    assert res.year == 2026 and res.hour == 12

    # 2. Non-UTC aware datetime
    offset_tz = timezone(timedelta(hours=3))
    aware = datetime(2026, 10, 28, 15, 0, 0, tzinfo=offset_tz)
    res = _coerce_utc_datetime(aware)
    assert res is not None
    assert res.tzinfo == timezone.utc
    assert res.hour == 12

    # 3. Naive ISO string
    iso_naive = "2026-10-28T12:00:00"
    res = _coerce_utc_datetime(iso_naive)
    assert res is not None
    assert res.tzinfo == timezone.utc
    assert res.hour == 12

    # 4. UTC ISO string
    iso_utc = "2026-10-28T12:00:00Z"
    res = _coerce_utc_datetime(iso_utc)
    assert res is not None
    assert res.tzinfo == timezone.utc
    assert res.hour == 12

    # 5. Invalid / None
    assert _coerce_utc_datetime(None) is None
    assert _coerce_utc_datetime("not-a-date") is None
    assert _coerce_utc_datetime(12345) is None


def test_timing_mixed_naive_aware_and_iso_strings():
    # 1. Mixed naive start and aware end
    start_naive = datetime(2026, 10, 28, 10, 0, 0)
    end_aware = datetime(2026, 10, 28, 10, 2, 30, tzinfo=timezone.utc)
    res = timing({'started_at': start_naive, 'finished_at': end_aware})
    assert res['duration_seconds'] == 150.0

    # 2. Mixed aware start and naive end
    start_aware = datetime(2026, 10, 28, 10, 0, 0, tzinfo=timezone.utc)
    end_naive = datetime(2026, 10, 28, 10, 1, 0)
    res = timing({'started_at': start_aware, 'finished_at': end_naive})
    assert res['duration_seconds'] == 60.0

    # 3. ISO-8601 strings for start and end
    res = timing({'started_at': '2026-10-28T10:00:00Z', 'finished_at': '2026-10-28T10:05:00Z'})
    assert res['duration_seconds'] == 300.0

    # 4. Fallback to created_at
    res = timing({'created_at': '2026-10-28T10:00:00', 'finished_at': '2026-10-28T10:01:00'})
    assert res['duration_seconds'] == 60.0


def test_lease_live_naive_and_iso_timestamps():
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Naive datetime for lease_expires_at in the future
    future_naive = datetime(2026, 10, 28, 12, 10, 0)
    assert lease_live({'lease_expires_at': future_naive}, now) is True

    # 2. Naive datetime in the past
    past_naive = datetime(2026, 10, 28, 11, 50, 0)
    assert lease_live({'lease_expires_at': past_naive}, now) is False

    # 3. ISO string in the future
    future_iso = "2026-10-28T12:15:00Z"
    assert lease_live({'lease_expires_at': future_iso}, now) is True

    # 4. Fallback to created_at with naive datetime
    created_naive = datetime(2026, 10, 28, 11, 50, 0)  # + 1800s -> 12:20:00 > 12:00:00
    assert lease_live({'created_at': created_naive}, now) is True

    # 5. Fallback to created_at with ISO string
    created_iso = "2026-10-28T11:55:00Z"  # + 1800s -> 12:25:00 > 12:00:00
    assert lease_live({'created_at': created_iso}, now) is True


def test_explicit_none_retry_field_guards():
    # 1. claim_in_transaction with item['retry'] = None
    tx = MagicMock()
    conv_ref = MagicMock()
    conv_ref.id = "conv1"
    conv_snapshot = MagicMock()
    conv_snapshot.exists = True
    conv_snapshot.to_dict.return_value = {
        'finalization_revision': 1,
        'sync_content_revision': 1,
        'finalization_job_id': 'job1',
    }
    conv_ref.get.return_value = conv_snapshot

    claim_ref = MagicMock()
    claim_ref.id = "claim1"
    claim_snapshot = MagicMock()
    claim_snapshot.exists = True
    claim_snapshot.to_dict.return_value = {
        'state': 'failed',
        'attempt': 1,
        'operation_id': 'op1',
    }
    conv_ref.collection.return_value.document.return_value = claim_ref
    claim_ref.get.return_value = claim_snapshot

    attention_ref = MagicMock()
    att_snapshot = MagicMock()
    att_snapshot.exists = True
    att_snapshot.to_dict.return_value = {
        'generation': "1:1:job1",
        'active': True,
        'retryable': False,
        'retry': None,  # EXPLICIT NONE
    }
    attention_ref.get.return_value = att_snapshot

    # Should raise ClaimRejected('not_retryable') instead of AttributeError: 'NoneType' object has no attribute 'get'
    with pytest.raises(Exception) as exc_info:
        claim_in_transaction(
            transaction=tx,
            conv_ref=conv_ref,
            uid="user1",
            attention_ref=attention_ref,
        )
    assert exc_info.type.__name__ == 'ClaimRejected'
    assert str(exc_info.value) == 'not_retryable'
