from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database import conversation_finalization_jobs as jobs_db
from services import conversation_selfheal as selfheal_svc


def test_recovery_admission_refusal_naive_recovery_cutoff_with_aware_finished_at():
    now_utc = datetime.now(timezone.utc)
    finished_at = now_utc - timedelta(hours=3)
    # recovery_cutoff is offset-naive
    naive_cutoff = (now_utc - timedelta(hours=2)).replace(tzinfo=None)

    conversation = {
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': finished_at,
        'transcript_segments': [{'text': 'persisted test message'}],
    }

    # Should not raise TypeError: can't compare offset-naive and offset-aware datetimes
    refusal = jobs_db.recovery_admission_refusal('u1', conversation, naive_cutoff)
    assert refusal is None  # stale because finished_at (3h ago) < naive_cutoff (2h ago)

    # When finished_at is more recent than cutoff, it should return 'not_stale'
    recent_finished_at = now_utc - timedelta(minutes=30)
    conversation['finished_at'] = recent_finished_at
    refusal = jobs_db.recovery_admission_refusal('u1', conversation, naive_cutoff)
    assert refusal == 'not_stale'


def test_recovery_admission_refusal_aware_recovery_cutoff_with_naive_finished_at():
    now_utc = datetime.now(timezone.utc)
    finished_at = (now_utc - timedelta(hours=3)).replace(tzinfo=None)
    aware_cutoff = now_utc - timedelta(hours=2)

    conversation = {
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': finished_at,
        'transcript_segments': [{'text': 'persisted test message'}],
    }

    refusal = jobs_db.recovery_admission_refusal('u1', conversation, aware_cutoff)
    assert refusal is None


def test_selfheal_evaluate_row_naive_cutoffs():
    now_naive = datetime(2026, 9, 25, 12, 0, 0)
    stale_cutoff = now_naive - timedelta(hours=2)
    page_cutoff = now_naive - timedelta(hours=12)
    counters = {
        'content_holding': 0,
        'oldest_age_seconds': 0.0,
        'content_holding_over_12h': 0,
        'skipped': 0,
    }

    # finished_at is aware
    row = {
        'uid': 'u1',
        'conversation_id': 'c1',
        'data': {
            'status': 'in_progress',
            'source': 'omi',
            'finished_at': datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc),
            'transcript_segments': [{'text': 'persisted'}],
        },
    }

    reason = selfheal_svc._evaluate_row(
        row,
        now=now_naive,
        stale_cutoff=stale_cutoff,
        page_cutoff=page_cutoff,
        counters=counters,
    )
    assert reason is None
    assert counters['content_holding'] == 1


def test_run_selfheal_tick_naive_now_parameter():
    now_naive = datetime(2026, 9, 25, 12, 0, 0)
    scan_fn = MagicMock(return_value={'rows': [], 'scanned': 0, 'exhausted': True})
    cursor_getter = MagicMock(return_value={'pending_verifications': []})
    cursor_advancer = MagicMock(return_value=True)

    result = selfheal_svc.run_selfheal_tick(
        now=now_naive,
        mode='off',
        scan_fn=scan_fn,
        cursor_getter=cursor_getter,
        cursor_advancer=cursor_advancer,
        wedge_runner=lambda **kwargs: {'wedged': 0},
    )
    assert result['scanned'] == 0
