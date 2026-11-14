"""Real PG/FS tickets at the production paid POST boundary; no paid network I/O."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from database.jobstore.authority import AuthorityRefused
from database.jobstore.provider_effect import FenceTicket
from database.privacy_fence import FenceRefused
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_handoff import upload
from utils.batch_pipeline.contracts import WorkItem, WorkResult

pytestmark = pytest.mark.integration


@pytest.fixture
def paid(context, monkeypatch):
    adapter, binding, _, _ = upload(context, monkeypatch, count=1)
    adapter.deliver(binding.job_id)
    (unit,) = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)
    ticket = adapter.fence_ticket(unit['unit_id'], unit['attempt_token'], lease_seconds=60)
    source = ticket.source
    item = WorkItem(**{key: source[key] for key in WorkItem.__dataclass_fields__ if key in source})
    return adapter, unit, ticket, item


def test_actual_paid_boundary_reserves_before_start_and_sends_once(paid, monkeypatch):
    from utils.batch_pipeline import provider_stt
    from utils.stt import allowance_session

    adapter, unit, ticket, item = paid
    events = []

    class Operation:
        def __init__(self, *a, **k):
            pass

        async def reserve_async(self, service):
            events.append('reserve')

    @asynccontextmanager
    async def track(scope):
        yield scope

    monkeypatch.setattr(allowance_session, 'Operation', Operation)
    monkeypatch.setattr(allowance_session, 'track', track)
    original = ticket.start

    def start(item, service):
        events.append('start')
        original(item, service)

    monkeypatch.setattr(ticket, 'start', start)

    async def vendor(service, wav, duration, language):
        events.append('send')
        # Every SQL pool slot and the exclusive owner guard are available
        # during actual provider I/O, rather than only around a mock callback.
        with adapter.units.pool.connection() as one, adapter.units.pool.connection() as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                from database.privacy_fence.protocol import lock

                lock(one, ticket.owner, exclusive=True)
            assert two.execute('SELECT 1').fetchone() == (1,)
        return [{'text': 'Hello', 'timestamp': [0.0, 1.0]}], 'ja'

    monkeypatch.setattr(provider_stt, '_vendor_words', vendor)
    inspected = (b'\0\0' * 160000, 10.0, [{'start': 0.0, 'end': 1.0}])
    result = asyncio.run(provider_stt.transcribe_async(item, 'ja', inspected, service='modulate', fence_ticket=ticket))
    assert result['words_provider'] == 'modulate'
    assert events == ['reserve', 'start', 'send']
    with pytest.raises(FenceRefused):
        asyncio.run(provider_stt.transcribe_async(item, 'ja', inspected, service='modulate', fence_ticket=ticket))
    assert events.count('send') == 1
    assert ticket.complete(WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30)
    with adapter.units.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM privacy_effect_inflight WHERE effect_id=%s', (ticket.effect,)
        ).fetchone() == (0,)
        assert conn.execute(
            'SELECT units_final FROM recordings WHERE namespace=%s', (adapter.units.namespace,)
        ).fetchone() == (1,)


def test_registered_ticket_replay_never_mints_another_effect(paid):
    adapter, unit, ticket, item = paid
    retry = FenceTicket(adapter.units, unit['unit_id'], unit['attempt_token'], lease_seconds=60)
    assert retry.effect == ticket.effect
    retry.start(item, 'modulate')
    with pytest.raises(FenceRefused):
        ticket.start(item, 'modulate')
    with pytest.raises(AuthorityRefused, match='COMPLETE'):
        adapter.units.settle(
            unit['unit_id'],
            unit['attempt_token'],
            'result_ready',
            WorkResult(item.segment_id, 'encrypted://result').to_dict(),
            now=202,
            partial_wait=30,
        )


def test_close_before_start_refuses_and_close_after_start_discards(paid):
    adapter, unit, ticket, item = paid
    ticket.start(item, 'modulate')
    adapter.units.fence.close(ticket.owner, local=True)
    with pytest.raises(FenceRefused):
        ticket.start(item, 'modulate')
    assert not ticket.complete(WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30)
    with adapter.units.pool.connection() as conn:
        assert conn.execute('SELECT state FROM units WHERE namespace=%s', (adapter.units.namespace,)).fetchone() == (
            'pending',
        )
    assert adapter.units.fence.drain_pass(ticket.owner) == 0


def test_terminal_rollback_keeps_started_effect_and_result_custody(paid, monkeypatch):
    adapter, _, ticket, item = paid
    ticket.start(item, 'modulate')
    original = adapter.units.settle_in_transaction

    def fail(*a, **k):
        assert original(*a, **k)
        raise RuntimeError('before terminal COMMIT')

    monkeypatch.setattr(adapter.units, 'settle_in_transaction', fail)
    with pytest.raises(RuntimeError):
        ticket.complete(WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30)
    with adapter.units.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (ticket.effect,)
        ).fetchone() == ('started',)
        assert conn.execute(
            'SELECT units_final FROM recordings WHERE namespace=%s', (adapter.units.namespace,)
        ).fetchone() == (0,)
    monkeypatch.setattr(adapter.units, 'settle_in_transaction', original)
    assert ticket.complete(WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30)


def test_ticket_rejects_wrong_vendor_and_raw_identity_replacement(paid):
    adapter, _, ticket, item = paid
    with pytest.raises(AuthorityRefused):
        ticket.start(item, 'soniox')
    with adapter.units.pool.connection() as conn:
        with pytest.raises(Exception, match='immutable'):
            with conn.transaction():
                adapter.units._guarded_unit(conn, item.segment_id)
                conn.execute('UPDATE units SET provider_effect_id=NULL WHERE namespace=%s', (adapter.units.namespace,))


@pytest.mark.parametrize('gap', ['before_start', 'after_start', 'before_complete', 'after_complete'])
def test_real_start_and_terminal_commit_process_exit(paid, gap):
    import os
    import subprocess
    import sys

    adapter, unit, ticket, item = paid
    if 'complete' in gap:
        ticket.start(item, 'modulate')
    with adapter.units.pool.connection() as conn:
        dsn = conn.info.dsn
    command = '''
import os
import testing.pipeline_sim._env
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.provider_handoff import ProviderHandoff
from database.jobstore.provider_effect import FenceTicket
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.batch_pipeline.contracts import WorkItem,WorkResult
pool=Pool(os.environ['OMI_EFFECT_CHILD_DSN'],size=2)
handoff=Handoff(pool,Fence(pool),_emulator_client(),Epoch(os.environ['OMI_EFFECT_CHILD_NS'],3))
units=ProviderHandoff(handoff).units
ticket=FenceTicket(units,os.environ['OMI_EFFECT_CHILD_UNIT'],os.environ['OMI_EFFECT_CHILD_ATTEMPT'],lease_seconds=60)
item=WorkItem(**{k:ticket.source[k] for k in WorkItem.__dataclass_fields__ if k in ticket.source})
gap=os.environ['OMI_EFFECT_CHILD_GAP']
if gap=='before_start':
    original=units.fence.start
    def killed(*a,**k):
        original(*a,**k)
        os._exit(86)
    units.fence.start=killed
if gap=='before_complete':
    original=units.settle_in_transaction
    def killed(*a,**k):
        original(*a,**k)
        os._exit(86)
    units.settle_in_transaction=killed
if 'start' in gap:ticket.start(item,'modulate')
else:ticket.complete(WorkResult(item.segment_id,'encrypted://result').to_dict(),now=202,partial_wait=30)
os._exit(86)
'''
    result = subprocess.run(
        [sys.executable, '-c', command],
        env={
            **os.environ,
            'OMI_EFFECT_CHILD_DSN': dsn,
            'OMI_EFFECT_CHILD_NS': adapter.units.namespace,
            'OMI_EFFECT_CHILD_UNIT': unit['unit_id'],
            'OMI_EFFECT_CHILD_ATTEMPT': unit['attempt_token'],
            'OMI_EFFECT_CHILD_GAP': gap,
        },
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 86, result.stderr
    with adapter.units.pool.connection() as conn:
        state = conn.execute(
            'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (ticket.effect,)
        ).fetchone()
        (final,) = conn.execute(
            'SELECT units_final FROM recordings WHERE namespace=%s', (adapter.units.namespace,)
        ).fetchone()
    if gap == 'before_start':
        assert state == ('registered',) and final == 0
        ticket.start(item, 'modulate')
    elif gap == 'after_complete':
        assert state is None and final == 1
        assert not ticket.complete(
            WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30
        )
    else:
        assert state == ('started',) and final == 0
        with pytest.raises(FenceRefused):
            ticket.start(item, 'modulate')
        assert ticket.complete(WorkResult(item.segment_id, 'encrypted://result').to_dict(), now=202, partial_wait=30)


@pytest.mark.parametrize('started', [False, True])
def test_expiry_never_authorizes_start_or_discards_started_completion(paid, started):
    adapter, _, ticket, item = paid
    if started:
        ticket.start(item, 'modulate')
    with adapter.units.pool.connection() as conn, conn.transaction():
        conn.execute(
            "UPDATE privacy_effect_inflight SET lease_until=now()-interval '1 second' WHERE effect_id=%s",
            (ticket.effect,),
        )
    with pytest.raises(FenceRefused):
        ticket.start(item, 'modulate')
    result = WorkResult(item.segment_id, 'encrypted://result').to_dict()
    assert ticket.complete(result, now=202, partial_wait=30) is started


def test_raw_isolated_terminal_transaction_cannot_leave_effect_unresolved(paid):
    adapter, unit, ticket, item = paid
    ticket.start(item, 'modulate')
    with adapter.units.pool.connection() as conn:
        with pytest.raises(Exception, match='grouped effect COMPLETE'):
            with conn.transaction():
                assert adapter.units.settle_in_transaction(
                    conn,
                    item.segment_id,
                    unit['attempt_token'],
                    'result_ready',
                    WorkResult(item.segment_id, 'encrypted://result').to_dict(),
                    now=202,
                    partial_wait=30,
                    effect=ticket.effect,
                )
        assert conn.execute(
            'SELECT units_final FROM recordings WHERE namespace=%s', (adapter.units.namespace,)
        ).fetchone() == (0,)
