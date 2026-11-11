"""Offline provider parser -> actual recovery pump -> receiver -> StrictFirestore."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import os
from pathlib import Path

from prometheus_client import REGISTRY

import pytest

from config.live_stt_replay import ReplayLimits
from routers.listen import legacy_recovery, receiver as receiver_module
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401
from tests.unit.test_capture_window_merge_union_r5 import harness, known, raw, tick
from tests.unit.test_capture_window_merge_union_r7 import adapter
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt import live_session
from utils.stt import resilient_stream
from utils.stt.resilient_stream import ResilientAudio
from utils.stt.replay_capture_accounting import record_replay_sends
from utils.stt.streaming import STTService
from utils.stt.vad_gate import GatedSTTSocket
from utils.stt.parakeet_window import WindowedParakeetSocket
from utils.stt.window_anchor import RawSegment

FLAG = 'LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS'
PROVIDERS = ['soniox', 'deepgram', 'modulate', 'parakeet']


async def parser(monkeypatch, provider, callback):
    if provider != 'parakeet':
        return await adapter(monkeypatch, provider, callback)
    batch = object.__new__(WindowedParakeetSocket)
    batch._diarize = False
    batch._sample_rate = RATE
    batch._last_emitted_end = 0.0

    async def emit(segment):
        segments, _ = await batch._materialize(
            [RawSegment(text=segment['text'], start=segment['start'], end=segment['end'])],
            b'\0\0' * RATE * 10,
            0,
            10,
        )
        for item in segments:
            item['speaker'] = segment['speaker']
            item['id'] = segment['id']
        callback(segments)

    return emit


class LocalTransport:
    """Accepted PCM followed by a callback on the loop, as queued providers do."""

    is_connection_dead = False
    idle_close_enabled = False
    manages_vad = False
    typed_death_reason = None
    death_reason = None

    def __init__(self, emit):
        self.emit = emit
        self.samples = 0
        self.sent = []
        self.pending = []
        self.reject = False

    def send(self, data, start_sample=None):
        if self.reject:
            return False
        self.sent.append((start_sample, data))
        self.samples += len(data) // 2
        return True

    async def complete_send(self):
        await asyncio.sleep(0)
        return True

    def finish(self):
        pass


async def recover(monkeypatch, enabled, provider, mode='paced'):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    receiver.host.stt_service = STTService(provider)
    receiver.host.state.active = True
    receiver.host.state.stt_terminal_failure = False
    receiver.recovery.begin()
    receiver.speaker_provider_epoch._connection_scope = 'r8-fixed-scope'
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    # Non-zero capture origin: a new provider socket starts at provider sample 0.
    receiver.capture_timeline.accept(b'\0\0' * RATE * 3, T0 + 3, 3)
    prefix = b'\1\0' * RATE * 2
    receiver.capture_timeline.accept(prefix, T0 + 5, 5)
    epoch.replay_origin_sample = RATE * 3
    ring = ResilientAudio(RATE)
    ring.append(prefix, RATE * 3)
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
    return receiver, epoch, transport, emit, processor, store


async def deliver(emit, segment):
    result = emit(segment)
    if result is not None:
        await result


@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('phase', ['prefix', 'tail'])
@pytest.mark.parametrize('mode', ['paced', 'legacy'])
async def test_paced_raw_replay_prefix_and_live_tail_capture_mapping(monkeypatch, provider, enabled, phase, mode):
    before = counters()
    receiver, epoch, transport, emit, processor, store = await recover(monkeypatch, enabled, provider, mode)
    if phase == 'prefix':
        await deliver(emit, raw('prefix', 'Recovered prefix.', 0.2, 1.8))
    prefix_rows = await tick(receiver, processor, store)
    assert known(prefix_rows) == (int(enabled) if phase == 'prefix' else 0)
    if enabled and phase == 'prefix':
        assert (prefix_rows[0]['audio_capture_start'], prefix_rows[0]['audio_capture_end']) == (T0 + 3.2, T0 + 4.8)
        assert epoch.send_map.last_provider_sample == 2 * RATE
    # Queued tail timestamps include the prefix. Main records this packet at 0.
    tail = b'\2\0' * RATE
    receiver.capture_timeline.accept(tail, T0 + 6, 6)
    assert receiver.stt_socket.send(tail, start_sample=5 * RATE)
    for _ in range(40):
        if sum(len(data) for _, data in transport.sent) == RATE * 6:
            break
        await asyncio.sleep(0)
    assert sum(len(data) for _, data in transport.sent) == len(tail) + RATE * 4
    await deliver(emit, raw('tail', 'New tail.', 2.2, 2.8, 'SPEAKER_01'))
    rows = await tick(receiver, processor, store)
    assert known(rows) == (2 if phase == 'prefix' else 1) * int(enabled)
    if enabled:
        assert (rows[-1]['audio_capture_start'], rows[-1]['audio_capture_end']) == (T0 + 5.2, T0 + 5.8)
    # Genuine overshoot must stay unknown despite the new send registrations.
    await deliver(emit, raw('overshoot', 'Beyond accepted audio.', 7, 8, 'SPEAKER_02'))
    rows = await tick(receiver, processor, store)
    assert 'audio_capture_start' not in rows[-1]
    assert rows[-1]['text'] == 'Beyond accepted audio.'
    save_parity(f'{provider}-{phase}-{mode}', rows, before, enabled)
    task = getattr(receiver.stt_socket, '_task', None)
    if task is not None:
        await task


@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('enabled', [False, True])
async def test_managed_accepted_audio_survives_finalize_failure(monkeypatch, provider, enabled):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    receiver.host.language = 'en'
    receiver.host.stt_service = STTService(provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)

    def finalize():
        raise RuntimeError('local flush failure after audio admission')

    transport.finalize = finalize
    output = SimpleNamespace(
        audio_to_send=b'\0\0' * RATE, is_speech=False, should_finalize=True, send_spans=((0, RATE),)
    )
    gate = SimpleNamespace(mode='active', process_audio=lambda *a, **kw: output)
    session = live_session.LiveChainSession(receiver)
    leg = live_session.LiveLegSocket(transport, gate, session, STTService(provider), RATE, False, False, epoch)
    receiver.capture_timeline.accept(output.audio_to_send, T0 + 1, 1)
    # Transport failure stays failure, but the earlier accepted send remains evidence.
    assert leg.send(output.audio_to_send, start_sample=0) is False
    await deliver(emit, raw('accepted', 'Final after failed flush.', 0.1, 0.8))
    rows = await tick(receiver, processor, store)
    assert known(rows) == int(enabled)
    assert transport.sent == [(None, output.audio_to_send)]
    leg.finish()


def counters():
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in REGISTRY.collect()
        for sample in family.samples
        if sample.name.endswith('_total')
        and sample.name.startswith('omi_')
        and sample.name != 'omi_audio_timeline_outside_sends_total'
    }


def save_parity(key, rows, before, enabled):
    output = os.getenv('CAPTURE_R8_PARITY_OUTPUT')
    if output and not enabled:
        after = counters()
        delta = [
            dict(name=name, labels=dict(labels), value=after.get((name, labels), 0) - before.get((name, labels), 0))
            for name, labels in sorted(set(before) | set(after))
            if after.get((name, labels), 0) != before.get((name, labels), 0)
        ]
        Path(output + '.' + key + '.json').write_text(
            json.dumps(dict(payloads=rows, existing_metrics=delta), indent=2, sort_keys=True) + '\n'
        )


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('recovery', [False, True])
async def test_same_provider_reconnect_uses_fresh_zero_axis(monkeypatch, enabled, recovery):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true' if recovery else 'false')
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'true')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, 'soniox')
    receiver.host.state.active = True
    receiver.host.stt_service = STTService.soniox
    prefix = b'\1\0' * RATE * 2
    receiver.capture_timeline.accept(b'\0\0' * RATE * 3, T0 + 3, 3)
    receiver.capture_timeline.accept(prefix, T0 + 5, 5)
    ring = receiver._resilient_audio
    assert ring is not None
    ring.append(prefix, 3 * RATE)
    old = LocalTransport(None)
    old.is_connection_dead, old.typed_death_reason = True, 'soniox_rotation'
    receiver.stt_socket = old
    emit = await parser(monkeypatch, 'soniox', callback)
    transport = LocalTransport(emit)
    receiver._stt_rebuild = (lambda: (callback, callback, epoch), RATE)
    receiver._create_stt_socket = AsyncMock(return_value=transport)
    monkeypatch.setattr(receiver_module, 'record_live_connection', lambda *a: None)
    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(resilient_stream, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    assert await receiver._reconnect_stt_socket_locked()
    await deliver(emit, raw('reconnect', 'Reconnected audio.', 0.2, 1.8))
    rows = await tick(receiver, processor, store)
    # The old (unpaced) reconnect already wraps its replay before sending.
    assert known(rows) == int(enabled or not recovery)
    if enabled or not recovery:
        assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == (T0 + 3.2, T0 + 4.8)
    assert sum(len(data) for _, data in transport.sent) == len(prefix)


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('fault', ['reject', 'capture_gap', 'wall_gap', 'overshoot_edge', 'unobserved'])
async def test_replay_never_fills_unobserved_audio(monkeypatch, enabled, provider, fault):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    prefix = b'\0\0' * RATE
    receiver.capture_timeline.accept(prefix, T0 + 1, 1)
    if fault in ('capture_gap', 'wall_gap'):
        if fault == 'capture_gap':
            receiver.capture_timeline.accept(prefix, T0 + 2, 2)  # never sent
        receiver.capture_timeline.accept(
            prefix, T0 + (7 if fault == 'wall_gap' else 3), 7 if fault == 'wall_gap' else 3
        )
    wrapped = record_replay_sends(transport, epoch)
    transport.reject = fault == 'reject'
    assert wrapped.send(prefix, start_sample=3 * RATE if fault == 'unobserved' else 0) is (fault != 'reject')
    if fault in ('capture_gap', 'wall_gap'):
        assert wrapped.send(prefix, start_sample=RATE * (2 if fault == 'capture_gap' else 1))
    first, end = (
        (0.8, 1.2) if fault in ('capture_gap', 'wall_gap') else (0.2, 1.01) if fault == 'overshoot_edge' else (0.2, 0.8)
    )
    await deliver(emit, raw('refused', 'Keep this unplaced.', first, end))
    rows = await tick(receiver, processor, store)
    assert known(rows) == 0
    assert rows[0]['text'] == 'Keep this unplaced.'
    if enabled and fault in ('reject', 'unobserved'):
        assert epoch.send_map.span_count == 0


@pytest.mark.parametrize('provider', PROVIDERS)
async def test_managed_replay_is_not_registered_twice(monkeypatch, provider):
    monkeypatch.setenv(FLAG, 'true')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    receiver.host.language = 'en'
    receiver.host.stt_service = STTService(provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    session = live_session.LiveChainSession(receiver)
    leg = live_session.LiveLegSocket(transport, None, session, STTService(provider), RATE, False, False, epoch)
    pcm = b'\0\0' * RATE
    receiver.capture_timeline.accept(pcm, T0 + 1, 1)
    assert record_replay_sends(leg, epoch) is leg
    assert leg.replay_send(pcm, 0)
    assert epoch.send_map.last_provider_sample == RATE
    await deliver(emit, raw('managed', 'Managed replay.', 0.1, 0.8))
    assert known(await tick(receiver, processor, store)) == 1
    leg.finish()


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('axis', ['compact', 'elapsed_candidate'])
async def test_gated_provider_axis_is_never_guessed(monkeypatch, enabled, provider, axis):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    monkeypatch.setenv('SONIOX_ELAPSED_AXIS', 'shadow')
    receiver, callback, epoch, _, processor, store = harness(monkeypatch, False, provider)
    emit = await parser(monkeypatch, provider, callback)
    transport = LocalTransport(emit)
    gate = SimpleNamespace(
        uid='offline',
        mode='active',
        process_audio=lambda data, wall, **kw: SimpleNamespace(
            audio_to_send=data, send_spans=((kw['start_sample'], len(data) // 2),), should_finalize=False
        ),
    )
    sender = GatedSTTSocket(transport, gate=gate, passthrough_audio=False, send_tracker=epoch)
    pcm = b'\0\0' * RATE
    receiver.capture_timeline.accept(pcm, T0 + 1, 1)
    assert sender.send(pcm, start_sample=0)
    receiver.capture_timeline.accept(pcm * 40, T0 + 41, 41)  # VAD skipped, never provider-sent
    receiver.capture_timeline.accept(pcm, T0 + 42, 42)
    assert sender.send(pcm, start_sample=41 * RATE)
    first = 1.2 if axis == 'compact' else 41.2
    await deliver(emit, raw('vad', 'Speech after skipped silence.', first, first + 0.6))
    rows = await tick(receiver, processor, store)
    assert known(rows) == int(axis == 'compact')
    if axis == 'compact':
        assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == pytest.approx(
            (T0 + 41.2, T0 + 41.8), abs=1 / RATE, rel=0
        )
    # The same observed sends cannot establish whether late elapsed-looking
    # tokens identify that span or are genuine provider drift. Never guess.


@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('enabled', [False, True])
async def test_delayed_prefix_final_never_borrows_live_tail_samples(monkeypatch, provider, enabled):
    receiver, epoch, transport, emit, processor, store = await recover(monkeypatch, enabled, provider)
    tail = b'\2\0' * RATE
    receiver.capture_timeline.accept(tail, T0 + 6, 6)
    assert receiver.stt_socket.send(tail, start_sample=5 * RATE)
    for _ in range(40):
        if sum(len(data) for _, data in transport.sent) == RATE * 6:
            break
        await asyncio.sleep(0)
    await deliver(emit, raw('late-prefix', 'Late prefix final.', 0.2, 0.8))
    rows = await tick(receiver, processor, store)
    assert known(rows) == 1
    # Main's incomplete map can appear "known" while assigning prefix speech
    # to newly accepted tail bytes. ON must retain the original prefix samples.
    first = 3.2 if enabled else 5.2
    end = 3.8 if enabled else 5.8
    assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == pytest.approx(
        (T0 + first, T0 + end), abs=1 / RATE, rel=0
    )
    task = receiver.stt_socket._task
    if task is not None:
        await task
