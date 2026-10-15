"""GET /v1/advice must skip a malformed stored advice row, not 500 the whole feed.

``database.advice.get_advice`` used to return raw Firestore dicts (only the doc id
injected) into the router's ``response_model=list[Advice]``. ``Advice`` requires
``content``/``category``/``created_at``/``updated_at``, so one legacy or corrupted
document made FastAPI raise ``ResponseValidationError`` — HTTP 500 — for the user's
entire advice feed. The fix parses rows through the shared read boundary
(``database.read_boundary.parse_snapshots``), the canonical prevention for
FC-malformed-doc-read, and drops malformed rows; ``update_advice``'s re-read uses
the same boundary so a poisoned row surfaces as "not found" instead of a 500.

Dropping rows must not skew pagination either: Firestore applies its own
offset/limit to raw documents before the parser runs, so ``get_advice`` streams
raw pages behind a ``start_after`` cursor and fills each request from VALID rows
(skip ``offset`` valid rows, return up to ``limit`` valid rows). The document id
is also made authoritative over any stored ``id`` — clients address advice by
that id on PATCH/DELETE, so a corrupt-but-string stored id must not survive.

Test isolation: the module imports cleanly (the Firestore client is lazy), so the
tests monkeypatch ``database.advice.db`` with a MagicMock query chain and feed
fake snapshots — plain objects exposing ``exists``/``id``/``to_dict``/
``reference.path``, exactly what the read boundary consumes. No network, no
services.
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import database.read_boundary as read_boundary
import pytest
from database import advice as advice_db


@pytest.fixture(autouse=True)
def _stub_fallback_recorder(monkeypatch):
    """Telemetry is not under test; keep the drop path from importing utils."""
    monkeypatch.setattr(read_boundary, '_fallback_recorder', lambda **kwargs: None)


def _snapshot(doc_id, payload, exists=True):
    return SimpleNamespace(
        exists=exists,
        id=doc_id,
        to_dict=lambda: payload,
        reference=SimpleNamespace(path=f'users/u1/advice/{doc_id}'),
    )


def _valid_payload(advice_id=None, **overrides):
    payload = {
        'content': 'Review your weekly focus report',
        'category': 'focus',
        'confidence': 0.8,
        'created_at': datetime(2026, 9, 30, tzinfo=timezone.utc),
        'updated_at': datetime(2026, 9, 30, tzinfo=timezone.utc),
        'is_read': False,
        'is_dismissed': False,
    }
    if advice_id:
        payload['id'] = advice_id
    payload.update(overrides)
    return payload


def _fake_db():
    """A MagicMock standing in for the lazy Firestore client module attribute.

    Must REPLACE ``database.advice.db`` (never mutate the lazy proxy) — touching
    the real proxy's attributes constructs real Google credentials.
    """
    return MagicMock()


def _wire_query(monkeypatch, *pages):
    """Make db.collection(...)...stream() yield one raw page per call.

    Each positional argument is one page (a list of fake snapshots); a stream
    call past the provided pages yields an empty page, matching an exhausted
    Firestore query.
    """
    page_queue = iter(pages)

    def _stream():
        try:
            return iter(next(page_queue))
        except StopIteration:
            return iter([])

    terminal = MagicMock()
    terminal.stream.side_effect = _stream
    for method in ('order_by', 'where', 'offset', 'limit', 'start_after'):
        getattr(terminal, method).return_value = terminal
    fake_db = _fake_db()
    # _user_col walks db.collection('users').document(uid).collection('advice').
    users_col = MagicMock()
    user_doc = MagicMock()
    advice_col = MagicMock()
    advice_col.order_by.return_value = terminal
    fake_db.collection.return_value = users_col
    users_col.document.return_value = user_doc
    user_doc.collection.return_value = advice_col
    monkeypatch.setattr(advice_db, 'db', fake_db)
    return terminal


def _wire_document(monkeypatch, snapshot):
    fake_db = _fake_db()
    users_col = MagicMock()
    user_doc = MagicMock()
    advice_col = MagicMock()
    advice_col.document.return_value.get.return_value = snapshot
    fake_db.collection.return_value = users_col
    users_col.document.return_value = user_doc
    user_doc.collection.return_value = advice_col
    monkeypatch.setattr(advice_db, 'db', fake_db)
    return advice_col


# ============================================================================
# get_advice — the poisoned feed
# ============================================================================


def test_get_advice_skips_malformed_row_and_keeps_valid_rows(monkeypatch):
    good = _snapshot('adv-good', _valid_payload())
    bad = _snapshot('adv-bad', {'id': 'adv-bad', 'category': 'focus'})  # missing content/created_at/updated_at
    _wire_query(monkeypatch, [bad, good])

    rows = advice_db.get_advice('u1')

    assert [r.id for r in rows] == ['adv-good']
    assert rows[0].content == 'Review your weekly focus report'


def test_get_advice_drops_row_missing_required_content(monkeypatch):
    _wire_query(monkeypatch, [_snapshot('adv-1', _valid_payload(content=None))])

    assert advice_db.get_advice('u1') == []


def test_get_advice_drops_row_missing_required_category(monkeypatch):
    _wire_query(monkeypatch, [_snapshot('adv-1', _valid_payload(category=None))])

    assert advice_db.get_advice('u1') == []


def test_get_advice_drops_row_with_missing_timestamps(monkeypatch):
    no_created = _snapshot('adv-1', _valid_payload(created_at=None))
    no_updated = _snapshot('adv-2', _valid_payload(updated_at=None))
    _wire_query(monkeypatch, [no_created, no_updated])

    assert advice_db.get_advice('u1') == []


def test_get_advice_drops_row_with_out_of_range_confidence(monkeypatch):
    too_high = _snapshot('adv-1', _valid_payload(confidence=1.5))
    wrong_type = _snapshot('adv-2', _valid_payload(confidence='high'))
    _wire_query(monkeypatch, [too_high, wrong_type])

    assert advice_db.get_advice('u1') == []


def test_get_advice_drops_non_mapping_payload(monkeypatch):
    good = _snapshot('adv-good', _valid_payload())
    garbage = _snapshot('adv-bad', 'not-a-dict')
    _wire_query(monkeypatch, [garbage, good])

    rows = advice_db.get_advice('u1')
    assert [r.id for r in rows] == ['adv-good']


def test_get_advice_injects_document_id_into_payload(monkeypatch):
    # Stored doc without an id field: the doc id must still populate Advice.id.
    _wire_query(monkeypatch, [_snapshot('doc-id-1', _valid_payload())])

    rows = advice_db.get_advice('u1')
    assert rows[0].id == 'doc-id-1'


def test_get_advice_overwrites_corrupt_stored_id_with_snapshot_id(monkeypatch):
    # A corrupt-but-string stored id must not survive parsing: clients address
    # advice by that id on PATCH/DELETE, so the snapshot id is authoritative.
    _wire_query(monkeypatch, [_snapshot('real-doc-id', _valid_payload(advice_id='forged-id'))])

    rows = advice_db.get_advice('u1')
    assert rows[0].id == 'real-doc-id'


def test_get_advice_all_valid_rows_survive_intact(monkeypatch):
    rows_in = [_snapshot(f'adv-{i}', _valid_payload()) for i in range(3)]
    _wire_query(monkeypatch, rows_in)

    rows = advice_db.get_advice('u1')
    assert [r.id for r in rows] == ['adv-0', 'adv-1', 'adv-2']
    assert rows[0].is_read is False
    assert rows[0].confidence == 0.8


def test_get_advice_keeps_streaming_until_limit_filled_across_raw_pages(monkeypatch):
    # A page of malformed rows must not end the response early: the cursor keeps
    # reading raw pages until `limit` valid rows are collected.
    page1 = [_snapshot('bad-1', {'id': 'bad-1'}), _snapshot('bad-2', {'id': 'bad-2'})]
    page2 = [_snapshot('good-1', _valid_payload())]
    terminal = _wire_query(monkeypatch, page1, page2)

    rows = advice_db.get_advice('u1', limit=1)

    assert [r.id for r in rows] == ['good-1']
    # Raw pagination advances by cursor, never by re-streaming from the top.
    terminal.start_after.assert_called_once_with(page1[-1])


def test_get_advice_offset_counts_valid_rows_not_raw_documents(monkeypatch):
    # `offset` skips VALID rows; a dropped raw document must not shift the window.
    bad = _snapshot('bad-1', {'id': 'bad-1'})
    _wire_query(
        monkeypatch,
        [bad, _snapshot('good-1', _valid_payload()), _snapshot('good-2', _valid_payload())],
    )

    rows = advice_db.get_advice('u1', offset=1, limit=5)
    assert [r.id for r in rows] == ['good-2']


def test_get_advice_streams_raw_pages_bounded_not_raw_offset(monkeypatch):
    # The raw query is paged, never offset: a raw offset before the parser would
    # re-introduce the short-page/hide-later-data bug the fill loop prevents.
    terminal = _wire_query(monkeypatch, [])

    advice_db.get_advice('u1', category='focus', limit=7, offset=3, include_dismissed=True)

    terminal.offset.assert_not_called()
    terminal.limit.assert_called_once_with(max(7, advice_db.RAW_ADVICE_STREAM_PAGE))


# ============================================================================
# update_advice — the PATCH path through the same boundary
# ============================================================================


def test_update_advice_returns_none_for_missing_document(monkeypatch):
    _wire_document(monkeypatch, _snapshot('adv-1', {}, exists=False))

    assert advice_db.update_advice('u1', 'adv-1', is_read=True) is None


def test_update_advice_returns_none_for_poisoned_document(monkeypatch):
    # Exists but missing required fields: PATCH must 404 upstream, not 500.
    _wire_document(monkeypatch, _snapshot('adv-1', {'id': 'adv-1'}))

    assert advice_db.update_advice('u1', 'adv-1', is_read=True) is None


def test_update_advice_returns_parsed_model_for_valid_document(monkeypatch):
    # Drive the two reads with side_effect: the existence read returns the
    # original (is_read=False) document, the post-update re-read returns the
    # updated one — so the test fails if update_advice ever skips its re-read.
    advice_col = _wire_document(monkeypatch, _snapshot('adv-1', _valid_payload(is_read=False)))
    advice_col.document.return_value.get.side_effect = [
        _snapshot('adv-1', _valid_payload(is_read=False)),
        _snapshot('adv-1', _valid_payload(is_read=True)),
    ]

    result = advice_db.update_advice('u1', 'adv-1', is_read=True)

    assert result is not None
    assert result.id == 'adv-1'
    assert result.is_read is True


def test_update_advice_re_read_makes_snapshot_id_authoritative(monkeypatch):
    # The PATCH response id comes from the re-read snapshot, not the stored field.
    advice_col = _wire_document(monkeypatch, _snapshot('real-doc-id', _valid_payload(advice_id='forged-id')))
    advice_col.document.return_value.get.side_effect = [
        _snapshot('real-doc-id', _valid_payload(advice_id='forged-id')),
        _snapshot('real-doc-id', _valid_payload(advice_id='forged-id')),
    ]

    result = advice_db.update_advice('u1', 'real-doc-id', is_read=True)

    assert result is not None
    assert result.id == 'real-doc-id'


# ============================================================================
# Structural guard
# ============================================================================


def test_advice_reads_go_through_the_shared_read_boundary():
    source = Path(advice_db.__file__).read_text(encoding='utf-8')
    assert 'parse_snapshots' in source
    assert 'parse_snapshot_or_none' in source
    # The raw-dict passthrough that caused the poison page must be gone.
    assert "data['id'] = doc.id" not in source
    # And pagination must fill from valid rows: a raw offset would apply before
    # the parser and let dropped rows short or empty a page.
    get_advice_body = source.split('def get_advice', 1)[1].split('def update_advice', 1)[0]
    assert '.offset(' not in get_advice_body
    assert 'start_after' in get_advice_body
