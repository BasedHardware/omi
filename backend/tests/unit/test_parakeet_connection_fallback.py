"""Construction-time Parakeet fallback and circuit integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.stt import streaming


@pytest.fixture(autouse=True)
def _fresh_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the module-level breakers per test.

    The breakers are singletons; leg-level circuit gating now makes cross-test
    state consequential (an earlier file's serve-death opened the Deepgram
    circuit, and later files' fallback legs were filtered by it).
    """
    from utils.stt.provider_resilience import ProviderCircuitBreaker

    for name in ('_deepgram_circuit', '_modulate_circuit', '_parakeet_circuit', '_soniox_circuit'):
        monkeypatch.setattr(streaming, name, ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))


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
