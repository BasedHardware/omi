"""Construction-time Parakeet fallback and circuit integration tests."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.stt_provider_policy import PARAKEET_PROVIDER
from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver
from utils.stt import streaming


@pytest.fixture(autouse=True)
def isolate_provider_circuits(monkeypatch):
    """Connection failures in one case must not influence another case's routing."""
    for name in ('_parakeet_circuit', '_deepgram_circuit', '_modulate_circuit', '_soniox_circuit'):
        original = getattr(streaming, name)
        monkeypatch.setattr(
            streaming,
            name,
            streaming.ProviderCircuitBreaker(
                failure_threshold=original._failure_threshold,
                cooldown_seconds=original._cooldown_seconds,
                serve_error_cooldown_seconds=original._serve_error_cooldown_seconds,
                serve_error_successes_to_close=original._serve_error_successes_to_close,
            ),
        )


def test_parakeet_stream_endpoint_prefers_dedicated_url_over_legacy_url():
    with patch.dict(
        os.environ,
        {
            'HOSTED_PARAKEET_STREAM_API_URL': 'ws://stream-parakeet',
            'HOSTED_PARAKEET_API_URL': 'http://batch-parakeet',
        },
    ):
        assert streaming.parakeet_stream_api_url() == 'ws://stream-parakeet'


def test_parakeet_stream_endpoint_keeps_legacy_compatibility():
    with patch.dict(
        os.environ,
        {'HOSTED_PARAKEET_STREAM_API_URL': '', 'HOSTED_PARAKEET_API_URL': 'http://batch-parakeet'},
    ):
        assert streaming.parakeet_stream_api_url() == 'http://batch-parakeet'


def test_real_selector_uses_parakeet_for_mono_and_vendor_for_two_channel_guard():
    """The runtime's channel guard must override the Parakeet preference safely."""
    with (
        patch.object(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2', 'dg-nova-3']),
        patch.object(streaming, '_deepgram_is_available', return_value=False),
        patch.dict(os.environ, {'HOSTED_PARAKEET_STREAM_API_URL': 'http://stream-parakeet'}),
        patch.object(streaming, 'record_fallback'),
    ):
        mono = streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='parakeet')
        two_channel = streaming.get_stt_service_for_language(
            'en',
            multi_lang_enabled=False,
            preferred_service='parakeet',
            exclude=frozenset({PARAKEET_PROVIDER}),
        )

    assert mono == (streaming.STTService.parakeet, 'en', 'parakeet')
    assert two_channel == (streaming.STTService.modulate, 'en', 'velma-2')


@pytest.mark.parametrize(
    ('language', 'preferred_service', 'exclude', 'expected'),
    [
        ('en', None, frozenset(), (streaming.STTService.parakeet, 'multi', 'parakeet')),
        ('fr', None, frozenset(), (streaming.STTService.parakeet, 'multi', 'parakeet')),
        ('zh', None, frozenset(), (streaming.STTService.modulate, 'multi', 'velma-2')),
        ('fr', 'parakeet', frozenset(), (streaming.STTService.parakeet, 'multi', 'parakeet')),
        ('fr', 'parakeet', frozenset({PARAKEET_PROVIDER}), (streaming.STTService.modulate, 'multi', 'velma-2')),
        ('zh', 'parakeet', frozenset(), (streaming.STTService.modulate, 'multi', 'velma-2')),
    ],
)
def test_tdt_v3_multilingual_selection_respects_language_capability_and_failover(
    language, preferred_service, exclude, expected
):
    """TDT v3 accepts supported languages in auto-detect mode, while zh stays on Velma."""
    with (
        patch.object(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2']),
        patch.dict(os.environ, {'HOSTED_PARAKEET_STREAM_API_URL': 'http://stream-parakeet'}),
        patch.object(streaming, 'record_fallback'),
    ):
        result = streaming.get_stt_service_for_language(
            language,
            multi_lang_enabled=True,
            preferred_service=preferred_service,
            exclude=exclude,
        )

    assert result == expected


@pytest.mark.parametrize('base_language', ['zh', 'ar'])
@pytest.mark.parametrize('primary_service', [streaming.STTService.modulate, streaming.STTService.deepgram])
@pytest.mark.asyncio
async def test_vendor_failures_do_not_route_unsupported_multi_language_to_parakeet(base_language, primary_service):
    """Keep the original zh/ar capability visible after live selection resolves to ``multi``."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        language=base_language,
        stt_service=primary_service,
        stt_language='multi',
        stt_model='velma-2' if primary_service == streaming.STTService.modulate else 'nova-3',
        vocabulary=[],
        is_multi_channel=False,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())

    with (
        patch.object(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2', 'dg-nova-3']),
        patch.dict(os.environ, {'HOSTED_PARAKEET_STREAM_API_URL': 'http://stream-parakeet'}),
        patch.object(
            receiver_mod,
            'process_audio_modulate',
            new=AsyncMock(side_effect=RuntimeError('modulate down')),
        ),
        patch.object(
            receiver_mod,
            'process_audio_dg',
            new=AsyncMock(side_effect=RuntimeError('deepgram down')),
        ),
        patch.object(receiver_mod, 'deepgram_fallback_model', return_value='nova-3'),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock()) as parakeet,
        patch.object(streaming, 'record_fallback'),
        pytest.raises(
            RuntimeError,
            match='deepgram down' if primary_service == streaming.STTService.modulate else 'modulate down',
        ),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    parakeet.assert_not_awaited()


def test_explicit_modulate_preference_survives_new_parakeet_default():
    with (
        patch.object(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2']),
        patch.dict(os.environ, {'HOSTED_PARAKEET_STREAM_API_URL': 'http://stream-parakeet'}),
    ):
        result = streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='modulate')

    assert result == (streaming.STTService.modulate, 'en', 'velma-2')


@pytest.mark.asyncio
async def test_process_audio_parakeet_uses_dedicated_stream_endpoint():
    socket = MagicMock()
    socket.start = AsyncMock()
    with (
        patch.dict(
            os.environ,
            {
                'HOSTED_PARAKEET_STREAM_API_URL': 'http://stream-parakeet',
                'HOSTED_PARAKEET_API_URL': 'http://batch-parakeet',
            },
        ),
        patch.object(streaming, 'ParakeetWebSocketSocket', return_value=socket) as socket_cls,
    ):
        result = await streaming.process_audio_parakeet(MagicMock(), 'en', 16000, 1)

    assert result is socket
    socket_cls.assert_called_once()
    assert socket_cls.call_args.args[1:] == ('ws://stream-parakeet/v3/stream', 16000)
    socket.start.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_capacity_rejection_falls_back_to_modulate_without_poisoning_circuit():
    circuit = MagicMock()
    circuit.allow_request.return_value = True
    fallback_socket = object()

    async def rejected_parakeet():
        raise streaming.ParakeetConnectionError('capacity_full')

    with patch.object(streaming, '_parakeet_circuit', circuit), patch.object(streaming, 'record_fallback') as record:
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=streaming.STTService.parakeet,
            connect_primary=rejected_parakeet,
            connect_modulate=AsyncMock(return_value=fallback_socket),
        )

    assert socket is fallback_socket
    assert service == streaming.STTService.modulate
    circuit.record_rejection.assert_called_once_with('capacity_full')
    circuit.record_failure.assert_not_called()
    record.assert_called_once_with(
        component='stt_selection',
        from_mode='parakeet',
        to_mode='modulate',
        reason='capacity_full',
        outcome='recovered',
    )


@pytest.mark.asyncio
async def test_open_parakeet_circuit_skips_connection_and_uses_modulate():
    circuit = MagicMock()
    circuit.allow_request.return_value = False
    connect_primary = AsyncMock()
    fallback_socket = object()

    with patch.object(streaming, '_parakeet_circuit', circuit), patch.object(streaming, 'record_fallback'):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=streaming.STTService.parakeet,
            connect_primary=connect_primary,
            connect_modulate=AsyncMock(return_value=fallback_socket),
        )

    assert socket is fallback_socket
    assert service == streaming.STTService.modulate
    connect_primary.assert_not_awaited()


@pytest.mark.asyncio
async def test_unhealthy_parakeet_connection_records_failure_before_fallback():
    circuit = MagicMock()
    circuit.allow_request.return_value = True

    async def unavailable_parakeet():
        raise streaming.ParakeetConnectionError('timeout')

    with patch.object(streaming, '_parakeet_circuit', circuit), patch.object(streaming, 'record_fallback'):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=streaming.STTService.parakeet,
            connect_primary=unavailable_parakeet,
            connect_modulate=AsyncMock(return_value=object()),
        )

    circuit.record_failure.assert_called_once_with()
    circuit.record_rejection.assert_not_called()


@pytest.mark.asyncio
async def test_parakeet_primary_walks_modulate_then_deepgram_and_adopts_dg_model():
    """A Parakeet connect failure must preserve the callback shape on each leg."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=streaming.STTService.parakeet,
        stt_language='en',
        stt_model='parakeet',
        vocabulary=[],
        is_multi_channel=False,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())
    callback = MagicMock(name='parakeet_callback')
    modulate_callback = MagicMock(name='modulate_callback')
    dg_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)) as modulate,
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)) as deepgram,
        patch.object(receiver_mod, 'deepgram_fallback_model', return_value='nova-3'),
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(
            receiver,
            callback,
            16000,
            modulate_callback=modulate_callback,
        )

    assert socket is dg_socket
    assert host.stt_service == streaming.STTService.deepgram
    assert host.stt_model == 'nova-3'
    assert 'parakeet' in receiver._stt_failed_providers
    assert modulate.await_args.args[0] is modulate_callback
    assert deepgram.await_args.args[0] is callback


@pytest.mark.asyncio
async def test_parakeet_primary_does_not_retry_an_excluded_modulate_leg():
    """A rebuild's failed-provider set must reach the connection helper."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=streaming.STTService.parakeet,
        stt_language='en',
        stt_model='parakeet',
        vocabulary=[],
        is_multi_channel=False,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())
    dg_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock()) as modulate,
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=dg_socket)) as deepgram,
        patch.object(receiver_mod, 'deepgram_fallback_model', return_value='nova-3'),
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(
            receiver,
            MagicMock(),
            16000,
            exclude=frozenset({'modulate'}),
        )

    assert socket is dg_socket
    modulate.assert_not_awaited()
    deepgram.assert_awaited_once()


@pytest.mark.asyncio
async def test_multi_channel_parakeet_keeps_existing_modulate_route_without_new_dg_leg():
    """The mono-only migration must not silently alter channel routing."""
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=streaming.STTService.parakeet,
        stt_language='en',
        stt_model='parakeet',
        vocabulary=[],
        is_multi_channel=True,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())
    modulate_socket = SimpleNamespace(is_connection_dead=False, death_reason=None)

    with (
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=None)) as parakeet,
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=modulate_socket)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock()) as deepgram,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert socket is modulate_socket
    parakeet.assert_not_awaited()
    deepgram.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_channel_vendor_primary_does_not_fall_back_to_parakeet():
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=streaming.STTService.modulate,
        stt_language='en',
        stt_model='velma-2',
        vocabulary=[],
        is_multi_channel=True,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())

    with (
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock()) as parakeet,
        patch.object(receiver_mod, 'deepgram_fallback_model', return_value=None),
        patch.object(receiver_mod, 'parakeet_is_configured_fallback', return_value=True),
        patch.object(streaming, 'record_fallback'),
        pytest.raises(RuntimeError, match='No STT fallback provider was configured'),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    parakeet.assert_not_awaited()


@pytest.mark.asyncio
async def test_parakeet_does_not_call_an_unconfigured_modulate_fallback():
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=streaming.STTService.parakeet,
        stt_language='en',
        stt_model='parakeet',
        vocabulary=[],
        is_multi_channel=False,
    )
    receiver = SimpleNamespace(host=host, _stt_failed_providers=set())

    with (
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock()) as modulate,
        patch.object(receiver_mod, 'deepgram_fallback_model', return_value=None),
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=False),
        patch.object(receiver_mod, 'parakeet_is_configured_fallback', return_value=False),
        patch.object(streaming, 'record_fallback'),
        pytest.raises(RuntimeError, match='No STT fallback provider was configured'),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    modulate.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_failure_is_reported_as_exhausted():
    circuit = MagicMock()
    circuit.allow_request.return_value = False

    with patch.object(streaming, '_parakeet_circuit', circuit), patch.object(streaming, 'record_fallback') as record:
        with pytest.raises(RuntimeError, match='modulate unavailable'):
            await streaming.connect_stt_socket_with_fallback(
                primary_service=streaming.STTService.parakeet,
                connect_primary=AsyncMock(),
                connect_modulate=AsyncMock(side_effect=RuntimeError('modulate unavailable')),
            )

    record.assert_called_once_with(
        component='stt_selection',
        from_mode='parakeet',
        to_mode='modulate',
        reason='circuit_open',
        outcome='exhausted',
    )


@pytest.mark.asyncio
async def test_shared_socket_drain_awaits_async_provider_teardown():
    socket = MagicMock()
    socket.drain_and_close = AsyncMock()

    await streaming.drain_stt_socket(socket)

    socket.drain_and_close.assert_awaited_once_with()
    socket.finish.assert_not_called()


@pytest.mark.asyncio
async def test_shared_socket_drain_finishes_legacy_sync_test_double():
    socket = MagicMock()
    socket.drain_and_close.return_value = None

    await streaming.drain_stt_socket(socket)

    socket.finish.assert_called_once_with()
