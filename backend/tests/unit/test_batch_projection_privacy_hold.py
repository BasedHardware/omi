"""A privacy refusal settles ordering without authorizing content or discarding input."""

from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason, privacy_owner_key
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_privacy import HOLD_REASONS, checkpoint, hold, resume
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity

POLICY = ProjectionPolicy()


@pytest.fixture
def lane(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='privacy_hold'))
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('head',))
    client.collection('users').document(binding.owner_id).create({'data_protection_level': 'standard'})
    store.ref('owners', owner_key(binding.owner_id)).create({'projection_watermark': None})
    add(store, binding, 'head', 1000, None)
    return client, store, binding


def add(store, binding, sid, capture, previous):
    result = {'outcome': 'success', 'result_uri': f'gs://synthetic/{sid}'}
    store.ref('jobs', sid).create(
        {
            'projection_binding': asdict(binding),
            'owner_id': binding.owner_id,
            'capture_at': capture,
            'privacy_generation': binding.privacy_generation,
            'result': result,
        }
    )
    store.ref('results', sid).create(
        {
            'protocol_version': 1,
            'segment_id': sid,
            'owner_key': owner_key(binding.owner_id),
            'capture_at': capture,
            'committed_at': capture,
            'previous_segment_id': previous,
            'projection_state': 'pending',
            'result': result,
        }
    )
    sync_content_ledger_ref(store.client, binding.owner_id, binding.content_id).create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {
                'protocol_version': 1,
                'namespace': store.store.namespace,
                'segment_ids': list(binding.segment_ids),
            },
        }
    )


def fence(client, binding, reason):
    uid = binding.owner_id
    cid = chunk_identity(uid, binding.source, binding.client_device_id, binding.is_locked, 1000)
    if reason == BatchPrivacyReason.ACCOUNT_DELETED:
        client.rows[('account_deletions', uid)] = {}
    elif reason == BatchPrivacyReason.ACCOUNT_MISSING:
        client.rows.pop(('users', uid))
    elif reason == BatchPrivacyReason.DATA_PROTECTION_CHANGED:
        client.rows[('users', uid)]['migration_status'] = 'pending'
    elif reason == BatchPrivacyReason.PRIVACY_GENERATION_CHANGED:
        client.rows[('batch_pipeline_privacy', privacy_owner_key(uid))] = {'generation': 1}
    elif reason == BatchPrivacyReason.RECORDING_PRIVACY_CHANGED:
        client.rows[('users', uid, 'conversations', cid)] = {
            'record_lane_owner': 'batch_live_v1',
            'uses_custom_stt': True,
        }
    elif reason == BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE:
        client.rows[('users', uid, 'conversations', cid)] = {'deleted': True, 'sync_merged_into': 'cycle'}
        client.rows[('users', uid, 'conversations', 'cycle')] = {'deleted': True, 'sync_merged_into': cid}
    elif reason == BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING:
        client.rows[('users', uid, 'conversations', cid)] = {'deleted': True, 'sync_merged_into': 'missing'}
    else:
        previous = cid
        for index in range(256):
            target = f'hop-{index}'
            client.rows[('users', uid, 'conversations', previous)] = {'deleted': True, 'sync_merged_into': target}
            previous = target
        client.rows[('users', uid, 'conversations', previous)] = {}


@pytest.mark.parametrize('reason', sorted(HOLD_REASONS, key=lambda value: value.value))
def test_refusal_is_metadata_only_idempotent_and_retains_input(lane, reason):
    client, store, binding = lane
    fence(client, binding, reason)
    before = deepcopy(client.rows)
    assert hold(store, 'head', binding, 2000, reason, policy=POLICY)
    entry = store.ref('results', 'head').get().to_dict()
    assert checkpoint(entry) and entry['projection_privacy_refusal']['reason'] == reason.value
    assert entry['projection']['state'] == 'quarantined' and entry['projection']['held_speech_seconds'] is None
    assert entry['result'] == before[('privacy_hold_results', 'head')]['result']
    changed = {key for key in client.rows if client.rows.get(key) != before.get(key)}
    assert changed == {('privacy_hold_results', 'head'), ('privacy_hold_owners', owner_key(binding.owner_id))}
    assert store.projection_watermark(owner_key(binding.owner_id)) == 'head'
    held = deepcopy(client.rows)
    assert not hold(store, 'head', binding, 3000, reason, policy=POLICY)
    assert client.rows == held


def test_repaired_replay_preserves_later_ordering_and_does_not_refetch_stt(lane):
    client, store, binding = lane
    fence(client, binding, BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    assert hold(store, 'head', binding, 2000, BatchPrivacyReason.DATA_PROTECTION_CHANGED, policy=POLICY)
    client.rows[('users', binding.owner_id)].pop('migration_status')
    following = replace(binding, job_id='next-job', content_id='next-content', segment_ids=('next',))
    add(store, following, 'next', 3000, 'head')
    session = store.session('next', following, 3001, policy=POLICY)
    transaction = client.transaction()
    session.prepare(transaction)
    session.speech_seconds = 3
    session.persist(transaction, ({'id': 'synthetic-next'}, True, []))
    assert store.projection_watermark(owner_key(binding.owner_id)) == 'next'
    restored = resume(store, 'head', binding, 3002, policy=POLICY)
    assert 'projection' not in restored and checkpoint(restored)
    session = store.session('head', binding, 3003, policy=POLICY)
    transaction = client.transaction()
    session.prepare(transaction)
    session.speech_seconds = 4
    session.persist(transaction, ({'id': 'synthetic-repaired'}, True, []))
    assert store.projection_watermark(owner_key(binding.owner_id)) == 'next'
    entry = store.ref('results', 'head').get().to_dict()
    assert entry['projection']['speech_seconds'] == 4 and entry['protocol_version'] == 1
    assert not entry.get('projection_privacy_refusal') and not checkpoint(entry)


def test_existing_assignment_hold_and_resume_never_rewind_or_repeat_assignment(lane):
    client, store, binding = lane
    client.rows[('privacy_hold_results', 'head')].update(
        projection_state='persisted',
        projection={'state': 'persisted', 'conversation_id': 'synthetic-output', 'speech_seconds': 4},
    )
    client.rows[('privacy_hold_owners', owner_key(binding.owner_id))]['projection_watermark'] = 'later'
    fence(client, binding, BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    assert hold(store, 'head', binding, 2000, BatchPrivacyReason.DATA_PROTECTION_CHANGED, policy=POLICY)
    assert store.projection_watermark(owner_key(binding.owner_id)) == 'later'
    client.rows[('users', binding.owner_id)].pop('migration_status')
    restored = resume(store, 'head', binding, 2001, policy=POLICY)
    assert restored['projection'] == {'state': 'persisted', 'conversation_id': 'synthetic-output', 'speech_seconds': 4}
    assert store.projection_watermark(owner_key(binding.owner_id)) == 'later'


def test_completed_ready_result_does_not_become_a_new_privacy_obligation(lane):
    client, store, binding = lane
    client.rows[('privacy_hold_results', 'head')].update(
        projection_state='ready',
        projection={'state': 'ready', 'conversation_id': 'synthetic-output', 'speech_seconds': 4},
    )
    client.rows[sync_content_ledger_ref(client, binding.owner_id, binding.content_id).path]['status'] = 'completed'
    client.rows[('privacy_hold_owners', owner_key(binding.owner_id))]['projection_watermark'] = 'later'
    fence(client, binding, BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    before = deepcopy(client.rows)
    assert not hold(store, 'head', binding, 2000, BatchPrivacyReason.DATA_PROTECTION_CHANGED, policy=POLICY)
    assert client.rows == before


@pytest.mark.parametrize('change', ['healthy', 'unknown', 'lease', 'binding', 'ledger', 'predecessor'])
def test_hold_cannot_bypass_unproven_privacy_or_intake_ownership(lane, change):
    client, store, binding = lane
    reason = BatchPrivacyReason.DATA_PROTECTION_CHANGED
    if change != 'healthy':
        fence(client, binding, reason)
    if change == 'unknown':
        reason = BatchPrivacyReason.UNKNOWN
    elif change == 'lease':
        reason = BatchPrivacyReason.RESULT_LEASE_LOST
    elif change == 'binding':
        client.rows[('privacy_hold_jobs', 'head')]['owner_id'] = 'foreign'
    elif change == 'ledger':
        client.rows[sync_content_ledger_ref(client, binding.owner_id, binding.content_id).path]['job_id'] = 'foreign'
    elif change == 'predecessor':
        client.rows[('privacy_hold_results', 'head')]['previous_segment_id'] = 'unpersisted'
    before = deepcopy(client.rows)
    with pytest.raises(ProjectionBlocked):
        hold(store, 'head', binding, 2000, reason, policy=POLICY)
    assert client.rows == before


def test_refusal_proof_cannot_assign_acknowledge_or_resume_while_blocked(lane):
    client, store, binding = lane
    fence(client, binding, BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    session = store.session('head', binding, 2000, policy=POLICY)
    transaction = client.transaction()
    session.prepare(transaction, privacy_refusal=BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    with pytest.raises(ProjectionBlocked):
        session.persist(transaction, ({'id': 'forbidden'}, True, []))
    with pytest.raises(ProjectionBlocked):
        session.write_receipt(transaction, {'state': 'ready'})
    assert not transaction.has_written
    hold(store, 'head', binding, 2001, BatchPrivacyReason.DATA_PROTECTION_CHANGED, policy=POLICY)
    before = deepcopy(client.rows)
    with pytest.raises(BatchPrivacyBlocked):
        resume(store, 'head', binding, 2002, policy=POLICY)
    assert client.rows == before


@pytest.mark.parametrize('change', ['completed_ledger', 'legacy_protocol'])
def test_control_receipt_cannot_impersonate_completed_assignment_or_ordering_proof(lane, change):
    client, store, binding = lane
    fence(client, binding, BatchPrivacyReason.DATA_PROTECTION_CHANGED)
    hold(store, 'head', binding, 2000, BatchPrivacyReason.DATA_PROTECTION_CHANGED, policy=POLICY)
    client.rows[('users', binding.owner_id)].pop('migration_status')
    if change == 'completed_ledger':
        client.rows[sync_content_ledger_ref(client, binding.owner_id, binding.content_id).path]['status'] = 'completed'
    else:
        client.rows[('privacy_hold_results', 'head')]['protocol_version'] = 1
    before = deepcopy(client.rows)
    with pytest.raises(ProjectionBlocked):
        resume(store, 'head', binding, 2001, policy=POLICY)
    assert client.rows == before
