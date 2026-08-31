"""A live session must survive a provider that dies after the socket is open.

Modulate accepts the WebSocket upgrade and only then sends an error frame, so its
outages land mid-session where ``connect_stt_socket_with_fallback`` — which runs
once, at connect time — cannot reach them. On 2026-08-30 that gap took Velma to
82% failure while Soniox and Deepgram served zero sessions: the fallback chain was
configured correctly and was structurally unable to fire.
"""

from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    MODULATE_PROVIDER,
    SONIOX_PROVIDER,
    provider_for_service,
)
from routers.listen.receiver import MAX_STT_FAILOVERS, ListenReceiver
from utils.stt.streaming import STTService, get_stt_service_for_language


class FakeSocket:
    def __init__(self, dead: bool = False):
        self._dead = dead
        self.finished = False
        self.sent: list[bytes] = []

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return 'modulate error: Internal server error' if self._dead else None

    def send(self, audio: bytes) -> bool:
        if self._dead:
            return False
        self.sent.append(audio)
        return True

    def finish(self) -> None:
        self.finished = True


def test_provider_for_service_round_trips_every_serving_provider():
    assert provider_for_service(STTService.modulate) == MODULATE_PROVIDER
    assert provider_for_service(STTService.soniox) == SONIOX_PROVIDER
    assert provider_for_service(STTService.deepgram) == DEEPGRAM_CLOUD_PROVIDER
    assert provider_for_service('nonsense') is None


def test_excluding_the_dead_provider_selects_the_next_one():
    """The whole point of the exclusion: never reselect what just died."""
    with patch.dict(
        'os.environ',
        {'STT_SERVICE_MODELS': 'modulate-velma-2,soniox,dg-nova-3,parakeet', 'SONIOX_API_KEY': 'k'},
    ), patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2', 'soniox', 'dg-nova-3']):
        first, _, _ = get_stt_service_for_language('en')
        assert first == STTService.modulate

        second, _, _ = get_stt_service_for_language('en', exclude=frozenset({MODULATE_PROVIDER}))
        assert second == STTService.soniox


def test_excluding_every_provider_selects_nothing():
    """Exhausting the chain must report no provider, not loop back to the first."""
    with patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2', 'soniox']), patch.dict(
        'os.environ', {'SONIOX_API_KEY': 'k'}
    ):
        service, _, _ = get_stt_service_for_language('en', exclude=frozenset({MODULATE_PROVIDER, SONIOX_PROVIDER}))
        assert service is None


def _receiver_with_dead_socket(monkeypatch: Any, *, replacement: Any):
    host = MagicMock()
    host.is_multi_channel = False
    host.use_custom_stt = False
    host.state.active = True
    host.state.stt_terminal_failure = False
    host.language = 'en'
    host.multi_lang_enabled = True
    host.stt_service = STTService.modulate

    receiver = ListenReceiver(host, [], {})
    receiver.stt_socket = FakeSocket(dead=True)
    receiver.vad_gate = None
    receiver._stt_rebuild = (lambda _s: None, lambda _s: None, 16000)
    receiver._create_stt_socket = AsyncMock(return_value=replacement)
    return receiver


@pytest.mark.asyncio
async def test_a_dead_primary_moves_the_session_to_the_next_provider(monkeypatch):
    healthy = FakeSocket(dead=False)
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=healthy)
    dead = receiver.stt_socket

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ):
        assert await receiver._failover_stt_socket() is True

    assert receiver.stt_socket is healthy
    assert receiver.host.stt_service == STTService.soniox
    # The dead socket is released rather than leaked for the session's lifetime.
    assert dead.finished is True
    assert MODULATE_PROVIDER in receiver._stt_failed_providers


@pytest.mark.asyncio
async def test_a_replacement_that_dies_immediately_is_not_treated_as_recovery(monkeypatch):
    """A provider can accept the upgrade and reject the stream ~150ms later."""
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket(dead=True))

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ):
        assert await receiver._failover_stt_socket() is False


@pytest.mark.asyncio
async def test_failover_stops_once_the_chain_is_exhausted(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket(dead=False))

    with patch('routers.listen.receiver.get_stt_service_for_language', return_value=(None, None, None)):
        assert await receiver._failover_stt_socket() is False


@pytest.mark.asyncio
async def test_multi_channel_sessions_do_not_failover(monkeypatch):
    """Multi-channel stitches segments across sockets; swapping one needs its own design."""
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket(dead=False))
    receiver.host.is_multi_channel = True

    assert await receiver._failover_stt_socket() is False


@pytest.mark.asyncio
async def test_failover_is_bounded_so_a_flapping_chain_cannot_loop(monkeypatch):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket(dead=False))
    receiver._stt_failed_providers = {f'p{i}' for i in range(MAX_STT_FAILOVERS + 1)}

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ):
        assert await receiver._failover_stt_socket() is False


@pytest.mark.asyncio
async def test_failover_adopts_a_replacement_installed_by_the_other_observer(monkeypatch):
    """The death monitor and the send path race to the same death; the loser of
    the failover lock must adopt the winner's healthy socket, not rebuild again."""
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=FakeSocket(dead=False))
    receiver.stt_socket = FakeSocket(dead=False)

    assert await receiver._failover_stt_socket() is True
    receiver._create_stt_socket.assert_not_called()


def _receiver_with_flowing_audio(monkeypatch: Any, *, primary: Any, replacement: Any):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=replacement)
    receiver.stt_socket = primary
    host = receiver.host
    host.state.fair_use_dg_budget_exhausted = False
    host.state.fair_use_track_dg_usage = False
    host.state.dg_usage_ms_pending = 0
    host.request.sample_rate = 16000
    host.request.websocket = MagicMock(send_json=AsyncMock(), close=AsyncMock())
    host.client_device_context.platform = 'ios'
    return receiver


@pytest.mark.asyncio
async def test_a_death_observed_by_the_audio_send_path_fails_over_not_terminates(monkeypatch):
    """The regression behind the 2026-08-31 outage hours: the send path observes
    a provider death on the very next audio chunk — before the 1s death-monitor
    poll — and used to terminate there, so the monitor's failover (#12459) never
    fired on a session with audio flowing (3,110 terminations, zero failovers in
    30 minutes). The flush must fail over and deliver the buffered audio to the
    replacement socket in the same call."""
    healthy = FakeSocket(dead=False)
    receiver = _receiver_with_flowing_audio(monkeypatch, primary=FakeSocket(dead=True), replacement=healthy)
    buffer = bytearray(b'synthetic-pcm')

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ):
        await receiver._flush_stt_buffer(buffer, force=True)

    assert receiver.stt_socket is healthy
    assert healthy.sent == [b'synthetic-pcm']
    assert len(buffer) == 0
    assert receiver.host.state.stt_terminal_failure is False
    receiver.host.request.websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_audio_send_path_still_terminates_once_the_chain_is_exhausted(monkeypatch):
    receiver = _receiver_with_flowing_audio(
        monkeypatch, primary=FakeSocket(dead=True), replacement=FakeSocket(dead=False)
    )
    buffer = bytearray(b'synthetic-pcm')

    with patch('routers.listen.receiver.get_stt_service_for_language', return_value=(None, None, None)):
        await receiver._flush_stt_buffer(buffer, force=True)

    assert receiver.host.state.stt_terminal_failure is True
    receiver.host.request.websocket.close.assert_awaited_once()
