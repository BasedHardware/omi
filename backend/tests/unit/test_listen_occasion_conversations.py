"""Occasion conversations (Episodes M3): inside the occasion window a new session continues the open
conversation, outside it (or past the span cap, or for another device or source) it does not."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from config import occasion_conversations as config
from tests.unit.test_listen_reconnect_continuity import CaptureHarness


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _occasion(controller, enabled=True):
    controller.host.occasion_mode = enabled
    controller.host.conversation_creation_timeout = (
        config.occasion_timeout(controller.host.conversation_creation_timeout) if enabled else 120
    )
    return controller


async def _open(harness, client_id, *, enabled=True):
    controller = _occasion(harness.connect(client_id=client_id), enabled)
    await controller.prepare()
    return controller


@pytest.mark.anyio
async def test_a_new_recording_id_inside_the_window_continues_the_open_conversation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    cid = first.host.state.current_conversation_id
    # A pendant reconnect 6 minutes later mints a new recording id.
    harness.now += timedelta(minutes=6)
    second = await _open(harness, 'rec-b')
    assert second.host.state.current_conversation_id == cid
    assert harness.creates == 1
    # Both recording ids now name the same conversation, so sync lineage finds it from either.
    assert harness.bindings['rec-a'] == harness.bindings['rec-b'] == cid


@pytest.mark.anyio
async def test_outside_the_occasion_window_a_new_recording_starts_a_new_conversation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    harness.now += timedelta(seconds=config.OCCASION_GAP_SECONDS + 1)
    second = await _open(harness, 'rec-b')
    assert second.host.state.current_conversation_id != first.host.state.current_conversation_id
    assert harness.creates == 2


@pytest.mark.anyio
async def test_without_occasion_mode_every_new_recording_id_is_its_own_conversation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a', enabled=False)
    harness.now += timedelta(minutes=1)
    second = await _open(harness, 'rec-b', enabled=False)
    assert second.host.state.current_conversation_id != first.host.state.current_conversation_id


@pytest.mark.anyio
async def test_another_device_or_source_never_joins(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    harness.now += timedelta(minutes=2)
    other = _occasion(harness.connect(client_id='rec-mac'))
    other.host.client_device_context.client_device_id = 'mac'
    await other.prepare()
    assert other.host.state.current_conversation_id != first.host.state.current_conversation_id
    harness.pointer = first.host.state.current_conversation_id
    web = _occasion(harness.connect(client_id='rec-web'))
    web.host.request.source = 'desktop'
    await web.prepare()
    assert web.host.state.current_conversation_id != first.host.state.current_conversation_id


@pytest.mark.anyio
async def test_a_true_reconnect_of_the_same_recording_still_resumes_its_own_conversation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    cid = first.host.state.current_conversation_id
    harness.now += timedelta(minutes=3)
    again = await _open(harness, 'rec-a')
    assert again.host.state.current_conversation_id == cid
    assert harness.creates == 1


@pytest.mark.anyio
async def test_the_span_cap_stops_joining_and_rolls_the_occasion_over(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    cid = first.host.state.current_conversation_id
    row = harness.rows[cid]
    row['started_at'] = harness.now - timedelta(seconds=config.OCCASION_MAX_SPAN_SECONDS)
    assert first._occasion_span_exceeded(row) is True
    harness.now += timedelta(minutes=1)
    later = await _open(harness, 'rec-b')
    assert later.host.state.current_conversation_id != cid
    # Without occasion mode the cap never applies.
    assert _occasion(harness.connect(client_id='rec-c'), False)._occasion_span_exceeded(row) is False


@pytest.mark.anyio
async def test_the_lifecycle_loop_rolls_a_capped_occasion_over_even_while_it_is_active(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = await _open(harness, 'rec-a')
    cid = controller.host.state.current_conversation_id
    # Still talking (finished_at is now), but the occasion is three hours old.
    harness.rows[cid]['started_at'] = harness.now - timedelta(seconds=config.OCCASION_MAX_SPAN_SECONDS)
    controller.host.wait = AsyncMock(side_effect=[False, True])
    await controller.lifecycle_loop()
    assert controller.host.state.current_conversation_id != cid
    assert harness.creates == 2


@pytest.mark.anyio
async def test_the_lifecycle_loop_keeps_an_active_occasion_under_the_cap(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = await _open(harness, 'rec-a')
    cid = controller.host.state.current_conversation_id
    harness.rows[cid]['started_at'] = harness.now - timedelta(hours=2)
    controller.host.wait = AsyncMock(side_effect=[False, True])
    await controller.lifecycle_loop()
    assert controller.host.state.current_conversation_id == cid
    assert harness.creates == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    'state', [{'status': 'processing'}, {'discarded': True}, {'is_locked': True}, {'deleted': True}]
)
async def test_an_open_conversation_that_is_not_live_and_clean_is_never_joined(monkeypatch, state):
    harness = CaptureHarness(monkeypatch)
    first = await _open(harness, 'rec-a')
    cid = first.host.state.current_conversation_id
    harness.rows[cid].update(state)
    harness.now += timedelta(minutes=3)
    second = await _open(harness, 'rec-b')
    assert second.host.state.current_conversation_id != cid


def test_the_kill_switch_and_the_window(monkeypatch):
    monkeypatch.delenv(config.OCCASION_CONVERSATIONS_ENABLED_ENV, raising=False)
    assert config.occasion_conversations_enabled() is True
    for off in ('0', 'false', 'OFF', ' no '):
        monkeypatch.setenv(config.OCCASION_CONVERSATIONS_ENABLED_ENV, off)
        assert config.occasion_conversations_enabled() is False
    assert config.occasion_timeout(120) == config.OCCASION_GAP_SECONDS
    # A user's own longer silence setting still wins.
    assert config.occasion_timeout(1800) == 1800


def test_occasion_mode_needs_admission_and_a_capable_client(monkeypatch):
    from utils.episodes import client_gate

    monkeypatch.delenv(config.OCCASION_CONVERSATIONS_ENABLED_ENV, raising=False)
    monkeypatch.setattr(client_gate, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(client_gate, 'client_seen_cached', lambda uid: uid == 'beta')
    assert client_gate.occasion_mode('beta') is True
    assert client_gate.occasion_mode('beta', 'phone') is True
    assert client_gate.occasion_mode('store') is False
    # The capability marker is per user; a cohort user's desktop capture keeps today's boundaries.
    assert client_gate.occasion_mode('beta', 'desktop') is False
    monkeypatch.setenv(config.OCCASION_CONVERSATIONS_ENABLED_ENV, 'off')
    assert client_gate.occasion_mode('beta') is False

    def broken(uid):
        raise ConnectionError('redis down')

    monkeypatch.delenv(config.OCCASION_CONVERSATIONS_ENABLED_ENV, raising=False)
    monkeypatch.setattr(client_gate, 'client_seen_cached', broken)
    assert client_gate.occasion_mode('beta') is False


@pytest.mark.anyio
@pytest.mark.parametrize('encoding', ['numeric', 'iso', 'naive'])
async def test_span_cap_accepts_all_persisted_timestamp_formats(monkeypatch, encoding):
    harness = CaptureHarness(monkeypatch)
    controller = await _open(harness, 'rec-a')
    start = harness.now - timedelta(seconds=config.OCCASION_MAX_SPAN_SECONDS)
    value = (
        start.timestamp()
        if encoding == 'numeric'
        else (start.isoformat() if encoding == 'iso' else start.replace(tzinfo=None))
    )
    assert controller._occasion_span_exceeded({'started_at': value})
    assert not controller._occasion_span_exceeded({'started_at': 'invalid'})
