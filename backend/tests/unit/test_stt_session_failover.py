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

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return 'modulate error: Internal server error' if self._dead else None

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
        {'STT_SERVICE_MODELS': 'modulate-velma-2,soniox,dg-nova-3', 'SONIOX_API_KEY': 'k'},
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
