"""Recovery and deployment-topology contracts for reservation state."""

import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock
from pathlib import Path

import fakeredis.aioredis
import httpx
import pytest
import yaml

from config import vertex_reservations as vr
from utils.llm.vertex_reservation_state import ReservationState, UNKNOWN_SHARED_ALERT_SECONDS
from utils.llm.desktop_reservation_policy import TASK_TOOLS, should_refuse
from routers import desktop_proxy as proxy

OLD, NEW = 'gemini-2.5-flash', 'gemini-3.8-flash'


@pytest.mark.asyncio
async def test_local_success_survives_failed_write_and_recovered_unknown_snapshot(monkeypatch):
    db = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = ReservationState(db)
    await store.transact()
    real_pipeline = db.pipeline

    def broken(*args, **kwargs):
        raise ConnectionError('synthetic write outage')

    monkeypatch.setattr(db, 'pipeline', broken)
    await store.record(NEW, 'dedicated', 200, 'PROVISIONED_THROUGHPUT')
    assert (await store.refresh())[NEW] == vr.State.ACTIVE
    monkeypatch.setattr(db, 'pipeline', real_pipeline)
    assert (await ReservationState(db).refresh())[NEW] == vr.State.UNKNOWN
    assert (await store.refresh())[NEW] == vr.State.ACTIVE
    assert (await ReservationState(db).refresh())[NEW] == vr.State.ACTIVE
    assert not store._pending_success
    await db.aclose()


@pytest.mark.asyncio
async def test_older_local_success_cannot_override_newer_confirmed_inactivity():
    db = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = ReservationState(db)
    now = time.time()
    store._positive[OLD] = time.monotonic() - 3000
    store._pending_success[OLD] = now - 3000
    await db.set(
        store.key(),
        json.dumps(
            {
                'evidence': {
                    OLD: {
                        'success_at': now - 3000,
                        'failure_start': now - 2000,
                        'failure_at': now - 100,
                        'failure_count': 4,
                    },
                    NEW: {'success_at': now - 50},
                }
            }
        ),
    )
    assert (await store.refresh())[OLD] == vr.State.INACTIVE
    await db.aclose()


@pytest.mark.asyncio
async def test_unconfigured_storage_uses_same_strict_reducer_and_warns_once(monkeypatch, caplog):
    monkeypatch.delenv('REDIS_DB_HOST', raising=False)
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    store = ReservationState()
    with caplog.at_level(logging.INFO):
        for at in [1000, 1600, 2200, 2800]:
            now[0] = at
            states, _ = await store.transact(OLD, 'capacity_error')
            assert states[OLD] == vr.State.UNKNOWN
        states, _ = await store.transact(NEW, 'dedicated_success')
        assert states[OLD] == vr.State.INACTIVE
        assert (await store.refresh())[OLD] == vr.State.INACTIVE
        inactive = [
            r for r in caplog.records if 'vertex_reservation_transition' in r.message and 'state=inactive' in r.message
        ]
        assert len(inactive) == 1 and inactive[0].levelno == logging.WARNING
        assert (
            'failure_count=4 failure_start=1000 failure_at=2800 success_at=0 successor_success_at=2800'
            in inactive[0].message
        )
        now[0] = 2801
        await store.record(OLD, 'dedicated', 200, 'PROVISIONED_THROUGHPUT')
        assert (await store.refresh())[OLD] == vr.State.ACTIVE
    assert caplog.text.count('vertex_reservation_storage mode=process_local') == 1
    await store.aclose()


@pytest.mark.asyncio
async def test_unconfigured_probe_lease_and_scope_are_local_and_bounded(monkeypatch):
    monkeypatch.delenv('REDIS_DB_HOST', raising=False)
    for key in ['OMI_VERTEX_PT_MODEL', 'OMI_VERTEX_RESERVATION_STATES']:
        monkeypatch.delenv(key, raising=False)
    store = ReservationState()
    calls = []

    async def probe(model, location):
        calls.append((model, location))
        return 'capacity_error'

    for _ in range(3):
        await store.refresh(probe)
        await asyncio.gather(*store._probe_tasks)
    assert calls == [(OLD, 'us-central1'), (NEW, 'us')]
    assert (await store.refresh())[OLD] == vr.State.UNKNOWN
    await store.record(NEW, 'dedicated', 200, 'PROVISIONED_THROUGHPUT')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'different-project')
    assert set((await store.refresh()).values()) == {vr.State.UNKNOWN}
    assert not store._positive
    await store.aclose()


@pytest.mark.asyncio
async def test_unknown_shared_age_survives_replica_change_and_warning_is_bounded(monkeypatch, caplog):
    db = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a, b = ReservationState(db), ReservationState(db)
    first = time.time()
    a.note_request(NEW, 'shared', vr.State.UNKNOWN)
    await a.transact()
    await b.refresh()
    assert b._unknown_shared_since[NEW] == a._unknown_shared_since[NEW]
    monkeypatch.setattr(time, 'time', lambda: first + UNKNOWN_SHARED_ALERT_SECONDS + 1)
    with caplog.at_level(logging.WARNING):
        b.note_request(NEW, 'shared', vr.State.UNKNOWN)
        b.note_request(NEW, 'shared', vr.State.UNKNOWN)
        b.note_request(OLD, 'shared', vr.State.UNKNOWN)
        b.note_request('unregistered-model', 'shared', vr.State.UNKNOWN)
    events = [r for r in caplog.records if 'vertex_reservation_discovery_overdue' in r.message]
    assert len(events) == 1
    assert 'threshold_seconds=21600' in events[0].message
    b.note_request(NEW, 'dedicated', vr.State.ACTIVE)
    assert NEW not in b._unknown_shared_since
    b.note_request(NEW, 'shared', vr.State.UNKNOWN)
    assert len([r for r in caplog.records if 'vertex_reservation_discovery_overdue' in r.message]) == 1
    await db.aclose()


@pytest.mark.asyncio
async def test_desktop_redis_confirms_cutoff_without_gateway_shared_state(monkeypatch):
    monkeypatch.delenv('REDIS_DB_HOST', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    for key in ['OMI_VERTEX_PT_MODEL', 'OMI_VERTEX_RESERVATION_STATES']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('OMI_VERTEX_LEGACY_TASK_MODE', 'enforce')
    monkeypatch.setenv('OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD', '12435')
    db = fakeredis.aioredis.FakeRedis(decode_responses=True)
    clock = [1000]
    real_pipeline = db.pipeline

    def timed_pipeline(*args, **kwargs):
        pipe = real_pipeline(*args, **kwargs)
        pipe.time = AsyncMock(side_effect=lambda: (clock[0], 0))
        return pipe

    monkeypatch.setattr(db, 'pipeline', timed_pipeline)
    calls = []

    def handler(request):
        model = request.url.path.split('/models/')[1].split(':')[0]
        calls.append(model)
        assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
        if model == OLD:
            return httpx.Response(429, json={'error': {'message': 'Exceeded the provisioned throughput.'}})
        return httpx.Response(
            200,
            json={
                'candidates': [{'content': {'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(proxy, 'get_desktop_gemini_client', lambda: client)
        monkeypatch.setattr(proxy._vertex_tokens, 'get_access_token', AsyncMock(return_value='synthetic-token'))
        for at in [1000, 1600, 2200, 2800]:
            clock[0] = at
            # New BFF process each interval: the history and lease live in Redis.
            owner = ReservationState(db)
            monkeypatch.setattr(proxy, 'reservation_state', owner)
            for _ in range(2):
                await proxy._refresh_reservations()
                await asyncio.gather(*owner._probe_tasks)
            await owner.aclose()
        owner = ReservationState(db)
        monkeypatch.setattr(proxy, 'reservation_state', owner)
        assert (await proxy._refresh_reservations())[OLD] == vr.State.INACTIVE
        gateway = ReservationState()  # No gateway Redis and no shared observations.
        assert set((await gateway.refresh()).values()) == {vr.State.UNKNOWN}
        body = json.dumps({'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}).encode()
        assert await should_refuse(
            OLD,
            'generateContent',
            body,
            {'x-omi-workload': 'extraction', 'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'},
            byok=False,
            refresh=proxy._refresh_reservations,
        )
        assert calls == [OLD, NEW] * 4
        await owner.aclose()
        await gateway.aclose()
    await db.aclose()


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_gateway_redis_bindings_are_optional(environment):
    root = Path(__file__).resolve().parents[3]
    values = yaml.safe_load(
        (root / f'backend/charts/llm-gateway/{environment}_omi_llm_gateway_values.yaml').read_text()
    )
    bindings = {item['name']: item for item in values['env']}
    for name in ['REDIS_DB_HOST', 'REDIS_DB_PORT', 'REDIS_DB_PASSWORD']:
        ref = next(iter(bindings[name]['valueFrom'].values()))
        assert ref['optional'] is True
