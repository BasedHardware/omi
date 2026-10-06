# LIFECYCLE: permanent
"""Finalize clock reports through managed wire/parser/receiver/persistence."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from tests.unit.test_soniox_capture_axis_r10 import managed, close, Wire
from tests.unit.test_soniox_wire_ledger import barrier
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt import soniox
from utils.stt.soniox_idle import IdleSonioxSocket


class PaddingPeer(Wire):
    """Independent wire-byte axis, replaying measured strict next-120ms padding."""

    def __init__(self):
        super().__init__()
        self.samples = 0
        self.finalizes = 0

    async def send(self, value):
        await super().send(value)
        if isinstance(value, bytes):
            self.samples += len(value) // 2
        elif value and json.loads(value).get('type') == 'finalize':
            self.finalizes += 1
            quantum = RATE * 120 // 1000
            self.samples = (self.samples // quantum + 1) * quantum

    def acknowledgment(self, **fields):
        position = self.samples * 1000 // RATE
        return dict(
            tokens=[dict(text='<fin>', is_final=True, start_ms=0, end_ms=0)],
            total_audio_proc_ms=position,
            final_audio_proc_ms=position,
            **fields,
        )


async def consume(wire, message):
    wire.messages.put_nowait(json.dumps(message))
    for _ in range(20):
        await asyncio.sleep(0)
        if wire.messages.empty():
            break
    await asyncio.sleep(0)


async def setup_peer(monkeypatch):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    result = await managed(monkeypatch, True)
    leg, wire = result[4:6]
    leg.gate = None
    wire.__class__ = PaddingPeer
    wire.samples = wire.finalizes = 0
    return result


def send_observed(receiver, leg, length):
    pcm = b'\1\0' * length
    end = (receiver.capture_timeline.next_sample + length) / RATE
    start, _, _ = receiver.capture_timeline.accept(pcm, T0 + end, end)
    assert leg.send(pcm, start_sample=start)
    return start


async def final(peer, speaker=1, first=None, end=None):
    end = peer.samples - RATE // 5 if end is None else end
    first = end - RATE * 3 // 5 if first is None else first
    await consume(
        peer,
        dict(
            tokens=[
                dict(
                    text='Observed audio. ',
                    is_final=True,
                    speaker=str(speaker),
                    start_ms=round(first * 1000 / RATE),
                    end_ms=round(end * 1000 / RATE),
                )
            ]
        ),
    )


@pytest.mark.asyncio
async def test_repeated_finalize_holes_preserve_late_capture_and_all_controls(monkeypatch):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        for _ in range(12):
            send_observed(receiver, leg, 42732)
            leg.finalize()
            await barrier(leg.raw, peer)
            await consume(peer, peer.acknowledgment())
        assert peer.finalizes == 12
        assert epoch.wire_audio_samples == 12 * 42732
        assert epoch.wire_provider_samples == peer.samples == 12 * 44160
        assert epoch.send_map.accepted_provider_samples(0, peer.samples) == epoch.wire_audio_samples
        # Exact provider-only holes grant no capture, including merged intervals.
        assert epoch.send_map.map_interval(42732, 44160) is None
        assert known(epoch.translate([dict(text='Padding.', start=2.680, end=2.750)])) == 0
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 32.049 + 0.2, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + 32.049 + 0.8, abs=2 / RATE, rel=0)
        assert leg.raw._capture_axis.written == leg.raw._capture_axis.ledger() == epoch.wire_audio_samples
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('inflight_ack', [False, True])
async def test_audio_before_finalize_ack_stays_unplaceable_until_clean_checkpoint(monkeypatch, inflight_ack):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        acknowledgment = peer.acknowledgment()
        if inflight_ack:
            original = peer.send

            async def send(value):
                await original(value)
                if isinstance(value, bytes):
                    # Ack inside the audio websocket await, before successful
                    # wire completion. Must not grant this in-flight packet.
                    await consume(peer, acknowledgment)

            monkeypatch.setattr(peer, 'send', send)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        if not inflight_ack:
            await consume(peer, acknowledgment)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
        assert epoch.wire_audio_samples == 42732 + RATE
        # No guessing from a plain progress report or token endpoint.
        await consume(
            peer, dict(total_audio_proc_ms=peer.samples * 1000 // RATE, final_audio_proc_ms=peer.samples * 1000 // RATE)
        )
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=2)
        assert known(await tick(receiver, processor, store)) == 0
        if inflight_ack:
            monkeypatch.setattr(peer, 'send', original)
        # Later sole finalize with no subsequent audio creates a fresh anchor.
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=3)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 4.87075, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + 5.47075, abs=2 / RATE, rel=0)
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'bad', ['missing_total', 'missing_final', 'unequal', 'regressing', 'float', 'bool', 'string', 'token_only']
)
async def test_invalid_finalize_position_never_grants_later_capture(monkeypatch, bad):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        msg = peer.acknowledgment()
        if bad.startswith('missing_'):
            msg.pop(bad.removeprefix('missing_') + '_audio_proc_ms')
        elif bad == 'unequal':
            msg['final_audio_proc_ms'] -= 120
        elif bad == 'regressing':
            msg['total_audio_proc_ms'] = msg['final_audio_proc_ms'] = 120
        elif bad in ('float', 'bool', 'string'):
            value = {'float': 2760.5, 'bool': True, 'string': '2760'}[bad]
            msg['total_audio_proc_ms'] = msg['final_audio_proc_ms'] = value
        else:
            msg = dict(tokens=msg['tokens'])
        await consume(peer, msg)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
        assert epoch.wire_audio_samples == 42732 + RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_overlapping_finalizes_refuse_ambiguous_report(monkeypatch):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, RATE)
        leg.finalize()
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('pending_close', [False, True])
async def test_idle_reopen_freezes_provider_origin_with_padding_and_separate_pcm_diagnostics(
    monkeypatch, pending_close
):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    peers = [leg.raw]

    async def connect(callback):
        raw = soniox.SafeSonioxSocket(PaddingPeer(), callback, asyncio.get_running_loop())
        peers.append(raw)
        return raw

    idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
    idle.set_wire_ledger(epoch)
    idle.set_capture_axis_ledger(lambda: epoch.wire_audio_samples)
    leg.raw = idle
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()

        async def drain_old():
            await barrier(peers[0], peer)
            await consume(peer, peer.acknowledgment())

        if pending_close:
            idle._close_task = asyncio.ensure_future(drain_old())
        else:
            await drain_old()
        idle._idle_since = 1
        send_observed(receiver, leg, RATE)
        assert await leg.complete_send()
        current = idle._transport
        await barrier(current, current._ws)
        await final(current._ws)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 2.87075, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + 3.47075, abs=2 / RATE, rel=0)
        assert current._capture_axis.origin == 42732  # PCM diagnostic origin.
        assert epoch.wire_audio_samples == 42732 + RATE
        assert epoch.wire_provider_samples == 44160 + RATE
    finally:
        for raw in peers:
            await close(type('Leg', (), dict(raw=raw, finish=raw.finish))())


@pytest.mark.asyncio
@pytest.mark.parametrize('recovery', [False, True])
async def test_on_off_byte_identical_audio_and_control_transcript(monkeypatch, recovery):
    receipts = []
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', str(recovery).lower())
    for enabled in (False, True):
        monkeypatch.setenv('SONIOX_WIRE_LEDGER', str(enabled).lower())
        receiver, _, _, _, leg, wire, _ = await managed(monkeypatch, True)
        try:
            # Real VAD pre-roll/hangover/finalize and replay admission.
            for i in range(12):
                pcm = (b'\1\0' if i in (3, 10) else b'\0\0') * (RATE // 10)
                start, _, _ = receiver.capture_timeline.accept(pcm, T0 + (i + 1) / 10, (i + 1) / 10)
                assert leg.replay_send(pcm, start) if recovery else leg.send(pcm, start_sample=start)
            leg.finalize()
            await barrier(leg.raw, wire)
            await leg.raw._write('{"type": "keepalive"}')
            leg.raw._planned_close = True
            leg.finalize()
            await barrier(leg.raw, wire)
            leg.finish()
            await asyncio.wait_for(leg.raw._send_task, 0.1)
            receipts.append(
                [
                    dict(kind='binary', hex=v.hex()) if isinstance(v, bytes) else dict(kind='text', text=v)
                    for v in wire.sent
                ]
            )
        finally:
            await close(leg)
    assert receipts[0] == receipts[1]
    assert sum(r.get('text') == '{"type": "finalize"}' for r in receipts[1]) >= 3
    assert receipts[1][-1] == dict(kind='text', text='')
    target = os.getenv('R13_WIRE_RECEIPT_PREFIX')
    if target:
        Path(f'{target}-{recovery}.json').write_text(json.dumps(dict(off=receipts[0], on=receipts[1]), indent=2))


@pytest.mark.asyncio
async def test_nonquantized_report_is_authority_and_progress_is_not(monkeypatch):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        # Deliberately unlike the measured model: no fixed-quantum assumption.
        msg = peer.acknowledgment()
        msg['total_audio_proc_ms'] = msg['final_audio_proc_ms'] = 2791
        await consume(peer, dict(total_audio_proc_ms=9999, final_audio_proc_ms=9999))
        assert epoch.wire_provider_samples == 42732
        await consume(peer, msg)
        peer.samples = 2791 * RATE // 1000
        assert epoch.wire_provider_samples == peer.samples
        assert epoch.wire_audio_samples == 42732
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 2.87075, abs=2 / RATE, rel=0)
        # Spanning any provider-only gap cannot yield a continuous capture window.
        segment = dict(text='Across padding.', start=2.6, end=2.9)
        assert known(epoch.translate([segment])) == 0
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_prebind_finalize_padding_and_no_audio_finalizes_grant_no_capture(monkeypatch):
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    opener = soniox._open_soniox

    async def connect(*args):
        raw = await opener(*args)
        raw._ws.__class__ = PaddingPeer
        raw._ws.samples = raw._ws.finalizes = 0
        await raw._write(b'\2\0' * 42732)
        await raw._write('{"type": "finalize"}')
        await consume(raw._ws, raw._ws.acknowledgment())
        return raw

    monkeypatch.setattr(soniox, '_open_soniox', connect)
    receiver, epoch, processor, store, leg, peer, _ = await managed(monkeypatch, True)
    leg.gate = None
    try:
        assert epoch.wire_audio_samples == 42732
        assert epoch.wire_provider_samples == 44160
        assert epoch.send_map.span_count == 0
        for _ in range(2):
            leg.finalize()
            await barrier(leg.raw, peer)
            await consume(peer, peer.acknowledgment())
        assert epoch.wire_provider_samples == 48000
        assert epoch.wire_audio_samples == 42732
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 0.2, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + 0.8, abs=2 / RATE, rel=0)
    finally:
        await close(leg)


class ClosingPeer(PaddingPeer):
    async def send(self, value):
        await super().send(value)
        if value == '':
            self.messages.put_nowait(json.dumps(dict(finished=True, tokens=[])))
        elif isinstance(value, str) and value and json.loads(value).get('type') == 'finalize':
            self.messages.put_nowait(json.dumps(self.acknowledgment()))


@pytest.mark.asyncio
async def test_on_off_idle_close_reopen_wire_transcript(monkeypatch):
    receipts = []
    for enabled in (False, True):
        monkeypatch.setenv('SONIOX_WIRE_LEDGER', str(enabled).lower())
        receiver, epoch, _, _, leg, peer, _ = await managed(monkeypatch, True)
        leg.gate = None
        peer.__class__ = ClosingPeer
        peer.samples = peer.finalizes = 0
        peers = [leg.raw]

        async def connect(callback):
            raw = soniox.SafeSonioxSocket(ClosingPeer(), callback, asyncio.get_running_loop())
            peers.append(raw)
            return raw

        idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
        if enabled:
            idle.set_wire_ledger(epoch)
        leg.raw = idle
        try:
            send_observed(receiver, leg, 42732)
            # Drive the actual planned drain, including finalize and end, with
            # onset queued before the old writer finishes (R12 origin freeze).
            idle._transport._planned_close = True
            idle._idle_since = 1
            idle._close_task = asyncio.ensure_future(idle._close_idle())
            send_observed(receiver, leg, RATE)
            assert await leg.complete_send()
            await barrier(idle._transport, idle._transport._ws)
            idle.finalize()
            await barrier(idle._transport, idle._transport._ws)
            await idle.drain_and_close()
            receipts.append(
                [
                    [
                        dict(kind='binary', hex=v.hex()) if isinstance(v, bytes) else dict(kind='text', text=v)
                        for v in raw._ws.sent
                    ]
                    for raw in peers
                ]
            )
        finally:
            for raw in peers:
                await close(type('Leg', (), dict(raw=raw, finish=raw.finish))())
    assert receipts[0] == receipts[1]
    assert receipts[1][0][-2:] == [dict(kind='text', text='{"type": "finalize"}'), dict(kind='text', text='')]
    target = os.getenv('R13_WIRE_RECEIPT_PREFIX')
    if target:
        Path(f'{target}-idle.json').write_text(json.dumps(dict(off=receipts[0], on=receipts[1]), indent=2))
