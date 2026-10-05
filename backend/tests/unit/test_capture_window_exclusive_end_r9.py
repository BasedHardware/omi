"""Actual four-provider parsers -> recovery/gated sends -> receiver -> StrictFirestore."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from config.live_stt_replay import ReplayLimits
from routers.listen import receiver as receiver_module, legacy_recovery
from utils.stt.resilient_stream import ResilientAudio
from utils.stt.streaming import STTService
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401

from tests.unit.test_capture_window_translator_r8 import LocalTransport, parser, deliver
from tests.unit.test_capture_window_merge_union_r5 import harness, raw, tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt.vad_gate import GatedSTTSocket

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('provider', ['soniox', 'deepgram', 'modulate', 'parakeet'])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('mode', ['paced', 'legacy'])
@pytest.mark.parametrize('first_capture,second_capture', [(0, 2), (0, 0), (1, 0)])
@pytest.mark.parametrize('end', [1.0, 1.1])
async def test_exclusive_prefix_end_does_not_include_unsent_gap(
    monkeypatch, provider, enabled, mode, first_capture, second_capture, end
):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS', str(enabled).lower())
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    pcm = b'\0\0' * RATE
    receiver.capture_timeline.accept(pcm * 3, T0 + 3, 3)
    receiver.host.stt_service = STTService(provider)
    receiver.host.state.active = True
    receiver.host.state.stt_terminal_failure = False
    receiver.recovery.begin()
    ring = ResilientAudio(RATE)
    ring.append(pcm, round(RATE * first_capture))
    ring.append(pcm, round(RATE * second_capture))
    epoch.replay_origin_sample = round(RATE * first_capture)
    hop = SimpleNamespace(settled=True, note_failure=lambda *a, **kw: None)
    monkeypatch.setattr(receiver_module, 'record_live_connection', lambda *a: None)
    if mode == 'paced':
        assert await receiver._pump_replacement(
            transport,
            epoch,
            hop,
            ring.snapshot(),
            ring,
            None,
            sample_rate=RATE,
            limits=ReplayLimits(),
            dead_provider='parakeet',
        )
    else:
        receiver._window_replay_audio = ring
        receiver._window_replay_started = True
        receiver._stt_rebuild = (lambda: (callback, callback, epoch), RATE)
        receiver.host.stt_language, receiver.host.stt_model = 'en', 'parakeet-window'
        receiver.host.stt_service = STTService.parakeet
        receiver.stt_socket = LocalTransport(None)
        receiver._create_stt_socket = AsyncMock(return_value=transport)
        monkeypatch.setattr(
            receiver_module, 'select_live_replacement', lambda *a, **kw: (STTService(provider), 'en', provider)
        )
        monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=True))
        assert await legacy_recovery.rebuild_stt_socket_locked(receiver)
    assert sum(len(data) for _, data in transport.sent) == len(pcm) * 2
    # The exact end belongs entirely to the first send. Crossing into a
    # gapped, duplicated or reordered second send must refuse placement.
    await deliver(emit, raw('boundary', 'Prefix boundary.', 0.2, end))
    rows = await tick(receiver, processor, store)
    if enabled and end == 1.0:
        assert known(rows) == 1
        assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == pytest.approx(
            (T0 + first_capture + 0.2, T0 + first_capture + 1), abs=1 / RATE, rel=0
        )
    else:
        assert known(rows) == 0


@pytest.mark.parametrize('provider', ['soniox', 'deepgram', 'modulate', 'parakeet'])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('end', [0.9, 1.0, 1.1, 2.0])
async def test_ordinary_gated_send_exact_boundary(monkeypatch, provider, enabled, end):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS', str(enabled).lower())
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    gate = SimpleNamespace(
        uid='offline',
        mode='active',
        process_audio=lambda data, wall, **kw: SimpleNamespace(
            audio_to_send=data if kw['start_sample'] != RATE else b'',
            send_spans=((kw['start_sample'], len(data) // 2),) if kw['start_sample'] != RATE else (),
            should_finalize=False,
        ),
    )
    sender = GatedSTTSocket(transport, gate=gate, passthrough_audio=False, send_tracker=epoch)
    pcm = b'\0\0' * RATE
    for first in range(3):
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + first + 1, first + 1)
        assert sender.send(pcm, start_sample=start)
    assert sum(len(data) for _, data in transport.sent) == 2 * len(pcm)
    await deliver(emit, raw('vad-boundary', 'Before withheld silence.', 0.2, end))
    rows = await tick(receiver, processor, store)
    assert rows[0]['text'] == 'Before withheld silence.'
    assert known(rows) == int(end <= 1)
    if end <= 1:
        assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == pytest.approx(
            (T0 + 0.2, T0 + end), abs=1 / RATE, rel=0
        )
