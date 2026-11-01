"""Ladder shadow metering stays off the listen runtime file's unrelated regressions."""

from types import SimpleNamespace

import pytest

from routers.listen.runtime import ListenSessionRuntime
from utils.stt.streaming import STTService


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
@pytest.mark.parametrize('flag,managed', [(False, False), (True, False), (False, True), (True, True)])
async def test_ladder_shadow_uses_fractional_accepted_managed_speech(monkeypatch, flag, managed):
    import routers.listen.runtime as runtime_module

    monkeypatch.setenv('LADDER_V1_LANE_METERING_ENABLED', 'true' if flag else 'false')
    monkeypatch.setattr(runtime_module, 'managed_chain_enabled', lambda runtime: managed)
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'record_live_stt_audio_seconds', lambda **kwargs: None)
    calls = []
    monkeypatch.setattr(runtime_module, 'record_usage', lambda *args, **kwargs: calls.append(kwargs))
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='ladder-user')
    runtime.use_custom_stt = False
    runtime.persistence = _Persistence()
    runtime.stt_service = STTService.soniox
    runtime.client_device_context = SimpleNamespace(platform='android')
    runtime.state = SimpleNamespace(
        fair_use_track_dg_usage=False,
        dg_usage_ms_pending=0,
        last_usage_record_timestamp=123.0,
        words_transcribed_since_last_record=0,
        last_audio_received_time=124.0,
    )
    runtime.receiver = SimpleNamespace(vad_gate=SimpleNamespace(consume_speech_ms_delta=lambda: 4200))
    await runtime._flush_usage(final=True)
    metadata = calls[0]['usage_metadata']
    if flag and managed:
        assert metadata['accepted_speech_seconds'] == 4.2
    else:
        assert 'accepted_speech_seconds' not in metadata
