"""Typed provider completion through real conversation/usage/ledger transactions."""

from types import SimpleNamespace

import pytest

from database.jobstore.authority import AuthorityRefused
from database.jobstore.provider_projection import ProviderProjection
from tests.integration.test_jobstore_handoff import context  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def lane(context, monkeypatch):
    from config.policy import BatchUnitPolicy
    from database import _client, conversations, llm_usage
    from database.batch_pipeline_intake import admit
    from database.batch_pipeline_store import FirestoreStore
    from database.jobstore.provider_handoff import ProviderHandoff
    from database.sync_ledger import sync_content_ledger_ref
    from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, WorkResult, Priority
    from utils.batch_pipeline.projection import Projector
    from utils.sync import reprocess
    from utils.sync.capture import chunk_identity
    import fakeredis
    from utils import fair_use

    handoff, uid = context
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.setenv('SYNC_BACKFILL_ROUTING_ENABLED', 'false')
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    client = handoff.client
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'standard'})
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *a, **k: 'pro')
    monkeypatch.setattr(fair_use, 'redis_client', fakeredis.FakeRedis())
    monkeypatch.setattr(fair_use, 'FAIR_USE_ENABLED', True)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations, '_delete_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(
        conversations,
        'get_conversation',
        lambda owner, cid: client.collection('users')
        .document(owner)
        .collection('conversations')
        .document(cid)
        .get()
        .to_dict(),
    )
    tasks, published = [], []
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: tasks.append(row))
    store = FirestoreStore(handoff.ticket.namespace, firestore_client=client)
    binding = ProjectionBinding(
        uid, 'recording', 'content', ('one', 'two'), language='ja', data_protection_level='standard'
    )
    items = [
        WorkItem(
            sid,
            uid,
            1000 + i * 30,
            f'encrypted://audio/{sid}',
            30,
            Priority.DEEP,
            conversation_id=chunk_identity(uid, 'omi', None, False, 1000 + i * 30),
            privacy_generation=0,
        )
        for i, sid in enumerate(binding.segment_ids)
    ]
    policy = BatchUnitPolicy(
        batch_enabled=True,
        batch_percent=100,
        stt_route='provider',
        provider_reason='unsupported_language',
        provider_service='modulate',
    )
    plan = {sid: dict(fresh=True, owner_turn=i, custody_deadline=20000) for i, sid in enumerate(binding.segment_ids)}
    assert (
        admit(
            store,
            items,
            binding,
            200,
            namespace=store.namespace,
            policy=policy,
            handoff=handoff,
            provider_plan=plan,
            intake={'owner_id': uid, 'segment_ids': list(binding.segment_ids), 'repair_lineage': 'synthetic-original'},
        )['outcome']
        == 'batch'
    )
    adapter = ProviderHandoff(handoff)
    adapter.deliver('recording')
    for unit in adapter.units.claim(2, now=201, lease_seconds=30, backlog_share=0):
        assert adapter.units.settle(
            unit['unit_id'],
            unit['attempt_token'],
            'result_ready',
            WorkResult(unit['unit_id'], f'encrypted://result/{unit["unit_id"]}').to_dict(),
            now=202,
            partial_wait=30,
        )
    from database.batch_pipeline_projection import ProjectionStore

    view = ProjectionStore.for_provider_handoff(handoff, 'recording')
    payload = {
        'words': [
            {'word': 'We', 'timestamp': [0.0, 1.0]},
            {'word': 'discussed', 'timestamp': [1.0, 2.0]},
            {'word': 'the', 'timestamp': [2.0, 3.0]},
            {'word': 'project.', 'timestamp': [3.0, 4.0]},
        ],
        'diarization': {'turns': [{'start': 0.0, 'end': 10.0, 'speaker': 'SPEAKER_00'}]},
        'audio_seconds': 30,
        'speech_seconds': 4.0,
        'words_provider': 'modulate',
    }
    projector = Projector(
        view.store,
        lambda *_: payload,
        projection_store=view,
        publish=lambda b, r: published.append(r),
        clock=lambda: 10000.0,
    )
    ledger = sync_content_ledger_ref(client, uid, 'content')
    return SimpleNamespace(**locals())


def test_real_assignment_grouped_usage_receipt_and_ack_replay(lane):
    x = lane
    assert x.view.prepare()
    assert not x.view.prepare()
    assert x.projector.project('one') is None
    result = x.projector.project('two')
    assert result and result['new_memories']
    ledger = x.ledger.get().to_dict()
    assert ledger['status'] == 'completed' and ledger['usage_committed_seconds'] == 8
    receipt = x.handoff.ref('receipt', 'recording').get().to_dict()
    assert receipt['result'] == result
    rows = [s.to_dict() for s in x.user.collection('conversations').stream() if s.id != 'c']
    assert rows
    segments = [
        seg
        for row in rows
        for seg in x.conversations.decode_transcript_segments_verified(
            x.uid, row.get('transcript_segments'), bool(row.get('transcript_segments_compressed'))
        )
    ]
    assert len(segments) == 2
    assert all(seg['text'] == 'We discussed the project.' for seg in segments)
    assert x.projector.project('two') == result
    assert x.ledger.get().to_dict()['usage_committed_seconds'] == 8
    assert x.view.ack(now=10001)
    assert not x.view.ack(now=10002)
    with x.handoff.pool.connection() as conn:
        assert x.handoff._required_row(conn, 'recording')['phase'] == 'acked'
        assert conn.execute(
            'SELECT projection_state FROM recordings WHERE namespace=%s', (x.store.namespace,)
        ).fetchone() == ('projected',)
        assert conn.execute(
            "SELECT count(*) FROM queue_custody WHERE namespace=%s AND phase='acked'", (x.store.namespace,)
        ).fetchone() == (2,)
        assert conn.execute(
            "SELECT count(*) FROM outbox WHERE namespace=%s AND done_at=10001 AND done_reason='projected'",
            (x.store.namespace,),
        ).fetchone() == (1,)
    for suffix in ('jobs', 'results', 'owners', 'control'):
        assert not x.client.collection(x.store.namespace + '_' + suffix).limit(1).get()
    assert 'expires_at' not in x.view.ref('jobs', 'one').get().to_dict()
    assert not x.view.prepare()


def test_missing_published_sibling_never_reconstructed(lane):
    lane.view.prepare()
    lane.view.ref('results', 'two').delete()
    with pytest.raises(AuthorityRefused, match='sibling view'):
        lane.view.prepare()
    assert not lane.view.ref('results', 'two').get().exists


def finish(lane):
    lane.view.prepare()
    assert lane.projector.project('one') is None
    return lane.projector.project('two')


def test_out_of_order_projection_refuses_then_ordered_replay_finishes(lane):
    from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending

    lane.view.prepare()
    with pytest.raises(ProjectionPredecessorPending):
        lane.projector.project('two')
    assert not lane.handoff.ref('receipt', 'recording').get().exists
    assert lane.projector.project('one') is None
    assert lane.projector.project('two')


def test_receipt_failure_rolls_back_customer_completion_and_usage(lane, monkeypatch):
    lane.view.prepare()
    lane.projector.project('one')
    original = lane.view._write_completion_receipt

    def killed(*args):
        original(*args)
        raise RuntimeError('before customer completion COMMIT')

    monkeypatch.setattr(lane.view, '_write_completion_receipt', killed)
    with pytest.raises(RuntimeError, match='customer completion COMMIT'):
        lane.projector.project('two')
    before = lane.ledger.get().to_dict()
    assert before['status'] == 'processing' and 'usage_committed_seconds' not in before
    assert not lane.handoff.ref('receipt', 'recording').get().exists
    monkeypatch.setattr(lane.view, '_write_completion_receipt', original)
    assert lane.projector.project('two')
    assert lane.ledger.get().to_dict()['usage_committed_seconds'] == 8


def test_grouped_ack_rolls_back_all_rows_on_unknown_commit(lane, monkeypatch):
    finish(lane)
    original = lane.handoff.ack_in_transaction

    def killed(*args):
        original(*args)
        raise RuntimeError('before grouped ack COMMIT')

    monkeypatch.setattr(lane.handoff, 'ack_in_transaction', killed)
    with pytest.raises(RuntimeError, match='grouped ack COMMIT'):
        lane.view.ack(now=10001)
    with lane.handoff.pool.connection() as conn:
        assert lane.handoff._required_row(conn, 'recording')['phase'] == 'completed'
        assert conn.execute(
            "SELECT projection_state FROM recordings WHERE namespace=%s", (lane.store.namespace,)
        ).fetchone() == ('pending',)
        assert conn.execute(
            "SELECT count(*) FROM queue_custody WHERE namespace=%s AND phase='completed'", (lane.store.namespace,)
        ).fetchone() == (2,)
        assert conn.execute("SELECT done_at FROM outbox WHERE namespace=%s", (lane.store.namespace,)).fetchone() == (
            None,
        )
    monkeypatch.setattr(lane.handoff, 'ack_in_transaction', original)
    assert lane.view.ack(now=10001)


def test_projection_refuses_real_account_privacy_change(lane):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    lane.view.prepare()
    lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'pending'})
    with pytest.raises(BatchPrivacyBlocked):
        lane.projector.project('one')
    assert lane.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.handoff.ref('receipt', 'recording').get().exists


def test_restore_cannot_readmit_old_paid_completion_for_projection(lane):
    from database.privacy_fence import FenceRefused

    lane.handoff.fence.close(lane.view.packet['owner_key'], local=True)
    # A fresh authority walk may restore the owner, but it cannot make the old
    # paid recording's admission current. No original result is re-adopted.
    lane.handoff.fence.admit_from_authority(
        lane.client, lane.uid, lane.view.packet['intent']['conversation_ids'], lambda *_: None
    )
    with pytest.raises(FenceRefused):
        lane.view.prepare()
    assert not lane.handoff.ref('completion', 'recording').get().exists


def test_f_rotation_after_fresh_e1_admission_is_still_fenced(lane, monkeypatch):
    from uuid import uuid4

    lane.view.prepare()
    original = lane.view._e1_admission

    def rotate():
        admission = original()
        lane.client.collection('batch_pipeline_privacy').document(lane.view.packet['owner_key']).update(
            {'memo_token': uuid4().hex}
        )
        return admission

    monkeypatch.setattr(lane.view, '_e1_admission', rotate)
    with pytest.raises(AuthorityRefused, match='token changed'):
        lane.projector.project('one')
    assert not lane.handoff.ref('receipt', 'recording').get().exists


def test_forged_sibling_view_cannot_bill_or_assign(lane):
    lane.view.prepare()
    lane.view.ref('results', 'two').update({'result': {'segment_id': 'two', 'result_uri': 'encrypted://foreign'}})
    with pytest.raises(AuthorityRefused, match='sibling view'):
        lane.projector.project('one')
    assert lane.ledger.get().to_dict()['status'] == 'processing'


def test_generic_projection_callback_cannot_complete_typed_provider(lane):
    lane.view.prepare()
    with pytest.raises(AuthorityRefused, match='concrete customer projection'):
        lane.handoff.project('recording', lambda *_: pytest.fail('generic callback ran'))


def test_manifest_preserves_original_deadlines_and_pool_guards_end_before_fs(lane, monkeypatch):
    from database.privacy_fence.protocol import lock

    lane.view.prepare()
    owner = lane.view.packet['owner_key']
    manifest = lane.view.ref('owners', owner).get().to_dict()['retained_copy_manifest']
    assert {row['original_custody_deadline'] for row in manifest if 'unit_id' in row} == {20000}
    assert {row['path'] for row in manifest if 'unit_id' in row} == {
        lane.view.ref(t, s).path for s in ('one', 'two') for t in ('jobs', 'results')
    }
    original = lane.handoff.authority.check
    seen = []

    def check(*args, **kwargs):
        with lane.handoff.pool.connection(timeout=2) as first, lane.handoff.pool.connection(timeout=2) as second:
            with first.transaction():
                lock(first, owner, exclusive=True)
                assert second.execute('SELECT 1').fetchone() == (1,)
                seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(lane.handoff.authority, 'check', check)
    assert lane.projector.project('one') is None
    assert seen


def test_generic_publication_and_ack_cannot_skip_recording_protocol(lane):
    with pytest.raises(AuthorityRefused, match='concrete completion publication'):
        lane.handoff.export('recording')
    finish(lane)
    with pytest.raises(AuthorityRefused, match='grouped acknowledgement'):
        lane.handoff.ack('recording')
    assert lane.view.ack(now=10001)


@pytest.mark.parametrize(
    'gap', ['before_customer_commit', 'after_customer_commit', 'before_ack_commit', 'after_ack_commit']
)
def test_customer_completion_and_grouped_ack_survive_process_exit(lane, monkeypatch, gap):
    import os
    import subprocess
    import sys

    lane.view.prepare()
    lane.projector.project('one')
    if 'customer' in gap:
        original = lane.view.complete

        def stop(*args, **kwargs):
            raise RuntimeError('pause before customer completion')

        monkeypatch.setattr(lane.view, 'complete', stop)
        with pytest.raises(RuntimeError, match='pause before'):
            lane.projector.project('two')
        monkeypatch.setattr(lane.view, 'complete', original)
    else:
        assert lane.projector.project('two')
    with lane.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = '''
import os
import testing.pipeline_sim._env
from database.jobstore import codec
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.provider_projection import ProviderProjection
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_PROJECTION_CHILD_DSN'],size=2)
gap=os.environ['OMI_PROJECTION_CHILD_GAP']
if gap=='before_ack_commit':
    original=pool._connect
    class ExitBeforeCommit:
        def __init__(self,conn):self.conn=conn
        def __getattr__(self,name):return getattr(self.conn,name)
        def execute(self,query,*args,**kwargs):
            result=self.conn.execute(query,*args,**kwargs)
            if 'UPDATE outbox SET done_at=' in query:os._exit(86)
            return result
    pool._connect=lambda:ExitBeforeCommit(original())
client=_emulator_client()
handoff=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_PROJECTION_CHILD_NS'],3))
view=ProviderProjection(handoff,'recording')
if 'customer' in gap:
    if gap=='before_customer_commit':
        original=view._write_completion_receipt
        def killed(*args):
            original(*args)
            os._exit(86)
        view._write_completion_receipt=killed
    else:
        view._mirror=lambda *args:os._exit(86)
    from database import llm_usage
    llm_usage.resolve_usage_plan_id=lambda *a,**k:'pro'
    accounting=view.prepare_accounting(view.binding,10000)
    view.complete('two',view.binding,10000,accounting)
else:
    view.ack(now=10001)
os._exit(86)
'''
    result = subprocess.run(
        [sys.executable, '-c', command],
        env={
            **os.environ,
            'OMI_PROJECTION_CHILD_DSN': dsn,
            'OMI_PROJECTION_CHILD_GAP': gap,
            'OMI_PROJECTION_CHILD_NS': lane.store.namespace,
        },
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 86, result.stderr
    if 'customer' in gap:
        completed = gap.startswith('after')
        assert (lane.ledger.get().to_dict()['status'] == 'completed') == completed
        assert lane.handoff.ref('receipt', 'recording').get().exists == completed
        # Abrupt client death leaves Firestore's server-side read lease alive.
        # A task delivery may exhaust its existing bounded contention policy.
        # Redeliver the durable recording (at most three deliveries), keeping
        # that policy and its deadlines unchanged; never resend paid work.
        from database.firestore_transaction_retry import FirestoreContentionExhausted

        for delivery in range(3):
            try:
                assert lane.projector.project('two')
                break
            except FirestoreContentionExhausted:
                assert gap == 'before_customer_commit'
                assert lane.ledger.get().to_dict()['status'] == 'processing'
                assert not lane.handoff.ref('receipt', 'recording').get().exists
        else:
            pytest.fail('server transaction lease outlived three bounded recording deliveries')
    else:
        with lane.handoff.pool.connection() as conn:
            assert (lane.handoff._required_row(conn, 'recording')['phase'] == 'acked') == gap.startswith('after')
    lane.view.ack(now=10002)
    assert lane.ledger.get().to_dict()['usage_committed_seconds'] == 8
    with lane.handoff.pool.connection() as conn:
        assert lane.handoff._required_row(conn, 'recording')['phase'] == 'acked'
        assert conn.execute(
            "SELECT count(*) FROM queue_custody WHERE namespace=%s AND phase='acked'", (lane.store.namespace,)
        ).fetchone() == (2,)
        assert conn.execute(
            "SELECT count(*) FROM outbox WHERE namespace=%s AND done_at IS NOT NULL", (lane.store.namespace,)
        ).fetchone() == (1,)


def test_direct_sql_cannot_ack_only_the_typed_handoff(lane):
    finish(lane)
    with lane.handoff.pool.connection() as conn, pytest.raises(Exception, match='grouped acknowledgement required'):
        with conn.transaction():
            lane.handoff._guard(conn, lane.handoff._required_row(conn, 'recording'))
            conn.execute(
                "UPDATE queue_handoffs SET phase='acked',projection_receipt='forged-alone' WHERE namespace=%s AND identity='recording'",
                (lane.store.namespace,),
            )
    with lane.handoff.pool.connection() as conn:
        assert lane.handoff._required_row(conn, 'recording')['phase'] == 'completed'
    assert lane.view.ack(now=10001)


def test_private_view_reads_stay_within_declared_per_attempt_budget(lane, monkeypatch):
    from collections import Counter
    from google.cloud.firestore_v1.document import DocumentReference

    counts = Counter()
    unscoped = 0
    original = DocumentReference.get

    def get(ref, *args, **kwargs):
        nonlocal unscoped
        value = original(ref, *args, **kwargs)
        family = ref.parent.id
        if family in {'jobstore_handoffs', lane.store.namespace + '_intakes'}:
            transaction = kwargs.get('transaction')
            if transaction is None:
                unscoped += 1
                key = ('unscoped', unscoped)
            else:
                key = transaction.id
            counts[family, key] += 1
        return value

    monkeypatch.setattr(DocumentReference, 'get', get)
    finish(lane)
    lane.view.ack(now=10001)
    assert counts
    assert (
        max(count for (family, _), count in counts.items() if family == 'jobstore_handoffs')
        <= 7 * len(lane.binding.segment_ids) + 20
    )
    assert max(count for (family, _), count in counts.items() if family.endswith('_intakes')) <= 3


def test_customer_writer_scope_reaches_actual_sdk_commit_and_resets(lane, monkeypatch):
    from database.batch_privacy_write_fence import g2_coordinator
    from database.privacy_fence.interceptor import Coordinator
    from database.privacy_fence.protocol import lock

    requests = []
    original = Coordinator.prepare

    def inspect(coordinator, request):
        # Neither a pool slot nor an owner guard spans the original FS RPC.
        with lane.handoff.pool.connection(timeout=2) as one, lane.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                lock(one, lane.view.packet['owner_key'], exclusive=True)
                assert two.execute('SELECT 1').fetchone() == (1,)
        requests.append([w.update.name or w.delete or w.transform.document for w in request.writes])
        return original(coordinator, request)

    monkeypatch.setattr(Coordinator, 'prepare', inspect)
    previous = g2_coordinator.get()
    assert finish(lane)
    assert g2_coordinator.get() is previous
    assert any(any('/conversations/' in path for path in paths) for paths in requests)
    assert any(lane.handoff.ref('receipt', 'recording')._document_path in paths for paths in requests)
    with pytest.raises(RuntimeError):
        with lane.view.writer_scope():
            assert isinstance(g2_coordinator.get(), Coordinator)
            raise RuntimeError('scope failure')
    assert g2_coordinator.get() is previous
