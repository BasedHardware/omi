"""Consumer absence must be established from real fanout authorities."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utils.stt import demand_consumers
from utils import proactivity_flags
from routers.listen import demand_routing
from utils.async_tasks import WebSocketTaskSupervisor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'consumer', ['none', 'app', 'audio_app', 'webhook', 'mentor', 'mentor_off', 'mentor_free', 'mentor_not_cohort']
)
async def test_active_consumers_require_vendor(monkeypatch, consumer):
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort' if consumer.startswith('mentor') else 'off')
    monkeypatch.setattr(demand_consumers, 'run_blocking', AsyncMock(side_effect=lambda pool, fn, *args: fn(*args)))
    monkeypatch.setattr(
        demand_consumers, 'get_mentor_notification_frequency', lambda uid: 0 if consumer == 'mentor_off' else 3
    )
    monkeypatch.setattr(demand_consumers, 'mentor_plan_allows_evaluation', lambda uid: consumer != 'mentor_free')
    monkeypatch.setattr(
        proactivity_flags, 'mentor_pipeline', lambda uid: None if consumer == 'mentor_not_cohort' else 'v2'
    )
    app = SimpleNamespace(
        enabled=True,
        triggers_realtime=lambda: consumer == 'app',
        triggers_realtime_audio_bytes=lambda: consumer == 'audio_app',
    )
    monkeypatch.setattr(demand_consumers, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(demand_consumers, 'user_webhook_status_db', lambda uid, kind: consumer == 'webhook')
    monkeypatch.setattr(demand_consumers, 'get_user_webhook_db', lambda uid, kind: 'https://example.invalid/hook')
    assert await demand_consumers.realtime_consumer_active('user') == (
        consumer not in {'none', 'mentor_off', 'mentor_free', 'mentor_not_cohort'}
    )


@pytest.mark.asyncio
async def test_unverifiable_consumer_keeps_vendor(monkeypatch):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    receiver = SimpleNamespace(host=SimpleNamespace(request=SimpleNamespace(uid='user')))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    monkeypatch.setattr(demand, 'publish', AsyncMock(return_value=False))
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(side_effect=OSError))
    assert not await demand.can_admit_window()
    assert demand.consumer is None and not demand.window_permitted


@pytest.mark.asyncio
async def test_failed_consumer_probe_backs_off_while_vendor_keeps_serving(monkeypatch):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    now = [0.0]
    monkeypatch.setattr(demand_routing.time, 'monotonic', lambda: now[0])
    state = SimpleNamespace(active=True, stt_terminal_failure=False)

    async def wait(seconds):
        now[0] += seconds
        state.active = now[0] < 20
        return not state.active

    host = SimpleNamespace(request=SimpleNamespace(uid='user'), state=state, wait=wait, stt_model='soniox')
    receiver = SimpleNamespace(host=host, lane_meter=SimpleNamespace(flush=lambda **kw: None))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    monkeypatch.setattr(demand, 'publish', AsyncMock(return_value=False))
    consumer = AsyncMock(side_effect=OSError)
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', consumer)
    await demand.run()
    assert consumer.await_count == 1
    assert demand.policy.reason == 'consumer_unknown' and not demand.window_permitted


@pytest.mark.asyncio
async def test_adopted_cheap_lane_cannot_survive_failed_demand_lifetime(monkeypatch):
    state = SimpleNamespace(active=True, stt_terminal_failure=False)
    host = SimpleNamespace(request=SimpleNamespace(uid='user'), state=state, stt_model='parakeet-window')
    receiver = SimpleNamespace(host=host, lane_meter=SimpleNamespace(flush=lambda **kw: None))
    demand = demand_routing.LiveDemandRouting(receiver, eligible=True)
    monkeypatch.setattr(demand, 'publish', AsyncMock(return_value=False))
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(return_value=False))
    monkeypatch.setattr(demand.policy, 'decide', Mock(side_effect=RuntimeError('policy crashed')))
    supervisor = WebSocketTaskSupervisor(uid='user', label='listen')
    receive = supervisor.create_task(asyncio.Event().wait(), name='receive')
    supervisor.create_lifetime_task(demand.run(), name='live_demand_routing')
    try:
        result = await asyncio.wait_for(supervisor.supervise(receive_task=receive), 1)
        assert result.reason == 'crash'
        assert result.task_name.endswith('live_demand_routing')
        assert isinstance(result.exception, RuntimeError)
        assert demand.closed
    finally:
        await supervisor.drain_all(timeout=1, cancel=True)
