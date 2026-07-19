"""list_review_conflicts must not TypeError sorting items with mixed tz-aware / missing created_at.

_review_conflict_sort_key used a naive datetime.min sentinel for a missing created_at. Stored
created_at is tz-aware (datetime.now(timezone.utc)); on an impact tie the sort compares the two
datetimes -> "can't compare offset-naive and offset-aware datetimes" TypeError -> HTTP 500 on
GET /v3/memories/review-queue. The sentinel is now tz-aware. Pure sort-key function, tested directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timezone

import database.review_queue as review_queue


def test_sort_key_tolerates_missing_created_at_on_impact_tie():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = [
        {'impact': 0.5, 'created_at': aware},
        {'impact': 0.5},  # missing created_at -> sentinel; equal impact forces a datetime comparison
    ]
    # Before the fix, comparing the naive datetime.min sentinel with the aware value raised TypeError.
    items.sort(key=review_queue._review_conflict_sort_key, reverse=True)
    assert [i.get('created_at') for i in items] == [aware, None]  # real timestamp sorts ahead of the sentinel


def test_sort_key_orders_by_impact_then_created_at():
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 2, 1, tzinfo=timezone.utc)
    items = [
        {'impact': 0.2, 'created_at': newer},
        {'impact': 0.9, 'created_at': older},
        {'impact': 0.2, 'created_at': older},
    ]
    items.sort(key=review_queue._review_conflict_sort_key, reverse=True)
    assert [i['impact'] for i in items] == [0.9, 0.2, 0.2]  # highest impact first
    assert items[1]['created_at'] == newer and items[2]['created_at'] == older  # tie -> newer first
