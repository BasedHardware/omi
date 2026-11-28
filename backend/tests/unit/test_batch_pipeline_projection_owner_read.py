"""The receipt fast path drops only the owner cursor read."""

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked, ProjectionPredecessorPending, ProjectionReplay
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key


SWITCH = 'BATCH_PIPELINE_PROJECTION_DEFER_OWNER_READ_ENABLED'


@pytest.fixture
def session_fixture(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='batch_owner_read'))
    binding = ProjectionBinding('owner', 'intake', 'content', ('segment',), run_token='run', run_epoch=1)
    session = store.session('segment', binding, 1_795_400_000, policy=ProjectionPolicy())
    client.collection('users').document(binding.owner_id).create({'data_protection_level': 'enhanced'})
    result = {'outcome': 'silence'}
    session.job_ref.create(
        {
            'projection_binding': asdict(binding),
            'owner_id': binding.owner_id,
            'capture_at': 1000,
            'privacy_generation': 0,
            'result': result,
        }
    )
    session.result_ref.create(
        {
            'owner_key': owner_key(binding.owner_id),
            'protocol_version': 1,
            'segment_id': 'segment',
            'capture_at': 1000,
            'previous_segment_id': 'predecessor',
            'result': result,
        }
    )
    session.owner_ref.create({'projection_watermark': 'older'})
    ledger = sync_content_ledger_ref(client, binding.owner_id, binding.content_id)
    ledger.create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'ledger_run_token': binding.run_token,
            'ledger_run_epoch': binding.run_epoch,
            'batch_pipeline': {'protocol_version': 1, 'namespace': store.store.namespace, 'segment_ids': ['segment']},
        }
    )
    reads = []
    original = StrictFirestoreDocument.get

    def track(ref, transaction=None, **kwargs):
        reads.append((ref.path, transaction))
        return original(ref, transaction=transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', track)
    return client, session, ledger, reads


@pytest.mark.parametrize('flag,owner_read', [(None, False), ('false', True), ('true', False)])
def test_valid_receipt_replays_with_configurable_owner_read(session_fixture, monkeypatch, flag, owner_read):
    client, session, ledger, reads = session_fixture
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    if flag is None:
        monkeypatch.delenv(SWITCH, raising=False)
    else:
        monkeypatch.setenv(SWITCH, flag)
    receipt = {'state': 'ready', 'speech_seconds': 0}
    client.rows[session.result_ref.path]['projection'] = receipt
    client.rows[ledger.path]['status'] = 'completed'

    transaction = client.transaction()
    with pytest.raises(ProjectionReplay) as error:
        session.prepare(transaction)
    assert error.value.receipt == receipt
    assert ((session.owner_ref.path, transaction) in reads) is owner_read
    assert (ledger.path, transaction) in reads

    # Publication uses the same checks but consumes the receipt instead of raising replay.
    transaction = client.transaction()
    session.prepare(transaction, replay=False)
    assert session.receipt() == receipt
    assert ((session.owner_ref.path, transaction) in reads) is owner_read
    assert (ledger.path, transaction) in reads


@pytest.mark.parametrize(
    'fault,error,reason',
    [
        ('missing', ProjectionBlocked, 'content ledger owner lost'),
        ('stale_owner', ProjectionBlocked, 'content ledger owner lost'),
        ('mismatched_binding', ProjectionBlocked, 'immutable result binding mismatch'),
        ('mismatched_ledger', ProjectionBlocked, 'durable intake ledger binding required'),
        ('deleted_owner', BatchPrivacyBlocked, 'account_missing'),
    ],
)
def test_invalid_receipt_cannot_bypass_authority(session_fixture, monkeypatch, fault, error, reason):
    client, session, ledger, _ = session_fixture
    monkeypatch.setenv(SWITCH, 'true')
    if fault != 'missing':
        client.rows[session.result_ref.path]['projection'] = {'state': 'ready'}
    if fault == 'stale_owner':
        client.rows[ledger.path]['ledger_run_epoch'] = 2
    else:
        client.rows[ledger.path]['status'] = 'completed'
    if fault == 'mismatched_binding':
        client.rows[session.job_ref.path]['projection_binding'] = asdict(replace(session.binding, job_id='other'))
    if fault == 'mismatched_ledger':
        client.rows[ledger.path]['job_id'] = 'other'
    if fault == 'deleted_owner':
        client.rows.pop(('users', session.binding.owner_id))

    with pytest.raises(error, match=reason):
        session.prepare(client.transaction(), replay=False)


def test_zero_speech_reads_current_predecessor_before_advancing(session_fixture, monkeypatch):
    client, session, ledger, reads = session_fixture
    monkeypatch.setenv(SWITCH, 'true')
    monkeypatch.setattr(session.store, 'run', lambda operation, **_: operation(client.transaction()))

    with pytest.raises(ProjectionPredecessorPending):
        session.persist_empty(silence=True)
    rejected = client.transactions[-1]
    assert (session.owner_ref.path, rejected) in reads
    assert client.rows[session.owner_ref.path]['projection_watermark'] == 'older'
    assert 'processed_segment_ids' not in client.rows[ledger.path]

    client.rows[session.owner_ref.path]['projection_watermark'] = 'predecessor'
    receipt = session.persist_empty(silence=True)
    committed = client.transactions[-1]
    assert (session.owner_ref.path, committed) in reads
    assert receipt['state'] == 'ready'
    assert receipt['speech_seconds'] == 0
    assert client.rows[session.owner_ref.path]['projection_watermark'] == 'segment'
