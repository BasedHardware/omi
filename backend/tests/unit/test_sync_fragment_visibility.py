"""Visibility and recovery coverage for sync review fragments.

Readers trust the stored ``discarded`` flag alone: intake stores review
fragments hidden, and scripts/conversation_relevance_backfill.py rewrites rows
from before it did.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction


class _MergeCapableTransaction(StrictFirestoreTransaction):
    """Adds the ``set(..., merge=True)`` branch the strict fixture omits."""

    def __init__(self, database, *, allow_reads_after_writes=False):
        super().__init__(database, allow_reads_after_writes=allow_reads_after_writes)
        self.merges = []

    def set(self, ref, data, merge=False):
        if not merge:
            return super().set(ref, data)
        self._assert_reference_belongs(ref)
        self.has_written = True
        self.merges.append((ref.path, merge))
        payload = deepcopy(data)
        self.sets.append((ref.path, payload))
        self._database.rows.setdefault(ref.path, {}).update(payload)


class _MergeFirestore(StrictFirestore):
    def transaction(self):
        transaction = _MergeCapableTransaction(self, allow_reads_after_writes=self._allow_reads_after_writes)
        self.transactions.append(transaction)
        return transaction


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
        'review-new': _review(
            id='review-new', created_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc), discarded=True
        ),
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
        'review-middle': _review(
            id='review-middle', created_at=datetime(2026, 9, 22, 11, 58, tzinfo=timezone.utc), discarded=True
        ),
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
        'review-old': _review(
            id='review-old', created_at=datetime(2026, 9, 22, 11, 56, tzinfo=timezone.utc), discarded=True
        ),
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


def test_low_signal_policy_protects_only_curated_rows():
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
    ):
        row = _review(**protected)
        assert not is_low_signal_sync_fragment(row), protected
    # Generated output is not curation: the pipeline writes it for everything.
    for generated in (
        {'structured': {'overview': 'Generated summary'}},
        {'structured': {'sections': [{'heading': 'Context'}]}},
        {'client_processing': {'schema_version': 1}},
    ):
        assert is_low_signal_sync_fragment(_review(**generated)), generated


def test_default_list_pages_by_the_stored_flag(conversations_db):
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


def test_typesense_indexes_the_stored_flag_only():
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
    # A legacy row is visible until the backfill stamps it; no read-time projection.
    assert document is not None
    assert document['discarded'] is False


def test_restore_of_any_row_persists_the_user_choice(monkeypatch):
    """A model-discarded sync row is not ``review``; its restore must still stick."""
    from database import conversations

    row = _review(id='restored', sync_relevance='keep', discarded=True)
    db = StrictFirestore({('users', 'u', 'conversations', 'restored'): row})
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', MagicMock())

    assert conversations.restore_conversation_from_discarded('u', 'restored') is True
    assert db.transactions[0].updates == [
        (
            ('users', 'u', 'conversations', 'restored'),
            {'discarded': False, 'sync_relevance_user_kept': True},
        )
    ]


def test_restore_of_jev_discard_stamps_the_marker(monkeypatch):
    """A restored Jev discard records ``jev_discard_restored`` in the same transaction."""
    from database import conversations

    row = _review(
        id='restored',
        sync_relevance='keep',
        discarded=True,
        relevance_decision={
            'verdict': 'discard',
            'decided_by': 'jev',
            'reason': 'jev_discard',
            'trigger': 'sync_update',
            'rules_version': 3,
            'jev': {'p_discard': 0.97, 'threshold': 0.95, 'model': 'typesafe/jev-1.13'},
        },
    )
    db = StrictFirestore({('users', 'u', 'conversations', 'restored'): row})
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', MagicMock())

    assert conversations.restore_conversation_from_discarded('u', 'restored') is True
    assert db.transactions[0].updates == [
        (
            ('users', 'u', 'conversations', 'restored'),
            {
                'discarded': False,
                'sync_relevance_user_kept': True,
                'jev_discard_restored': True,
            },
        )
    ]
    assert db.rows[('users', 'u', 'conversations', 'restored')]['jev_discard_restored'] is True


@pytest.mark.parametrize(
    'relevance_decision',
    [
        pytest.param({'verdict': 'discard', 'decided_by': 'model', 'reason': 'model_discard'}, id='model-decision'),
        pytest.param({'verdict': 'discard', 'decided_by': 'rule', 'reason': 'too_short'}, id='rule-decision'),
        pytest.param({'verdict': 'keep', 'decided_by': 'jev', 'reason': 'jev_keep'}, id='jev-keep'),
        pytest.param('stale-non-mapping', id='non-mapping-decision'),
        pytest.param(None, id='legacy-row'),
    ],
)
def test_restore_of_non_jev_discard_writes_no_marker(monkeypatch, relevance_decision):
    """Only a currently discarded row carrying a Jev discard decision gets the marker."""
    from database import conversations

    row = _review(id='restored', sync_relevance='keep', discarded=True)
    if relevance_decision is not None:
        row['relevance_decision'] = relevance_decision
    db = StrictFirestore({('users', 'u', 'conversations', 'restored'): row})
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', MagicMock())

    assert conversations.restore_conversation_from_discarded('u', 'restored') is True
    (update,) = db.transactions[0].updates
    assert 'jev_discard_restored' not in update[1]
    assert 'jev_discard_restored' not in db.rows[('users', 'u', 'conversations', 'restored')]


def test_restored_jev_discard_survives_reassessment_persist(monkeypatch):
    """Restore stamps the marker; reassessment rewrites the decision, not the marker."""
    from types import SimpleNamespace

    from database import conversations
    from utils.conversations.processing_trigger import ProcessingTrigger
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.relevance_io import apply_relevance

    row = _review(
        id='restored',
        sync_relevance='keep',
        discarded=True,
        relevance_decision={'verdict': 'discard', 'decided_by': 'jev', 'reason': 'jev_discard'},
    )
    db = _MergeFirestore({('users', 'u', 'conversations', 'restored'): row})
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', MagicMock())

    assert conversations.restore_conversation_from_discarded('u', 'restored') is True

    decision = decide_relevance(
        trigger=ProcessingTrigger.SYNC_UPDATE,
        texts=['a real conversation'],
        speech_seconds=60.0,
        has_photos=False,
        user_kept=True,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=lambda: False,
    )
    conversation = SimpleNamespace(discarded=True)
    payload = {'id': 'restored', 'status': 'completed', 'data_protection_level': 'standard'}
    apply_relevance(conversation, payload, decision)
    assert 'jev_discard_restored' not in payload

    assert conversations.persist_processing_result_with_lifecycle('u', payload) is True

    assert db.transactions[-1].merges == [(('users', 'u', 'conversations', 'restored'), True)]
    stored = db.rows[('users', 'u', 'conversations', 'restored')]
    assert stored['relevance_decision']['decided_by'] == 'user'
    assert stored['relevance_decision']['verdict'] == 'keep'
    assert stored['discarded'] is False
    assert stored['jev_discard_restored'] is True
