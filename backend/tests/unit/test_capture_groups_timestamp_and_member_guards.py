import os
import pytest
from datetime import datetime, timezone, timedelta

# Ensure ENCRYPTION_SECRET is set for any module transitively importing encryption
os.environ.setdefault('ENCRYPTION_SECRET', '01234567890123456789012345678901')

from database import capture_groups
from utils.conversations import duplicate_capture
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def test_aware_and_record_normalize_naive_aware_and_iso_timestamps():
    """_aware(), _primary_rank(), and _record() should normalize naive datetimes, non-UTC offsets, and ISO-8601 strings."""
    iso_start = '2026-04-21T10:00:00Z'
    naive_finish = datetime(2026, 4, 21, 10, 5, 0)
    plus_two = timezone(timedelta(hours=2))
    offset_start = datetime(2026, 4, 21, 12, 1, 0, tzinfo=plus_two)  # 10:01:00 UTC

    assert capture_groups._aware(iso_start) == datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    assert capture_groups._aware(naive_finish) == datetime(2026, 4, 21, 10, 5, 0, tzinfo=timezone.utc)
    assert capture_groups._aware(offset_start) == datetime(2026, 4, 21, 10, 1, 0, tzinfo=timezone.utc)

    members = [
        {
            'id': 'c-short',
            'source': 'phone',
            'started_at': offset_start,
            'finished_at': '2026-04-21T10:03:00Z',  # 120s
        },
        {
            'id': 'c-long',
            'source': 'desktop',
            'started_at': datetime(2026, 4, 21, 10, 0, 0),  # naive datetime
            'finished_at': datetime(2026, 4, 21, 10, 5, 0, tzinfo=timezone.utc),  # 300s
        },
    ]
    rec = capture_groups._record('grp-1', members, revision=2)
    assert rec['primary_id'] == 'c-long'
    assert rec['members'][0]['id'] == 'c-long'
    assert rec['members'][1]['id'] == 'c-short'


def test_record_ordering_handles_members_with_missing_id():
    """_record() ordering and _primary_rank() handle member dicts missing or having None 'id'."""
    members = [
        {
            'id': None,
            'source': 'desktop',
            'started_at': '2026-04-21T10:00:00Z',
            'finished_at': '2026-04-21T10:05:00Z',
        },
        {
            'id': 'c-valid',
            'source': 'phone',
            'started_at': '2026-04-21T10:01:00Z',
            'finished_at': '2026-04-21T10:04:00Z',
        },
    ]
    rec = capture_groups._record('grp-2', members, revision=1)
    assert len(rec['members']) == 2
    assert rec['members'][0]['id'] is None
    assert rec['members'][1]['id'] == 'c-valid'


def test_join_and_leave_capture_group_guard_null_and_malformed_members():
    """join_capture_group and leave_capture_group must not raise TypeError/KeyError when existing members is None or contains malformed entries."""
    store = StrictFirestore()
    uid = 'uid-1'
    c1_path = ('users', uid, 'conversations', 'c-1')
    c2_path = ('users', uid, 'conversations', 'c-2')

    store.rows[c1_path] = {
        'id': 'c-1',
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'desktop',
        'started_at': '2026-04-21T10:00:00Z',
        'finished_at': '2026-04-21T10:10:00Z',
        'capture_group': {'id': 'grp-existing', 'revision': 1, 'members': None},
    }
    store.rows[c2_path] = {
        'id': 'c-2',
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'started_at': datetime(2026, 4, 21, 10, 1, 0),
        'finished_at': datetime(2026, 4, 21, 10, 9, 0, tzinfo=timezone.utc),
    }

    gid = capture_groups.join_capture_group(
        uid, 'c-1', 'c-2', evidence={'reason': 'test'}, firestore_client=store
    )
    assert gid == 'grp-existing'
    row1 = store.rows[c1_path]
    grp1 = row1.get('capture_group')
    assert grp1['revision'] == 2
    assert len(grp1['members']) == 2

    # Now leave capture group
    res = capture_groups.leave_capture_group(
        uid, 'c-1', sticky=False, firestore_client=store
    )
    assert res is True


def test_duplicate_capture_record_normalizes_iso_and_aware_timestamps():
    """capture_record() parses ISO-8601 strings and normalizes offsets to UTC."""
    raw = {
        'id': 'c-iso',
        'status': 'completed',
        'discarded': False,
        'source': 'desktop',
        'started_at': '2026-04-21T10:00:00Z',
        'finished_at': '2026-04-21T10:10:00Z',
    }
    rec = duplicate_capture.capture_record(raw)
    assert rec is not None
    assert rec.conversation_id == 'c-iso'
    assert rec.started_at == datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    assert rec.finished_at == datetime(2026, 4, 21, 10, 10, 0, tzinfo=timezone.utc)
    assert rec.duration_seconds == 600.0

    # Inverted window or malformed ISO returns None safely
    bad = {**raw, 'started_at': 'not-a-datetime'}
    assert duplicate_capture.capture_record(bad) is None
