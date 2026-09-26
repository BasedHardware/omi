"""The legacy listen sender must account for audio even when VAD is disabled.

This exercises the receiver's socket installation and buffer flush, the real
VAD gate state machine when enabled, and Modulate-shaped provider timestamps.
Only provider IO and Silero inference are replaced with deterministic doubles.
"""

from types import SimpleNamespace

import numpy as np
import pytest

import routers.listen.receiver as receiver_module
import utils.stt.vad_gate as vad_gate_module
from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from utils.stt.socket import STTSocket
from utils.stt.streaming import STTService, SafeModulateSocket
from utils.stt.vad_gate import GatedSTTSocket
from utils.metrics import OMI_AUDIO_TIMELINE_REJECTS_TOTAL


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class Provider(STTSocket):
    def __init__(self):
        self.samples = 0

    def send(self, data: bytes) -> bool:
        self.samples += len(data) // 2
        return True

    def finalize(self) -> None:
        pass

    def finish(self) -> None:
        pass

    @property
    def is_connection_dead(self) -> bool:
        return False

    @property
    def death_reason(self):
        return None


@pytest.mark.anyio
@pytest.mark.parametrize('sample_rate', [8000, 16000, 48000])
@pytest.mark.parametrize('override', [None, 'disabled', 'failed_init'])
@pytest.mark.parametrize('v2', [False, True])
async def test_legacy_receiver_accounts_every_accepted_modulate_send(monkeypatch, override, sample_rate, v2):
    """The disabled and failed-init cases rejected 10/10 segments on #19198."""
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
    monkeypatch.setattr(receiver_module, 'managed_chain_enabled', lambda _host: False)
    monkeypatch.setattr(receiver_module, 'VAD_GATE_MODE', 'active')
    monkeypatch.setattr(receiver_module, 'is_gate_enabled', lambda: True)
    if override == 'failed_init':
        monkeypatch.setattr(
            vad_gate_module, '_get_ort_session', lambda: (_ for _ in ()).throw(RuntimeError('vad unavailable'))
        )
    else:
        monkeypatch.setattr(vad_gate_module, '_get_ort_session', lambda: object())
    monkeypatch.setattr(
        vad_gate_module,
        'make_fresh_state',
        lambda: (np.zeros((2, 1, 128), dtype=np.float32), np.zeros((1, 64), dtype=np.float32)),
    )
    monkeypatch.setattr(vad_gate_module, 'run_vad_window', lambda window, state, context: (0.9, state, context))

    state = ListenSessionState()
    state.active = True
    state.current_conversation_id = 'conversation'
    if v2:
        state.conversations_awaiting_capture_origin.add('conversation')
    collected = []
    request = SimpleNamespace(
        uid='send-accounting',
        websocket=None,
        sample_rate=sample_rate,
        codec='pcm16',
        channels=1,
        vad_gate_override=None if override == 'failed_init' else override,
        source='desktop',
    )
    host = SimpleNamespace(
        request=request,
        state=state,
        session_id='session',
        is_multi_channel=False,
        use_custom_stt=False,
        stt_service=STTService.modulate,
        stt_model='velma-2',
        stt_language='en',
        vocabulary=[],
        client_device_context=SimpleNamespace(platform='test'),
        transcripts=SimpleNamespace(enqueue=collected.extend),
        audio_bytes_send=None,
        spawn=lambda coro, *, name: coro.close(),
    )
    receiver = ListenReceiver(host, [], {})
    provider = Provider()
    callbacks = {}

    async def connect(callback, sample_rate, modulate_callback=None, epoch=None):
        assert sample_rate == request.sample_rate
        callbacks['provider'] = modulate_callback
        callbacks['epoch'] = epoch
        return provider

    monkeypatch.setattr(receiver, '_create_stt_socket', connect)
    assert await receiver.initialize_stt()

    pcm = b'\x01\x00' * (sample_rate // 5)
    for index in range(10):
        start, end, _ = receiver.capture_timeline.accept(pcm, 1000 + (index + 1) / 5, (index + 1) / 5)
        receiver._note_accepted_frame(start, end)
        receiver._stt_buffer_start_sample = start
        await receiver._flush_stt_buffer(bytearray(pcm))

    outside = OMI_AUDIO_TIMELINE_REJECTS_TOTAL.labels(
        mode='v2' if v2 else 'legacy', reason='outside_accepted_sends', provider='modulate'
    )
    before_outside = outside._value.get()
    adapter = object.__new__(SafeModulateSocket)
    adapter._stream_transcript = callbacks['provider']
    adapter._preseconds = 0
    adapter._prev_partial_text = ''
    adapter._prev_partial_word_count = 0
    adapter._observe_served = lambda: None
    for index in range(10):
        adapter._handle_utterance({'text': f'word {index}', 'start_ms': index * 200, 'duration_ms': 200, 'speaker': 1})

    assert provider.samples == 2 * sample_rate
    assert len(collected) == 10
    assert outside._value.get() - before_outside == 0
    assert isinstance(receiver.stt_socket, GatedSTTSocket)
    assert (receiver.stt_socket._gate is None) == (override is not None)
    assert callbacks['epoch'].send_map.last_capture_sample == 2 * sample_rate
    if v2:
        assert all(
            segment['start'] < segment['end'] and segment.get('audio_alignment') != 'unplaced' for segment in collected
        )
    else:
        assert sum('_capture_abs_start' not in segment for segment in collected) == 0
