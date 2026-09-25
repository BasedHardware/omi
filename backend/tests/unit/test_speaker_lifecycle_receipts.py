"""Processor snapshots cannot overwrite the manual decision committed after them."""

from copy import deepcopy

import pytest

from database import conversations as db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreTransaction
from tests.unit.test_manual_speaker_assignments import world, read


@pytest.mark.parametrize('writer', ['upsert_conversation_with_lifecycle', 'persist_processing_result_with_lifecycle'])
@pytest.mark.parametrize(
    'selector,decision',
    [
        ({'segment_ids': ['s1']}, {'person_id': 'new'}),
        ({'segment_ids': ['s1']}, {'person_id': None}),
        ({'segment_ids': ['s1']}, {'is_user': True}),
        ({'speaker_id': 4}, {'person_id': 'new', 'use_for_speech_training': False}),
    ],
)
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_processor_commit_reapplies_current_receipt(world, monkeypatch, writer, selector, decision, level):
    store, path, stale = world
    store.rows[path]['data_protection_level'] = level
    snapshot = dict(
        id='c',
        transcript_segments=deepcopy(stale),
        data_protection_level='standard',
        structured={'title': 'Generated', 'overview': 'Old names remain until explicit refresh.'},
    )
    db.assign_conversation_speaker('u', 'c', **selector, **decision)
    expected = read(world)
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    original_set = StrictFirestoreTransaction.set

    def set_with_merge(transaction, ref, data, merge=False):
        if merge:
            transaction.update(ref, data)
        else:
            original_set(transaction, ref, data)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', set_with_merge)
    # Exercise the decorated persistence body with exactly the encoded input
    # produced by its outer codec, without consulting a real user profile.
    encoded = db._prepare_conversation_for_write(snapshot, 'u', 'standard')
    getattr(db, writer).__wrapped__.__wrapped__('u', encoded)
    saved = read(world)
    assert saved['transcript_segments'] == expected['transcript_segments']
    assert saved['manual_speaker_assignments'] == expected['manual_speaker_assignments']
    assert saved['structured']['overview'] == snapshot['structured']['overview']
    assert isinstance(store.rows[path]['transcript_segments'], str if level == 'enhanced' else bytes)
