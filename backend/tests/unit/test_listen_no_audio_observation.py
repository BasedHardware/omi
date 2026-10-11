"""Live zero-byte sockets must be visible before teardown, without customer labels."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry, Gauge
from starlette.websockets import WebSocketState

from utils.observability import transcription as telemetry
from routers.listen.runtime import ListenSessionRuntime


@pytest.fixture
def observed(monkeypatch):
    clock = [0.0]
    gauge = Gauge('test_no_audio', 'test', registry=CollectorRegistry())
    monkeypatch.setattr(telemetry, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(telemetry, 'OMI_LISTEN_LIVE_NO_AUDIO_SESSIONS', gauge)
    return clock, gauge, telemetry.ListenNoAudioObservation()


def value(gauge):
    return next(iter(gauge.collect())).samples[0].value


def test_no_audio_threshold_once_and_recovery(observed, caplog):
    clock, gauge, observation = observed
    clock[0] = 299
    observation.observe(has_audio=False)
    assert value(gauge) == 0
    clock[0] = 300
    with caplog.at_level(logging.WARNING):
        observation.observe(has_audio=False)
        observation.observe(has_audio=False)
    assert value(gauge) == 1
    assert len(caplog.records) == 1
    assert 'no_upstream_audio' in caplog.text
    observation.observe(has_audio=True, audio_received_at=300)
    assert value(gauge) == 0
    observation.close()
    assert value(gauge) == 0


def test_teardown_removes_only_its_session_and_is_idempotent(observed):
    clock, gauge, first = observed
    second = telemetry.ListenNoAudioObservation()
    clock[0] = 600
    first.observe(has_audio=False)
    second.observe(has_audio=False)
    assert value(gauge) == 2
    first.close()
    first.close()
    first.observe(has_audio=False)
    assert value(gauge) == 1
    second.close()
    assert value(gauge) == 0


@pytest.mark.asyncio
async def test_control_activity_does_not_hide_zero_audio_and_teardown_failure_cleans_up(observed):
    clock, gauge, observation = observed
    runtime = object.__new__(ListenSessionRuntime)
    runtime._no_audio_observation = observation
    runtime.state = SimpleNamespace(
        active=True, last_activity_time=10**20, first_audio_byte_timestamp=None, last_audio_received_time=0
    )
    runtime.request = SimpleNamespace(
        websocket=SimpleNamespace(client_state=WebSocketState.CONNECTED),
        owner_persistence_blocked=SimpleNamespace(is_set=lambda: True),
    )
    runtime._send_ping = AsyncMock(return_value=True)
    runtime.wait = AsyncMock(return_value=True)
    clock[0] = 300
    await runtime._heartbeat()
    assert value(gauge) == 1
    runtime._teardown_components = AsyncMock(side_effect=RuntimeError('synthetic teardown failure'))
    with pytest.raises(RuntimeError):
        await runtime._teardown()
    assert value(gauge) == 0


@pytest.mark.asyncio
async def test_first_audio_clears_live_observation(observed):
    clock, gauge, observation = observed
    clock[0] = 300
    observation.observe(has_audio=False)
    runtime = object.__new__(ListenSessionRuntime)
    runtime._no_audio_observation = observation
    runtime.state = SimpleNamespace(
        active=True, last_activity_time=10**20, first_audio_byte_timestamp=1, last_audio_received_time=300
    )
    runtime.request = SimpleNamespace(websocket=SimpleNamespace(client_state=WebSocketState.CONNECTED))
    runtime._send_ping = AsyncMock(return_value=True)
    runtime.wait = AsyncMock(return_value=True)
    await runtime._heartbeat()
    assert value(gauge) == 0


def test_audio_stops_after_first_frame_and_resumes(observed):
    clock, gauge, observation = observed
    observation.observe(has_audio=True, audio_received_at=10)
    clock[0] = 299
    observation.observe(has_audio=True, audio_received_at=10)
    assert value(gauge) == 0
    clock[0] = 300
    observation.observe(has_audio=True, audio_received_at=10)
    assert value(gauge) == 1
    clock[0] = 310
    observation.observe(has_audio=True, audio_received_at=310)
    assert value(gauge) == 0
    clock[0] = 610
    observation.observe(has_audio=True, audio_received_at=310)
    assert value(gauge) == 1
    observation.close()
    assert value(gauge) == 0
