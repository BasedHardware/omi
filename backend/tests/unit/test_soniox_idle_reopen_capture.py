# LIFECYCLE: permanent
"""Idle reopen token clipping through the managed parser and StrictFirestore."""

import asyncio
import json
import pytest
from tests.unit.test_soniox_finalize_padding import setup_peer, send_observed, final, consume, PaddingPeer
from tests.unit.test_soniox_wire_ledger import barrier
from tests.unit.test_soniox_capture_axis_r10 import close, managed
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt.soniox_idle import IdleSonioxSocket
from utils.stt import soniox


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', ['missing', 'invalid', 'overlapping'])
@pytest.mark.parametrize('prior_ack', ['raced', 'missing'])
async def test_reopen_after_raced_padding_never_clips_cross_gap_token_into_known_span(monkeypatch, terminal, prior_ack):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    raws = [leg.raw]

    async def connect(callback):
        raw = soniox.SafeSonioxSocket(PaddingPeer(), callback, asyncio.get_running_loop())
        raws.append(raw)
        return raw

    idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
    idle.set_wire_ledger(epoch)
    leg.raw = idle
    try:
        previous_ack = None
        for _ in range(4):
            send_observed(receiver, leg, 42732)
            await barrier(raws[0], peer)
            if previous_ack is not None and prior_ack == 'raced':
                await consume(peer, previous_ack)
            leg.finalize()
            await barrier(raws[0], peer)
            previous_ack = peer.acknowledgment()
        send_observed(receiver, leg, RATE)
        await barrier(raws[0], peer)
        if prior_ack == 'raced':
            await consume(peer, previous_ack)
        await final(peer)
        await tick(receiver, processor, store)
        offset = epoch.wire_provider_samples / RATE
        assert idle._last_end > offset + 0.1

        # Drain closes the old writer/receiver without a valid finalize anchor.
        class MissingTerminalAckPeer(PaddingPeer):
            async def send(self, value):
                await super().send(value)
                if isinstance(value, str) and value and json.loads(value).get('type') == 'finalize':
                    self.terminal_finalizes += 1
                if (
                    terminal != 'missing'
                    and self.terminal_finalizes >= (2 if terminal == 'overlapping' else 1)
                    and value == '{"type": "finalize"}'
                ):
                    msg = self.acknowledgment()
                    if terminal == 'invalid':
                        msg.pop('total_audio_proc_ms')
                    self.messages.put_nowait(json.dumps(msg))
                if value == '':
                    self.messages.put_nowait(json.dumps(dict(finished=True, tokens=[])))

        peer.__class__ = MissingTerminalAckPeer
        peer.terminal_finalizes = 0
        if terminal == 'overlapping':
            leg.finalize()
            await barrier(raws[0], peer)
        idle._transport._planned_close = True
        idle._idle_since = 1
        idle._close_task = asyncio.ensure_future(idle._close_idle())
        send_observed(receiver, leg, RATE // 10)
        assert await leg.complete_send()
        current = idle._transport
        await barrier(current, current._ws)
        # Capture one second of withheld source audio between two real writes.
        pcm = b'\0\0' * RATE
        end = (receiver.capture_timeline.next_sample + RATE) / RATE
        receiver.capture_timeline.accept(pcm, T0 + end, end)
        send_observed(receiver, leg, RATE)
        await barrier(current, current._ws)
        # Native token spans both the onset and later capture after the gap.
        # The old last_end must not clip it into the later accepted span.
        assert known(epoch.translate([dict(text='Unclipped.', start=offset + 0.05, end=offset + 0.3)])) == 0
        await final(current._ws, first=RATE // 20, end=3 * RATE // 10, speaker=2)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 0
        assert len(rows) == 2 and all(row['text'] == 'Observed audio.' for row in rows)
        assert all(not key.startswith('_provider_') for row in rows for key in row)
        # Refusal does not poison later native intervals contained in a real send.
        await final(current._ws, first=2 * RATE // 5, end=4 * RATE // 5, speaker=3)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + offset + 1.4, abs=2 / RATE, rel=0)
    finally:
        for raw in raws:
            await close(type('Leg', (), dict(raw=raw, finish=raw.finish))())


class MissingAckClosingPeer(PaddingPeer):
    async def send(self, value):
        await super().send(value)
        if value == '':
            self.messages.put_nowait(json.dumps(dict(finished=True, tokens=[])))


@pytest.mark.asyncio
async def test_visible_idle_clamp_is_identical_off_and_on_after_native_capture_translation(monkeypatch):
    receipts = []
    for enabled in (False, True):
        monkeypatch.setenv('SONIOX_WIRE_LEDGER', str(enabled).lower())
        receiver, epoch, processor, store, leg, peer, _ = await managed(monkeypatch, True)
        leg.gate = None
        peer.__class__ = MissingAckClosingPeer
        peer.samples = peer.finalizes = 0
        raws = [leg.raw]

        async def connect(callback):
            raw = soniox.SafeSonioxSocket(MissingAckClosingPeer(), callback, asyncio.get_running_loop())
            raws.append(raw)
            return raw

        idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
        if enabled:
            idle.set_wire_ledger(epoch)
        leg.raw = idle
        try:
            send_observed(receiver, leg, RATE)
            await barrier(raws[0], peer)
            await final(peer, first=6 * RATE // 5, end=7 * RATE // 5)
            await tick(receiver, processor, store)
            assert idle._last_end == 1.4
            idle._transport._planned_close = True
            idle._idle_since = 1
            idle._close_task = asyncio.ensure_future(idle._close_idle())
            send_observed(receiver, leg, RATE // 10)
            assert await leg.complete_send()
            current = idle._transport
            await barrier(current, current._ws)
            pcm = b'\0\0' * RATE
            first = receiver.capture_timeline.next_sample
            receiver.capture_timeline.accept(pcm, T0 + (first + RATE) / RATE, (first + RATE) / RATE)
            send_observed(receiver, leg, RATE)
            await barrier(current, current._ws)
            seen = []
            translate = epoch.translate

            def record_native(segments):
                seen.extend((s['start'], s['end']) for s in segments)
                return translate(segments)

            monkeypatch.setattr(epoch, 'translate', record_native)
            await final(current._ws, first=RATE // 20, end=4 * RATE // 5, speaker=2)
            rows = await tick(receiver, processor, store)
            assert seen == ([(1.05, 1.8)] if enabled else [(1.4, 1.8)])
            assert known(rows) == (0 if enabled else 1)
            receipts.append([(r['text'], r['start'], r['end'], r['speaker']) for r in rows])
            assert all(not key.startswith('_provider_') for row in rows for key in row)
            # The wrapper's own endpoint remains on the visible legacy axis.
            assert idle._last_end == 1.8
        finally:
            for raw in raws:
                await close(type('Leg', (), dict(raw=raw, finish=raw.finish))())
    assert receipts[0] == receipts[1]
