"""Actual staging registration, FS custody seal and destructive PG COMMIT units."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from database.jobstore.authority import AuthorityRefused, transition
from database.jobstore.cold_sink import ColdSink
from database.jobstore.original_copies import OriginalCopies
from database.jobstore.postgres_store import jsonb
from database.jobstore.retained_copies import RetainedCopiesPending
from database.jobstore.staging_copies import StagingCopies
from database.jobstore.staging_operations import PREFIX, StagingOperations
from database.privacy_fence.protocol import conversation_key, lock, owner_key
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_original_copies import objects, unit, progress  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.parametrize('lane', [True], indirect=True)]


@pytest.fixture
def retained(lane):
    from database import batch_pipeline_privacy_queries as queries
    from database.batch_pipeline_purge import retained_provider_copies
    from utils.batch_pipeline.contracts import WorkItem
    from utils.batch_pipeline.retention import register_batch_artifact

    x = lane
    x.view.prepare()
    with x.handoff.pool.connection() as conn:
        source = x.handoff._required_row(conn, x.view.identity)
    refs = []
    for sid in ('one', 'two'):
        job = source['intent']['payload']['jobs'][sid]
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        uris = [item.audio_uri.split('#')[0]]
        if sid == 'one':
            uris.append(f'gs://synthetic/syncing/{x.uid}/late/one')
        for uri in uris:
            key = register_batch_artifact(x.store, x.uid, sid, uri, 'audio', item.privacy_generation, item=item)
            refs.append(x.client.collection(x.store.namespace + '_artifacts').document(key))
    original_values = [(ref.id, ref.get().to_dict()) for ref in refs]
    with x.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, owner_key(x.uid), exclusive=True)
        conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
        for key, value in original_values:
            conn.execute(
                "INSERT INTO docs(namespace,tbl,key,doc) VALUES (%s,'artifacts',%s,%s)",
                (x.store.namespace, key, jsonb(value)),
            )
    # The fixture registers real production receipts while P is open, then
    # begins the actual erasure prerequisite. No runnable FS jobs are created.
    cid = source['intent']['conversation_ids'][0]
    x.client.document(f'users/{x.uid}/deleted_conversations/{cid}').set({'id': cid})
    x.handoff.fence.close(
        owner_key(x.uid), conversation=conversation_key(owner_key(x.uid), cid), state='deleted', local=True
    )
    assert sum(len(queries.segment_artifacts(x.client, x.store.namespace, sid, None)) for sid in ('one', 'two')) == 3
    return SimpleNamespace(
        view=x.view,
        handoff=x.handoff,
        uid=x.uid,
        conversation=cid,
        purge=retained_provider_copies(x.handoff),
        artifacts=refs,
    )


def prepared(r, authority):
    identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
    r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
    OriginalCopies(r.purge).retire(r.uid, identity, authority, conversation=r.conversation)
    stage = StagingCopies(r.purge)
    target = stage.prepare(r.uid, identity, authority, conversation=r.conversation)
    return stage, target


def copies(r):
    with r.handoff.pool.connection() as conn:
        return conn.execute(
            "SELECT count(*) FROM docs WHERE namespace=%s AND tbl='artifacts'", (r.handoff.ticket.namespace,)
        ).fetchone()[0]


def test_actual_conversation_entrypoint_retires_redundant_pg_copies_but_keeps_unique_custody(retained, objects):
    from database.batch_pipeline_conversation_purge import purge_conversation

    r = retained
    with pytest.raises(RetainedCopiesPending):
        purge_conversation(
            r.uid, r.conversation, progress(r), firestore_client=r.handoff.client, retained_copies=r.purge
        )
    assert copies(r) == 0 and not objects.left
    assert all(ref.get().to_dict()['erasure_requested'] for ref in r.artifacts)
    assert r.view.ref('intakes', r.view.identity).get().to_dict()['repair_lineage'] == 'synthetic-original'
    with r.handoff.pool.connection() as conn:
        manifest = conn.execute(
            'SELECT manifest FROM queue_staging_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone()[0]
        assert len(manifest['artifacts']) == 3 and manifest['original_deadlines'] == {'one': 20000, 'two': 20000}
        assert 'repair_lineage' not in str(manifest) and 'synthetic-original' not in str(manifest)
        assert any(a['uri'].endswith('/late/one') for a in manifest['artifacts'])
        assert conn.execute(
            'SELECT state FROM queue_staging_erasure_operations WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == ('committed',)
        seqs = conn.execute(
            'SELECT seq FROM queue_journal WHERE namespace=%s ORDER BY seq', (r.handoff.ticket.namespace,)
        ).fetchall()
        assert [x[0] for x in seqs] == list(range(1, len(seqs) + 1))
        assert conn.execute(
            "SELECT count(*) FROM queue_journal WHERE namespace=%s AND family='docs' AND operation='delete'",
            (r.handoff.ticket.namespace,),
        ).fetchone() == (3,)
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == (2,)
    # Every source version is covered by actual cold erasure, even the new
    # destructive DELETE journal entries. Never turn erased copies into jobs.
    with r.handoff.pool.connection() as conn, conn.transaction():
        conn.execute(
            'UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (r.handoff.ticket.namespace,)
        )
    assert ColdSink(r.handoff).page(limit=100) == len(seqs)
    with pytest.raises(RetainedCopiesPending):
        purge_conversation(
            r.uid, r.conversation, progress(r), firestore_client=r.handoff.client, retained_copies=r.purge
        )
    assert copies(r) == 0 and r.view.ref('intakes', r.view.identity).get().exists


def test_cancelled_destructive_unit_fences_paused_old_executor(retained, objects):
    r = retained
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        assert stage.operations.resolve(r.uid, target)
        with pytest.raises(AuthorityRefused, match='cancelled'):
            stage.execute(r.uid, target, authority, conversation=r.conversation)
    assert copies(r) == 3


@pytest.mark.parametrize('changed', ['intake', 'artifact', 'marker'])
def test_missing_or_changed_unique_fs_custody_refuses_destructive_pg_unit(retained, objects, changed):
    r = retained
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        ref = (
            r.view.ref('intakes', r.view.identity)
            if changed == 'intake'
            else r.artifacts[0] if changed == 'artifact' else r.handoff.ref('staging_erasure', r.view.identity)
        )
        ref.delete()
        with pytest.raises(AuthorityRefused, match='missing|changed|custody'):
            stage.execute(r.uid, target, authority, conversation=r.conversation)
    assert copies(r) == 3


@pytest.mark.parametrize('mutation', ['delete_only', 'commit_only', 'recreate', 'census_delete'])
def test_raw_sql_cannot_split_destructive_delete_from_its_outcome_or_drop_custody(retained, objects, mutation):
    r = retained
    with unit(r) as authority:
        _, target = prepared(r, authority)
        operation = target.split(':')[-1]
        with r.handoff.pool.connection() as conn, pytest.raises(Exception, match='staging|unresolved|custody|fenced'):
            with conn.transaction():
                lock(conn, owner_key(r.uid), exclusive=True)
                conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
                conn.execute("SELECT set_config('omi.staging_erasure_operation',%s,true)", (operation,))
                if mutation == 'delete_only':
                    conn.execute(
                        "DELETE FROM docs WHERE namespace=%s AND tbl='artifacts'", (r.handoff.ticket.namespace,)
                    )
                elif mutation == 'commit_only':
                    conn.execute(
                        "UPDATE queue_staging_erasure_operations SET state='committed' WHERE namespace=%s",
                        (r.handoff.ticket.namespace,),
                    )
                elif mutation == 'recreate':
                    conn.execute(
                        "UPDATE docs SET doc=doc||'{\"new\":true}'::jsonb WHERE namespace=%s AND tbl='artifacts'",
                        (r.handoff.ticket.namespace,),
                    )
                else:
                    conn.execute(
                        'DELETE FROM queue_staging_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
                    )
    assert copies(r) == 3


def test_pg_copy_mismatch_rolls_back_all_deletes_and_outcome(retained, objects):
    r = retained
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, owner_key(r.uid), exclusive=True)
        conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
        conn.execute(
            "UPDATE docs SET doc=doc||'{\"different\":true}'::jsonb WHERE namespace=%s AND key=%s",
            (r.handoff.ticket.namespace, r.artifacts[-1].id),
        )
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        with pytest.raises(AuthorityRefused, match='differs'):
            authority.remote(
                lambda: stage.execute(r.uid, target, authority, conversation=r.conversation), target=target
            )
    assert copies(r) == 3
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM queue_staging_erasure_operations WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == ('prepared',)


def test_missing_operation_is_not_rollback_proof(retained):
    with pytest.raises(ConnectionError, match='missing'):
        StagingOperations(retained.purge).resolve(
            retained.uid, PREFIX + retained.handoff.ticket.namespace + ':' + '0' * 32
        )


def test_actual_fs_seal_and_verify_hold_no_pool_slots_or_owner_guards(retained, objects, monkeypatch):
    r = retained
    with unit(r) as authority:
        identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
        r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
        OriginalCopies(r.purge).retire(r.uid, identity, authority, conversation=r.conversation)
        real = r.handoff.authority.check
        seen = []

        def check(*a, **k):
            with r.handoff.pool.connection(timeout=2) as one, r.handoff.pool.connection(timeout=2) as two:
                with one.transaction():
                    lock(one, owner_key(r.uid), exclusive=True)
                    assert two.execute('SELECT 1').fetchone() == (1,)
                    seen.append(True)
            return real(*a, **k)

        monkeypatch.setattr(r.handoff.authority, 'check', check)
        StagingCopies(r.purge).retire_mirrors(r.uid, identity, authority, conversation=r.conversation)
        assert len(seen) >= 4
    assert copies(r) == 0


@pytest.mark.parametrize('committed', [False, True])
def test_lost_pg_commit_reply_keeps_real_gate_until_definitive_redelivery(retained, objects, monkeypatch, committed):
    import psycopg
    from database import legal_holds

    r = retained
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        real = r.handoff.pool.connection
        lost = []

        class Lost:
            def __init__(self, conn):
                self.conn, self.updated = conn, False

            def __getattr__(self, name):
                return getattr(self.conn, name)

            def execute(self, query, *a, **k):
                value = self.conn.execute(query, *a, **k)
                self.updated |= "UPDATE queue_staging_erasure_operations SET state='committed'" in query
                return value

            @contextmanager
            def transaction(self):
                with self.conn.transaction():
                    yield
                    if self.updated and not lost and not committed:
                        lost.append(True)
                        raise psycopg.OperationalError('lost before staging COMMIT')
                if self.updated and not lost:
                    lost.append(True)
                    raise psycopg.OperationalError('lost staging COMMIT reply')

        @contextmanager
        def connection(**kw):
            with real(**kw) as conn:
                yield Lost(conn)

        monkeypatch.setattr(r.handoff.pool, 'connection', connection)
        with pytest.raises(ConnectionError, match='outcome unresolved'):
            authority.remote(
                lambda: stage.execute(r.uid, target, authority, conversation=r.conversation), target=target
            )
        gate = r.handoff.client.document(f'{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{r.uid}').get().to_dict()
        assert lost and not authority.unresolved and not gate['remote_inflight']
    assert copies(r) == 0


@pytest.mark.parametrize('gap', ['before_commit', 'after_commit'])
def test_abrupt_destructive_pg_commit_resolves_before_actual_gate_takeover(retained, objects, gap):
    import os
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from database import legal_holds
    from database.conversation_batch_purge_jobs import RunProgress

    r = retained
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        operations = stage.operations
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
from database.jobstore.staging_operations import StagingOperations
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_ERASE_DSN'],size=2)
connect=pool._connect
class ExitAtCommit:
    def __init__(self,conn):self.conn,self.updated=conn,False
    def __getattr__(self,name):return getattr(self.conn,name)
    def execute(self,query,*a,**k):
        result=self.conn.execute(query,*a,**k)
        if "UPDATE queue_staging_erasure_operations SET state='committed'" in query:
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
operations=StagingOperations(RetainedCopies(handoff))
uid,cid,target=os.environ['OMI_ERASE_UID'],os.environ['OMI_ERASE_CID'],os.environ['OMI_ERASE_TARGET']
authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_ERASE_TOKEN'],client,None)
authority.remote(lambda:operations.execute(uid,target,authority,conversation=cid),target=target)
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
    from database.batch_pipeline_conversation_purge import PurgeCheckpointed, purge_conversation

    recovery = SimpleNamespace(
        position={},
        expired=lambda: True,
        unit=lambda: unit(r),
        settle_stuck=lambda resolve: RunProgress.settle_stuck(SimpleNamespace(uid=r.uid), resolve),
    )
    with pytest.raises(PurgeCheckpointed):
        purge_conversation(r.uid, r.conversation, recovery, firestore_client=r.handoff.client, retained_copies=r.purge)
    with unit(r) as successor:
        assert successor.token != token
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM queue_staging_erasure_operations WHERE namespace=%s',
            (r.handoff.ticket.namespace,),
        ).fetchone() == ('committed' if gap == 'after_commit' else 'cancelled',)
    with (
        pytest.raises(AuthorityRefused, match='cancelled')
        if gap == 'before_commit'
        else __import__('contextlib').nullcontext()
    ):
        operations.execute(r.uid, target, authority, conversation=r.conversation)
    assert copies(r) == (0 if gap == 'after_commit' else 3)
    assert r.view.ref('intakes', r.view.identity).get().exists
    assert all(ref.get().exists for ref in r.artifacts)
    with r.handoff.pool.connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM queue_journal WHERE namespace=%s AND family='docs' AND operation='delete'",
            (r.handoff.ticket.namespace,),
        ).fetchone()[0]
    assert count == (3 if gap == 'after_commit' else 0)


@pytest.mark.parametrize('gap', ['before', 'after'])
def test_actual_staging_seal_exit_preserves_unique_intake_and_all_pg_copies(retained, objects, gap):
    import os
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from database import legal_holds
    from google.api_core.exceptions import Aborted

    r = retained
    with unit(r) as authority:
        identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
        r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
        OriginalCopies(r.purge).retire(r.uid, identity, authority, conversation=r.conversation)
        token = authority.token
    legal_holds.acquire_destructive_operation(
        r.uid,
        kind='explicit_memory_deletion',
        token=token,
        firestore_client=r.handoff.client,
        now=datetime.now(timezone.utc) - timedelta(seconds=2 * legal_holds.UNIT_EXPIRY_SECONDS),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=legal_holds.UNIT_EXPIRY_SECONDS),
    )
    with r.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = """
import os
import testing.pipeline_sim._env
from google.cloud.firestore_v1.types import CommitRequest
from database import legal_holds
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.authority import Epoch
from database.jobstore.retained_copies import RetainedCopies
from database.jobstore.staging_copies import StagingCopies
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_STAGE_DSN'],size=2)
client=_emulator_client()
handoff=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_STAGE_NS'],3))
uid,cid=os.environ['OMI_STAGE_UID'],os.environ['OMI_STAGE_CID']
authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_STAGE_TOKEN'],client,None)
api=client._firestore_api
real=api.commit
def commit(*a,**k):
    request=CommitRequest(k.get('request') or a[0])
    sealing=any(w.update.name.endswith('/'+handoff.ref('staging_erasure','recording').id) for w in request.writes)
    if sealing and os.environ['OMI_STAGE_GAP']=='before':os._exit(86)
    result=real(*a,**k)
    if sealing:os._exit(86)
    return result
api.commit=commit
StagingCopies(RetainedCopies(handoff)).prepare(uid,'recording',authority,conversation=cid)
raise AssertionError('did not exit at staging COMMIT')
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_STAGE_DSN': dsn,
            'OMI_STAGE_NS': r.handoff.ticket.namespace,
            'OMI_STAGE_UID': r.uid,
            'OMI_STAGE_CID': r.conversation,
            'OMI_STAGE_TOKEN': token,
            'OMI_STAGE_GAP': gap,
        },
    )
    assert result.returncode == 86, result.stderr
    assert r.handoff.ref('staging_erasure', r.view.identity).get().exists == (gap == 'after')
    assert copies(r) == 3
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_staging_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == (0,)
    for _ in range(12):
        try:
            with unit(r) as successor:
                StagingCopies(r.purge).retire_mirrors(r.uid, r.view.identity, successor, conversation=r.conversation)
            break
        except (ValueError, Aborted) as error:
            assert gap == 'before' and (isinstance(error, Aborted) or isinstance(error.__cause__, Aborted))
    else:
        pytest.fail('abandoned staging read lease exceeded bounded redelivery')
    assert copies(r) == 0
    assert r.view.ref('intakes', r.view.identity).get().to_dict()['repair_lineage'] == 'synthetic-original'
    assert all(ref.get().exists for ref in r.artifacts)


def test_queue_epoch_change_refuses_old_destructive_operation(retained, objects):
    r = retained
    with unit(r) as authority:
        stage, target = prepared(r, authority)
        with r.handoff.pool.connection() as conn, conn.transaction():
            transition(conn, r.handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
        with pytest.raises(AuthorityRefused):
            stage.execute(r.uid, target, authority, conversation=r.conversation)
    assert copies(r) == 3


def test_closed_queue_allows_only_bound_artifact_delete_and_preserves_journal_prefix(retained, objects):
    from database.jobstore.handoff import Handoff
    from database.jobstore.retained_copies import RetainedCopies

    r = retained
    with unit(r) as authority:
        identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
        r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
        OriginalCopies(r.purge).retire(r.uid, identity, authority, conversation=r.conversation)
        with r.handoff.pool.connection() as conn, conn.transaction():
            ticket = transition(conn, r.handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
        # Synthetic phase prerequisite only; runtime close orchestration remains a gate.
        r.handoff.authority.ref.update({'epoch': 4, 'state': 'PG_CLOSING'})
        closed = Handoff(r.handoff.pool, r.handoff.fence, r.handoff.client, ticket)
        stage = StagingCopies(RetainedCopies(closed))
        target = stage.prepare(r.uid, identity, authority, conversation=r.conversation)
        authority.remote(lambda: stage.execute(r.uid, target, authority, conversation=r.conversation), target=target)
    assert copies(r) == 0
    with r.handoff.pool.connection() as conn:
        assert (
            conn.execute(
                'SELECT count(*) FROM queue_journal WHERE namespace=%s', (r.handoff.ticket.namespace,)
            ).fetchone()[0]
            > 3
        )


def test_original_intake_is_read_once_per_actual_seal_and_verify_attempt(retained, objects, monkeypatch):
    from google.cloud.firestore_v1.document import DocumentReference

    r = retained
    with unit(r) as authority:
        identity, manifest = r.purge.inventory(r.uid, r.conversation)[0]
        r.purge.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)
        OriginalCopies(r.purge).retire(r.uid, identity, authority, conversation=r.conversation)
        actual = DocumentReference.get
        reads = []
        intake = r.view.ref('intakes', r.view.identity).path

        def get(ref, *a, **k):
            if ref.path == intake:
                reads.append(k.get('transaction'))
            return actual(ref, *a, **k)

        monkeypatch.setattr(DocumentReference, 'get', get)
        stage = StagingCopies(r.purge)
        target = stage.prepare(r.uid, identity, authority, conversation=r.conversation)
        authority.remote(lambda: stage.execute(r.uid, target, authority, conversation=r.conversation), target=target)
        assert len(reads) == 2 and all(read is not None for read in reads)
    assert copies(r) == 0
