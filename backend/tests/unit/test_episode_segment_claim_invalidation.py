"""Transcript edits atomically invalidate only dependent episode claims."""

import json
import zlib

import pytest

from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument


@pytest.mark.parametrize('claims_present', [True, False, None])
def test_segment_edit_drops_dependent_claims_without_extra_reads(monkeypatch, claims_present):
    dependent = [
        {'evidence_ids': ['speech:s1', 'speech:s2']},
        {
            'evidence_ids': ['legacy'],
            'evidence_sources': [{'id': 'legacy', 'source_kind': 'speech', 'source_ref': 's1'}],
        },
        {'evidence_sources': [{'source_kind': 'speech', 'id': 'speech:s1'}]},
    ]
    untouched = [
        {'evidence_ids': ['speech:s2']},
        {'evidence_ids': ['screen_ocr:s1'], 'evidence_sources': [{'source_kind': 'screen_ocr', 'source_ref': 's1'}]},
        {'evidence_sources': [{'id': 'speech:s10', 'source_kind': 'speech', 'source_ref': 's10'}]},
    ]
    for claim in dependent + untouched:
        claim.update(text='Synthetic summary', target='/overview', provenance='inferred')
    structured = {'overview': 'Synthetic summary', 'sections': [{'source_segment_ids': ['s1', 's2']}]}
    if claims_present is not None:
        structured['note_claims'] = dependent + untouched if claims_present else []
    path = ('users', 'synthetic-user', conversations_db.conversations_collection, 'synthetic-conversation')
    db = StrictFirestore({path: {'transcript_segments': [{'id': 's1', 'text': 'Old text'}], 'structured': structured}})
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, transaction=None, **kwargs):
        reads.append((ref.path, transaction))
        return original_get(ref, transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(conversations_db, 'db', db)
    assert (
        conversations_db.update_conversation_segment_text('synthetic-user', 'synthetic-conversation', 's1', 'New text')
        == 'ok'
    )
    assert len(db.transactions) == 1
    transaction = db.transactions[0]
    assert reads == [(path, transaction)]
    assert len(transaction.updates) == 1
    updated_path, payload = transaction.updates[0]
    assert updated_path == path
    assert json.loads(zlib.decompress(payload['transcript_segments'])) == [{'id': 's1', 'text': 'New text'}]
    assert payload['structured.sections'] == [{'source_segment_ids': []}]
    assert 'structured.overview' not in payload
    if claims_present:
        assert payload['structured.note_claims'] == untouched
    else:
        assert 'structured.note_claims' not in payload
    assert structured['sections'][0]['source_segment_ids'] == ['s1', 's2']
