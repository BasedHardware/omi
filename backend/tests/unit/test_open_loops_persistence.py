"""Open-loop persistence: encrypted write shape, server-only wire, read seam.

The extractions ride the same compressed/encrypted-at-rest protection as the
other derived per-conversation JSON blobs, and never appear on the client wire
model.
"""

import pytest

import database.conversations as db
from models.conversation import Conversation
from models.structured import Structured
from utils.conversations import llm_input_dedupe
from utils.open_loops.extraction import (
    OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD,
    OPEN_LOOP_EXTRACTIONS_FIELD,
)

_EXTRACTED = {
    'version': 1,
    'delegated_by_user': [
        {
            'who': 'Maya',
            'what': 'send the vendor write-up',
            'by_when': None,
            'evidence': 'I will send it over tomorrow',
            'work_related': True,
        }
    ],
    'commitments_by_others': [],
    'observed_issue_or_blocker': None,
}


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_write_shape_protects_the_extractions(level):
    encoded = db.encode_conversation_for_write('u', {OPEN_LOOP_EXTRACTIONS_FIELD: _EXTRACTED}, level)
    stored = encoded[OPEN_LOOP_EXTRACTIONS_FIELD]
    # Standard: compressed bytes; enhanced: encrypted string. Neither is a
    # plain JSON dict readable straight from Firestore.
    assert isinstance(stored, bytes if level == 'standard' else str)
    assert encoded[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] is True
    assert b'Maya' not in (stored if isinstance(stored, bytes) else stored.encode())

    decoded = db.get_open_loop_extractions('u', encoded)
    assert decoded == _EXTRACTED


def test_explicit_clear_writes_null_and_clears_the_marker():
    encoded = db.encode_conversation_for_write('u', {OPEN_LOOP_EXTRACTIONS_FIELD: None}, 'standard')
    assert encoded[OPEN_LOOP_EXTRACTIONS_FIELD] is None
    assert encoded[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] is None
    assert db.get_open_loop_extractions('u', encoded) is None


def test_non_object_value_is_rejected():
    with pytest.raises(ValueError):
        db.encode_conversation_for_write('u', {OPEN_LOOP_EXTRACTIONS_FIELD: ['nope']}, 'standard')


def test_read_helpers_fail_closed():
    assert db.get_open_loop_extractions('u', None) is None
    assert db.get_open_loop_extractions('u', {}) is None
    assert (
        db.get_open_loop_extractions(
            'u', {OPEN_LOOP_EXTRACTIONS_FIELD: 'garbage', OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD: True}
        )
        is None
    )


def test_conversation_wire_model_never_exposes_the_field():
    raw = {
        'id': 'c1',
        'created_at': '2026-10-26T00:00:00+00:00',
        'started_at': '2026-10-26T00:00:00+00:00',
        'finished_at': '2026-10-26T00:10:00+00:00',
        'structured': {'title': 'Vendor sync'},
        OPEN_LOOP_EXTRACTIONS_FIELD: _EXTRACTED,
        OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD: True,
    }
    conversation = Conversation.model_validate(raw)
    dumped = conversation.model_dump(mode='json')
    assert OPEN_LOOP_EXTRACTIONS_FIELD not in dumped
    assert OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD not in dumped
    assert OPEN_LOOP_EXTRACTIONS_FIELD not in conversation.model_json_schema()['properties']


def test_dedupe_wrapper_passes_the_sink_and_reuse_leaves_it_empty(monkeypatch):
    """The dedupe seam forwards the sink to a fresh generate, but a reuse hit
    must not wipe stored extractions: the sink stays empty and the pipeline
    then omits the field so Firestore merge keeps the prior value."""
    monkeypatch.setattr(llm_input_dedupe, 'dedupe_enabled', lambda: False)

    seen: dict = {}

    def generate(prefix, *, uid=None, open_loop_out=None, **kwargs):
        seen['open_loop_out'] = open_loop_out
        return Structured(title='fresh')

    sink: dict = {}
    hashes: dict = {}
    llm_input_dedupe.notes('u', type('C', (), {'id': 'c1'})(), object(), generate, hashes, open_loop_out=sink)
    assert seen['open_loop_out'] is sink
    assert hashes == {}  # dedupe off: no checkpoint written
