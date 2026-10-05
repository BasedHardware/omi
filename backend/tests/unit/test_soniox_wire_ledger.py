# LIFECYCLE: permanent
"""Managed connector -> emitted PCM-derived Soniox response -> receiver -> persistence."""

import asyncio
import json

import pytest

from tests.unit.test_soniox_capture_axis_r10 import (
    managed,
    close,
    Wire,
    test_off_exact_payload_wire_and_existing_metric_receipt as off_receipt,
)
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401
from utils.stt import replay_delivery, soniox
from utils.stt.soniox_idle import IdleSonioxSocket


async def barrier(raw, wire):
    marker = '{"type":"keepalive","r12_barrier":true}'
    raw._send_queue.put_nowait(marker)
    while await asyncio.wait_for(wire.writes.get(), 0.1) != marker:
        pass
    await asyncio.sleep(0)


async def byte_derived_final(raw, wire, rate=RATE, duration=0.6, speaker=1):
    # Independent of all adapter/ledger counters: model the provider's byte axis.
    samples = sum(len(frame) // 2 for frame in wire.sent if isinstance(frame, bytes))
    end = samples / rate - 0.2
    msg = {
        'tokens': [
            {
                'text': 'Observed audio. ',
                'is_final': True,
                'speaker': str(speaker),
                'start_ms': round((end - duration) * 1000),
                'end_ms': round(end * 1000),
            }
        ],
        'total_audio_proc_ms': samples * 1000 / rate,
    }
    wire.messages.put_nowait(json.dumps(msg))
    for _ in range(20):
        await asyncio.sleep(0)
        if wire.messages.empty():
            break
    await asyncio.sleep(0)
    return samples


@pytest.mark.asyncio
@pytest.mark.parametrize('seconds', [2.7, 9.9])
@pytest.mark.parametrize('path', ['raw_send', 'wire_write', 'unknown_managed', 'unobserved_claim'])
async def test_unknown_pcm_consumes_provider_time_without_granting_capture(monkeypatch, seconds, path):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    receiver, epoch, processor, store, leg, wire, gate = await managed(monkeypatch, True)
    leg.gate = None
    unknown = b'\2\0' * round(seconds * RATE)
    try:
        if path == 'raw_send':
            assert leg.raw.send(unknown)
        elif path == 'wire_write':
            await leg.raw._write(unknown)
        else:
            assert leg.send(unknown, start_sample=None if path == 'unknown_managed' else 100 * RATE)
        await barrier(leg.raw, wire)
        assert epoch.wire_audio_samples == len(unknown) // 2
        assert epoch.send_map.span_count == 0
        await byte_derived_final(leg.raw, wire)
        assert known(await tick(receiver, processor, store)) == 0
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        await barrier(leg.raw, wire)
        samples = await byte_derived_final(leg.raw, wire, speaker=2)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 0.2, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + 0.8, abs=2 / RATE, rel=0)
        assert epoch.send_map.map_interval(len(unknown) // 2 + RATE // 5, samples - RATE // 5) == (
            RATE // 5,
            RATE * 4 // 5,
        )
        assert epoch.wire_audio_samples == leg.raw._capture_axis.written == samples
        # The existing diagnostic already counted unknown writes on main.
        assert leg.raw._capture_axis.queued == samples if path != 'wire_write' else samples - len(unknown) // 2
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_prefix_written_before_binding_is_reserved_as_unknown(monkeypatch):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    original = soniox._open_soniox

    async def connect(*args):
        raw = await original(*args)
        await raw._write(b'\2\0' * RATE)
        return raw

    monkeypatch.setattr(soniox, '_open_soniox', connect)
    receiver, epoch, _, _, leg, wire, _ = await managed(monkeypatch, True)
    try:
        assert epoch.wire_audio_samples == RATE
        assert epoch.send_map.span_count == 0
        assert leg.raw._capture_axis.written == RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('replay', [False, True])
async def test_real_vad_preroll_hangover_and_replay_conserve_bytes(monkeypatch, replay):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    receiver, epoch, _, _, leg, wire, gate = await managed(monkeypatch, True)
    try:
        for i in range(12):
            pcm = (b'\1\0' if i in (3, 10) else b'\0\0') * (RATE // 10)
            start, _, _ = receiver.capture_timeline.accept(pcm, T0 + (i + 1) / 10, (i + 1) / 10)
            assert leg.replay_send(pcm, start) if replay else leg.send(pcm, start_sample=start)
        await barrier(leg.raw, wire)
        samples = sum(len(v) // 2 for v in wire.sent if isinstance(v, bytes))
        assert epoch.wire_audio_samples == epoch.wire_provider_samples == samples
        # The real VAD finalize is preserved. With no peer acknowledgment,
        # the later onset cannot be mapped onto a guessed provider clock.
        assert epoch.send_map.accepted_provider_samples(0, samples) < samples
        assert leg.raw._capture_axis.queued == leg.raw._capture_axis.written == samples
        # Keepalive/finalize consume no provider samples.
        await leg.raw._write('{"type":"keepalive"}')
        assert epoch.wire_audio_samples == samples
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('pending_close', [False, True])
async def test_idle_reopen_retains_observed_onset_provenance(monkeypatch, pending_close):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    receiver, epoch, processor, store, leg, wire, _ = await managed(monkeypatch, True)
    leg.gate = None
    peers = [leg.raw]

    async def connect(callback):
        peer = soniox.SafeSonioxSocket(Wire(), callback, asyncio.get_running_loop())
        peers.append(peer)
        return peer

    idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
    idle.set_wire_ledger(epoch)
    idle.set_capture_axis_ledger(lambda: epoch.wire_audio_samples)
    leg.raw = idle
    try:
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        if pending_close:
            # Real old writer has not run yet: complete_send sees an empty
            # emitted ledger, and then waits for this old-transport drain.
            assert epoch.wire_audio_samples == 0
            idle._close_task = asyncio.ensure_future(barrier(peers[0], wire))
        else:
            await barrier(peers[0], wire)
        idle._idle_since = 1
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 2, 2)
        assert leg.send(pcm, start_sample=start)
        assert await leg.complete_send()
        current = idle._transport
        await barrier(current, current._ws)
        await byte_derived_final(current, current._ws)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[0]['audio_capture_start'] == pytest.approx(T0 + 1.2, abs=2 / RATE, rel=0)
        assert epoch.wire_audio_samples == 2 * RATE
        assert current._capture_axis.origin == RATE
        assert current._capture_axis.written == RATE
    finally:
        for peer in peers:
            await close(type('Leg', (), {'raw': peer, 'finish': peer.finish})())


@pytest.mark.asyncio
async def test_failed_wire_never_registers_capture(monkeypatch):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    receiver, epoch, _, _, leg, wire, _ = await managed(monkeypatch, True)
    try:
        wire.reject = True
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        await leg.raw._send_task
        assert epoch.wire_audio_samples == 0
        assert epoch.send_map.span_count == 0
        assert leg.raw._capture_axis.written == 0
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_off_receipt(monkeypatch):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'false')
    # Reuse the persisted/wire/metric receipt used to prove R10/R11 OFF parity.
    await off_receipt(monkeypatch)


@pytest.mark.asyncio
async def test_recovery_pacer_and_writer_preserve_capture_spans(monkeypatch, virtual_clock):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    receiver, epoch, processor, store, leg, wire, _ = await managed(monkeypatch, True)
    leg.gate = None
    leg.raw.enable_writer_pacing(RATE, 1.0)
    pacer = replay_delivery.ReplayPacer(RATE, 'soniox', leg)
    try:
        for i in range(10):
            pcm = b'\1\0' * (RATE // 10)
            start, _, _ = receiver.capture_timeline.accept(pcm, T0 + (i + 1) / 10, (i + 1) / 10)
            assert await pacer.send(leg, pcm, start, lambda: True, replay=True)
        await barrier(leg.raw, wire)
        await byte_derived_final(leg.raw, wire)
        assert known(await tick(receiver, processor, store)) == 1
        assert epoch.wire_audio_samples == epoch.send_map.last_provider_sample == RATE
        assert leg.raw._capture_axis.written == RATE
    finally:
        await close(leg)
