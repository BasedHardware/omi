"""Recovery proof shares conversation transaction and never bypasses its lease."""

from unittest.mock import Mock

import pytest

from database import sync_cap_recovery as checkpoint
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import lifecycle


@pytest.mark.parametrize('fence', ['valid', 'expired', 'replaced', 'attempt'])
def test_piece_ingest_proof_commits_with_assignment_or_is_fenced(monkeypatch, fence):
    key = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    row = {
        'lease_token': 'owner',
        'lease_until': 1000,
        'piece_receipts': {'piece.wav': {'state': 'dispatched', 'attempt': 1}},
    }
    if fence == 'expired':
        row['lease_until'] = 99
    elif fence == 'replaced':
        row['lease_token'] = 'new-owner'
    elif fence == 'attempt':
        row['piece_receipts']['piece.wav']['attempt'] = 2
    client = StrictFirestore({key: row})
    monkeypatch.setattr(checkpoint, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(checkpoint.time, 'time', lambda: 100)
    monkeypatch.setattr(lifecycle, 'observe_completed_conversation_shape', Mock())
    context = {
        'hold_id': 'hold',
        'piece': 'piece.wav',
        'lease_token': 'owner',
        'attempt': 1,
        'receipt': {'seconds': 20, 'attempt': 1, 'usage_metadata': {'provider': 'modulate'}},
    }
    conversation = {'id': 'canonical', 'status': 'completed', 'sync_relevance': 'keep'}
    tx = client.transaction()

    def assign(uid, incoming, **kwargs):
        kwargs['before_assign'](tx)
        tx.set(client.document('users/synthetic/conversations/canonical'), conversation)
        kwargs['after_assign'](tx, (conversation, True, []))
        return conversation, True, []

    monkeypatch.setattr(lifecycle.conversations_db, 'assign_sync_conversation', assign)
    incoming = {'id': 'piece-lineage-anchor', 'status': 'completed', 'language': 'en'}
    if fence != 'valid':
        with pytest.raises(checkpoint.RecoveryIngestFenced):
            lifecycle.ingest_sync_conversation('synthetic', incoming, recovery_checkpoint=context)
        assert not tx.has_written
        assert not client.rows[key].get('piece_ingests')
        return
    lifecycle.ingest_sync_conversation('synthetic', incoming, recovery_checkpoint=context)
    assert tx.sets and tx.updates  # Same transaction; strict fixture forbids late reads.
    proof = checkpoint.ingested_piece('synthetic', 'hold', 'piece.wav')
    assert proof['lineage_anchor'] == 'piece-lineage-anchor'
    assert proof['conversation_id'] == 'canonical'
    assert proof['response']['new_memories'] == ['canonical']
    assert proof['response']['_merged'] == {'canonical': 'en'}


def test_ordinary_ingest_preserves_main_assignment_call(monkeypatch):
    assigned = {'id': 'canonical', 'status': 'completed'}
    call = Mock(return_value=(assigned, False, []))
    monkeypatch.setattr(lifecycle.conversations_db, 'assign_sync_conversation', call)
    lifecycle.ingest_sync_conversation('synthetic', assigned)
    call.assert_called_once_with('synthetic', assigned, candidate_id=None, target_id=None)
