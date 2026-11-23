"""Poll-independent receipt fanout: strict Firestore read/write boundary."""

from copy import deepcopy

import pytest

from database import batch_pipeline_coalescing_completion as completion
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_upload_coalescing import member
from utils.batch_pipeline.contracts import ProjectionBinding


@pytest.fixture
def receipts(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StrictFirestore()
    original = member('first')
    original['coalesce_group'] = 'group'
    intake_ref = client.collection('synthetic_intakes').document(original['job_id'])
    content_ref = sync_content_ledger_ref(client, 'owner', original['content_id'])
    client.rows[intake_ref.path] = original
    client.rows[content_ref.path] = {
        'job_id': original['job_id'],
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
    }
    binding = ProjectionBinding(
        'owner', 'bp_merged', 'merged', ('unit',), privacy_generation=0, target_conversation_id='recording'
    )
    ledger = {'status': 'processing', **completion.manifest({'id': 'group', 'mode': 'merged', 'members': [original]})}
    return client, binding, ledger, intake_ref, content_ref


def test_ordinary_completion_adds_no_reads():
    assert completion.manifest(None) == {}
    assert completion.prepare(object(), 'synthetic', object(), object(), {}) == []


def test_completion_reads_before_writes_and_replay_does_not_extend_expiry(receipts):
    client, binding, ledger, intake_ref, content_ref = receipts
    transaction = client.transaction()
    prepared = completion.prepare(client, 'synthetic', transaction, binding, ledger)
    result = {'new_memories': [], 'updated_memories': [], 'failed_segments': 0, 'total_segments': 2, 'errors': []}
    completion.write(transaction, prepared, result, 100)
    saved = deepcopy(client.rows)
    assert saved[content_ref.path]['status'] == 'completed'
    assert saved[content_ref.path]['result']['total_segments'] == 1
    assert saved[intake_ref.path]['coalesce_target'] == binding.job_id
    ledger['status'] = 'completed'
    prepared = completion.prepare(client, 'synthetic', client.transaction(), binding, ledger)
    assert prepared == []
    completion.write(client.transaction(), prepared, result, 999)
    assert client.rows == saved
    del client.rows[intake_ref.path]
    del client.rows[content_ref.path]
    assert completion.prepare(client, 'synthetic', client.transaction(), binding, ledger) == []


@pytest.mark.parametrize('mismatch', ['owner', 'conversation', 'generation', 'group', 'target', 'ledger', 'missing'])
def test_original_identity_mismatch_never_writes(receipts, mismatch):
    client, binding, ledger, intake_ref, content_ref = receipts
    updates = {
        'owner': {'owner_id': 'foreign'},
        'conversation': {'conversation_id': 'foreign'},
        'generation': {'privacy_generation': 1},
        'group': {'coalesce_group': 'foreign'},
        'target': {'coalesce_target': 'foreign'},
    }
    if mismatch in updates:
        client.rows[intake_ref.path].update(updates[mismatch])
    elif mismatch == 'ledger':
        client.rows[content_ref.path]['job_id'] = 'foreign'
    else:
        del client.rows[intake_ref.path]
    before = deepcopy(client.rows)
    with pytest.raises(ValueError, match='identity'):
        completion.prepare(client, 'synthetic', client.transaction(), binding, ledger)
    assert client.rows == before


def test_partial_result_never_acknowledges_originals(receipts):
    client, binding, ledger, _, _ = receipts
    transaction = client.transaction()
    prepared = completion.prepare(client, 'synthetic', transaction, binding, ledger)
    before = deepcopy(client.rows)
    with pytest.raises(ValueError, match='authoritative'):
        completion.write(transaction, prepared, {'failed_segments': 1}, 100)
    assert client.rows == before
