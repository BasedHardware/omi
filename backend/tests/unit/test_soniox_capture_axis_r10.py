"""Actual managed Soniox wire adapter -> receiver -> transcript tick -> StrictFirestore."""

import asyncio
from collections import deque
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID
import uuid as soniox_capture_uuid

import pytest
from prometheus_client import REGISTRY

from routers.listen.receiver import ListenReceiver
from tests.unit.test_capture_window_merge_union_r5 import harness, tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt import live_session, soniox, soniox_capture_axis as diagnostics
from utils.stt.streaming import STTService
from utils.stt.vad_gate import VADStreamingGate
from utils.stt import vad_gate
from utils.stt.soniox_idle import IdleSonioxSocket


class Wire:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.sent = []
        self.writes = asyncio.Queue()
        self.reject = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.messages.get()

    async def send(self, value):
        if self.reject:
            raise RuntimeError('local wire failure')
        self.sent.append(value)
        self.writes.put_nowait(value)

    async def close(self):
        pass


def values():
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in REGISTRY.collect()
        for sample in family.samples
        if sample.name.startswith('omi_')
        and sample.name.endswith('_total')
        and not sample.name.startswith(('omi_soniox_capture_axis_', 'omi_audio_timeline_elapsed_validation_detail_'))
    }


async def managed(monkeypatch, enabled):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', str(enabled).lower())
    monkeypatch.setenv('SONIOX_ELAPSED_AXIS', 'shadow')
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '0')
    monkeypatch.setenv('SONIOX_API_KEY', 'offline-placeholder')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS', 'true')
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    receiver, _, epoch, _, processor, store = harness(monkeypatch, True, 'soniox')
    host = receiver.host
    host.language = host.stt_language = 'en'
    host.stt_service, host.stt_model = STTService.soniox, 'soniox'
    host.vocabulary, host.language_profile = [], None
    host.request.vad_gate_override = 'enabled'
    wire = Wire()
    monkeypatch.setattr(soniox.websockets, 'connect', AsyncMock(return_value=wire))
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)
    gate = VADStreamingGate(sample_rate=RATE, mode='active', hangover_ms=0)
    # Only the classifier is deterministic. Real pre-roll, hangover, finalize,
    # span bookkeeping and compact remap run unchanged.
    monkeypatch.setattr(gate, '_run_vad', lambda pcm: pcm[:2] == b'\1\0')
    monkeypatch.setattr(live_session, 'VADStreamingGate', lambda **kw: gate)
    session = live_session.LiveChainSession(receiver)
    leg = await session.connect(RATE, epoch, same_provider=True)
    return receiver, epoch, processor, store, leg, wire, gate


async def close(leg):
    leg.finish()
    raw = leg.raw
    raw._recv_task.cancel()
    raw._send_task.cancel()
    await asyncio.gather(raw._recv_task, raw._send_task, return_exceptions=True)


async def final(wire, raw, first, end):
    frame = {
        'tokens': [{'text': 'After silence. ', 'is_final': True, 'speaker': '1', 'start_ms': first, 'end_ms': end}],
        'total_audio_proc_ms': 2000,
        'final_audio_proc_ms': 1800,
    }
    wire.messages.put_nowait(json.dumps(frame))
    # Wait for the actual receive/parser/callback task, without real delays.
    for _ in range(20):
        await asyncio.sleep(0)
        if wire.messages.empty():
            break
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('axis', ['compact', 'elapsed', 'cross_gap'])
async def test_managed_provider_frames_never_promote_unproven_axis(monkeypatch, enabled, axis):
    receiver, epoch, processor, store, leg, wire, gate = await managed(monkeypatch, enabled)
    try:
        for i in range(8):
            pcm = (b'\1\0' if i in (0, 7) else b'\0\0') * RATE
            first, _, _ = receiver.capture_timeline.accept(pcm, T0 + i + 1, i + 1)
            assert leg.send(pcm, start_sample=first)
        leg.raw.finalize()  # FIFO control after all admitted PCM.
        while await wire.writes.get() != '{"type": "finalize"}':
            pass
        # Wait until the last explicit finalize (the gate may have queued one).
        for _ in range(20):
            await asyncio.sleep(0)
            if leg.raw._send_queue.empty():
                break
        written = sum(len(value) // 2 for value in wire.sent if isinstance(value, bytes))
        assert epoch.send_map.last_provider_sample == written
        assert written < 8 * RATE
        first, end = (
            (written / RATE - 0.8, written / RATE - 0.2)
            if axis == 'compact'
            else (7.2, 7.8) if axis == 'elapsed' else (0.2, written / RATE - 0.2)
        )
        before = (
            REGISTRY.get_sample_value(
                'omi_soniox_capture_axis_delta_seconds_count',
                {'reference': 'token_minus_written', 'phase': 'initial', 'write_state': 'settled', 'queue': 'drained'},
            )
            or 0
        )
        await final(wire, leg.raw, round(first * 1000), round(end * 1000))
        rows = await tick(receiver, processor, store)
        assert rows[0]['text'] == 'After silence.'
        assert known(rows) == int(axis == 'compact')
        if axis == 'compact':
            assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == pytest.approx(
                (T0 + 7.2, T0 + 7.8), abs=1 / RATE, rel=0
            )
        if enabled:
            assert getattr(leg.raw, '_capture_axis', None) is not None
            diag = leg.raw._capture_axis
            assert diag.queued == diag.written == written
            assert diag.ledger() == written
            assert (
                REGISTRY.get_sample_value(
                    'omi_soniox_capture_axis_delta_seconds_count',
                    {
                        'reference': 'token_minus_written',
                        'phase': 'initial',
                        'write_state': 'settled',
                        'queue': 'drained',
                    },
                )
                == before + 1
            )
        else:
            assert getattr(leg.raw, '_capture_axis', None) is None
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_off_exact_payload_wire_and_existing_metric_receipt(monkeypatch):
    ids = iter(range(1, 100))
    monkeypatch.setattr(soniox_capture_uuid, 'uuid4', lambda: UUID(int=next(ids)))
    before = values()
    receiver, epoch, processor, store, leg, wire, _ = await managed(monkeypatch, False)
    try:
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        await wire.writes.get()  # config
        assert await wire.writes.get() == pcm
        await final(wire, leg.raw, 200, 800)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        # Include a refused raw final, preserving its legacy visible times.
        await final(wire, leg.raw, 7200, 7800)
        rows = await tick(receiver, processor, store)
        leg.finish()
        for _ in range(8):
            await asyncio.sleep(0)
        after = values()
        receipt = {
            'rows': rows,
            'wire': [v.hex() if isinstance(v, bytes) else json.loads(v) if v else v for v in wire.sent],
            'counters': sorted(
                [
                    [name, list(labels), value - before.get((name, labels), 0)]
                    for (name, labels), value in after.items()
                    if value != before.get((name, labels), 0)
                ]
            ),
        }
        target = os.getenv('R10_RECEIPT_PATH')
        if target:
            Path(target).write_text(json.dumps(receipt, sort_keys=True, default=str))
    finally:
        await close(leg)


@pytest.mark.parametrize(
    'interval,gate,outcome,reason',
    [
        (None, None, 'unknown', 'map_refused'),
        ((1, 2), None, 'unknown', 'no_gate'),
        ((1, 2), SimpleNamespace(), 'unknown', 'vad_uncovered'),
        ((1, 1), SimpleNamespace(), 'unknown', 'invalid_interval'),
        ((1, 2), SimpleNamespace(), 'on_speech', 'classified'),
    ],
)
def test_unknown_detail_is_additive(monkeypatch, interval, gate, outcome, reason):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    before = diagnostics.VALIDATION_DETAIL.labels(provider='soniox', reason=reason)._value.get()
    diagnostics.validation_detail('soniox', interval, gate, outcome)
    assert diagnostics.VALIDATION_DETAIL.labels(provider='soniox', reason=reason)._value.get() == before + 1


def test_wire_counts_do_not_include_controls_and_errors_never_suppress_tokens(monkeypatch):
    diag = diagnostics.CaptureAxisDiagnostics(8000)
    diag.sent(b'\0\0' * 8000)
    for control in ('{"type":"keepalive"}', '{"type":"finalize"}', ''):
        diag.sent(control)
    assert diag.written == 8000
    diag.bind(lambda: (_ for _ in ()).throw(RuntimeError('local getter failure')))
    with pytest.raises(RuntimeError, match='local getter failure'):
        diag.response({'tokens': [{'text': 'word', 'is_final': True, 'end_ms': 1700}]})
    with pytest.raises(ValueError):
        diag.response({'total_audio_proc_ms': 'malformed'})
    assert diag.written == 8000


@pytest.mark.asyncio
async def test_failed_wire_write_is_not_counted(monkeypatch):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    wire = Wire()
    raw = soniox.SafeSonioxSocket(wire, lambda _: None, asyncio.get_running_loop())
    wire.reject = True
    assert raw.send(b'\0\0' * 100)
    await raw._send_task
    assert raw.is_connection_dead
    assert getattr(raw, '_capture_axis', None) is not None
    assert raw._capture_axis.queued == 100 and raw._capture_axis.written == 0
    raw._recv_task.cancel()
    await asyncio.gather(raw._recv_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_keepalive_and_finalize_write_zero_pcm(monkeypatch):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    monkeypatch.setattr(soniox, 'SONIOX_KEEPALIVE_SECONDS', 0.001)
    wire = Wire()
    monkeypatch.setattr(soniox.websockets, 'connect', AsyncMock(return_value=wire))
    raw = await soniox._open_soniox({'sample_rate': 8000}, 'wss://offline.invalid', lambda _: None, 0)
    assert json.loads(await wire.writes.get()) == {'sample_rate': 8000}
    try:
        assert json.loads(await asyncio.wait_for(wire.writes.get(), 0.1)) == {'type': 'keepalive'}
        assert raw.send(b'\1\0' * 8000)
        raw.finalize()
        while await asyncio.wait_for(wire.writes.get(), 0.1) != '{"type": "finalize"}':
            pass
        assert getattr(raw, '_capture_axis', None) is not None
        assert raw._capture_axis.queued == raw._capture_axis.written == 8000
        assert raw._capture_axis.keepalives >= 1 and raw._capture_axis.finalizes == 1
    finally:
        raw._send_task.cancel()
        raw._recv_task.cancel()
        await asyncio.gather(raw._send_task, raw._recv_task, return_exceptions=True)


@pytest.mark.parametrize(
    'decisions,outcome',
    [
        ([(0, 10, True)], 'on_speech'),
        ([(0, 10, False)], 'on_silence'),
        ([(0, 5, True), (5, 10, False)], 'partial'),
        ([(0, 10, None)], 'partial'),
        ([(5, 10, True)], 'unknown'),
    ],
)
def test_validator_uses_retained_raw_decisions(monkeypatch, decisions, outcome):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    gate = object.__new__(VADStreamingGate)
    gate._speech_frames = deque(decisions, maxlen=2048)
    assert gate.classify_capture_speech(0, 10) == outcome
    reason = 'vad_uncovered' if outcome == 'unknown' else 'classified'
    before = diagnostics.VALIDATION_DETAIL.labels(provider='soniox', reason=reason)._value.get()
    ListenReceiver._record_elapsed_validation('soniox', (0, 10), gate)
    assert diagnostics.VALIDATION_DETAIL.labels(provider='soniox', reason=reason)._value.get() == before + 1


@pytest.mark.asyncio
async def test_idle_reopen_diagnostic_origin_is_exact_and_raw_times_are_unshifted(monkeypatch):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    first = soniox.SafeSonioxSocket(Wire(), lambda _: None, asyncio.get_running_loop())
    peers = [first]
    seen = []

    async def connect(callback):
        raw = soniox.SafeSonioxSocket(Wire(), callback, asyncio.get_running_loop())
        peers.append(raw)
        return raw

    idle = IdleSonioxSocket(first, connect, seen.extend, RATE, 20)
    ledger = [RATE]
    assert callable(getattr(idle, 'set_capture_axis_ledger', None))
    idle.set_capture_axis_ledger(lambda: ledger[0])
    assert idle.send(b'\1\0' * RATE)
    idle._idle_since = 1
    assert idle.send(b'\1\0' * RATE)
    ledger[0] = 2 * RATE
    idle.set_resume_provider_offset(RATE)
    try:
        assert await idle.complete_send()
        current = idle._transport
        assert current._capture_axis.origin == RATE
        assert current._capture_axis.phase == 'reopened'
        assert current._capture_axis.ledger() - current._capture_axis.origin == current._capture_axis.queued == RATE
        assert await current._ws.writes.get() == b'\1\0' * RATE
        labels = {
            'reference': 'token_minus_written',
            'phase': 'reopened',
            'write_state': 'settled',
            'queue': 'drained',
            'le': '-0.1',
        }
        before = REGISTRY.get_sample_value('omi_soniox_capture_axis_delta_seconds_bucket', labels) or 0
        await final(current._ws, current, 200, 800)
        assert seen[0]['start'] == 1.2 and seen[0]['end'] == 1.8
        assert current._capture_axis.written == RATE
        after = REGISTRY.get_sample_value('omi_soniox_capture_axis_delta_seconds_bucket', labels)
        assert after - before == 1  # Raw .8 minus 1s PCM is negative; rebased 1.8 is not.
    finally:
        for peer in peers:
            peer._send_task.cancel()
            peer._recv_task.cancel()
        await asyncio.gather(
            *(task for peer in peers for task in (peer._send_task, peer._recv_task)), return_exceptions=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing_ledger', 'getter_error'])
async def test_wire_ledger_fault_diagnostics_preserve_receiver_persistence(monkeypatch, fault):
    receiver, epoch, processor, store, leg, wire, _ = await managed(monkeypatch, True)
    try:
        if fault == 'missing_ledger':
            monkeypatch.setattr(epoch, 'note_accepted_spans', lambda _: None)
        else:
            assert getattr(leg.raw, '_capture_axis', None) is not None
            leg.raw._capture_axis.ledger = lambda: (_ for _ in ()).throw(RuntimeError('local getter failure'))
        before = diagnostics.AXIS_COMPARISON.labels(
            wire='within', ledger='queue_ahead', phase='initial', write_state='settled', queue='drained'
        )._value.get()
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        await wire.writes.get()  # config
        assert await wire.writes.get() == pcm
        await final(wire, leg.raw, 200, 800)
        rows = await tick(receiver, processor, store)
        assert rows[0]['text'] == 'After silence.'
        assert known(rows) == int(fault == 'getter_error')
        assert not leg.raw.is_connection_dead
        if fault == 'missing_ledger':
            assert (
                diagnostics.AXIS_COMPARISON.labels(
                    wire='within', ledger='queue_ahead', phase='initial', write_state='settled', queue='drained'
                )._value.get()
                == before + 1
            )
    finally:
        await close(leg)
