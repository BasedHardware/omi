"""V6 config and the v5 env rollback use the same gated clock and wire path."""

import asyncio
import importlib
import json
from unittest.mock import AsyncMock

import pytest

from utils.stt import soniox, soniox_batch
from utils.stt.soniox_wire_ledger import OrderedSonioxProviderClock, SonioxProviderClock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'model,ledger,ordered,rate,url,clock_type',
    [
        (None, True, True, 16000, None, OrderedSonioxProviderClock),
        ('stt-rt-v5', True, True, 16000, None, OrderedSonioxProviderClock),
        ('stt-rt-v6', True, False, 16000, None, SonioxProviderClock),
        ('stt-rt-v5', True, False, 16000, None, SonioxProviderClock),
        ('stt-rt-v6', False, True, 16000, None, type(None)),
        ('stt-rt-v6', True, True, 8000, None, SonioxProviderClock),
        ('stt-rt-v6', True, True, 16000, 'wss://example.invalid', SonioxProviderClock),
        ('custom-model', True, True, 16000, None, SonioxProviderClock),
    ],
)
async def test_model_env_selects_wire_config_and_preserves_clock_gates(
    monkeypatch, model, ledger, ordered, rate, url, clock_type
):
    sock = None
    try:
        with monkeypatch.context() as patch:
            patch.delenv('SONIOX_MODEL', raising=False)
            patch.delenv('SONIOX_WS_URL', raising=False)
            if model is not None:
                patch.setenv('SONIOX_MODEL', model)
            if url is not None:
                patch.setenv('SONIOX_WS_URL', url)
            patch.setenv('SONIOX_API_KEY', 'test-key')
            patch.setenv('SONIOX_WIRE_LEDGER', str(ledger).lower())
            patch.setenv('SONIOX_ORDERED_FINALIZE', str(ordered).lower())
            patch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '0')
            importlib.reload(soniox)
            ws = AsyncMock()
            connect = AsyncMock(return_value=ws)
            patch.setattr(soniox.websockets, 'connect', connect)
            sock = await soniox.process_audio_soniox(lambda _: None, rate, 'multi')
            config = json.loads(ws.send.await_args.args[0])
            assert config == {
                'api_key': 'test-key',
                'model': model or 'stt-rt-v6',
                'audio_format': 'pcm_s16le',
                'sample_rate': rate,
                'num_channels': 1,
                'enable_speaker_diarization': True,
                'enable_language_identification': True,
            }
            assert connect.await_args.args[0] == (url or 'wss://stt-rt.soniox.com/transcribe-websocket')
            assert type(sock._provider_clock) is clock_type
            if clock_type is OrderedSonioxProviderClock:
                clock = sock._provider_clock
                clock.begin_finalize()
                clock.response(
                    {
                        'tokens': [{'text': '<fin>', 'is_final': True}],
                        'final_audio_proc_ms': 121,
                        'total_audio_proc_ms': 121,
                    }
                )
                assert clock.invalid_from == 0
                assert not clock.placeable  # A different v6 quantum cannot authorize capture.
            sock._send_task.cancel()
            await asyncio.gather(sock._send_task, sock._recv_task, return_exceptions=True)
    finally:
        if sock is not None:
            sock._send_task.cancel()
            sock._recv_task.cancel()
            await asyncio.gather(sock._send_task, sock._recv_task, return_exceptions=True)
        importlib.reload(soniox)


def test_batch_request_uses_v6_model():
    assert soniox_batch.transcription_body('test-file', None) == {
        'model': 'stt-async-v6',
        'file_id': 'test-file',
        'enable_speaker_diarization': True,
        'enable_language_identification': True,
    }
