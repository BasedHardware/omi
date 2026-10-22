"""Unit tests for timestamp coercion and null/malformed member guards in capture_groups and duplicate_capture."""

from datetime import datetime, timedelta, timezone
import sys
from types import ModuleType
from unittest.mock import MagicMock

for _mod_name, _attrs in (
    ('database._client', {'get_firestore_client': MagicMock(), 'db': MagicMock()}),
    ('database.conversations', {'get_conversations_finished_after': MagicMock(), 'link_duplicate_capture': MagicMock(), 'get_conversation_for_capture_check': MagicMock()}),
    ('database.capture_speech', {'get_shared_speech_snapshot': MagicMock()}),
):
    if _mod_name not in sys.modules:
        _mod = ModuleType(_mod_name)
        for _k, _v in _attrs.items():
            setattr(_mod, _k, _v)
        sys.modules[_mod_name] = _mod

from database import capture_groups
from utils.conversations import duplicate_capture


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


def test_join_and_leave_capture_group_guard_null_and_malformed_members(monkeypatch):
    """join_capture_group and leave_capture_group must not raise TypeError/KeyError when existing members is None or contains malformed entries."""
    monkeypatch.setattr(capture_groups.firestore, 'transactional', lambda fn: fn)

    docs = {
        'c-1': {
            'status': 'completed',
            'discarded': False,
            'deleted': False,
            'source': 'desktop',
            'started_at': '2026-04-21T10:00:00Z',
            'finished_at': '2026-04-21T10:10:00Z',
            'capture_group': {'id': 'grp-existing', 'revision': 1, 'members': None},
        },
        'c-2': {
            'status': 'completed',
            'discarded': False,
            'deleted': False,
            'source': 'omi',
            'started_at': datetime(2026, 4, 21, 10, 1, 0),
            'finished_at': datetime(2026, 4, 21, 10, 9, 0, tzinfo=timezone.utc),
        },
    }

    client = MagicMock()
    tx = MagicMock()
    client.transaction.return_value = tx

    def get_doc(cid):
        doc_ref = MagicMock()
        snap = MagicMock()
        snap.to_dict.return_value = dict(docs[cid]) if cid in docs else None
        doc_ref.get.return_value = snap
        return doc_ref

    collection = MagicMock()
    collection.document.side_effect = get_doc
    client.collection.return_value.document.return_value.collection.return_value = collection

    group_id = capture_groups.join_capture_group(
        'uid-1',
        'c-1',
        'c-2',
        {'method': 'shared_speech'},
        firestore_client=client,
    )
    assert group_id == 'grp-existing'
    assert tx.update.call_count == 2

    # Now test leave_capture_group when group['members'] is explicitly None
    tx.reset_mock()
    left = capture_groups.leave_capture_group('uid-1', 'c-1', sticky=True, firestore_client=client)
    assert left is True
    assert tx.update.call_count == 1


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
    assert rec.duration_seconds == 240.0
