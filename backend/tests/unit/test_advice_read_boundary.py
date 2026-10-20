"""#20277 — get_advice must not 500 on a malformed stored advice doc.

The fix routes reads through parse_snapshots(Advice, ..., document_id_field='id'):
a doc missing content or carrying an out-of-range confidence is dropped, not
surfaced as a ResponseValidationError that poisons the whole feed page.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import database.advice as advice_db


def _snap(doc_id, data):
    return SimpleNamespace(id=doc_id, exists=True, to_dict=lambda: data)


def _fake_db(docs):
    query = MagicMock()
    query.order_by.return_value = query
    query.where.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.stream.return_value = iter(docs)
    col = MagicMock()
    col.order_by.return_value = query
    user_ref = MagicMock()
    user_ref.collection.return_value = col
    db = MagicMock()
    db.collection.return_value.document.return_value = user_ref
    return db


def test_malformed_docs_are_dropped_not_fatal(monkeypatch):
    docs = [
        _snap(
            'a1',
            {
                'content': 'try a walk',
                'category': 'other',
                'created_at': '2026-10-14T00:00:00Z',
                'updated_at': '2026-10-14T00:00:00Z',
            },
        ),
        _snap(
            'a2', {'category': 'other', 'created_at': '2026-10-14T00:00:00Z', 'updated_at': '2026-10-14T00:00:00Z'}
        ),  # missing required content
        _snap(
            'a3',
            {
                'content': 'x',
                'category': 'other',
                'confidence': 5.0,
                'created_at': '2026-10-14T00:00:00Z',
                'updated_at': '2026-10-14T00:00:00Z',
            },
        ),  # out of range
        _snap(
            'a4',
            {
                'content': 'rest first',
                'category': 'focus',
                'created_at': '2026-10-14T00:00:00Z',
                'updated_at': '2026-10-14T00:00:00Z',
            },
        ),
    ]
    monkeypatch.setattr(advice_db, 'db', _fake_db(docs))
    out = advice_db.get_advice('u1')
    assert [a.id for a in out] == ['a1', 'a4']
    assert out[0].content == 'try a walk'


def test_all_poisoned_returns_empty_page(monkeypatch):
    monkeypatch.setattr(
        advice_db,
        'db',
        _fake_db(
            [
                _snap(
                    'a1',
                    {'category': 'other', 'created_at': '2026-10-14T00:00:00Z', 'updated_at': '2026-10-14T00:00:00Z'},
                )
            ]
        ),
    )
    assert advice_db.get_advice('u1') == []


def test_advice_type_returned(monkeypatch):
    from models.advice import Advice

    monkeypatch.setattr(
        advice_db,
        'db',
        _fake_db(
            [
                _snap(
                    'a9',
                    {
                        'content': 'hi',
                        'category': 'other',
                        'created_at': '2026-10-14T00:00:00Z',
                        'updated_at': '2026-10-14T00:00:00Z',
                    },
                )
            ]
        ),
    )
    out = advice_db.get_advice('u1')
    assert isinstance(out[0], Advice)
