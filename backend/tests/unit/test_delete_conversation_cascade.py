"""Regression: deleting a conversation must purge every subcollection under it.

``delete_conversation`` used to purge only the ``photos`` subcollection. A conversation owns more
children — per-provider post-processing transcripts (``deepgram_streaming``, ``fal_whisperx``, ...),
Hume emotion predictions, and the ``analytics_markers`` marker. Migrated to the WP2 storage port,
``delete_conversation`` is now ``store.delete_recursive(path)``, which removes the document and every
descendant; this test injects a FakeDocumentStore and asserts nothing survives under the deleted
conversation.
"""

import os

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from database import conversations as conversations_db
from tests.store_fakes import FakeDocumentStore

CONV = 'users/uid-1/conversations/conv-1'


@pytest.fixture
def store(monkeypatch) -> FakeDocumentStore:
    fake = FakeDocumentStore()
    monkeypatch.setattr(conversations_db, '_store', lambda: fake)
    return fake


def _seed(store: FakeDocumentStore) -> None:
    store.set(CONV, {'id': 'conv-1'})
    store.set(f'{CONV}/photos/photo-1', {'x': 1})
    store.set(f'{CONV}/deepgram_streaming/seg-1', {'x': 1})
    store.set(f'{CONV}/deepgram_streaming/seg-2', {'x': 1})
    store.set(f'{CONV}/fal_whisperx/seg-1', {'x': 1})
    store.set(f'{CONV}/analytics_markers/conversation_memories_extracted', {'x': 1})


def test_delete_conversation_purges_every_subcollection(store):
    _seed(store)
    conversations_db.delete_conversation('uid-1', 'conv-1')
    assert not store.exists(CONV)
    for sub in ('photos', 'deepgram_streaming', 'fal_whisperx', 'analytics_markers'):
        assert store.list_ids(f'{CONV}/{sub}') == []


def test_delete_conversation_descends_into_nested_subcollections(store):
    _seed(store)
    nested = f'{CONV}/photos/photo-1/ocr/line-1'
    store.set(nested, {'x': 1})
    conversations_db.delete_conversation('uid-1', 'conv-1')
    assert not store.exists(nested)  # a child's own children are purged too


def test_delete_conversation_without_children_still_deletes_the_document(store):
    store.set(CONV, {'id': 'conv-1'})
    conversations_db.delete_conversation('uid-1', 'conv-1')
    assert not store.exists(CONV)
