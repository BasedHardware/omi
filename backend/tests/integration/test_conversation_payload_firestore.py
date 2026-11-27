"""Run with a local Firestore emulator and synthetic rows."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from google.api_core.exceptions import AlreadyExists
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.conversation_payload import (
    MAX_ATOMIC_CHUNKS,
    PAYLOAD_CHUNKS,
    get_conversation_with_payload,
    read_conversation_payload,
    stage_conversation_payload,
    stage_conversation_payload_patch,
    read_payload_children_for_delete,
)
from database.home_feed_fields import COMMIT_STAMPED_FIELDS
from utils.conversation_payload import (
    CHUNK_BYTES,
    PAYLOAD_FIELD,
    ConversationProjectionTooLarge,
    InvalidConversationPayload,
)
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

pytestmark = pytest.mark.skipif(not os.getenv('FIRESTORE_EMULATOR_HOST'), reason='local Firestore emulator required')
SPILL_FIELDS = {'transcript_segments'}


@pytest.fixture
def conversation():
    assert os.environ['FIRESTORE_EMULATOR_HOST'].startswith(('127.0.0.1:', 'localhost:'))
    client = firestore.Client(project='demo-conversation-payload', credentials=AnonymousCredentials())
    ref = client.collection('users').document(uuid4().hex).collection('conversations').document('synthetic')
    try:
        yield client, ref
    finally:
        for chunk in ref.collection(PAYLOAD_CHUNKS).list_documents():
            chunk.delete()
        ref.delete()
        client.close()


def publish(client, ref, mutate, *, allow_promotion=False):
    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        current = read_conversation_payload(client, transaction, snapshot)
        stage_conversation_payload(
            transaction, snapshot, mutate(current), spill_fields=SPILL_FIELDS, allow_promotion=allow_promotion
        )

    commit(client.transaction())


def read(client, ref):
    row, _ = get_conversation_with_payload(client, ref)
    return {key: value for key, value in row.items() if key not in COMMIT_STAMPED_FIELDS} if row is not None else None


@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_publication_and_readback_at_firestore_boundary(conversation, delta):
    client, ref = conversation
    row = {'status': 'processing', 'transcript_segments': b''}
    base = estimate_firestore_document_bytes(row, ref.path)
    row['transcript_segments'] = b'x' * (FIRESTORE_MAX_DOCUMENT_BYTES - base + delta)

    publish(client, ref, lambda _: row, allow_promotion=True)

    projection = ref.get().to_dict()
    assert estimate_firestore_document_bytes(projection, ref.path) < FIRESTORE_MAX_DOCUMENT_BYTES
    assert projection['status'] == 'processing'
    assert PAYLOAD_FIELD in projection
    assert read(client, ref) == row


def test_switch_off_preserves_legacy_rows_and_allows_spilled_updates(conversation):
    client, ref = conversation
    inline = {'status': 'processing', 'transcript_segments': b'bytes'}
    ref.set(inline)
    stored_inline = ref.get().to_dict()
    assert read(client, ref) == inline
    large = {**inline, 'transcript_segments': b'x' * FIRESTORE_MAX_DOCUMENT_BYTES}
    with pytest.raises(ConversationProjectionTooLarge, match='promotion is disabled'):
        publish(client, ref, lambda _: large)
    assert ref.get().to_dict() == stored_inline
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())

    publish(client, ref, lambda _: large, allow_promotion=True)
    first_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    assert first_chunks
    notes = {'overview': 'synthetic notes'}
    pending_since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    publish(client, ref, lambda row: {**row, 'structured': notes, 'pending_since': pending_since})

    assert read(client, ref) == {**large, 'structured': notes, 'pending_since': pending_since}
    current_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    assert len(current_chunks) == len(first_chunks)
    assert not (first_chunks & current_chunks)


def test_notes_with_new_category_return_to_the_indexed_parent(conversation):
    client, ref = conversation
    row = {'transcript_segments': b'x' * FIRESTORE_MAX_DOCUMENT_BYTES, 'structured': {'overview': 'Synthetic'}}

    @firestore.transactional
    def seed(tx):
        stage_conversation_payload(
            tx, ref.get(transaction=tx), row, spill_fields={'transcript_segments', 'structured'}, allow_promotion=True
        )

    seed(client.transaction())
    assert 'structured' not in ref.get().to_dict()
    notes = {**row['structured'], 'category': 'work'}

    @firestore.transactional
    def update(tx):
        snapshot = ref.get(transaction=tx)
        hydrated = read_conversation_payload(client, tx, snapshot)
        stage_conversation_payload_patch(tx, snapshot, hydrated, {'structured': notes}, overflow_fields={'structured'})

    update(client.transaction())

    assert ref.get().to_dict()['structured'] == notes
    matches = ref.parent.where(filter=FieldFilter('structured.category', '==', 'work')).stream()
    assert [snapshot.id for snapshot in matches] == [ref.id]
    assert read(client, ref) == {**row, 'structured': notes}


def test_failed_fence_commit_keeps_previous_generation(conversation):
    client, ref = conversation
    row = {'transcript_segments': b'x' * FIRESTORE_MAX_DOCUMENT_BYTES}
    publish(client, ref, lambda _: row, allow_promotion=True)
    original = ref.get().to_dict()
    chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    fence = ref.collection('test_markers').document('existing')
    fence.create({'exists': True})

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        stage_conversation_payload(transaction, snapshot, {**row, 'status': 'completed'}, spill_fields=SPILL_FIELDS)
        transaction.create(fence, {'exists': True})

    try:
        with pytest.raises(AlreadyExists):
            commit(client.transaction())
    finally:
        fence.delete()
    assert ref.get().to_dict() == original
    assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == chunks
    assert read(client, ref) == row


def test_missing_chunk_fails_read_and_corrupt_descriptor_does_not_block_erase(conversation):
    client, ref = conversation
    row = {'transcript_segments': b'x' * FIRESTORE_MAX_DOCUMENT_BYTES}
    publish(client, ref, lambda _: row, allow_promotion=True)
    next(iter(ref.collection(PAYLOAD_CHUNKS).list_documents())).delete()
    with pytest.raises(InvalidConversationPayload):
        read(client, ref)
    ref.update({PAYLOAD_FIELD: 'malformed'})

    @firestore.transactional
    def erase(transaction):
        ref.get(transaction=transaction)
        children, _ = read_payload_children_for_delete(transaction, ref)
        for child in children:
            transaction.delete(child)
        transaction.delete(ref)

    erase(client.transaction())
    assert read(client, ref) is None
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())


def test_rejects_write_above_atomic_chunk_budget_without_partial_publication(conversation):
    client, ref = conversation
    row = {'transcript_segments': b'x' * (MAX_ATOMIC_CHUNKS * CHUNK_BYTES)}
    with pytest.raises(ConversationProjectionTooLarge, match='atomic chunk budget'):
        publish(client, ref, lambda _: row, allow_promotion=True)
    assert not ref.get().exists
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
