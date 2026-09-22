"""Visibility and recovery coverage for legacy sync review fragments."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def _review(**overrides):
    row = {
        'id': 'review',
        'created_at': datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        'status': 'completed',
        'discarded': False,
        'sync_relevance': 'review',
        'structured': {'title': 'Mm-hmm.', 'overview': '', 'sections': [], 'action_items': [], 'events': []},
    }
    row.update(overrides)
    return row


@pytest.fixture
def conversations_db(monkeypatch):
    from database import conversations

    rows = {
        'review-new': _review(id='review-new', created_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)),
        'kept-new': _review(
            id='kept-new',
            created_at=datetime(2026, 9, 22, 11, 59, tzinfo=timezone.utc),
            sync_relevance='keep',
            structured={
                'title': 'Lunch',
                'overview': 'A meaningful note',
                'sections': [],
                'action_items': [],
                'events': [],
            },
        ),
        'review-middle': _review(id='review-middle', created_at=datetime(2026, 9, 22, 11, 58, tzinfo=timezone.utc)),
        'kept-middle': _review(
            id='kept-middle',
            created_at=datetime(2026, 9, 22, 11, 57, tzinfo=timezone.utc),
            sync_relevance='keep',
            structured={
                'title': 'Walk',
                'overview': 'A meaningful note',
                'sections': [],
                'action_items': [],
                'events': [],
            },
        ),
        'review-old': _review(id='review-old', created_at=datetime(2026, 9, 22, 11, 56, tzinfo=timezone.utc)),
        'kept-old': _review(
            id='kept-old',
            created_at=datetime(2026, 9, 22, 11, 55, tzinfo=timezone.utc),
            sync_relevance='keep',
            structured={
                'title': 'Read',
                'overview': 'A meaningful note',
                'sections': [],
                'action_items': [],
                'events': [],
            },
        ),
    }
    _install_listing(monkeypatch, rows)
    return conversations


def test_low_signal_policy_protects_curated_and_enriched_rows():
    from utils.conversations.fragment_visibility import is_low_signal_sync_fragment

    assert is_low_signal_sync_fragment(_review())
    for protected in (
        {'status': 'processing'},
        {'sync_relevance': 'keep'},
        {'sync_live_target': True},
        {'has_photos': True},
        {'user_title': 'Keep this'},
        {'starred': True},
        {'folder_user_set': True},
        {'visibility': 'shared'},
        {'sync_relevance_user_kept': True},
        {'structured': {'overview': 'Generated summary'}},
    ):
        row = _review(**protected)
        assert not is_low_signal_sync_fragment(row), protected


def test_default_list_fills_pages_around_legacy_review_rows(conversations_db):
    page = conversations_db.get_conversations_without_photos('u', limit=2, offset=0)
    assert [row['id'] for row in page] == ['kept-new', 'kept-middle']
    next_page = conversations_db.get_conversations_without_photos('u', limit=2, offset=2)
    assert [row['id'] for row in next_page] == ['kept-old']

    archive = conversations_db.get_conversations_without_photos('u', limit=2, offset=0, include_discarded=True)
    assert [row['id'] for row in archive] == ['review-new', 'kept-new']
    assert archive[0]['discarded'] is True


def test_count_matches_default_list_and_archive(conversations_db):
    assert conversations_db.get_conversations_count('u') == 3
    assert conversations_db.get_conversations_count('u', include_discarded=True) == 6


def test_count_does_not_subtract_review_rows_missing_discarded_field(monkeypatch):
    from database import conversations

    missing = _review(id='missing')
    missing.pop('discarded')
    rows = {
        'missing': missing,
        'kept': _review(
            id='kept',
            sync_relevance='keep',
            structured={
                'title': 'Lunch',
                'overview': 'A note',
                'sections': [],
                'action_items': [],
                'events': [],
            },
        ),
    }
    _install_listing(monkeypatch, rows)
    assert conversations.get_conversations_count('u') == 1


def test_restore_promotes_legacy_review_and_persists_user_choice(monkeypatch):
    from database import conversations

    row = _review(id='restored')
    db = StrictFirestore({('users', 'u', 'conversations', 'restored'): row})
    monkeypatch.setattr(conversations, 'db', db)
    sync = MagicMock()
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', sync)

    assert conversations.restore_conversation_from_discarded('u', 'restored') is True
    assert db.rows[('users', 'u', 'conversations', 'restored')].get('discarded') is False
    assert db.rows[('users', 'u', 'conversations', 'restored')].get('sync_relevance') == 'keep'
    assert db.rows[('users', 'u', 'conversations', 'restored')].get('sync_relevance_user_kept') is True
    assert db.transactions[0].updates == [
        (
            ('users', 'u', 'conversations', 'restored'),
            {
                'discarded': False,
                'sync_relevance': 'keep',
                'sync_relevance_user_kept': True,
            },
        )
    ]
    sync.assert_called_once_with('u', 'restored')


def test_stale_processor_result_cannot_rehide_restored_review(monkeypatch):
    from database import conversations

    class _Snapshot:
        exists = True

        def to_dict(self):
            return {
                'id': 'restored',
                'status': 'completed',
                'discarded': False,
                'sync_relevance': 'keep',
                'sync_relevance_user_kept': True,
            }

    class _Ref:
        def __init__(self):
            self.written = None

        def get(self, transaction=None):
            return _Snapshot()

    class _Transaction:
        def set(self, ref, data, merge=False):
            ref.written = dict(data)

    ref = _Ref()
    transaction = _Transaction()
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    db.transaction.return_value = transaction
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *args: None)

    assert (
        conversations.persist_processing_result_with_lifecycle(
            'u',
            {
                'id': 'restored',
                'status': 'completed',
                'discarded': True,
                'sync_relevance': 'review',
                'data_protection_level': 'standard',
            },
        )
        is True
    )
    assert ref.written['discarded'] is False
    assert ref.written['sync_relevance'] == 'keep'
    assert ref.written['sync_relevance_user_kept'] is True


def test_explicit_discard_clears_restore_marker(monkeypatch):
    from database import conversations

    ref = MagicMock()
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *args: None)

    conversations.set_conversation_as_discarded('u', 'restored')

    ref.update.assert_called_once_with({'discarded': True, 'sync_relevance_user_kept': False})


def test_typesense_projection_hides_legacy_review_without_changing_schema():
    from utils.conversations.typesense_index import build_conversation_index_document

    document = build_conversation_index_document(
        'u',
        {
            'id': 'review',
            'created_at': datetime(2026, 9, 22, tzinfo=timezone.utc),
            'status': 'completed',
            'discarded': False,
            'sync_relevance': 'review',
            'structured': {'title': 'Mm-hmm.', 'overview': ''},
        },
    )
    assert document is not None
    assert document['discarded'] is True
