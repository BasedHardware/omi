"""A held source is durable custody, never a completed-transcription proof."""

from copy import deepcopy

import pytest

from database import sync_cap_holds as holds, sync_ledger as ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = StrictFirestore()
    ref = ledger.sync_content_reference(client, 'synthetic', 'content')
    row = {
        'status': 'processing',
        'job_id': 'original',
        'ledger_run_token': 'owner-token',
        'ledger_run_epoch': 1,
        'expires_at': 'old-ttl',
    }
    client.rows[ref.path] = row
    monkeypatch.setattr(holds, 'get_firestore_client', lambda: client)
    return client, ref


def _hold():
    return holds.mark_content_held(
        'synthetic',
        'content',
        'original',
        {
            'held_audio': True,
            'new_memories': [],
            'updated_memories': [],
            'failed_segments': 0,
            'total_segments': 0,
            'errors': [],
            'outcome': 'success',
        },
        ['a', 'b'],
        run_token='owner-token',
        run_epoch=1,
    )


def test_hold_is_fenced_and_never_manufactures_completion(state):
    client, ref = state
    before = deepcopy(client.rows[ref.path])
    assert not holds.mark_content_held(
        'synthetic',
        'content',
        'stale',
        {'held_audio': True, 'failed_segments': 0, 'total_segments': 0, 'errors': [], 'outcome': 'success'},
        ['a'],
        run_token='stale',
        run_epoch=0,
    )
    assert client.rows[ref.path] == before
    assert _hold()
    row = client.rows[ref.path]
    assert row['status'] == 'held'
    # The strict transaction fixture records transforms rather than applying
    # DELETE_FIELD; assert the removal request, not a simulated TTL deletion.
    assert str(row['expires_at']) == str(holds.firestore.DELETE_FIELD)
    assert not ledger.is_valid_completed_sync_content_result(row['result'])
    claim = ledger.claim_sync_content('synthetic', 'content', 'retry', 'fresh', firestore_client=client)
    assert claim['outcome'] == 'held' and claim['result']['held_audio']
    assert holds.recovery_status('synthetic', 'content', 'a') == 'ready'


def test_only_all_recovered_holds_can_complete_and_settlement_is_idempotent(state):
    client, ref = state
    assert _hold()
    assert holds.settle_hold('synthetic', 'content', 'a', {'new_memories': ['one']}, 2)
    first = deepcopy(client.rows[ref.path])
    assert first['status'] == 'held'
    assert first['result']['held_audio']
    assert holds.settle_hold('synthetic', 'content', 'a', {'new_memories': ['wrong']}, 99)
    assert client.rows[ref.path] == first
    assert holds.settle_hold('synthetic', 'content', 'b', {'updated_memories': ['two']}, 1)
    row = client.rows[ref.path]
    assert row['status'] == 'completed'
    assert row['result']['new_memories'] == ['one']
    assert row['result']['updated_memories'] == ['two']
    assert row['result']['recovered_segments'] == 3
    assert ledger.is_valid_completed_sync_content_result(row['result'])
    assert 'expires_at' in row


def test_recovery_does_not_overwrite_a_different_content_owner(state):
    client, ref = state
    assert _hold()
    client.rows[ref.path].update(status='processing', dispatch_protocol='replacement', job_id='replacement')
    before = deepcopy(client.rows[ref.path])
    assert holds.recovery_status('synthetic', 'content', 'a') == 'waiting'
    assert not holds.settle_hold('synthetic', 'content', 'a', {}, 1)
    assert client.rows[ref.path] == before
