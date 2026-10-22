"""Unit tests for timestamp coercion and null/malformed member guards in capture_groups and duplicate_capture."""

from datetime import datetime, timedelta, timezone

import pytest

from database import capture_groups
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import duplicate_capture


@pytest.fixture
def store(monkeypatch):
    fake = StrictFirestore()
    monkeypatch.setattr(capture_groups, 'get_firestore_client', lambda: fake)
    return fake


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
    assert [m['id'] for m in rec['members']] == ['c-long', 'c-short']


def test_join_and_leave_capture_group_guard_null_and_malformed_members(store):
    """join_capture_group and leave_capture_group must not raise TypeError/KeyError when existing members is None or contains malformed entries."""
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

    group_id = capture_groups.join_capture_group(uid, 'c-1', 'c-2', {'method': 'shared_speech'})
    assert group_id == 'grp-existing'
    assert store.rows[c1_path]['capture_group']['primary_id'] == 'c-1'
    assert {m['id'] for m in store.rows[c1_path]['capture_group']['members']} == {'c-1', 'c-2'}
    assert store.rows[c2_path]['capture_group'] == store.rows[c1_path]['capture_group']

    # Now test leave_capture_group when group['members'] is explicitly None
    store.rows[c1_path]['capture_group'] = {'id': 'grp-existing', 'revision': 2, 'members': None}
    left = capture_groups.leave_capture_group(uid, 'c-1', sticky=True)
    assert left is True
    assert store.rows[c1_path]['capture_group'] is None
    assert store.rows[c1_path]['capture_group_exclusions'] == []


def test_duplicate_capture_record_accepts_iso_and_offset_timestamps():
    """duplicate_capture.capture_record() should parse ISO-8601 strings and normalize non-UTC datetimes to UTC."""
    rec = duplicate_capture.capture_record(
        {
            'id': 'conv-1',
            'status': 'completed',
            'discarded': False,
            'source': 'desktop',
            'started_at': '2026-04-21T10:00:00Z',
            'finished_at': '2026-04-21T10:04:00+00:00',
        }
    )
    assert rec is not None
    assert rec.started_at == datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    assert rec.finished_at == datetime(2026, 4, 21, 10, 4, 0, tzinfo=timezone.utc)
    assert rec.duration_seconds == 240.0
