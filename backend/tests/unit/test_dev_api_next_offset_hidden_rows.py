"""Regression: ``X-Omi-Next-Offset`` must step over hidden rows on Developer API offset pages.

``GET /v1/dev/user/conversations`` with ``include_transcript=true`` (or a folder
or starred filter) reads ``limit + 1`` stored rows at the server ``offset``.
Dream duplicates and legacy completed rule discards still match the indexed
``discarded == False`` filter, so the reader drops them in Python and reads past
them to fill the page. The next offset was ``offset + len(page)``, which counts
only visible rows while Firestore's offset counts stored rows: the next page
started too early and returned conversations the client already had.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Response

from dependencies import ApiKeyAuth
from routers import developer
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing

T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
RULE_DISCARD = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}


def _row(row_id: str, minutes: int, **extra) -> dict:
    created = T0 + timedelta(minutes=minutes)
    return {
        'id': row_id,
        'created_at': created,
        'started_at': created,
        'finished_at': created,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': row_id, 'overview': 'Synthetic', 'category': 'personal'},
        **extra,
    }


# Newest first, the order the list query reads them.
ROWS = [
    _row('c5', 50),
    _row('dup', 45, dream_duplicate_of='c5', dream_duplicate=True),
    _row('c4', 40),
    _row('c3', 30),
    _row('rule', 25, relevance_decision=RULE_DISCARD),
    _row('c2', 20),
    _row('c1', 10),
]


@pytest.fixture(autouse=True)
def listing(monkeypatch):
    _install_listing(monkeypatch, {row['id']: row for row in ROWS})
    monkeypatch.delenv('OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED', raising=False)
    monkeypatch.setattr(developer, 'check_conversation_transcript_read_limit', lambda *a, **k: None)
    monkeypatch.setattr(developer, 'populate_speaker_names', lambda *a: None)
    monkeypatch.setattr(developer, 'populate_folder_names', lambda *a: None)


def _page(offset: int):
    response = Response()
    page = developer.get_conversations(
        start_date=None,
        end_date=None,
        categories=None,
        limit=2,
        offset=offset,
        include_transcript=True,
        folder_id=None,
        starred=None,
        uid=ApiKeyAuth(uid='uid-next-offset', scopes=['conversations:read'], app_id='app', key_id='key'),
        request=None,
        response=response,
        cursor=None,
    )
    return [conversation.id for conversation in page], response.headers


def test_next_offset_skips_hidden_rows_so_pages_never_repeat():
    ids, headers = _page(0)
    assert ids == ['c5', 'c4']
    assert headers['X-Omi-Has-More'] == 'true'
    # c5, the Dream duplicate and c4 occupy stored offsets 0-2; the page ends before c3.
    assert headers['X-Omi-Next-Offset'] == '3'

    listed = list(ids)
    for _ in ROWS:
        if headers['X-Omi-Has-More'] != 'true':
            break
        ids, headers = _page(int(headers['X-Omi-Next-Offset']))
        listed += ids
    assert listed == ['c5', 'c4', 'c3', 'c2', 'c1']


def test_truncated_page_resumes_after_every_row_it_read(monkeypatch):
    # Allowance for the offset-1 skip plus two rows: the Dream duplicate and c4.
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '3')
    ids, headers = _page(1)
    assert ids == ['c4']
    assert headers['X-Omi-List-Truncated'] == 'true'
    assert headers['X-Omi-Has-More'] == 'true'
    assert headers['X-Omi-Next-Offset'] == '3'

    monkeypatch.delenv('OMI_LIST_READ_MAX_DOCUMENTS')
    assert _page(3)[0] == ['c3', 'c2']
