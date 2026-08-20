"""Regression (#11695): a Deepgram account that rejects every live connect must
not take the deployment's transcription down.

``STT_SERVICE_MODELS`` states an ordered preference (prod's Deepgram canary runs
``dg-nova-3,modulate-velma-2,parakeet``), but a Deepgram socket that failed to
open returned ``None`` straight to ``initialize_stt``, which terminalized the
session instead of advancing to the next configured provider. Deepgram answering
every WebSocket upgrade with HTTP 402 therefore killed 100% of the sessions that
deployment served.
"""

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


def _deepgram_receiver():
    """Duck-typed receiver exposing only what `_create_stt_socket` touches."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=STTService.deepgram,
        stt_language='en',
        stt_model='nova-3',
        vocabulary=[],
    )
    return SimpleNamespace(host=host)


@pytest.mark.anyio
async def test_rejected_deepgram_connect_serves_the_session_from_modulate():
    receiver = _deepgram_receiver()
    modulate_socket = object()

    with (
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)) as dg,
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=modulate_socket)),
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    dg.assert_awaited_once()
    assert socket is modulate_socket
    assert receiver.host.stt_service == STTService.modulate
    assert receiver.host.stt_model == 'velma-2'


@pytest.mark.anyio
async def test_modulate_fallback_receives_its_own_stream_callback():
    """Modulate segments need the Modulate-shaped callback, as on the Parakeet path."""
    receiver = _deepgram_receiver()
    modulate_callback = MagicMock(name='modulate_callback')

    with (
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=object())) as modulate,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000, modulate_callback=modulate_callback)

    assert modulate.await_args.args[0] is modulate_callback


@pytest.mark.anyio
async def test_healthy_deepgram_connect_keeps_serving_deepgram():
    receiver = _deepgram_receiver()
    dg_socket = object()

    with (
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock()) as modulate,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert socket is dg_socket
    assert receiver.host.stt_service == STTService.deepgram
    modulate.assert_not_awaited()


@pytest.mark.anyio
async def test_no_fallback_when_the_deployment_does_not_configure_modulate():
    """Without Modulate in the serving policy the session still fails closed."""
    receiver = _deepgram_receiver()

    with (
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock()) as modulate,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=False),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert socket is None
    assert receiver.host.stt_service == STTService.deepgram
    modulate.assert_not_awaited()


def test_modulate_is_a_configured_fallback_only_when_the_policy_lists_it():
    with patch.object(streaming, 'stt_service_models', ['dg-nova-3', ' modulate-velma-2', 'parakeet']):
        assert streaming.modulate_is_configured_fallback('en') is True
        # Velma-2 has no capability for an unknown code, so the session must not move.
        assert streaming.modulate_is_configured_fallback('zz') is False
    with patch.object(streaming, 'stt_service_models', ['dg-nova-3']):
        assert streaming.modulate_is_configured_fallback('en') is False


@pytest.mark.anyio
async def test_repeated_rejections_open_the_deepgram_circuit():
    """A dead Deepgram account stops costing every new session a connect attempt."""
    circuit = MagicMock()
    circuit.allow_request.return_value = True
    fallback_socket = object()

    with patch.object(streaming, '_deepgram_circuit', circuit), patch.object(streaming, 'record_fallback') as record:
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=fallback_socket),
        )

    assert socket is fallback_socket
    assert service == STTService.modulate
    circuit.record_failure.assert_called_once_with()
    record.assert_called_once_with(
        component='stt_selection',
        from_mode='deepgram',
        to_mode='modulate',
        reason='config_incomplete',
        outcome='recovered',
    )


@pytest.mark.anyio
async def test_open_deepgram_circuit_skips_the_connect_attempt():
    circuit = MagicMock()
    circuit.allow_request.return_value = False
    connect_primary = AsyncMock()

    with patch.object(streaming, '_deepgram_circuit', circuit), patch.object(streaming, 'record_fallback') as record:
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=connect_primary,
            connect_modulate=AsyncMock(return_value=object()),
        )

    assert service == STTService.modulate
    assert socket is not None
    connect_primary.assert_not_awaited()
    assert record.call_args.kwargs['reason'] == 'circuit_open'


@pytest.mark.anyio
async def test_the_deepgram_and_parakeet_circuits_stay_independent():
    """A dead Deepgram account must not open Parakeet's circuit, or vice versa."""
    parakeet_circuit = MagicMock()
    parakeet_circuit.allow_request.return_value = True

    with (
        patch.object(streaming, '_parakeet_circuit', parakeet_circuit),
        patch.object(streaming, 'record_fallback'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=object()),
        )

    parakeet_circuit.record_failure.assert_not_called()
    parakeet_circuit.allow_request.assert_not_called()


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


@pytest.mark.anyio
async def test_a_fallback_that_is_already_dead_is_not_reported_as_recovered():
    """Regression (#11752): an over-quota Modulate connect is an exhausted chain, not a heal."""
    rejected = _RejectedSocket()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback') as record,
        pytest.raises(RuntimeError, match='Monthly usage limit reached'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.parakeet,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=rejected),
        )

    assert record.call_args.kwargs['outcome'] == 'exhausted'
    assert rejected.finished, 'the rejected socket must be released, not leaked'


@pytest.mark.anyio
async def test_a_live_fallback_socket_still_serves_the_session():
    """The liveness check must not fail a healthy fallback that simply has no audio yet."""
    live_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback') as record,
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.parakeet,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=live_socket),
        )

    assert socket is live_socket
    assert service == STTService.modulate
    assert record.call_args.kwargs['outcome'] == 'recovered'


@pytest.mark.anyio
async def test_the_chain_continues_to_parakeet_when_modulate_cannot_serve():
    """Regression (#11752): Deepgram 402 + Modulate rejection must not end the chain.

    ``STT_SERVICE_MODELS`` lists Parakeet behind both of them, so a healthy
    Parakeet deployment has to take the session instead of it being terminalized.
    """
    parakeet_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback') as record,
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=_RejectedSocket()),
            connect_parakeet=AsyncMock(return_value=parakeet_socket),
        )

    assert socket is parakeet_socket
    assert service == STTService.parakeet
    modulate_leg, parakeet_leg = [call.kwargs for call in record.call_args_list]
    assert (modulate_leg['from_mode'], modulate_leg['to_mode'], modulate_leg['outcome']) == (
        'deepgram',
        'modulate',
        'exhausted',
    )
    assert (parakeet_leg['from_mode'], parakeet_leg['to_mode'], parakeet_leg['outcome']) == (
        'modulate',
        'parakeet',
        'recovered',
    )
    # The over-quota Modulate rejection is why the session moved on, not Deepgram's 402.
    assert parakeet_leg['reason'] == 'quota'


@pytest.mark.anyio
async def test_an_exhausted_chain_still_raises_after_parakeet_also_fails():
    rejected_modulate = _RejectedSocket()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback') as record,
        pytest.raises(RuntimeError, match='parakeet returned no socket'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=rejected_modulate),
            connect_parakeet=AsyncMock(return_value=None),
        )

    assert [call.kwargs['outcome'] for call in record.call_args_list] == ['exhausted', 'exhausted']
    assert rejected_modulate.finished


@pytest.mark.anyio
async def test_a_parakeet_primary_never_falls_back_to_itself():
    """The chain must not retry the provider that just failed as its own fallback."""
    connect_parakeet = AsyncMock()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, 'record_fallback'),
    ):
        _, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.parakeet,
            connect_primary=AsyncMock(return_value=None),
            connect_modulate=AsyncMock(return_value=SimpleNamespace(is_connection_dead=False, death_reason=None)),
            connect_parakeet=connect_parakeet,
        )

    assert service == STTService.modulate
    connect_parakeet.assert_not_awaited()


@pytest.mark.anyio
async def test_the_deepgram_session_serves_from_parakeet_when_modulate_is_down():
    """End of the receiver path: the session survives on Parakeet, labelled as Parakeet."""
    receiver = _deepgram_receiver()
    parakeet_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=_RejectedSocket())),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=parakeet_socket)) as parakeet,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(receiver_mod, 'parakeet_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    parakeet.assert_awaited_once()
    assert socket is parakeet_socket
    assert receiver.host.stt_service == STTService.parakeet
    assert receiver.host.stt_model == 'parakeet'


@pytest.mark.anyio
async def test_a_language_parakeet_cannot_serve_is_not_offered_to_it():
    receiver = _deepgram_receiver()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=_RejectedSocket())),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock()) as parakeet,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(receiver_mod, 'parakeet_is_configured_fallback', return_value=False),
        patch.object(streaming, 'record_fallback'),
        pytest.raises(RuntimeError, match='modulate rejected the stream'),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    parakeet.assert_not_awaited()


def test_parakeet_is_a_configured_fallback_only_when_the_deployment_can_serve_it():
    with (
        patch.object(streaming, 'stt_service_models', ['dg-nova-3', ' modulate-velma-2', 'parakeet']),
        patch.dict('os.environ', {'HOSTED_PARAKEET_API_URL': 'ws://parakeet.omi.me/v3/stream'}),
    ):
        assert streaming.parakeet_is_configured_fallback('en') is True
        # Parakeet has no multilingual live mode, so a `multi` session must not move to it.
        assert streaming.parakeet_is_configured_fallback('multi') is False
    with (
        patch.object(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2']),
        patch.dict('os.environ', {'HOSTED_PARAKEET_API_URL': 'ws://parakeet.omi.me/v3/stream'}),
    ):
        assert streaming.parakeet_is_configured_fallback('en') is False


# A Modulate primary is no longer rejected by the helper — it walks the chain like
# its siblings. That contract, including the "never falls back to itself" guard this
# assertion used to provide, now lives in test_modulate_connection_fallback.py (#11752).
