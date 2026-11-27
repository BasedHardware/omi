from datetime import datetime, timezone

import pytest
from google.cloud.firestore_v1 import GeoPoint

from utils.conversation_payload import (
    CHUNK_BYTES,
    PAYLOAD_FIELD,
    PROJECTION_BYTES,
    ConversationProjectionTooLarge,
    InvalidConversationPayload,
    hydrate_conversation,
    pack_conversation,
)
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

PATH = 'users/synthetic/conversations/test'
GENERATION = '0' * 32


def pack(row):
    return pack_conversation(row, PATH, spill_fields={'transcript_segments', 'claims'}, generation=GENERATION)


@pytest.mark.parametrize('budget', [PROJECTION_BYTES, FIRESTORE_MAX_DOCUMENT_BYTES])
@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_boundaries(budget, delta):
    row = {'status': 'completed', 'transcript_segments': ''}
    base_bytes = estimate_firestore_document_bytes(row, PATH)
    row['transcript_segments'] = 'x' * (budget + delta - base_bytes)

    write = pack(row)

    assert estimate_firestore_document_bytes(row, PATH) == budget + delta
    assert bool(write.chunks) == (budget + delta > PROJECTION_BYTES)
    assert estimate_firestore_document_bytes(write.parent, PATH) <= PROJECTION_BYTES
    assert write.parent['status'] == 'completed'
    assert all(0 < len(chunk) <= CHUNK_BYTES for chunk in write.chunks)
    assert hydrate_conversation(write.parent, write.chunks) == row


def test_preserves_prepared_firestore_types_and_inline_query_fields():
    row = {
        'status': 'processing',
        'transcript_segments': b'\x00\xff' * (FIRESTORE_MAX_DOCUMENT_BYTES // 2),
        'claims': [
            {'end': 42, 'start': 0, 'label': '東京', 'locked': False, 'value': None},
            {'at': datetime(2026, 1, 1, tzinfo=timezone.utc), 'point': GeoPoint(1.25, -2.5)},
        ],
    }

    write = pack(row)

    assert write.parent.keys() == {'status', PAYLOAD_FIELD}
    decoded = hydrate_conversation(write.parent, write.chunks)
    assert decoded == row
    assert isinstance(decoded['claims'][0]['end'], int)
    assert decoded['claims'][0]['locked'] is False
    assert 'value' not in decoded['claims'][1]


def test_projection_cannot_drop_an_uncertified_field():
    with pytest.raises(ConversationProjectionTooLarge):
        pack({'status': 'x' * FIRESTORE_MAX_DOCUMENT_BYTES, 'transcript_segments': 'short'})


def test_rejects_spilling_the_indexed_conversation_category():
    row = {
        'structured': {'category': 'work', 'overview': 'x' * FIRESTORE_MAX_DOCUMENT_BYTES},
        'transcript_segments': 'short',
    }

    with pytest.raises(ConversationProjectionTooLarge, match='category must stay'):
        pack_conversation(row, PATH, spill_fields=row.keys(), generation=GENERATION)


def test_spills_speech_while_preserving_indexed_notes_inline():
    notes = {'title': 'Synthetic', 'category': 'work'}
    row = {'structured': notes, 'transcript_segments': 'x' * FIRESTORE_MAX_DOCUMENT_BYTES}

    write = pack_conversation(row, PATH, spill_fields=row.keys(), generation=GENERATION)

    assert write.parent['structured'] == notes
    assert 'transcript_segments' not in write.parent
    assert hydrate_conversation(write.parent, write.chunks) == row


def test_claim_growth_spills_the_final_row_and_preserves_its_pending_clock():
    row = {'transcript_segments': '', 'claims': [], 'status': 'processing'}
    row['transcript_segments'] = 'x' * (PROJECTION_BYTES - estimate_firestore_document_bytes(row, PATH))
    assert not pack(row).chunks

    pending_since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated = {**row, 'claims': [{'start': 0, 'end': 100}], 'pending_since': pending_since}
    write = pack(updated)

    assert write.chunks
    assert write.parent['pending_since'] == pending_since
    assert hydrate_conversation(write.parent, write.chunks) == updated
    assert pack(dict(reversed(list(updated.items())))).chunks == write.chunks


def test_inline_read_ignores_chunks():
    def unexpected_chunks():
        raise AssertionError('inline read requested a chunk')
        yield b''

    assert hydrate_conversation({'status': 'processing'}, unexpected_chunks()) == {'status': 'processing'}


@pytest.mark.parametrize('damage', ['missing', 'extra', 'reordered', 'corrupt', 'colliding', 'unsupported'])
def test_rejects_incomplete_or_conflicting_payload(damage):
    row = {'transcript_segments': b'a' * CHUNK_BYTES + b'b' * FIRESTORE_MAX_DOCUMENT_BYTES}
    write = pack(row)
    parent, chunks = write.parent, write.chunks
    if damage == 'missing':
        chunks = chunks[:-1]
    elif damage == 'extra':
        chunks = chunks + (b'extra',)
    elif damage == 'reordered':
        chunks = (chunks[1], chunks[0], *chunks[2:])
    elif damage == 'corrupt':
        chunks = (b'z' + chunks[0][1:], *chunks[1:])
    elif damage == 'colliding':
        parent['transcript_segments'] = 'stale inline value'
    elif damage == 'unsupported':
        parent[PAYLOAD_FIELD]['version'] += 1

    with pytest.raises(InvalidConversationPayload):
        hydrate_conversation(parent, chunks)
