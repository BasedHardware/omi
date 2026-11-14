"""Actual result publication -> production purge; local transport, not remote C4."""

from types import SimpleNamespace

import pytest

from database import legal_holds
from database.batch_pipeline_conversation_purge import purge_conversation
from database.conversation_batch_purge_jobs import GATE_KIND
from database.jobstore.authority import AuthorityRefused
from database.jobstore.published_copies import PublishedCopies, payload
from database.jobstore.retained_copies import RetainedCopies, RetainedCopiesPending
from database.privacy_fence.protocol import conversation_key
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_effect import paid  # noqa: F401
from tests.integration.test_jobstore_result_sessions import result, row  # noqa: F401
from utils.batch_pipeline.contracts import WorkResult

pytestmark = pytest.mark.integration


@pytest.fixture
def published(result, monkeypatch):
    adapter, _, ticket, item, storage, artifacts = result
    uri = artifacts.persist_result(item, {'words': ['original']})
    handoff = adapter.handoff
    conversation = ticket.conversation_ids[0]
    handoff.client.document(f'users/{item.owner_id}/deleted_conversations/{conversation}').set({'id': conversation})
    handoff.fence.close(
        ticket.owner, conversation=conversation_key(ticket.owner, conversation), state='deleted', local=True
    )
    # The actual paid COMPLETE discards the result after close, retiring its
    # registry without producing a terminal recording or copying this URI.
    assert not ticket.complete(WorkResult(item.segment_id, uri).to_dict(), now=202, partial_wait=30)
    from utils.other import local_storage

    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: storage)
    retained = RetainedCopies(handoff)
    copies = PublishedCopies(retained, storage_client=storage)
    unit = lambda: legal_holds.bounded_destructive_unit(item.owner_id, kind=GATE_KIND, firestore_client=handoff.client)
    return SimpleNamespace(
        result=result,
        uid=item.owner_id,
        identity=result[1]['recording_id'],
        conversation=conversation,
        handoff=handoff,
        retained=retained,
        copies=copies,
        unit=unit,
        uri=uri,
    )


def prepare(r, authority):
    identity, manifest = r.retained.inventory(r.uid, r.conversation)[0]
    r.retained.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)


def test_actual_purge_discovers_published_before_paid_terminal(published):
    r = published
    source = row(r.result)
    progress = SimpleNamespace(position={}, expired=lambda: False, unit=r.unit, settle_stuck=lambda _: None)
    with pytest.raises(RetainedCopiesPending, match='complete ordinary source required'):
        purge_conversation(
            r.uid, r.conversation, progress, firestore_client=r.handoff.client, retained_copies=r.retained
        )
    assert not list(r.result[4].bucket('synthetic').list_blobs())
    assert not r.copies._reference(source).get().exists
    assert row(r.result) == source  # original deadline, identity, phase remain
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT completion FROM queue_handoffs WHERE namespace=%s', (source['namespace'],)
        ).fetchone() == (None,)
        assert conn.execute(
            'SELECT purpose,state FROM queue_original_erasure_operations WHERE namespace=%s ORDER BY purpose',
            (source['namespace'],),
        ).fetchall() == [('published_object', 'committed'), ('published_reference', 'committed')]
    with r.unit() as authority:
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)


def test_reference_cannot_retire_before_object_proof(published):
    r = published
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(AuthorityRefused, match='object proof'):
            r.copies.operations.prepare(
                r.uid, r.identity, authority, 'published_reference', payload(row(r.result)), conversation=r.conversation
            )
    assert list(r.result[4].bucket('synthetic').list_blobs())


def test_changed_reference_refuses_before_object_delete(published):
    r = published
    ref = r.copies._reference(row(r.result))
    ref.update({'owner_id': 'foreign'})
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(AuthorityRefused, match='reference changed'):
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert list(r.result[4].bucket('synthetic').list_blobs())


def test_absence_error_pins_real_remote_gate(published, monkeypatch):
    r = published
    from utils.other.local_storage import LocalBlob

    monkeypatch.setattr(LocalBlob, 'reload', lambda *a, **k: (_ for _ in ()).throw(TimeoutError('unknown absence')))
    with pytest.raises(ConnectionError, match='absence unresolved'):
        with r.unit() as authority:
            prepare(r, authority)
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    gate = r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(r.uid).get().to_dict()
    assert gate['remote_inflight'] and gate['remote_target'] == r.uri
    assert r.copies._reference(row(r.result)).get().exists


def test_actual_reads_and_free_pool_during_original_object_io(published, monkeypatch):
    from google.cloud.firestore_v1.document import DocumentReference
    from utils.other.local_storage import LocalBlob
    from database.privacy_fence.protocol import lock

    r = published
    actual_get, actual_delete = DocumentReference.get, LocalBlob.delete
    reads = []

    def get(ref, *a, **k):
        if ref.path.startswith(r.handoff.ticket.namespace + '_artifacts/'):
            reads.append(k.get('transaction'))
        return actual_get(ref, *a, **k)

    def delete(blob, **kwargs):
        with r.handoff.pool.connection(timeout=2) as one, r.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                lock(one, r.result[2].owner, exclusive=True)
            assert two.execute('SELECT 1').fetchone() == (1,)
        return actual_delete(blob, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', get)
    monkeypatch.setattr(LocalBlob, 'delete', delete)
    with r.unit() as authority:
        prepare(r, authority)
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert len(reads) == 3 and all(t is not None for t in reads)


@pytest.mark.parametrize('change', ['token', 'epoch', 'intent'])
def test_real_write_authority_changes_refuse_before_deletion(published, change):
    r = published
    with r.unit() as authority:
        prepare(r, authority)
        if change == 'token':
            r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(r.uid).update(
                {'token': 'successor'}
            )
        elif change == 'intent':
            r.handoff.client.document(f'users/{r.uid}/deleted_conversations/{r.conversation}').delete()
        else:
            r.handoff.authority.ref.update({'epoch': 4})
        with pytest.raises(Exception):
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert list(r.result[4].bucket('synthetic').list_blobs())


def test_published_progress_cancellation_fences_paused_finish(published):
    r = published
    with r.unit() as authority:
        prepare(r, authority)
        target = r.copies.operations.prepare(
            r.uid, r.identity, authority, 'published_object', payload(row(r.result)), conversation=r.conversation
        )
        assert r.copies.operations.resolve(r.uid, target)
        with pytest.raises(AuthorityRefused, match='cancelled'):
            r.copies.operations.finish(r.uid, target, authority, conversation=r.conversation)
    assert list(r.result[4].bucket('synthetic').list_blobs())


@pytest.mark.parametrize('gap', ['after_object', 'before_progress_commit', 'after_progress_commit', 'after_reference'])
def test_actual_process_exit_preserves_original_custody(published, gap):
    import os
    import subprocess
    import sys

    r = published
    with r.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    code = '''
import os
from pathlib import Path
from contextlib import contextmanager
import testing.pipeline_sim._env
from database import legal_holds
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.published_copies import PublishedCopies
from database.jobstore.retained_copies import RetainedCopies
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.other.local_storage import LocalStorageClient
pool=Pool(os.environ['PUB_DSN'],size=2)
h=Handoff(pool,Fence(pool),_emulator_client(),Epoch(os.environ['PUB_NS'],3))
r=RetainedCopies(h)
p=PublishedCopies(r,storage_client=LocalStorageClient(Path(os.environ['PUB_ROOT'])))
a=legal_holds.UnitAuthority(os.environ['PUB_UID'],os.environ['PUB_KIND'],os.environ['PUB_TOKEN'],h.client,None)
gap=os.environ['PUB_GAP']
if gap=='after_object':
    real=p._absent
    def killed(*args):
        real(*args)
        os._exit(86)
    p._absent=killed
elif gap=='after_reference':
    real=p._check
    def killed(*args,**kwargs):
        real(*args,**kwargs)
        if kwargs.get('erase'): os._exit(86)
    p._check=killed
else:
    connection=pool.connection
    class Wrapper:
        def __init__(self,conn): self.conn,self.updated=conn,False
        def __getattr__(self,name): return getattr(self.conn,name)
        def execute(self,query,*args,**kwargs):
            value=self.conn.execute(query,*args,**kwargs)
            self.updated |= "UPDATE queue_original_erasure_operations SET state='committed'" in query
            return value
        @contextmanager
        def transaction(self):
            with self.conn.transaction():
                yield
                if self.updated and gap=='before_progress_commit': os._exit(86)
            if self.updated: os._exit(86)
    @contextmanager
    def wrapped(**kwargs):
        with connection(**kwargs) as conn: yield Wrapper(conn)
    pool.connection=wrapped
p.retire(os.environ['PUB_UID'],os.environ['PUB_ID'],a,conversation=os.environ['PUB_CONVERSATION'])
os._exit(87)
'''
    with r.unit() as authority:
        prepare(r, authority)
        child = subprocess.run(
            [sys.executable, '-c', code],
            env={
                **os.environ,
                'PUB_DSN': dsn,
                'PUB_NS': r.handoff.ticket.namespace,
                'PUB_UID': r.uid,
                'PUB_ID': r.identity,
                'PUB_TOKEN': authority.token,
                'PUB_KIND': authority.kind,
                'PUB_ROOT': str(r.result[4].root),
                'PUB_CONVERSATION': r.conversation,
                'PUB_GAP': gap,
            },
            capture_output=True,
            timeout=45,
        )
        assert child.returncode == 86, child.stderr.decode()
        # Reuse the still-pinned actual unit; progress cancellation is resolved
        # by the same existing durable operation adapter before redelivery.
        gate = (
            r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION)
            .document(r.uid)
            .get()
            .to_dict()
        )
        if (gate.get('remote_target') or '').startswith('jobstore-erasure-v1:'):
            assert r.copies.operations.resolve(r.uid, gate['remote_target'])
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert not list(r.result[4].bucket('synthetic').list_blobs())
    assert not r.copies._reference(row(r.result)).get().exists
    assert row(r.result)['phase'] == 'published'


def test_actual_account_entrypoint_uses_exact_advanced_fs_generation(published):
    from database.batch_pipeline_purge import purge_batch_owner
    from database.privacy_fence.protocol import lock

    r = published
    r.handoff.fence.close(r.result[2].owner, reason='deleted', local=True)
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, r.result[2].owner, exclusive=True)
        conn.execute(
            "UPDATE privacy_owner_fence SET state='purging',close_reason='deleted',purge_generation=generation WHERE owner_key=%s",
            (r.result[2].owner,),
        )
    with r.unit() as authority:
        with pytest.raises(RetainedCopiesPending, match='complete ordinary source required'):
            purge_batch_owner(
                r.uid,
                firestore_client=r.handoff.client,
                namespaces=(r.handoff.ticket.namespace,),
                retained_copies=r.retained,
                destructive_authority=authority,
            )
    assert not list(r.result[4].bucket('synthetic').list_blobs())
    assert not r.copies._reference(row(r.result)).get().exists
    value = r.handoff.client.collection('batch_pipeline_privacy').document(r.result[2].owner).get().to_dict()
    assert value['purging'] and value['blocked']
    assert row(r.result)['phase'] == 'published'


def test_lost_reference_commit_reply_replays_without_dropping_custody(published, monkeypatch):
    r = published
    real = r.copies._check
    lost = []

    def check(*a, **k):
        real(*a, **k)
        if k.get('erase') and not lost:
            lost.append(True)
            raise ConnectionError('lost actual FS COMMIT reply')

    monkeypatch.setattr(r.copies, '_check', check)
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(ConnectionError, match='lost actual FS'):
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert row(r.result)['phase'] == 'published'
    with r.unit() as authority:
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert not r.copies._reference(row(r.result)).get().exists


def test_original_probe_refuses_dispatch_after_unit_deadline(published, monkeypatch):
    from database import rpc_deadline
    from utils.other.local_storage import LocalBlob

    r = published
    left = iter([1, -1])  # actual retention delete still has time; probe does not
    monkeypatch.setattr(rpc_deadline, 'remaining', lambda: next(left))
    monkeypatch.setattr(LocalBlob, 'reload', lambda *a, **k: pytest.fail('expired probe was dispatched'))
    with pytest.raises(ConnectionError, match='absence unresolved'):
        r.copies._absent(r.uid, row(r.result))
    monkeypatch.undo()  # restore the real clock before the assertion's FS RPC
    assert r.copies._reference(row(r.result)).get().exists
