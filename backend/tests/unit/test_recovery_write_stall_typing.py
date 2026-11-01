"""A paced recovery write that misses our own bound is a local delivery stall.

Prod 2026-11-01: 43% of Modulate ``connection_lost`` provider failures were
``cause=timeout`` on recovery legs — ``RecoveryWriterPace`` raising when the
replay episode budget or the 2 s slot bound ran out while the vendor socket
was still open. The bare ``except Exception`` left them untyped, so they voted
against the successor's health. The terminal contract (stt ARCHITECTURE.md)
names this case ``replay_send_stalled``, censored.
"""

import asyncio

import pytest
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

from tests.unit.test_live_replay_provider_pairs import SafeModulateSocket, SafeSonioxSocket, Transport, stop, until
from config.live_stt_replay import ReplayLimits
from utils.stt.live_failure import live_stt_terminal_reason
from utils.stt.live_signal import provider_observation
from utils.stt.replay_delivery import RecoveryWriteStalled, RecoveryWriterPace, enable_recovery_writer_pace, paced_send

SAMPLE_RATE = 16000
FRAME = b'\x01\x00' * 1600


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


def assert_local_stall(raw):
    assert raw.is_connection_dead
    assert raw.typed_death_reason == 'replay_send_stalled'
    assert raw.connection_cause is None
    assert live_stt_terminal_reason(raw, 'send_failed') == 'replay_send_stalled'
    assert provider_observation('failover', 'replay_send_stalled') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_spent_episode_budget_is_local_stall_not_connection_lost(kind):
    transport = Transport()
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), lambda: 0.0)
    try:
        assert raw.send(FRAME)
        await until(lambda: raw.is_connection_dead)
        assert_local_stall(raw)
        assert transport.pcm == b''
    finally:
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_write_blocked_past_its_slot_bound_is_local_stall(kind):
    transport = Transport()
    transport.gate.clear()  # the vendor socket stays open but stops reading
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), lambda: 0.05)
    try:
        assert raw.send(FRAME)
        await until(lambda: raw.is_connection_dead)
        assert_local_stall(raw)
        assert not transport.closed
    finally:
        transport.gate.set()
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_transport_failure_on_paced_leg_stays_provider_death(kind):
    transport = Transport(fail_after=0)
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    enable_recovery_writer_pace(raw, SAMPLE_RATE, ReplayLimits(), lambda: None)
    try:
        assert raw.send(FRAME)
        await until(lambda: raw.is_connection_dead)
        assert raw.typed_death_reason != 'replay_send_stalled'
        assert live_stt_terminal_reason(raw, 'connection_lost') != 'replay_send_stalled'
    finally:
        await stop([raw])


@pytest.mark.asyncio
async def test_paced_send_reraises_a_timeout_that_is_not_its_own_bound():
    async def send():
        raise TimeoutError('transport ETIMEDOUT')

    with pytest.raises(TimeoutError) as raised:
        await paced_send(send, RecoveryWriterPace(SAMPLE_RATE, 1.0))
    assert not isinstance(raised.value, RecoveryWriteStalled)
