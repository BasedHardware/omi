"""Two serving processes, real owner drains and walks, one shard writer per owner."""

import asyncio
from contextlib import contextmanager

import fakeredis
import pytest

from tests.unit.test_batch_pipeline_owner_chain_projection import ResultLog, chain, projector_for
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
    pumps[0].projector.request_drain(owner)
    assert pumps[0].projector.drain_requests == {}
    await pumps[1].tick()
    await quiesce([pumps[1].projector])
    assert log.persist_order == ids


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
