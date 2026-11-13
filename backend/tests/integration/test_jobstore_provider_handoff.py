"""Production admission -> typed provider units -> immutable terminal custody.

Both stores are real isolated backends. Provider calls and customer projection
are outside this proof: result references below are synthetic durable handles.
"""

from copy import deepcopy

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_store import FirestoreStore
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.provider_handoff import ProviderHandoff, validate_provider_payload
from database.jobstore.units import Units
from database.sync_ledger import sync_content_ledger_ref
from tests.integration.test_jobstore_handoff import context  # noqa: F401 -- shared real FS/PG fixture
from utils.batch_pipeline.contracts import ProjectionBinding, Priority, WorkItem, WorkResult

pytestmark = pytest.mark.integration


def upload(context, monkeypatch, *, count=2, **overrides):
    handoff, uid = context
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    store = FirestoreStore(handoff.ticket.namespace, firestore_client=handoff.client)
    segments = tuple(f'segment-{index}' for index in range(count))
    binding = ProjectionBinding(
        uid, 'provider-recording', 'provider-content', segments, language='ja', target_conversation_id='c'
    )
    items = [
        WorkItem(
            segment,
            uid,
            100 + i,
            f'encrypted://audio/{segment}',
            10,
            Priority.RECENT,
            conversation_id='c',
            privacy_generation=0,
        )
        for i, segment in enumerate(segments)
    ]
    plan = {segment: dict(fresh=i % 2 == 0, owner_turn=i, custody_deadline=10000) for i, segment in enumerate(segments)}
    kwargs = dict(
        namespace=store.namespace,
        policy=BatchUnitPolicy(
            batch_enabled=True,
            batch_percent=100,
            stt_route='provider',
            provider_reason='unsupported_language',
            provider_service='modulate',
        ),
        handoff=handoff,
        provider_plan=plan,
        intake={'owner_id': uid, 'segment_ids': list(segments), 'repair_lineage': 'synthetic-original'},
    )
    kwargs.update(overrides)
    outcome = admit(store, items, binding, 200, **kwargs)
    return ProviderHandoff(handoff), binding, store, outcome


def terminal(adapter, unit, *, now=202):
    return adapter.units.settle(
        unit['unit_id'],
        unit['attempt_token'],
        'result_ready',
        WorkResult(unit['unit_id'], f'encrypted://result/{unit["unit_id"]}').to_dict(),
        now=now,
        partial_wait=30,
    )


def rows(handoff):
    with handoff.pool.connection() as conn:
        ns = handoff.ticket.namespace
        return {
            name: conn.execute(f'SELECT count(*) FROM {name} WHERE namespace=%s', (ns,)).fetchone()[0]
            for name in ('units', 'recordings', 'outbox', 'queue_handoffs', 'queue_custody')
        }


def test_real_upload_admission_terminal_seal_and_replay(context, monkeypatch):
    adapter, binding, store, outcome = upload(context, monkeypatch)
    handoff = adapter.handoff
    assert outcome == {'outcome': 'batch', 'job_id': binding.job_id}
    assert (
        sync_content_ledger_ref(handoff.client, binding.owner_id, binding.content_id).get().to_dict()['status']
        == 'processing'
    )
    for suffix in ('jobs', 'results', 'owners', 'control', 'outbox'):
        assert not handoff.client.collection(store.namespace + '_' + suffix).limit(1).get()
    intent = handoff.ref('intent', binding.job_id).get().to_dict()['intent']
    assert 'repair_lineage' not in intent['payload']['intakes'][binding.job_id]
    assert (
        handoff.client.collection(store.namespace + '_intakes')
        .document(binding.job_id)
        .get()
        .to_dict()['repair_lineage']
        == 'synthetic-original'
    )
    first = adapter.deliver(binding.job_id)
    assert adapter.deliver(binding.job_id) == first
    assert rows(handoff) == dict(units=2, recordings=1, outbox=0, queue_handoffs=1, queue_custody=2)
    claimed = adapter.units.claim(2, now=201, lease_seconds=30, backlog_share=1)
    assert len(claimed) == 2
    assert terminal(adapter, claimed[1])
    with handoff.pool.connection() as conn:
        assert handoff._required_row(conn, binding.job_id)['completion'] is None
    assert terminal(adapter, claimed[0])
    assert not terminal(adapter, claimed[0])
    with handoff.pool.connection() as conn:
        row = handoff._required_row(conn, binding.job_id)
        recording = conn.execute(
            'SELECT units_final,projection_state FROM recordings WHERE namespace=%s', (store.namespace,)
        ).fetchone()
    assert recording == (2, 'pending')
    assert row['phase'] == 'completed'
    assert row['completion_hash'] == fingerprint(row['completion'])
    assert [unit['unit_id'] for unit in row['completion']['units']] == list(binding.segment_ids)
    assert rows(handoff) == dict(units=2, recordings=1, outbox=1, queue_handoffs=1, queue_custody=2)
    # Custody remains completed/unacknowledged; no callback is substituted for
    # the still-required production customer projection and grouped receipt.
    with pytest.raises(AuthorityRefused, match='receipt required'):
        handoff.ack(binding.job_id)


@pytest.mark.parametrize(
    'plan',
    [
        None,
        {},
        {'segment-0': dict(fresh=True, owner_turn=0, custody_deadline=10000)},
        {
            'segment-0': dict(fresh=True, owner_turn=0, custody_deadline=100),
            'segment-1': dict(fresh=False, owner_turn=1, custody_deadline=10000),
        },
    ],
)
def test_invalid_plan_rejects_before_customer_custody(context, monkeypatch, plan):
    handoff, uid = context
    with pytest.raises(AuthorityRefused):
        upload(context, monkeypatch, provider_plan=plan)
    assert not handoff.ref('intent', 'provider-recording').get().exists
    assert not sync_content_ledger_ref(handoff.client, uid, 'provider-content').get().exists
    assert not handoff.client.collection(handoff.ticket.namespace + '_intakes').limit(1).get()
    assert not any(rows(handoff).values())


def test_corrupt_sibling_plan_rolls_back_all_pg_admission(context, monkeypatch):
    adapter, binding, _, _ = upload(context, monkeypatch)
    handoff = adapter.handoff
    source = handoff.ref('intent', binding.job_id).get().to_dict()
    # A matching digest is insufficient: the ingress validates actual typed
    # source/binding and census rather than trusting a shape-only callback.
    source['intent']['payload']['jobs']['segment-1']['owner_id'] = 'foreign-owner'
    source['fingerprint'] = fingerprint(source['intent'])
    handoff.ref('intent', binding.job_id).set(source)
    with pytest.raises(AuthorityRefused):
        adapter.deliver(binding.job_id)
    assert not any(rows(handoff).values())


def test_final_seal_failure_rolls_back_last_terminal_counter_and_outbox(context, monkeypatch):
    adapter, binding, store, _ = upload(context, monkeypatch)
    adapter.deliver(binding.job_id)
    claimed = adapter.units.claim(2, now=201, lease_seconds=30, backlog_share=1)
    assert terminal(adapter, claimed[0])
    import database.jobstore.provider_handoff as implementation

    real = implementation.seal_recording

    def lost(conn, handoff, recording):
        real(conn, handoff, recording)
        raise RuntimeError('exit before terminal COMMIT')

    monkeypatch.setattr(implementation, 'seal_recording', lost)
    with pytest.raises(RuntimeError, match='terminal COMMIT'):
        terminal(adapter, claimed[1])
    with adapter.handoff.pool.connection() as conn:
        assert conn.execute('SELECT units_final FROM recordings WHERE namespace=%s', (store.namespace,)).fetchone() == (
            1,
        )
        assert adapter.handoff._required_row(conn, binding.job_id)['completion'] is None
        assert conn.execute(
            "SELECT count(*) FROM units WHERE namespace=%s AND state='pending' AND attempt_token IS NOT NULL",
            (store.namespace,),
        ).fetchone() == (1,)
    monkeypatch.setattr(implementation, 'seal_recording', real)
    assert terminal(adapter, claimed[1])
    assert rows(adapter.handoff)['outbox'] == 1


def test_plain_units_cannot_bypass_source_terminal_seal(context, monkeypatch):
    adapter, binding, _, _ = upload(context, monkeypatch, count=1)
    adapter.deliver(binding.job_id)
    unit = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)[0]
    handoff = adapter.handoff
    plain = Units(handoff.pool, handoff.fence, handoff.ticket)
    with pytest.raises(AuthorityRefused, match='requires its handoff'):
        plain.settle(
            unit['unit_id'],
            unit['attempt_token'],
            'result_ready',
            {'result_uri': 'encrypted://bypass'},
            now=202,
            partial_wait=30,
        )
    assert terminal(adapter, unit)


def test_admission_reserves_completion_packet_budget(context, monkeypatch):
    handoff, _ = context
    adapter, binding, _, _ = upload(context, monkeypatch)
    payload = handoff.ref('intent', binding.job_id).get().to_dict()['intent']['payload']
    huge = deepcopy(payload)
    huge['intakes'][binding.job_id]['oversized'] = 'x' * 128000
    with pytest.raises(AuthorityRefused, match='budget exceeded'):
        validate_provider_payload(huge)


@pytest.mark.parametrize(
    'gap', ['before_admission_commit', 'after_admission_commit', 'before_terminal_commit', 'after_terminal_commit']
)
def test_provider_custody_survives_abrupt_process_exit(context, monkeypatch, gap):
    import os
    import subprocess
    import sys

    adapter, binding, store, _ = upload(context, monkeypatch, count=1)
    handoff = adapter.handoff
    unit = None
    if 'terminal' in gap:
        adapter.deliver(binding.job_id)
        unit = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)[0]
    with handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = '''
import os
import testing.pipeline_sim._env
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.provider_handoff import ProviderHandoff
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.batch_pipeline.contracts import WorkResult
pool = Pool(os.environ['OMI_PROVIDER_CHILD_DSN'], size=1)
gap = os.environ['OMI_PROVIDER_CHILD_GAP']
if gap.startswith('before_'):
    original = pool._connect
    class ExitBeforeCommit:
        def __init__(self, conn): self.conn = conn
        def __getattr__(self, name): return getattr(self.conn, name)
        def execute(self, query, *args, **kwargs):
            result = self.conn.execute(query, *args, **kwargs)
            if (gap == 'before_admission_commit' and 'INSERT INTO queue_custody' in query
                or gap == 'before_terminal_commit' and "UPDATE queue_handoffs SET phase='completed'" in query):
                os._exit(86)
            return result
    pool._connect = lambda: ExitBeforeCommit(original())
client = _emulator_client()
handoff = Handoff(pool, Fence(pool), client, Epoch(os.environ['OMI_PROVIDER_CHILD_NS'], 3))
adapter = ProviderHandoff(handoff)
if 'admission' in gap:
    adapter.deliver('provider-recording')
else:
    segment = 'segment-0'
    assert adapter.units.settle(segment, os.environ['OMI_PROVIDER_CHILD_ATTEMPT'], 'result_ready',
        WorkResult(segment, 'encrypted://result/' + segment).to_dict(), now=202, partial_wait=30)
os._exit(86)
'''
    result = subprocess.run(
        [sys.executable, '-c', command],
        env={
            **os.environ,
            'OMI_PROVIDER_CHILD_DSN': dsn,
            'OMI_PROVIDER_CHILD_GAP': gap,
            'OMI_PROVIDER_CHILD_NS': store.namespace,
            'OMI_PROVIDER_CHILD_ATTEMPT': unit['attempt_token'] if unit else '',
        },
        timeout=20,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 86, result.stderr
    if 'admission' in gap:
        assert rows(handoff)['units'] == int(gap.startswith('after'))
        adapter.deliver(binding.job_id)
        assert rows(handoff)['units'] == 1
        unit = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)[0]
        assert terminal(adapter, unit)
    else:
        with handoff.pool.connection() as conn:
            before = handoff._required_row(conn, binding.job_id)
        assert (before['completion'] is not None) == gap.startswith('after')
        assert terminal(adapter, unit) == gap.startswith('before')
    with handoff.pool.connection() as conn:
        assert conn.execute('SELECT units_final FROM recordings WHERE namespace=%s', (store.namespace,)).fetchone() == (
            1,
        )
        assert handoff._required_row(conn, binding.job_id)['phase'] == 'completed'
    assert rows(handoff) == dict(units=1, recordings=1, outbox=1, queue_handoffs=1, queue_custody=1)


def test_sql_cannot_rewrite_original_provider_source(context, monkeypatch):
    from database.jobstore.authority import acquire

    adapter, binding, store, _ = upload(context, monkeypatch, count=1)
    adapter.deliver(binding.job_id)
    with adapter.handoff.pool.connection() as conn, pytest.raises(Exception, match='source/terminal time is immutable'):
        with conn.transaction():
            adapter.handoff._guard(conn, adapter.handoff._required_row(conn, binding.job_id))
            acquire(conn, adapter.handoff.ticket)
            conn.execute("UPDATE units SET source='{}' WHERE namespace=%s", (store.namespace,))
