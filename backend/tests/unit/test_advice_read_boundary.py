"""GET /v1/advice must skip a malformed stored advice row, not 500 the whole feed.

``database.advice.get_advice`` used to return raw Firestore dicts (only the doc id
injected) into the router's ``response_model=list[Advice]``. ``Advice`` requires
``content``/``category``/``created_at``/``updated_at``, so one legacy or corrupted
document made FastAPI raise ``ResponseValidationError`` — HTTP 500 — for the user's
entire advice feed. The fix parses rows through the shared read boundary
(``database.read_boundary.parse_snapshots``), the canonical prevention for
FC-malformed-doc-read, and drops malformed rows; ``update_advice``'s re-read uses
the same boundary so a poisoned row surfaces as "not found" instead of a 500.

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


def _wire_query(monkeypatch, snapshots):
    """Make db.collection(...)...stream() yield the given fake snapshots."""
    terminal = MagicMock()
    terminal.stream.return_value = iter(snapshots)
    for method in ('order_by', 'where', 'offset', 'limit'):
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


def test_get_advice_all_valid_rows_survive_intact(monkeypatch):
    rows_in = [_snapshot(f'adv-{i}', _valid_payload()) for i in range(3)]
    _wire_query(monkeypatch, rows_in)

    rows = advice_db.get_advice('u1')
    assert [r.id for r in rows] == ['adv-0', 'adv-1', 'adv-2']
    assert rows[0].is_read is False
    assert rows[0].confidence == 0.8


def test_get_advice_pagination_arguments_reach_the_query(monkeypatch):
    terminal = _wire_query(monkeypatch, [])

    advice_db.get_advice('u1', category='focus', limit=7, offset=3, include_dismissed=True)

    terminal.offset.assert_called_once_with(3)
    terminal.limit.assert_called_once_with(7)


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
    ref = _wire_document(monkeypatch, _snapshot('adv-1', _valid_payload(is_read=False))).document.return_value
    ref.get.return_value = _snapshot('adv-1', _valid_payload(is_read=True))

    result = advice_db.update_advice('u1', 'adv-1', is_read=True)

    assert result is not None
    assert result.id == 'adv-1'
    assert result.is_read is True


# ============================================================================
# Structural guard
# ============================================================================


def test_advice_reads_go_through_the_shared_read_boundary():
    source = Path(advice_db.__file__).read_text(encoding='utf-8')
    assert 'parse_snapshots' in source
    assert 'parse_snapshot_or_none' in source
    # The raw-dict passthrough that caused the poison page must be gone.
    assert "data['id'] = doc.id" not in source
