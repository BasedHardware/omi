"""Joined production paid phases, actual storage/SQL and customer SDK writes.

Only allowance billing, audio inspection and paid network transport are
synthetic. No callback substitutes for admission, result publication, terminal,
assignment, usage, receipt or grouped acknowledgement.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from database.batch_pipeline_purge import provider_result_artifacts
from database.jobstore.authority import AuthorityRefused
from database.jobstore.provider_projection import ProviderProjection
from database.privacy_fence import owner_key
from database.privacy_fence import FenceRefused
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from utils.batch_pipeline.typed_provider import TypedProviderRunner, TypedProviderStage
from utils.observability.reasons import VendorHealthReason

pytestmark = [pytest.mark.integration, pytest.mark.parametrize('lane', ['runner'], indirect=True)]


@pytest.fixture
def runtime(lane, monkeypatch):
    from utils.batch_pipeline import provider_stt
    from utils.stt import allowance_session

    x = lane
    events = []
    stores = {}

    class Operation:
        def __init__(self, uid, surface, *, operation, seconds, billing_period):
            self.uid, self.operation, self.closed = uid, operation, False
            events.append(('operation', billing_period))

        async def reserve_async(self, service):
            events.append(('allowance', service))

    @asynccontextmanager
    async def track(scope):
        yield scope

    def allowed(*args):
        events.append(('funding', args[0]))
        return True, 'allowed'

    def inspect(item, audio):
        assert audio == b'synthetic audio'
        events.append(('inspect', item.segment_id))
        return b'\0\0' * 480000, 30.0, [{'start': 0.0, 'end': 4.0}]

    class Health:
        def allows(self, service):
            events.append(('health', service))
            return True, VendorHealthReason.HEALTHY

        def reserve(self, service, seconds):
            events.append(('cap', seconds))
            return True, VendorHealthReason.HEALTHY

    async def vendor(service, wav, duration, language):
        events.append(('send', service))
        assert len(wav) > 1000 and duration == 30 and language == 'ja'
        free_slots()
        with x.handoff.pool.connection() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM privacy_effect_inflight WHERE owner_key=%s AND state='started' AND kind='provider'",
                    (owner_key(x.uid),),
                ).fetchone()[0]
                >= 1
            )
        return [{'text': 'The project is ready.', 'timestamp': [0.0, 4.0], 'speaker': 'SPEAKER_00'}], 'ja'

    def artifacts(ticket):
        store = provider_result_artifacts(ticket, x.storage, 'synthetic', b'x' * 32, lease_seconds=60)
        stores[ticket.identity] = store
        return store

    def free_slots():
        from database.privacy_fence.protocol import lock, owner_key

        with x.handoff.pool.connection(timeout=2) as one, x.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                lock(one, owner_key(x.uid), exclusive=True)
            assert two.execute('SELECT 1').fetchone() == (1,)

    monkeypatch.setattr(allowance_session, 'Operation', Operation)
    monkeypatch.setattr(allowance_session, 'track', track)
    monkeypatch.setattr(provider_stt, '_vendor_words', vendor)
    options = dict(
        health=Health(),
        allowed=allowed,
        inspect=inspect,
        armed=lambda: True,
        failover_routes=lambda _: ('modulate',),
        clock=lambda: 202,
    )
    return SimpleNamespace(**locals())


async def run_sync(fn, *args, **kwargs):
    # Match the actual route's managed executor, including ContextVar flow.
    from utils.executors import sync_executor, run_blocking

    return await run_blocking(sync_executor, fn, *args, **kwargs)


def stage(r, claim, **options):
    return TypedProviderStage(
        r.x.adapter,
        claim['unit_id'],
        claim['attempt_token'],
        r.artifacts,
        effect_lease_seconds=60,
        partial_wait=30,
        **{**r.options, **options}
    )


def claims(r):
    return r.x.adapter.units.claim(2, now=201, lease_seconds=30, backlog_share=0)


def test_actual_runner_result_customer_receipt_and_grouped_ack(runtime):
    r, x = runtime, runtime.x
    runner = TypedProviderRunner(
        x.adapter,
        r.artifacts,
        count=2,
        backlog_share=0,
        lease_seconds=30,
        effect_lease_seconds=60,
        partial_wait=30,
        **r.options
    )
    from routers.batch_provider_stt import run_typed_provider_async

    assert asyncio.run(run_typed_provider_async()) == []
    assert asyncio.run(run_typed_provider_async(runner)) == []  # default-off: no claim/registration
    with x.handoff.pool.connection() as conn:
        assert conn.execute('SELECT sum(attempts) FROM units WHERE namespace=%s', (x.store.namespace,)).fetchone() == (
            0,
        )
    runner.enabled = True
    x.storage._http.before_request = lambda *a: r.free_slots()
    assert asyncio.run(run_typed_provider_async(runner)) == ['recording']
    names = [e[0] for e in r.events]
    assert names == ['funding', 'inspect', 'funding', 'health', 'cap', 'operation', 'allowance', 'send'] * 2
    assert [e[1] for e in r.events if e[0] == 'operation'] == ['2026-11'] * 2
    view = ProviderProjection(x.handoff, 'recording')
    from database.jobstore.provider_result_reader import ProviderResultReader

    # Customer restart uses only original retained SQL rows and a new reader;
    # none of the worker's in-memory tickets/stores is required for projection.
    reader = ProviderResultReader(x.handoff, x.storage, 'synthetic', b'x' * 32, lease_seconds=60)
    assert view.project_recording(reader, clock=lambda: 10000, publish=lambda b, result: x.published.append(result))
    assert x.ledger.get().to_dict()['status'] == 'completed'
    assert x.ledger.get().to_dict()['usage_committed_seconds'] == 8
    assert x.handoff.ref('receipt', 'recording').get().to_dict()['result']
    assert not view.project_recording(reader, clock=lambda: 10001, publish=lambda *a: None)
    assert x.ledger.get().to_dict()['usage_committed_seconds'] == 8
    assert x.handoff.ref('intent', 'recording').get().exists
    with x.handoff.pool.connection() as conn:
        assert x.handoff._required_row(conn, 'recording')['phase'] == 'acked'
        assert conn.execute(
            "SELECT count(*) FROM outbox WHERE namespace=%s AND done_reason='projected'", (x.store.namespace,)
        ).fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM queue_custody WHERE namespace=%s AND phase='acked'", (x.store.namespace,)
        ).fetchone() == (2,)
    for suffix in ('jobs', 'results', 'owners', 'control'):
        assert not x.client.collection(x.store.namespace + '_' + suffix).limit(1).get()
    assert names.count('send') == 2


@pytest.mark.parametrize('denial', ['before_inspect', 'after_inspect', 'health', 'inspection', 'silence'])
def test_pre_start_refusal_keeps_original_attempt_and_never_sends(runtime, denial):
    r = runtime
    claim = claims(r)[0]
    calls = []

    def allowed(*args):
        calls.append(1)
        return (False, 'budget_exhausted') if len(calls) == (1 if denial == 'before_inspect' else 2) else True

    options = {}
    if denial in {'before_inspect', 'after_inspect'}:
        options['allowed'] = allowed
    elif denial == 'health':
        options['health'] = SimpleNamespace(allows=lambda _: (False, VendorHealthReason.STATE_UNAVAILABLE))
    elif denial == 'inspection':
        from utils.batch_pipeline.recovery_disposition import RecoveryFailure

        def invalid(*args):
            raise RecoveryFailure('audio_validation', 'invalid_audio')

        options['inspect'] = invalid
    else:
        options['inspect'] = lambda *a: (b'\0\0', 30.0, [])
    s = stage(r, claim, **options)
    if denial in {'before_inspect', 'after_inspect'}:
        assert asyncio.run(s.run_async(claim['unit_id'], run_sync)).outcome == 'deferred'
    else:
        with pytest.raises(AuthorityRefused):
            asyncio.run(s.run_async(claim['unit_id'], run_sync))
    assert not any(e[0] == 'send' for e in r.events)
    with r.x.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (s.ticket.effect,)
        ).fetchone() == ('registered',)
        job = r.x.adapter.units._unit(conn, claim['unit_id'])
        assert job['state'] == 'pending' and job['attempt_token'] == claim['attempt_token']


def test_lost_terminal_reply_redelivery_uses_original_result_without_paid_send(runtime, monkeypatch):
    r = runtime
    claim = claims(r)[0]
    s = stage(r, claim)
    original = s.ticket.complete
    monkeypatch.setattr(s.ticket, 'complete', lambda *a, **k: (_ for _ in ()).throw(ConnectionError('before terminal')))
    with pytest.raises(ConnectionError):
        asyncio.run(s.run_async(claim['unit_id'], run_sync))
    assert [e[0] for e in r.events].count('send') == 1
    monkeypatch.setattr(s.ticket, 'complete', original)
    assert asyncio.run(s.run_async(claim['unit_id'], run_sync)).outcome == 'done'
    assert [e[0] for e in r.events].count('send') == 1


def test_unknown_paid_reply_never_sends_again(runtime, monkeypatch):
    r = runtime
    claim = claims(r)[0]
    s = stage(r, claim)
    from utils.batch_pipeline import provider_stt

    async def lost(*args):
        r.events.append(('send', 'lost'))
        raise ConnectionError('unknown paid reply')

    monkeypatch.setattr(provider_stt, '_vendor_words', lost)
    with pytest.raises(AuthorityRefused, match='outcome retained'):
        asyncio.run(s.run_async(claim['unit_id'], run_sync))
    with pytest.raises(AuthorityRefused, match='another POST forbidden'):
        asyncio.run(s.run_async(claim['unit_id'], run_sync))
    assert [e[0] for e in r.events].count('send') == 1


def test_partial_recording_is_not_dispatched_and_failover_is_not_reinterpreted(runtime, monkeypatch):
    r = runtime
    runner = TypedProviderRunner(
        r.x.adapter,
        r.artifacts,
        count=1,
        backlog_share=0,
        lease_seconds=30,
        effect_lease_seconds=60,
        partial_wait=30,
        enabled=True,
        **r.options
    )
    assert asyncio.run(runner.run_once(run_sync)) == []
    (claim,) = r.x.adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)
    monkeypatch.setenv('BATCH_VENDOR_FAILOVER_ENABLED', 'true')
    with pytest.raises(AuthorityRefused, match='failover routing'):
        stage(r, claim, failover_routes=lambda _: ('modulate', 'soniox'))
    with r.x.handoff.pool.connection() as conn:
        assert r.x.adapter.units._unit(conn, claim['unit_id'])['provider_effect_id'] is None


def test_terminal_commit_lost_reply_is_resolved_against_original_attempt(runtime, monkeypatch):
    from utils.batch_pipeline.typed_provider import run_claimed_provider

    r = runtime
    claim = claims(r)[0]
    s = stage(r, claim)
    original = s.ticket.complete

    def lost(*args, **kwargs):
        assert original(*args, **kwargs)
        raise ConnectionError('after terminal COMMIT')

    monkeypatch.setattr(s.ticket, 'complete', lost)
    with pytest.raises(ConnectionError):
        asyncio.run(s.run_async(claim['unit_id'], run_sync))
    result = asyncio.run(
        run_claimed_provider(
            r.x.adapter, claim, r.artifacts, run_sync=run_sync, effect_lease_seconds=60, partial_wait=30, **r.options
        )
    )
    assert result.outcome == 'done'
    assert [e[0] for e in r.events].count('send') == 1
    with pytest.raises(AuthorityRefused, match='not proved'):
        asyncio.run(
            run_claimed_provider(
                r.x.adapter,
                {**claim, 'attempt_token': 'foreign'},
                r.artifacts,
                run_sync=run_sync,
                effect_lease_seconds=60,
                partial_wait=30,
                **r.options
            )
        )


@pytest.mark.parametrize('change', ['privacy', 'token', 'epoch'])
def test_authority_change_after_preparation_never_reaches_paid_post(runtime, change):
    r = runtime
    claim = claims(r)[0]

    def reserve(service, seconds):
        if change == 'privacy':
            r.x.handoff.fence.close(owner_key(r.x.uid), local=True)
        elif change == 'token':
            from database.batch_privacy_attempt import TOKEN_FIELD

            r.x.client.collection('batch_pipeline_privacy').document(owner_key(r.x.uid)).update(
                {TOKEN_FIELD: 'changed'}
            )
        else:
            r.x.handoff.authority.ref.update({'epoch': 4})
        return True, VendorHealthReason.HEALTHY

    s = stage(r, claim, health=SimpleNamespace(allows=lambda _: (True, VendorHealthReason.HEALTHY), reserve=reserve))
    with pytest.raises((AuthorityRefused, FenceRefused)):
        asyncio.run(s.run_async(claim['unit_id'], run_sync))
    assert not any(e[0] == 'send' for e in r.events)
    with r.x.handoff.pool.connection() as conn:
        assert r.x.adapter.units._unit(conn, claim['unit_id'])['state'] == 'pending'
        assert conn.execute(
            'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (s.ticket.effect,)
        ).fetchone() == ('registered',)


def test_bound_dequeue_does_not_claim_byok_or_legacy_cohort(runtime, monkeypatch):
    from config.policy import BatchUnitPolicy
    from tests.integration.test_jobstore_provider_handoff import upload

    r = runtime
    adapter, binding, _, _ = upload(
        (r.x.handoff, r.x.uid),
        monkeypatch,
        count=1,
        policy=BatchUnitPolicy(
            batch_enabled=True,
            batch_percent=100,
            stt_route='provider',
            provider_reason='byok',
            provider_service='modulate',
        ),
    )
    adapter.deliver(binding.job_id)
    selected = adapter.units.claim(3, now=201, lease_seconds=30, backlog_share=0, ordinary_provider_only=True)
    assert {row['unit_id'] for row in selected} == set(r.x.binding.segment_ids)
    with r.x.handoff.pool.connection() as conn:
        untouched = adapter.units._unit(conn, binding.segment_ids[0])
        assert untouched['attempt_token'] is None and untouched['attempts'] == 0


@pytest.mark.parametrize('change', ['reference', 'owner', 'privacy', 'epoch'])
def test_customer_restart_reader_cannot_adopt_foreign_or_revoked_result(runtime, change):
    from dataclasses import replace
    from database.jobstore.provider_result_reader import ProviderResultReader
    from utils.batch_pipeline.contracts import WorkItem

    r = runtime
    claim = claims(r)[0]
    s = stage(r, claim)
    assert asyncio.run(s.run_async(claim['unit_id'], run_sync)).outcome == 'done'
    with r.x.handoff.pool.connection() as conn:
        uri = r.x.adapter.units._unit(conn, claim['unit_id'])['result']['result_uri']
    item = WorkItem(**{k: claim['source'][k] for k in WorkItem.__dataclass_fields__ if k in claim['source']})
    reader = ProviderResultReader(r.x.handoff, r.x.storage, 'synthetic', b'x' * 32, lease_seconds=60)
    assert reader.load_result(item, uri)['words_provider'] == 'modulate'
    if change == 'reference':
        uri = 'gs://synthetic/foreign#1'
    elif change == 'owner':
        item = replace(item, owner_id='foreign')
    elif change == 'privacy':
        r.x.handoff.fence.close(owner_key(r.x.uid), local=True)
    else:
        r.x.handoff.authority.ref.update({'epoch': 4})
    with pytest.raises((AuthorityRefused, FenceRefused)):
        reader.load_result(item, uri)
