import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock
from fastapi import Response

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

if "deepgram" not in sys.modules:
    sys.modules["deepgram"] = MagicMock()

import database.conversations as conversations_db
from dependencies import ApiKeyAuth
import routers.developer as dev_router


class _Snapshot:
    update_time = None

    def __init__(self, row):
        self.id = row['id']
        self._row = row

    def to_dict(self):
        return dict(self._row)


class _Query:
    def __init__(self, rows, filters=(), limit=None, offset=0, after_id=None):
        self._rows = rows
        self._filters = filters
        self._limit = limit
        self._offset = offset
        self._after_id = after_id

    def where(self, *, filter):
        return _Query(
            self._rows,
            filters=self._filters + ((filter.field_path, filter.value),),
            limit=self._limit,
            offset=self._offset,
            after_id=self._after_id,
        )

    def order_by(self, field_path, direction=None):
        return self

    def limit(self, count):
        return _Query(
            self._rows,
            filters=self._filters,
            limit=count,
            offset=self._offset,
            after_id=self._after_id,
        )

    def offset(self, num):
        return _Query(
            self._rows,
            filters=self._filters,
            limit=self._limit,
            offset=num,
            after_id=self._after_id,
        )

    def start_after(self, doc):
        doc_id = doc.id if hasattr(doc, 'id') else doc
        return _Query(
            self._rows,
            filters=self._filters,
            limit=self._limit,
            offset=0,
            after_id=doc_id,
        )

    def stream(self):
        filtered = [
            row for row in self._rows
            if all(row.get(f) == val for f, val in self._filters)
        ]
        if self._after_id is not None:
            idx = next((i for i, r in enumerate(filtered) if r['id'] == self._after_id), -1)
            filtered = filtered[idx + 1:] if idx != -1 else []
        filtered = filtered[self._offset:]
        if self._limit is not None:
            filtered = filtered[:self._limit]
        return iter([_Snapshot(r) for r in filtered])


class _MockCollection:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        return self

    def document(self, doc_id=None):
        return self

    def where(self, *, filter):
        return _Query(self.rows).where(filter=filter)

    def order_by(self, field_path, direction=None):
        return _Query(self.rows).order_by(field_path, direction)


def _make_row(conv_id, **extra):
    row = {
        'id': conv_id,
        'discarded': False,
        'status': 'completed',
        'structured': {
            'title': f'Title {conv_id}',
            'overview': 'Overview',
            'category': 'personal',
            'action_items': [],
            'events': [],
        },
        'transcript_segments': [],
        'started_at': datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc),
        'created_at': datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc),
        'is_locked': False,
    }
    row.update(extra)
    return row


def _read_auth(uid='test-uid'):
    return ApiKeyAuth(
        uid=uid,
        scopes=['conversations:read'],
        app_id='test-app',
        key_id='test-key',
    )


def test_collect_visible_conversation_page_assigns_next_offset_past_hidden_rows():
    """_collect_visible_conversation_page records next_offset_by_id in cursor_page matching the stored doc position."""
    rows = [
        _make_row('c5'),
        _make_row('c5_dup', dream_duplicate_of='c5'),  # hidden: dream duplicate
        _make_row('c4'),
        _make_row('c3'),
        _make_row('c2'),
        _make_row('c1'),
    ]
    query = _Query(rows)
    cursor_page = {}

    page = conversations_db._collect_visible_conversation_page(
        query, limit=3, offset=0, include_discarded=False, cursor_page=cursor_page
    )
    ids = [c['id'] for c in page]
    assert ids == ['c5', 'c4', 'c3']

    # c5 was stored row 0 -> consumed 1 stored row -> next offset 1
    assert cursor_page['next_offset_by_id']['c5'] == 1
    # c4 was stored row 2 (past c5_dup at stored row 1) -> consumed 3 stored rows -> next offset 3
    assert cursor_page['next_offset_by_id']['c4'] == 3
    # c3 was stored row 3 -> consumed 4 stored rows -> next offset 4
    assert cursor_page['next_offset_by_id']['c3'] == 4

    # Ensure conversation dicts themselves are NOT mutated/polluted
    assert '_next_offset' not in page[0]



def test_dev_get_conversations_reproduction_issue_22421(monkeypatch):
    """Reproduction of issue #22421:
    1. An account whose newest stored conversations are: c5, Dream duplicate of c5, c4, c3, c2, c1.
    2. GET /v1/dev/user/conversations?include_transcript=true&limit=2 returns c5, c4 with X-Omi-Next-Offset: 3.
    3. GET /v1/dev/user/conversations?include_transcript=true&limit=2&offset=3 returns c3, c2 with X-Omi-Next-Offset: 5.
    4. GET /v1/dev/user/conversations?include_transcript=true&limit=2&offset=5 returns c1 with no next offset.
    5. c4 is NOT listed twice, and all 5 visible conversations are retrieved.
    """
    rows = [
        _make_row('c5'),
        _make_row('c5_dup', dream_duplicate_of='c5'),
        _make_row('c4'),
        _make_row('c3'),
        _make_row('c2'),
        _make_row('c1'),
    ]

    mock_db = _MockCollection(rows)
    monkeypatch.setattr(conversations_db, 'db', mock_db)
    monkeypatch.setattr(dev_router, 'populate_speaker_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'populate_folder_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'check_conversation_transcript_read_limit', lambda auth, request=None: None)

    auth = _read_auth('test-uid')

    # Page 1
    resp1 = Response()
    page1 = dev_router.get_conversations(
        uid=auth,
        include_transcript=True,
        limit=2,
        offset=0,
        folder_id=None,
        starred=None,
        response=resp1,
    )
    ids1 = [c.id for c in page1]
    assert ids1 == ['c5', 'c4']
    assert resp1.headers.get('X-Omi-Has-More') == 'true'
    assert resp1.headers.get('X-Omi-Next-Offset') == '3'  # Resumes after c4 at stored row 2

    # Page 2
    resp2 = Response()
    page2 = dev_router.get_conversations(
        uid=auth,
        include_transcript=True,
        limit=2,
        offset=int(resp1.headers['X-Omi-Next-Offset']),
        folder_id=None,
        starred=None,
        response=resp2,
    )
    ids2 = [c.id for c in page2]
    assert ids2 == ['c3', 'c2']
    assert 'c4' not in ids2
    assert resp2.headers.get('X-Omi-Has-More') == 'true'
    assert resp2.headers.get('X-Omi-Next-Offset') == '5'

    # Page 3
    resp3 = Response()
    page3 = dev_router.get_conversations(
        uid=auth,
        include_transcript=True,
        limit=2,
        offset=int(resp2.headers['X-Omi-Next-Offset']),
        folder_id=None,
        starred=None,
        response=resp3,
    )
    ids3 = [c.id for c in page3]
    assert ids3 == ['c1']
    assert resp3.headers.get('X-Omi-Has-More') == 'false'
    assert 'X-Omi-Next-Offset' not in resp3.headers

    # Total set of conversations returned across all pages
    all_returned = ids1 + ids2 + ids3
    assert all_returned == ['c5', 'c4', 'c3', 'c2', 'c1']
    assert len(all_returned) == len(set(all_returned))


def test_dev_get_conversations_folder_filter_hidden_rows(monkeypatch):
    """Paging with folder_id past soft-deleted or rule-discarded rows advances next_offset accurately."""
    rule_discard = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}
    rows = [
        _make_row('c4', folder_id='folder-a'),
        _make_row('c3_del', folder_id='folder-a', deleted=True),  # soft deleted
        _make_row('c2_disc', folder_id='folder-a', relevance_decision=rule_discard),  # rule discard
        _make_row('c1', folder_id='folder-a'),
    ]

    mock_db = _MockCollection(rows)
    monkeypatch.setattr(conversations_db, 'db', mock_db)
    monkeypatch.setattr(dev_router, 'populate_speaker_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'populate_folder_names', lambda uid, convs: None)

    auth = _read_auth('test-uid')

    # Page 1 (limit 1)
    resp1 = Response()
    page1 = dev_router.get_conversations(
        uid=auth,
        folder_id='folder-a',
        limit=1,
        offset=0,
        response=resp1,
    )
    assert [c.id for c in page1] == ['c4']
    assert resp1.headers.get('X-Omi-Has-More') == 'true'
    # Next offset must be 1 (after c4 at stored row 0)
    assert resp1.headers.get('X-Omi-Next-Offset') == '1'

    # Page 2 (limit 1, starting at offset 1)
    resp2 = Response()
    page2 = dev_router.get_conversations(
        uid=auth,
        folder_id='folder-a',
        limit=1,
        offset=1,
        response=resp2,
    )
    # Stored rows 1 and 2 were hidden; c1 is the next visible row
    assert [c.id for c in page2] == ['c1']
    assert resp2.headers.get('X-Omi-Has-More') == 'false'
    assert 'X-Omi-Next-Offset' not in resp2.headers


def test_dev_get_conversations_starred_filter_hidden_rows(monkeypatch):
    """Paging with starred=True past dream duplicates advances next_offset accurately."""
    rows = [
        _make_row('c3', starred=True),
        _make_row('c2_dup', starred=True, dream_duplicate_of='c3'),
        _make_row('c1', starred=True),
    ]

    mock_db = _MockCollection(rows)
    monkeypatch.setattr(conversations_db, 'db', mock_db)
    monkeypatch.setattr(dev_router, 'populate_speaker_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'populate_folder_names', lambda uid, convs: None)

    auth = _read_auth('test-uid')

    resp1 = Response()
    page1 = dev_router.get_conversations(
        uid=auth,
        starred=True,
        folder_id=None,
        limit=1,
        offset=0,
        response=resp1,
    )
    assert [c.id for c in page1] == ['c3']
    assert resp1.headers.get('X-Omi-Has-More') == 'true'
    assert resp1.headers.get('X-Omi-Next-Offset') == '1'

    resp2 = Response()
    page2 = dev_router.get_conversations(
        uid=auth,
        starred=True,
        folder_id=None,
        limit=1,
        offset=1,
        response=resp2,
    )
    assert [c.id for c in page2] == ['c1']
    assert resp2.headers.get('X-Omi-Has-More') == 'false'
    assert 'X-Omi-Next-Offset' not in resp2.headers


def test_clean_collection_without_hidden_rows(monkeypatch):
    """Without hidden rows, X-Omi-Next-Offset advances normally by limit."""
    rows = [
        _make_row('c3'),
        _make_row('c2'),
        _make_row('c1'),
    ]

    mock_db = _MockCollection(rows)
    monkeypatch.setattr(conversations_db, 'db', mock_db)
    monkeypatch.setattr(dev_router, 'populate_speaker_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'populate_folder_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'check_conversation_transcript_read_limit', lambda auth, request=None: None)

    auth = _read_auth('test-uid')

    resp = Response()
    page = dev_router.get_conversations(
        uid=auth,
        include_transcript=True,
        limit=2,
        offset=0,
        folder_id=None,
        starred=None,
        response=resp,
    )
    assert [c.id for c in page] == ['c3', 'c2']
    assert resp.headers.get('X-Omi-Next-Offset') == '2'


def test_internal_next_offset_key_not_leaked_in_response(monkeypatch):
    """The internal _next_offset key is removed from all returned conversation models and dicts."""
    rows = [
        _make_row('c2'),
        _make_row('c1_dup', dream_duplicate_of='c2'),
        _make_row('c1'),
    ]

    mock_db = _MockCollection(rows)
    monkeypatch.setattr(conversations_db, 'db', mock_db)
    monkeypatch.setattr(dev_router, 'populate_speaker_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'populate_folder_names', lambda uid, convs: None)
    monkeypatch.setattr(dev_router, 'check_conversation_transcript_read_limit', lambda auth, request=None: None)

    auth = _read_auth('test-uid')
    resp = Response()
    page = dev_router.get_conversations(
        uid=auth,
        include_transcript=True,
        limit=2,
        offset=0,
        folder_id=None,
        starred=None,
        response=resp,
    )
    assert len(page) == 2
    for conv in page:
        conv_dict = conv.model_dump()
        assert '_next_offset' not in conv_dict
        assert not hasattr(conv, '_next_offset')
