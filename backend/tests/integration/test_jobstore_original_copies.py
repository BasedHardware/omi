"""Real source/PG/FS erasure boundaries; synthetic GCS transport, never C4."""

from types import SimpleNamespace

import pytest
from google.api_core.exceptions import NotFound

from database.batch_pipeline_conversation_purge import purge_conversation
from database.jobstore.authority import AuthorityRefused
from database.jobstore.erasure_operations import ErasureOperations, PREFIX
from database.jobstore.original_copies import OriginalCopies
from database.jobstore.retained_copies import RetainedCopiesPending
from database.privacy_fence.protocol import lock, owner_key
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_retained_copies import retained  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.parametrize('lane', [True], indirect=True)]


def unit(r):
    from database import legal_holds
    from database.conversation_batch_purge_jobs import GATE_KIND

    return legal_holds.bounded_destructive_unit(r.uid, kind=GATE_KIND, firestore_client=r.handoff.client)


@pytest.fixture
def objects(retained, monkeypatch):
    r = retained
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic')
    left, calls = set(), []
    for sid in ('one', 'two'):
        left.add((f'syncing/{r.uid}/audio/{sid}', 1))
        left.add((f'syncing/{r.uid}/result/{sid}', 2))

    class Bucket:
        def blob(self, path, *, generation):
            def delete(**kwargs):
                assert kwargs['if_generation_match'] == generation
                assert kwargs['retry'] is None
                # Actual retention helper must perform sink I/O without PG guards.
                with r.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                    lock(conn, owner_key(r.uid), exclusive=True)
                calls.append((path, generation))
                if (path, generation) not in left:
                    raise NotFound('original version absent')
                left.remove((path, generation))

            return SimpleNamespace(delete=delete)

    storage = SimpleNamespace(bucket=lambda name: Bucket())
    from utils.other import local_storage

    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: storage)
    return SimpleNamespace(left=left, calls=calls, storage=storage)


def progress(r):
    return SimpleNamespace(position={}, expired=lambda: False, unit=lambda: unit(r), settle_stuck=lambda _: None)


def prepared(r, authority):
    identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
    r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
    original = OriginalCopies(r.purge)
    row, _, uris = original._plan(r.uid, identity, r.conversation)
    operations = original.operations
    target = operations.prepare(
        r.uid,
        identity,
        authority,
        'object',
        dict(uri=uris[0], completion_hash=row['completion_hash']),
        conversation=r.conversation,
    )
    return operations, target


def test_actual_entrypoint_erases_original_versions_and_metadata_but_not_pg_or_journal(retained, objects):
    r = retained
    with pytest.raises(RetainedCopiesPending, match='certification remains'):
        purge_conversation(
            r.uid, r.conversation, progress(r), firestore_client=r.handoff.client, retained_copies=r.purge
        )
    assert not objects.left and len(objects.calls) == 4
    for kind in ('intent', 'completion', 'receipt'):
        assert not r.handoff.ref(kind, r.view.identity).get().exists
    assert r.view.ref('intakes', r.view.identity).get().to_dict()['repair_lineage'] == 'synthetic-original'
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            "SELECT purpose,state,count(*) FROM queue_original_erasure_operations WHERE namespace=%s "
            "GROUP BY purpose,state ORDER BY purpose",
            (r.handoff.ticket.namespace,),
        ).fetchall() == [('metadata', 'committed', 1), ('object', 'committed', 4)]
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == (2,)
        assert (
            conn.execute(
                'SELECT count(*) FROM queue_journal WHERE namespace=%s', (r.handoff.ticket.namespace,)
            ).fetchone()[0]
            > 0
        )
    # Same original versions are harmless after metadata removal. A recreated
    # name with another generation survives; no current-generation lookup.
    objects.left.add((f'syncing/{r.uid}/audio/one', 99))
    with pytest.raises(RetainedCopiesPending):
        purge_conversation(
            r.uid, r.conversation, progress(r), firestore_client=r.handoff.client, retained_copies=r.purge
        )
    assert objects.left == {(f'syncing/{r.uid}/audio/one', 99)}


def test_cancelled_operation_fences_paused_old_finish(retained):
    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        assert operations.resolve(r.uid, target)
        with pytest.raises(AuthorityRefused, match='cancelled'):
            operations.finish(r.uid, target, authority, conversation=r.conversation)
        assert operations.resolve(r.uid, target)
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM queue_original_erasure_operations WHERE namespace=%s',
            (r.handoff.ticket.namespace,),
        ).fetchone() == ('cancelled',)


def test_committed_operation_resolves_without_executing_again(retained):
    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        operations.finish(r.uid, target, authority, conversation=r.conversation)
        assert operations.resolve(r.uid, target)
        operations.finish(r.uid, target, authority, conversation=r.conversation)


def test_missing_foreign_and_unknown_operations_raise_never_return_false(retained):
    r = retained
    operations = ErasureOperations(r.purge)
    with pytest.raises(ConnectionError, match='not rollback proof'):
        operations.resolve(r.uid, PREFIX + r.handoff.ticket.namespace + ':' + '0' * 32)
    with pytest.raises(ConnectionError):
        operations.resolve(r.uid, 'gs://not-a-pg-operation')
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        with pytest.raises(ConnectionError, match='foreign'):
            operations.resolve('another-owner', target)


@pytest.mark.parametrize(
    'mutation',
    [
        "DELETE FROM queue_original_erasure_operations WHERE namespace=%s",
        "UPDATE queue_original_erasure_operations SET payload='{}' WHERE namespace=%s",
        "UPDATE queue_original_erasure_operations SET state='prepared' WHERE namespace=%s",
    ],
)
def test_sql_cannot_drop_or_rearm_resolved_barrier(retained, mutation):
    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        assert operations.resolve(r.uid, target)
    with r.handoff.pool.connection() as conn, pytest.raises(Exception, match='barrier|immutable'):
        with conn.transaction():
            lock(conn, owner_key(r.uid), exclusive=True)
            conn.execute(mutation, (r.handoff.ticket.namespace,))


def test_metadata_progress_cannot_precede_object_custody(retained):
    r = retained
    with unit(r) as authority:
        operations, _ = prepared(r, authority)
        row, manifest, uris = OriginalCopies(r.purge)._plan(r.uid, r.view.identity, r.conversation)
        with pytest.raises(AuthorityRefused, match='unresolved object custody'):
            operations.prepare(
                r.uid,
                r.view.identity,
                authority,
                'metadata',
                dict(paths=manifest['original_paths'][:3], uris=uris, completion_hash=row['completion_hash']),
                conversation=r.conversation,
            )


@pytest.mark.parametrize('committed', [False, True])
def test_pg_transport_errors_keep_real_gate_until_definitive_retry(retained, monkeypatch, committed):
    from contextlib import contextmanager
    from database import legal_holds
    import psycopg

    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        real_connection = r.handoff.pool.connection
        lost = []

        class LostReply:
            def __init__(self, conn):
                self.conn, self.updated = conn, False

            def __getattr__(self, name):
                return getattr(self.conn, name)

            def execute(self, query, *a, **k):
                result = self.conn.execute(query, *a, **k)
                self.updated |= "UPDATE queue_original_erasure_operations SET state='committed'" in query
                return result

            @contextmanager
            def transaction(self):
                with self.conn.transaction():
                    yield
                    if self.updated and not lost and not committed:
                        lost.append(True)
                        raise psycopg.OperationalError('lost before COMMIT')
                if self.updated and not lost:
                    lost.append(True)
                    raise psycopg.OperationalError('lost COMMIT reply')

        @contextmanager
        def connection(**kwargs):
            with real_connection(**kwargs) as conn:
                yield LostReply(conn)

        monkeypatch.setattr(r.handoff.pool, 'connection', connection)
        with pytest.raises(ConnectionError, match='PG outcome unresolved'):
            authority.remote(
                lambda: operations.finish(r.uid, target, authority, conversation=r.conversation), target=target
            )
        assert lost and not authority.unresolved
        gate = (
            r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION)
            .document(r.uid)
            .get()
            .to_dict()
        )
        assert not gate['remote_inflight']
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM queue_original_erasure_operations WHERE namespace=%s',
            (r.handoff.ticket.namespace,),
        ).fetchone() == ('committed',)


@pytest.mark.parametrize('gap', ['before_commit', 'after_commit'])
def test_abrupt_pg_exit_recovery_cancels_or_observes_real_commit_before_gate_takeover(retained, gap):
    import os
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from database import legal_holds
    from database.conversation_batch_purge_jobs import RunProgress

    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        token = authority.token
    legal_holds.acquire_destructive_operation(
        r.uid,
        kind='explicit_memory_deletion',
        token=token,
        firestore_client=r.handoff.client,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    with r.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = """
import os
from contextlib import contextmanager
import testing.pipeline_sim._env
from database import legal_holds
from database.jobstore.connection import Pool
from database.jobstore.authority import Epoch
from database.jobstore.handoff import Handoff
from database.jobstore.retained_copies import RetainedCopies
from database.jobstore.erasure_operations import ErasureOperations
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_ERASE_DSN'],size=2)
connect=pool._connect
class ExitAtCommit:
    def __init__(self,conn):self.conn,self.updated=conn,False
    def __getattr__(self,name):return getattr(self.conn,name)
    def execute(self,query,*a,**k):
        result=self.conn.execute(query,*a,**k)
        if "UPDATE queue_original_erasure_operations SET state='committed'" in query:
            self.updated=True
            if os.environ['OMI_ERASE_GAP']=='before_commit':os._exit(86)
        return result
    @contextmanager
    def transaction(self):
        with self.conn.transaction():yield
        if self.updated:os._exit(86)
pool._connect=lambda:ExitAtCommit(connect())
client=_emulator_client()
handoff=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_ERASE_NS'],3))
operations=ErasureOperations(RetainedCopies(handoff))
uid,cid,target=os.environ['OMI_ERASE_UID'],os.environ['OMI_ERASE_CID'],os.environ['OMI_ERASE_TARGET']
authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_ERASE_TOKEN'],client,None)
authority.remote(lambda:operations.finish(uid,target,authority,conversation=cid),target=target)
raise AssertionError('did not exit at COMMIT')
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_ERASE_DSN': dsn,
            'OMI_ERASE_GAP': gap,
            'OMI_ERASE_UID': r.uid,
            'OMI_ERASE_CID': r.conversation,
            'OMI_ERASE_NS': r.handoff.ticket.namespace,
            'OMI_ERASE_TARGET': target,
            'OMI_ERASE_TOKEN': token,
        },
    )
    assert result.returncode == 86, result.stderr
    gate_ref = r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(r.uid)
    assert gate_ref.get().to_dict()['remote_inflight']
    # Expiry alone cannot take over an unknown operation.
    gate_ref.update(
        {
            'expires_at': datetime.now(timezone.utc) - timedelta(seconds=60),
            'remote_inflight_at': datetime.now(timezone.utc) - timedelta(seconds=60),
        }
    )
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with unit(r):
            pytest.fail('unknown PG operation allowed gate takeover')
    # Actual production progress recovery clears only after a durable barrier.
    RunProgress.settle_stuck(SimpleNamespace(uid=r.uid), lambda value: operations.resolve(r.uid, value))
    with unit(r) as successor:
        assert successor.token != token
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM queue_original_erasure_operations WHERE namespace=%s',
            (r.handoff.ticket.namespace,),
        ).fetchone() == ('committed' if gap == 'after_commit' else 'cancelled',)
    with (
        pytest.raises(AuthorityRefused, match='cancelled')
        if gap == 'before_commit'
        else __import__('contextlib').nullcontext()
    ):
        operations.finish(r.uid, target, authority, conversation=r.conversation)
    assert r.handoff.ref('intent', r.view.identity).get().exists


def test_account_metadata_requires_exact_original_fs_generation(retained, objects):
    from database.batch_pipeline_privacy import advance_privacy_generation

    r = retained
    r.handoff.fence.close(owner_key(r.uid), reason='deleted', local=True)
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, owner_key(r.uid), exclusive=True)
        conn.execute(
            "UPDATE privacy_owner_fence SET state='purging',close_reason='deleted',purge_generation=generation "
            "WHERE owner_key=%s",
            (owner_key(r.uid),),
        )
    with unit(r) as authority:
        generation = advance_privacy_generation(r.handoff.client, r.uid, blocked=True, fence=authority.fence)
        identity, manifest = r.purge.inventory(r.uid)[0]
        r.purge.retire_private(r.uid, identity, manifest, authority, fs_generation=generation)
        r.handoff.client.collection('batch_pipeline_privacy').document(owner_key(r.uid)).update(
            {'generation': generation + 1}
        )
        with pytest.raises(AuthorityRefused, match='account purge must still be active'):
            OriginalCopies(r.purge, storage_client=objects.storage).retire(
                r.uid, identity, authority, fs_generation=generation
            )
    assert r.handoff.ref('intent', r.view.identity).get().exists
    assert r.view.ref('intakes', r.view.identity).get().exists


def test_pg_recovery_lock_timeout_is_unresolved_not_rollback_proof(retained):
    from database import legal_holds

    r = retained
    with unit(r) as authority:
        operations, target = prepared(r, authority)
        with r.handoff.pool.connection() as blocker, blocker.transaction():
            lock(blocker, owner_key(r.uid), exclusive=True)
            assert not legal_holds.settles_unknown_erasure(lambda: operations.resolve(r.uid, target))
        with r.handoff.pool.connection() as conn:
            assert conn.execute(
                'SELECT state FROM queue_original_erasure_operations WHERE namespace=%s',
                (r.handoff.ticket.namespace,),
            ).fetchone() == ('prepared',)
        assert operations.resolve(r.uid, target)
