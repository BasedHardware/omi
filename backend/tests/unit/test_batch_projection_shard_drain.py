"""Two serving processes, real owner drains and walks, one shard writer per owner."""

import asyncio
from concurrent.futures import Future
from contextlib import contextmanager
import threading

import fakeredis
import pytest

from tests.unit.test_batch_pipeline_owner_chain_projection import ResultLog, chain, projector_for
from utils import executors
from utils.batch_pipeline import projection, projection_drain, projection_followup, projection_shard_pump
from utils.batch_pipeline.projection_shard_pump import ShardPump
from utils.batch_pipeline.projection_shards import BACKLOG, FRESH, ProjectionShards
from utils.batch_pipeline.scheduler import owner_key


@pytest.fixture(autouse=True)
def claims(monkeypatch):
    state = {'held': set(), 'overlaps': 0}

    @contextmanager
    def claim(namespace, key):
        if key in state['held']:
            state['overlaps'] += 1
            yield False
            return
        state['held'].add(key)
        try:
            yield True
        finally:
            state['held'].discard(key)

    monkeypatch.setattr(projection_drain, 'projection_claim_held', lambda namespace, key: key in state['held'])
    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    for name in ('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'BATCH_PIPELINE_PROJECTION_PREFETCH'):
        monkeypatch.delenv(name, raising=False)

    async def inline(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(projection_shard_pump, 'run_blocking', inline)
    return state


async def quiesce(projectors):
    for _ in range(2000):
        busy = [p for p in projectors if p.drains is not None and (p.drains.tasks or p.drains.queue)]
        if not busy:
            return
        for p in busy:
            await asyncio.gather(*list(p.drains.tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)
    raise AssertionError('drains did not settle')


@pytest.mark.asyncio
async def test_two_processes_drain_every_owner_once_in_chain_order(claims):
    server = fakeredis.FakeServer()
    log = ResultLog()
    owners = [f'owner-{n}' for n in range(12)]
    chains = {owner: chain(log, owner, owner, 4) for owner in owners}
    walkers: dict[str, set[int]] = {owner: set() for owner in owners}
    pumps = []
    for index in range(2):
        client = fakeredis.FakeRedis(server=server)
        shards = ProjectionShards('ns', count=8, client=lambda client=client: client, clock=lambda: 10_000.0)
        projector = projector_for(log)
        real = projector.drain_step

        def step(owner, budget, real=real, index=index, **kwargs):
            walkers[owner].add(index)
            return real(owner, budget, **kwargs)

        projector.drain_step = step
        pump = ShardPump(projector, shards)
        projector.router = pump.route
        pumps.append(pump)
    for _ in range(3):
        for pump in pumps:
            pump.shards.refresh()
    assert sorted(s for p in pumps for s in p.shards.held) == list(range(8))
    # Commits arrive on whichever process served the worker's RPC.
    for n, owner in enumerate(owners):
        pumps[n % 2].committed(owner, [{'capture_at': 10_000.0 - n, 'committed_at': 10_000.0}])
    for _ in range(6):
        for pump in pumps:
            await pump.tick()
        await quiesce([p.projector for p in pumps])
    for owner, ids in chains.items():
        assert [sid for sid in log.persist_order if log.results[sid]['owner_key'] == owner_key(owner)] == ids
        assert len(walkers[owner]) == 1, 'one shard writer per owner'
        holder = next(i for i, p in enumerate(pumps) if p.shards.owns(owner_key(owner)))
        assert walkers[owner] == {holder}
    assert claims['overlaps'] == 0
    for pump in pumps:
        assert pump.shards.take(FRESH, 100) == [] and pump.shards.take(BACKLOG, 100) == []
        assert pump.inflight == {}


@pytest.mark.asyncio
async def test_router_sends_foreign_owners_to_their_holder(claims):
    server = fakeredis.FakeServer()
    log = ResultLog()
    pumps = []
    for _ in range(2):
        client = fakeredis.FakeRedis(server=server)
        shards = ProjectionShards('ns', count=4, client=lambda client=client: client, clock=lambda: 1.0)
        projector = projector_for(log)
        pump = ShardPump(projector, shards)
        projector.router = pump.route
        pumps.append(pump)
    for _ in range(3):
        for pump in pumps:
            pump.shards.refresh()
    owner = next(f'o{n}' for n in range(1000) if pumps[1].shards.owns(owner_key(f'o{n}')))
    ids = chain(log, owner, owner, 2)
    # A recovery wake on process 0 asks for a drain of process 1's owner.
    await asyncio.to_thread(pumps[0].projector.request_drain, owner)
    assert pumps[0].projector.drain_requests == {}
    await pumps[1].tick()
    await quiesce([pumps[1].projector])
    assert log.persist_order == ids


@pytest.mark.asyncio
@pytest.mark.parametrize('redis_fails', [False, True])
async def test_async_drain_request_keeps_loop_responsive_during_redis(claims, monkeypatch, redis_fails):
    client = fakeredis.FakeRedis()
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: 1000.0)
    projector = projector_for(ResultLog())
    pump = ShardPump(projector, shards)
    projector.router = pump.route
    shards.refresh()
    entered, release, completed = threading.Event(), threading.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    threads = []
    real_eval = client.eval

    def slow_eval(*args, **kwargs):
        threads.append(threading.current_thread().name)
        entered.set()
        try:
            # Old inline routing fails immediately; do not freeze the test loop.
            assert threading.get_ident() != loop_thread, 'Redis ran on the event loop'
            assert release.wait(10), 'test did not release Redis'
            if redis_fails:
                raise ConnectionError('Redis unavailable')
            return real_eval(*args, **kwargs)
        finally:
            loop.call_soon_threadsafe(completed.set)

    monkeypatch.setattr(client, 'eval', slow_eval)
    try:
        projector.request_drain('owner')
        assert await asyncio.to_thread(entered.wait, 10)
        # Redis is still waiting, while this task and another loop turn run.
        await asyncio.sleep(0)
        assert not release.is_set()
        assert threads and all(name.startswith('db') for name in threads)
    finally:
        release.set()
        await asyncio.wait_for(completed.wait(), 10)
        monkeypatch.setattr(client, 'eval', real_eval)
        # Completion is signaled inside eval; fence the remainder of the router.
        for _ in range(1000):
            if shards.take(BACKLOG, 1) or projector.owes_drains:
                break
            await asyncio.sleep(0.001)
        else:
            pytest.fail('route did not finish or preserve its local fallback')
    assert bool(projector.drain_requests) == redis_fails


@pytest.mark.asyncio
@pytest.mark.parametrize('stop', ['privacy_unchanged', 'blocked_privacy_deleted', 'claim_held'])
async def test_delayed_drain_returns_shard_wake_for_retry(claims, monkeypatch, stop):
    monkeypatch.setattr(projection_shard_pump.random, 'uniform', lambda a, b: (a + b) / 2)
    monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', 'on')
    now = [1000.0]
    client = fakeredis.FakeRedis()
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now[0])
    projector = projector_for(ResultLog())
    drains = projector.ensure_drains()
    pump = ShardPump(projector, shards, monotonic=lambda: now[0])

    async def turn(owner):
        drains.stops[owner] = stop
        return False

    monkeypatch.setattr(drains, 'run', turn)
    monkeypatch.setattr(drains, 'privacy_head_unchanged', lambda owner: (True, False))
    if stop == 'claim_held':
        monkeypatch.setattr(projection_drain, 'projection_claim_held', lambda namespace, key: True)
    shards.refresh()
    shards.push('owner', owner_key('owner'), FRESH, 990.0)
    try:
        assert await pump.tick() == 1
        if stop == 'privacy_unchanged':
            # The admitted task rechecks a privacy head before its existing TTL.
            drains.defer('owner', delay=300)
            drains.privacy_heads['owner'] = ('head', 'version')
        await quiesce([projector])
        assert 'owner' in drains.delayed
        assert 'owner' not in pump.inflight
        if stop == 'claim_held':
            # Claims keep their lane position and only use the existing local
            # cooldown; privacy retries use the durable backlog score below.
            assert not pump.deferring
            assert pump.cooldown['owner'] == now[0] + projection_shard_pump.CLAIM_RETRY_SECONDS
            return
        assert pump.deferring
        retry_at = pump.deferring[0][1]
        assert await pump.tick() == 0
        assert client.zscore(shards._lane_key(BACKLOG, 0), 'owner') == retry_at
        # A replacement process has no local hold; the durable wake must wait
        # until due, then be admitted and settled rather than stranded inflight.
        drains.close()
        monkeypatch.setattr(projection_drain, 'projection_claim_held', lambda namespace, key: False)
        next_projector = projector_for(ResultLog())
        next_pump = ShardPump(next_projector, shards, monotonic=lambda: now[0])
        now[0] = retry_at - 0.001
        assert await next_pump.tick() == 0
        now[0] = retry_at
        assert await next_pump.tick() == 1
        await quiesce([next_projector])
        await next_pump.tick()
        assert next_pump.inflight == {}
        assert shards.take(FRESH, 1) == shards.take(BACKLOG, 1) == []
        next_projector.ensure_drains().close()
    finally:
        drains.close()


@pytest.mark.asyncio
async def test_lost_router_notification_is_recovered_from_durable_results(claims, monkeypatch):
    now = 1000.0
    client = fakeredis.FakeRedis()
    log = ResultLog()
    log.clock = 994.0
    ids = chain(log, 'owner', 'durable', 2)

    def pages(**kwargs):
        return [
            (sid, log.bindings[sid].owner_id, row['committed_at'], 990.0)
            for sid, row in log.results.items()
            if row['projection_state'] == 'pending'
        ], None

    monkeypatch.setattr(log, 'projection_page_owners', pages, raising=False)
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now)
    shards.refresh()
    projector = projector_for(log)
    pump = ShardPump(projector, shards)
    projector.router = pump.route
    lost = []

    def lose_dispatch(executor, fn, *args):
        assert executor is executors.db_executor
        future = Future()
        assert future.cancel()
        lost.append(future)
        return future  # Model process loss before this advisory notification runs.

    with monkeypatch.context() as patch:
        patch.setattr(executors, 'submit_with_context', lose_dispatch)
        projector.request_drain('owner')
    assert len(lost) == 1 and lost[0].cancelled()
    assert not projector.owes_drains
    assert shards.take(FRESH, 1) == shards.take(BACKLOG, 1) == []
    assert log.persist_order == []
    assert all(log.results[sid]['projection_state'] == 'pending' for sid in ids)
    shards.release()

    replacement = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now)
    replacement.refresh()
    next_projector = projector_for(log)
    next_projector.clock = lambda: now
    next_pump = ShardPump(next_projector, replacement)
    try:
        # Discovery reconstructs the wake from durable metadata, without any
        # memory, Redis wake or Future from the lost request.
        await asyncio.to_thread(next_pump.backstop)
        assert await next_pump.tick() == 1
        await quiesce([next_projector])
        await next_pump.tick()
        assert log.persist_order == ids
        assert claims['overlaps'] == 0
        assert replacement.take(FRESH, 1) == replacement.take(BACKLOG, 1) == []
    finally:
        drains = next_projector.ensure_drains()
        drains.close()
        await asyncio.gather(*list(drains.tasks.values()), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('slots', [4, 8])
async def test_productive_turns_yield_for_waiting_fresh_and_backlog(claims, monkeypatch, slots):
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', slots)
    monkeypatch.setenv('BATCH_PROJECTION_BACKLOG_RESERVE', '2')
    now = [10_000.0]
    client = fakeredis.FakeRedis()
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now[0])
    projector = projector_for(ResultLog())
    drains = projector.ensure_drains()
    pump = ShardPump(projector, shards, monotonic=lambda: now[0])
    release = asyncio.Event()
    started = []

    async def sustained(owner, *, continuation=False):
        started.append(owner)
        await release.wait()
        await asyncio.sleep(0)
        return owner.startswith('hot')

    monkeypatch.setattr(drains, 'admit_and_run', sustained)
    shards.refresh()
    for index in range(slots):
        shards.push(f'hot{index}', owner_key(f'hot{index}'), FRESH, now[0])
    try:
        assert await pump.tick() == slots
        await asyncio.sleep(0)
        assert len(started) == slots
        for index in range(slots):
            shards.push(f'fresh{index}', owner_key(f'fresh{index}'), FRESH, now[0])
        for index in range(2):
            shards.push(f'backlog{index}', owner_key(f'backlog{index}'), BACKLOG, 1.0)
        assert await pump.tick() == 0  # Every active turn still owns its slot.
        drains.request(['hot0'])  # A concurrent request cannot bypass the yield.
        release.set()
        await asyncio.gather(*list(drains.tasks.values()))
        await asyncio.sleep(0)
        now[0] += 1
        admitted = await pump.tick()
        await asyncio.sleep(0)
        newcomers = started[slots:]
        assert admitted == slots
        assert sum(owner.startswith('backlog') for owner in newcomers) == 2
        assert sum(owner.startswith('fresh') for owner in newcomers) == slots - 2
        assert not any(owner.startswith('hot') for owner in newcomers)
        assert len(drains.tasks) <= slots
        # Yielded productive owners retain durable wakes behind the due backlog.
        backlog = shards.take(BACKLOG, 100)
        assert {w.owner_id for w in backlog if w.owner_id.startswith('hot')} == {f'hot{i}' for i in range(slots)}
        assert all(w.score > 1.0 for w in backlog if w.owner_id.startswith('hot'))
    finally:
        drains.close()
        await asyncio.gather(*list(drains.tasks.values()), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('fallback', ['local_owner', 'redis_failure', 'disabled_switch'])
async def test_legacy_productive_continuations_do_not_yield(claims, monkeypatch, fallback):
    client = fakeredis.FakeRedis()
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: 10_000.0)
    projector = projector_for(ResultLog())
    drains = projector.ensure_drains()
    pump = ShardPump(projector, shards)
    pump.attach()
    shards.refresh()
    if fallback != 'local_owner':
        shards.push('owner', owner_key('owner'), BACKLOG, 1.0)
        pump.inflight['owner'] = shards.take(BACKLOG, 1)
    if fallback == 'redis_failure':
        shards.healthy = False
    elif fallback == 'disabled_switch':
        monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    turns = []

    async def run(owner):
        turns.append(owner)
        drains.turn_stops[owner] = 'end' if len(turns) == 2 else 'turn_deadline'
        return len(turns) < 2

    monkeypatch.setattr(drains, 'run', run)
    try:
        drains.request(['owner'])
        await quiesce([projector])
        assert turns == ['owner', 'owner']
        assert pump.deferring == [] and pump.cooldown == {}
    finally:
        drains.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('commit_at', ['before_defer', 'after_defer'])
@pytest.mark.parametrize('capture_at', [990.0, None])
async def test_real_commit_survives_discovery_and_deferral(claims, monkeypatch, commit_at, capture_at):
    monkeypatch.setattr(projection_shard_pump.random, 'uniform', lambda a, b: 1.0)
    now = [1000.0]
    client = fakeredis.FakeRedis()
    shards = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now[0])
    log = ResultLog()
    log.clock = 994.0
    first = chain(log, 'owner', 'old', 1)

    def pages(**kwargs):
        rows = [
            (sid, log.bindings[sid].owner_id, row['committed_at'], 990.0)
            for sid, row in log.results.items()
            if row['projection_state'] == 'pending'
        ]
        return rows, None

    monkeypatch.setattr(log, 'projection_page_owners', pages, raising=False)
    projector = projector_for(log)
    projector.clock = lambda: now[0]
    pump = ShardPump(projector, shards, monotonic=lambda: now[0])
    real_step = projector.drain_step
    stopped = False

    def step(*args, **kwargs):
        nonlocal stopped
        if not stopped:
            stopped = True
            pump.backstop()  # Both real passes replay the owner while its wake is taken.
            return projection.Walk([], [], stop='blocked_other')
        return real_step(*args, **kwargs)

    monkeypatch.setattr(projector, 'drain_step', step)
    shards.refresh()
    pump.committed('owner', [{'capture_at': capture_at, 'committed_at': 995.0}])
    try:
        assert await pump.tick() == 1
        await quiesce([projector])
        assert pump.deferring and log.persist_order == []
        if commit_at == 'after_defer':
            assert await pump.tick() == 0
            assert client.zscore(shards._lane_key(BACKLOG, 0), 'owner') == 1120.0
        new = chain(log, 'owner', 'new', 1)
        # Equal capture/unchanged backlog ordering still represents genuinely new work.
        pump.committed('owner', [{'capture_at': capture_at, 'committed_at': 996.0}])
        pump.backstop()
        if commit_at == 'before_defer':
            assert await pump.tick() == 0
        assert shards.take(FRESH, 10) or shards.take(BACKLOG, 10)
    finally:
        projector.ensure_drains().close()
    shards.release()

    # Lose every local cooldown. The durable new commit must still be walked and settled.
    replacement = ProjectionShards('ns', count=1, client=lambda: client, clock=lambda: now[0])
    replacement.refresh()
    next_projector = projector_for(log)
    next_projector.clock = lambda: now[0]
    next_pump = ShardPump(next_projector, replacement, monotonic=lambda: now[0])
    try:
        next_pump.backstop()
        assert await next_pump.tick() == 1
        await quiesce([next_projector])
        await next_pump.tick()
        assert log.persist_order == first + new
        assert replacement.take(FRESH, 10) == replacement.take(BACKLOG, 10) == []
        assert claims['overlaps'] == 0
    finally:
        next_projector.ensure_drains().close()
