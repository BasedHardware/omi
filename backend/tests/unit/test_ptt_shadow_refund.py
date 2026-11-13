"""Refunded PTT streams release shadow holds even when the daily budget failed open."""

from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def ptt_modules():
    import routers.chat as chat
    from utils.stt.allowance_session import Operation
    from utils.stt.streaming import STTService
    from utils.stt import live_failure

    return chat, Operation, STTService, live_failure


@pytest.mark.asyncio
@pytest.mark.parametrize('reserved_ms', [0, 30_000])
@pytest.mark.parametrize('failure', ['connect', 'drain'])
async def test_failed_ptt_settles_shadow_zero_after_daily_refund(monkeypatch, ptt_modules, reserved_ms, failure):
    chat, Operation, STTService, live_failure = ptt_modules

    monkeypatch.setattr(chat, 'get_stt_service_for_language', lambda *a, **kw: (STTService.modulate, 'en', 'test'))
    monkeypatch.setattr(chat, 'check_rate_limit', lambda *a: (True, 1, 0))
    monkeypatch.setattr(chat, 'try_reserve_session_budget', lambda *a: (True, reserved_ms, 0, 0))
    refund = Mock()
    monkeypatch.setattr(chat, 'settle_reserved_duration', refund)
    monkeypatch.setattr(
        chat, 'process_audio_modulate', AsyncMock(return_value=None if failure == 'connect' else Mock())
    )
    monkeypatch.setattr(chat, 'drain_stt_socket', AsyncMock(side_effect=RuntimeError('synthetic drain failure')))
    monkeypatch.setattr(live_failure, 'terminate_live_stt_session', AsyncMock())
    billed = Mock()
    monkeypatch.setattr(Operation, 'billed', billed)
    socket = Mock()
    socket.accept = AsyncMock()
    socket.close = AsyncMock()
    socket.receive = AsyncMock(return_value={'type': 'websocket.disconnect'})

    await chat.transcribe_voice_message_stream(socket, uid='synthetic', x_app_platform='desktop')

    if reserved_ms:
        refund.assert_called_once_with('synthetic', reserved_ms, 0)
    else:
        refund.assert_not_called()
    billed.assert_called_once_with(0)
    if failure == 'connect':
        socket.close.assert_awaited_once_with(code=1011, reason='Transcription service unavailable')
