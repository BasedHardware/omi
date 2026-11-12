"""R9: real transactional silence receipts, privacy fences and zero-speech completion."""

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from config.batch_pipeline import silence_read_skip_enabled
from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionReplay
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.projection import Projector
from utils import fair_use  # Import the legacy metering dependency during collection, outside the call CPU budget.
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity


@pytest.fixture
def lane(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='batch_silence_test'))
    monkeypatch.setattr(store, 'run', lambda operation, **kw: operation(client.transaction()))
    monkeypatch.setattr(store, '_mirror', lambda *a, **k: None)
    monkeypatch.setattr(store, 'mirror_assignment', lambda *a, **k: None)
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('a', 'b'))
    user = client.collection('users').document(binding.owner_id)
    user.create({'data_protection_level': 'standard'})
    store.ref('owners', owner_key(binding.owner_id)).create({'projection_watermark': None})
    for i, sid in enumerate(binding.segment_ids):
        result = {'outcome': 'silence', 'result_uri': f'gs://synthetic/{sid}-result'}
        store.ref('jobs', sid).create(
            {
                'segment_id': sid,
                'priority': 2,
                'policy_parts': {'projection': ProjectionPolicy().to_dict()},
                'projection_binding': asdict(binding),
                'owner_id': binding.owner_id,
                'capture_at': 1000 + i * 30,
                'duration_seconds': 30,
                'privacy_generation': 0,
                'result': result,
                'state': 'committed',
                'audio_uri': f'gs://synthetic/{sid}-audio#1',
            }
        )
        store.ref('results', sid).create(
            {
                'owner_key': owner_key(binding.owner_id),
                'protocol_version': 1,
                'segment_id': sid,
                'capture_at': 1000 + i * 30,
                'committed_at': 2000,
                'previous_segment_id': None if i == 0 else binding.segment_ids[i - 1],
                'result': result,
                'projection_state': 'pending',
            }
        )
    ledger = sync_content_ledger_ref(client, binding.owner_id, binding.content_id)
    ledger.create(
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
    return SimpleNamespace(
        client=client, store=store, binding=binding, user=user, ledger=ledger, policy=ProjectionPolicy()
    )


def assign(lane, sid, *, fast=True):
    return lane.store.session(sid, lane.binding, 10000, policy=lane.policy).persist_empty(silence=fast)


def complete(lane, accounting=None):
    return lane.store.complete('b', lane.binding, 10000, accounting, policy=lane.policy)


def test_ready_silence_preserves_custody_and_completes_once(lane):
    audio = {sid: lane.store.ref('jobs', sid).get().to_dict()['audio_uri'] for sid in ('a', 'b')}
    assert assign(lane, 'a')['state'] == 'ready'
    assert complete(lane) is None  # An unassigned sibling still owes its receipt.
    assert assign(lane, 'b')['state'] == 'ready'
    result = complete(lane)
    assert result == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 2,
        'errors': [],
        'outcome': 'expected_silence',
    }
    assert lane.ledger.get().to_dict()['usage_committed_seconds'] == 0
    checkpoints = [
        patch['processed_segment_ids'].values
        for tx in lane.client.transactions
        for path, patch in tx.updates
        if path == lane.ledger.path and 'processed_segment_ids' in patch
    ]
    assert checkpoints == [['a'], ['b']]
    before = deepcopy(lane.client.rows)
    assert complete(lane) == result
    assert lane.client.rows == before
    for sid in ('a', 'b'):
        job = lane.store.ref('jobs', sid).get().to_dict()
        assert job['audio_uri'] == audio[sid]
        assert 'expires_at' not in job  # Only the existing retention path arms cleanup.
    with pytest.raises(ProjectionReplay):
        assign(lane, 'a')


@pytest.mark.parametrize('fence', ['account', 'source', 'generation', 'ledger'])
def test_silent_assignment_keeps_live_privacy_and_ownership_fences(lane, fence):
    if fence == 'account':
        lane.client.rows[('account_deletions', lane.binding.owner_id)] = {'status': 'pending'}
    elif fence == 'source':
        cid = chunk_identity(lane.binding.owner_id, lane.binding.source, None, False, 1000)
        lane.user.collection('deleted_conversations').document(cid).create({'deleted': True})
    elif fence == 'generation':
        lane.client.rows[('batch_pipeline_privacy', owner_key(lane.binding.owner_id))] = {'generation': 1}
    else:
        lane.client.rows[lane.ledger.path]['job_id'] = 'new-owner'
    before = deepcopy(lane.client.rows)
    with pytest.raises((BatchPrivacyBlocked, ProjectionBlocked)):
        assign(lane, 'a')
    assert lane.client.rows == before


@pytest.mark.parametrize('change', ['speech', 'output', 'partial', 'charged', 'erased', 'binding'])
def test_zero_accounting_refuses_mixed_or_changed_receipts(lane, change):
    assign(lane, 'a')
    assign(lane, 'b')
    if change == 'speech':
        lane.client.rows[lane.store.ref('results', 'a').path]['result']['outcome'] = 'success'
    elif change == 'output':
        lane.client.rows[lane.store.ref('results', 'a').path]['projection']['conversation_id'] = 'output'
    elif change == 'partial':
        lane.client.rows[lane.ledger.path]['status'] = 'partial'
    elif change == 'charged':
        lane.client.rows[lane.ledger.path]['usage_committed_seconds'] = 4
    elif change == 'erased':
        lane.client.rows[lane.store.ref('results', 'a').path]['projection_state'] = 'erased'
    else:
        lane.client.rows[lane.store.ref('jobs', 'a').path]['projection_binding']['content_id'] = 'different'
    before = deepcopy(lane.client.rows)
    if change == 'binding':
        with pytest.raises(ProjectionBlocked):
            complete(lane)
    else:
        assert complete(lane) is None
    assert lane.client.rows == before


def test_off_keeps_legacy_persisted_receipt(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED', 'false')
    assert not silence_read_skip_enabled()
    assert assign(lane, 'a', fast=False)['state'] == 'persisted'
    monkeypatch.delenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED')
    assert silence_read_skip_enabled()


def test_speech_cannot_use_silent_receipt(lane):
    for table in ('jobs', 'results'):
        lane.client.rows[lane.store.ref(table, 'a').path]['result']['outcome'] = 'success'
    before = deepcopy(lane.client.rows)
    with pytest.raises(ProjectionBlocked):
        assign(lane, 'a')
    assert lane.client.rows == before


def test_post_classification_reads_halved_without_caching(lane, monkeypatch):
    seed = deepcopy(lane.client.rows)
    reads = []
    original_get = StrictFirestoreDocument.get

    def counted_get(self, *args, **kwargs):
        reads.append(self.path)
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted_get)
    projector = Projector.__new__(Projector)
    projector.store, projector.clock = lane.store, lambda: 10000
    projector.publish_completion = lambda binding, result, **kw: result
    counts = {}
    for fast in (False, True):
        lane.client.rows = deepcopy(seed)
        monkeypatch.setenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED', 'true' if fast else 'false')
        reads.clear()
        for sid in lane.binding.segment_ids:
            job = lane.store.ref('jobs', sid).get().to_dict()
            entry = lane.store.ref('results', sid).get().to_dict()
            projector._assign(sid, job, entry, lane.binding)
            receipt = lane.store.ref('results', sid).get().to_dict()['projection']
            item = WorkItem(**{k: job[k] for k in WorkItem.__dataclass_fields__ if k in job})
            projector.finish_part(item, lane.binding, receipt, None, policy=lane.policy)
        result = projector.complete_content('b', lane.binding, policy=lane.policy, silence=True)
        assert result['outcome'] == 'expected_silence'
        counts[fast] = len(reads)
    print(f'post-classification document lookups, two silent units: {counts}')
    assert counts[True] <= counts[False] / 2


@pytest.mark.parametrize('fence', ['account', 'source', 'generation'])
def test_silence_completion_rechecks_privacy_after_assignment(lane, fence):
    assign(lane, 'a')
    assign(lane, 'b')
    if fence == 'account':
        lane.client.rows[('account_deletions', lane.binding.owner_id)] = {'status': 'pending'}
    elif fence == 'source':
        cid = chunk_identity(lane.binding.owner_id, lane.binding.source, None, False, 1030)
        lane.user.collection('deleted_conversations').document(cid).create({'deleted': True})
    else:
        lane.client.rows[('batch_pipeline_privacy', owner_key(lane.binding.owner_id))] = {'generation': 1}
    before = deepcopy(lane.client.rows)
    with pytest.raises(BatchPrivacyBlocked):
        complete(lane)
    assert lane.client.rows == before
