"""Regression (#11752): a Modulate-primary session must walk the configured fallbacks.

``prod-omi-backend-listen`` ran ``STT_SERVICE_MODELS=modulate-velma-2,dg-nova-3,parakeet``
and lost 100% of its live sessions for ~50 minutes: Modulate accepted every
WebSocket upgrade and then answered ``Monthly usage limit reached.``. Deepgram and
Parakeet were listed right behind it, but ``_create_stt_socket`` called
``process_audio_modulate`` directly and returned, so a Modulate primary had no
fallback at all while the Parakeet and Deepgram legs sat idle.

Deepgram-primary (#11695) and Parakeet-primary sessions already route through
``connect_stt_socket_with_fallback``. These tests pin the Modulate entry point to
the same contract.
"""

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver
from utils.stt import provider_resilience, streaming
from utils.stt.streaming import STTService


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _modulate_receiver():
    """Duck-typed receiver exposing only what `_create_stt_socket` touches."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=STTService.modulate,
        stt_language='en',
        stt_model='velma-2',
        vocabulary=[],
    )
    return SimpleNamespace(host=host)


@contextmanager
def _serving_policy(models=('modulate-velma-2', 'dg-nova-3', 'parakeet')):
    """Drive the real provider gates, not a stubbed answer about them.

    The outage deployment listed Modulate first with Deepgram and Parakeet behind
    it, so the fallback decision has to come from ``STT_SERVICE_MODELS`` itself.
    """
    with (
        patch.object(streaming, 'stt_service_models', list(models)),
        patch.object(streaming, '_deepgram_is_available', return_value=True),
        patch.dict(os.environ, {'HOSTED_PARAKEET_API_URL': 'ws://parakeet.omi.me/v3/stream'}),
    ):
        yield


class _RejectedSocket:
    """Velma's over-quota shape: the upgrade succeeds, then the stream is refused."""

    def __init__(self, reason: str = 'modulate error: Monthly usage limit reached.') -> None:
        self.death_reason = reason
        self.finished = False

    @property
    def is_connection_dead(self) -> bool:
        return True

    def finish(self) -> None:
        self.finished = True


def _live_socket():
    return SimpleNamespace(is_connection_dead=False, death_reason=None)


# --- the receiver seam: what the outage actually exercised -------------------


@pytest.mark.anyio
async def test_a_modulate_connect_that_returns_no_socket_serves_from_deepgram():
    receiver = _modulate_receiver()
    dg_socket = _live_socket()

    with (
        _serving_policy(),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)) as modulate,
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)) as dg,
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    modulate.assert_awaited_once()
    dg.assert_awaited_once()
    assert socket is dg_socket
    assert receiver.host.stt_service == STTService.deepgram
    assert receiver.host.stt_model == 'nova-3'


@pytest.mark.anyio
async def test_an_over_quota_modulate_stream_moves_the_session_to_deepgram():
    """The real #11752 shape: the upgrade succeeds, then Velma refuses the stream."""
    receiver = _modulate_receiver()
    rejected = _RejectedSocket()
    dg_socket = _live_socket()

    with (
        _serving_policy(),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=rejected)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)),
        patch.object(streaming, 'record_fallback') as record,
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert socket is dg_socket
    assert receiver.host.stt_service == STTService.deepgram
    assert rejected.finished, 'the over-quota socket must be released, not leaked'
    leg = record.call_args.kwargs
    assert (leg['component'], leg['from_mode'], leg['to_mode'], leg['outcome']) == (
        'stt_selection',
        'modulate',
        'deepgram',
        'recovered',
    )


@pytest.mark.anyio
async def test_a_healthy_modulate_session_still_serves_from_modulate():
    receiver = _modulate_receiver()
    modulate_socket = _live_socket()

    with (
        _serving_policy(),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=modulate_socket)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock()) as dg,
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock()) as parakeet,
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert socket is modulate_socket
    assert receiver.host.stt_service == STTService.modulate
    assert receiver.host.stt_model == 'velma-2'
    dg.assert_not_awaited()
    parakeet.assert_not_awaited()


@pytest.mark.anyio
async def test_the_session_reaches_parakeet_when_both_vendors_are_in_billing_failure():
    """Both #11752 vendors down at once: Modulate over quota, Deepgram at HTTP 402."""
    receiver = _modulate_receiver()
    parakeet_socket = _live_socket()

    with (
        _serving_policy(),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=_RejectedSocket())),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=parakeet_socket)) as parakeet,
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    parakeet.assert_awaited_once()
    assert socket is parakeet_socket
    assert receiver.host.stt_service == STTService.parakeet
    assert receiver.host.stt_model == 'parakeet'


@pytest.mark.anyio
async def test_deepgram_is_not_offered_a_session_the_deployment_never_listed_it_for():
    """Modulate-only policy keeps failing closed rather than inventing a provider."""
    receiver = _modulate_receiver()

    with (
        _serving_policy(models=('modulate-velma-2',)),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock()) as dg,
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock()) as parakeet,
        patch.object(streaming, 'record_fallback'),
        pytest.raises(RuntimeError),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    dg.assert_not_awaited()
    parakeet.assert_not_awaited()


@pytest.mark.anyio
async def test_the_deepgram_leg_gets_the_plain_callback_not_the_modulate_one():
    """Modulate segments arrive in Velma's shape; Deepgram must not be handed it."""
    receiver = _modulate_receiver()
    callback = MagicMock(name='callback')
    modulate_callback = MagicMock(name='modulate_callback')

    with (
        _serving_policy(),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)) as modulate,
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=_live_socket())) as dg,
        patch.object(streaming, 'record_fallback'),
    ):
        await ListenReceiver._create_stt_socket(receiver, callback, 16000, modulate_callback=modulate_callback)

    assert modulate.await_args.args[0] is modulate_callback
    assert dg.await_args.args[0] is callback


# --- the helper seam: chain construction for a Modulate primary -------------


@pytest.mark.anyio
async def test_a_modulate_primary_never_falls_back_to_itself():
    """Replaces the old `test_modulate_primary_is_still_rejected` guard.

    The helper used to raise `ValueError` for a Modulate primary because its
    candidate list hard-coded Modulate as the first fallback — a Modulate primary
    would have retried the provider that just failed. The chain now excludes the
    primary, so the rejection is no longer the thing keeping it correct.
    """
    connect_modulate = AsyncMock()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback'),
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=connect_modulate,
            connect_deepgram=AsyncMock(return_value=_live_socket()),
        )

    assert service == STTService.deepgram
    assert socket is not None
    connect_modulate.assert_not_awaited()


@pytest.mark.anyio
async def test_a_modulate_primary_walks_deepgram_then_parakeet_in_policy_order():
    parakeet_socket = _live_socket()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback') as record,
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=AsyncMock(return_value=_RejectedSocket()),
            connect_modulate=AsyncMock(),
            connect_deepgram=AsyncMock(return_value=None),
            connect_parakeet=AsyncMock(return_value=parakeet_socket),
        )

    assert socket is parakeet_socket
    assert service == STTService.parakeet
    dg_leg, parakeet_leg = [call.kwargs for call in record.call_args_list]
    assert (dg_leg['from_mode'], dg_leg['to_mode'], dg_leg['outcome']) == ('modulate', 'deepgram', 'exhausted')
    assert (parakeet_leg['from_mode'], parakeet_leg['to_mode'], parakeet_leg['outcome']) == (
        'deepgram',
        'parakeet',
        'recovered',
    )


@pytest.mark.anyio
async def test_repeated_modulate_rejections_open_its_own_circuit():
    """A quota-exhausted Modulate account stops costing every session a connect."""
    circuit = MagicMock()
    circuit.allow_request.return_value = True

    with (
        patch.object(streaming, '_modulate_circuit', circuit),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback'),
    ):
        _, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(),
            connect_deepgram=AsyncMock(return_value=_live_socket()),
        )

    assert service == STTService.deepgram
    circuit.record_failure.assert_called_once_with()


@pytest.mark.anyio
async def test_the_modulate_circuit_stays_independent_of_the_other_providers():
    deepgram_circuit = MagicMock()
    deepgram_circuit.allow_request.return_value = True

    with (
        patch.object(streaming, '_deepgram_circuit', deepgram_circuit),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(),
            connect_deepgram=AsyncMock(return_value=_live_socket()),
        )

    deepgram_circuit.record_failure.assert_not_called()
    deepgram_circuit.allow_request.assert_not_called()


# --- the policy gate --------------------------------------------------------


def test_deepgram_is_a_configured_fallback_only_when_the_policy_lists_it():
    with patch.object(streaming, '_deepgram_is_available', return_value=True):
        with patch.object(streaming, 'stt_service_models', ['modulate-velma-2', ' dg-nova-3', 'parakeet']):
            assert streaming.deepgram_fallback_model('en') == 'nova-3'
            # Nova-3 has no capability for an unknown code, so the session must not move.
            assert streaming.deepgram_fallback_model('zz') is None
        with patch.object(streaming, 'stt_service_models', ['modulate-velma-2', 'parakeet']):
            assert streaming.deepgram_fallback_model('en') is None
    # No reachable Deepgram credential means Deepgram cannot take the session over.
    with (
        patch.object(streaming, '_deepgram_is_available', return_value=False),
        patch.object(streaming, 'stt_service_models', ['modulate-velma-2', 'dg-nova-3']),
    ):
        assert streaming.deepgram_fallback_model('en') is None
