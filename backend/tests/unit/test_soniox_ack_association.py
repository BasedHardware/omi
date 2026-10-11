# LIFECYCLE: permanent
"""R16 ambiguous acknowledgments through managed parser -> StrictFirestore."""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from prometheus_client import REGISTRY

from tests.unit.test_soniox_finalize_padding import setup_peer, send_observed, consume, final, PaddingPeer, ClosingPeer
from tests.unit.test_soniox_capture_axis_r10 import close, managed, soniox_capture_uuid
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt import soniox, soniox_wire_metrics
from utils.stt.soniox_idle import IdleSonioxSocket


async def barrier(raw, wire):
    """Exact local write completion, bounded by turns rather than host wall time."""
    marker = '{"type":"keepalive","r12_barrier":true}'
    turns = 20 * (raw._send_queue.qsize() + 1)
    raw._send_queue.put_nowait(marker)
    for _ in range(turns):
        await asyncio.sleep(0)
        while not wire.writes.empty():
            if wire.writes.get_nowait() == marker:
                await asyncio.sleep(0)
                return
    pytest.fail(f'Local FIFO writer did not complete the barrier in {turns} turns')


def gate_values(mode):
    return {
        outcome: REGISTRY.get_sample_value('omi_soniox_wire_ledger_controls_total', {'mode': mode, 'outcome': outcome})
        or 0
        for outcome in ('sent', 'verified', 'mismatch', 'unverified')
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('ordered', [False, True])
async def test_duplicate_ack_must_not_reanchor_to_previous_control(monkeypatch, ordered):
    """Reviewer's exact F1=2760, F2=2880, F3=3000 false persistence repro."""
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', str(ordered).lower())
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        ack1 = peer.acknowledgment()
        await consume(peer, ack1)
        leg.finalize()
        await barrier(leg.raw, peer)
        ack2 = peer.acknowledgment()
        await consume(peer, ack1)  # Duplicate F1, while F2 remains in flight.
        leg.finalize()
        await barrier(leg.raw, peer)
        ack3 = peer.acknowledgment()
        await consume(peer, ack2)  # Delayed F2 must never authorize F3's origin.
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        rows = await tick(receiver, processor, store)
        await consume(peer, ack3)
        after = await tick(receiver, processor, store)
        assert known(rows) == 0, 'F2 ack cannot establish F3 origin; persisted window is 120 ms late'
        assert known(after) == 0
        assert epoch.wire_audio_samples == 42732 + RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('ordered', [False, True])
@pytest.mark.parametrize('bad', ['verified_duplicate', 'unsolicited', 'combined', 'mismatch', 'malformed', 'overlap'])
async def test_association_loss_survives_many_clean_looking_acks(monkeypatch, ordered, bad):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', str(ordered).lower())
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        if bad != 'unsolicited':
            leg.finalize()
            await barrier(leg.raw, peer)
        report = peer.acknowledgment()
        if bad == 'verified_duplicate':
            await consume(peer, report)
        elif bad == 'combined':
            report['tokens'] *= 2
        elif bad == 'mismatch':
            report['total_audio_proc_ms'] = report['final_audio_proc_ms'] = 120
        elif bad == 'malformed':
            report.pop('final_audio_proc_ms')
        elif bad == 'overlap':
            leg.finalize()
            await barrier(leg.raw, peer)
            # Report the newest control, with the oldest one still pending.
            report = peer.acknowledgment()
        await consume(peer, report)
        for i in range(8):
            leg.finalize()
            await barrier(leg.raw, peer)
            await consume(peer, peer.acknowledgment())
            send_observed(receiver, leg, RATE)
            await barrier(leg.raw, peer)
            await final(peer, speaker=i + 1)
        assert known(await tick(receiver, processor, store)) == 0
        assert leg.raw._provider_clock._association_lost
        assert epoch.wire_audio_samples == 42732 + 8 * RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('ordered', [False, True])
async def test_new_idle_transport_recovers_after_old_association_loss(monkeypatch, ordered):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', str(ordered).lower())
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    transports = [leg.raw]

    async def connect(callback):
        raw = soniox.SafeSonioxSocket(PaddingPeer(), callback, asyncio.get_running_loop())
        transports.append(raw)
        return raw

    idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
    idle.set_wire_ledger(epoch)
    try:
        send_observed(receiver, leg, 42732)
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())  # Unsolicited; poison old socket.
        assert leg.raw._provider_clock._association_lost
        # Drain the poisoned socket through the actual planned idle close.
        peer.__class__ = ClosingPeer
        leg.raw._planned_close = True
        idle._idle_since = 1
        idle._close_task = asyncio.ensure_future(idle._close_idle())
        leg.raw = idle
        send_observed(receiver, leg, RATE)
        assert await leg.complete_send()
        fresh = idle._transport
        await barrier(fresh, fresh._ws)
        assert not fresh._provider_clock._association_lost
        leg.finalize()
        await barrier(fresh, fresh._ws)
        await consume(fresh._ws, fresh._ws.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(fresh, fresh._ws)
        await final(fresh._ws)
        assert known(await tick(receiver, processor, store)) == 1
    finally:
        for raw in transports:
            await close(type('Leg', (), dict(raw=raw, finish=raw.finish))())


@pytest.fixture
async def gate_accounting_peer(monkeypatch, request):
    ordered = request.node.callspec.params['ordered']
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', str(ordered).lower())
    mode = 'ordered' if ordered else 'reported'
    before = gate_values(mode)
    gauge = (
        lambda state: soniox_wire_metrics.finalize_gate_metrics().sockets.labels(mode=mode, state=state)._value.get()
    )
    states = ('placeable', 'pending', 'uncertain', 'association_lost')
    occupancy = {state: gauge(state) for state in states}
    lost_before = soniox_wire_metrics.finalize_gate_metrics().association_lost.labels(mode=mode)._value.get()
    ordered_before = {
        outcome: soniox_wire_metrics.ordered_finalize_metrics().labels(outcome=outcome)._value.get()
        for outcome in ('verified', 'mismatch', 'unverified')
    }
    receiver, _, _, _, leg, peer, _ = await setup_peer(monkeypatch)
    yield receiver, leg, peer, mode, before, gauge, states, occupancy, lost_before, ordered_before
    await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('ordered', [False, True])
@pytest.mark.parametrize('case', ['clean', 'mismatch', 'combined', 'missing', 'failed', 'inside_write', 'overflow'])
async def test_gate_counts_successful_controls_once_and_releases_occupancy(
    monkeypatch, ordered, case, gate_accounting_peer
):
    receiver, leg, peer, mode, before, gauge, states, occupancy, lost_before, ordered_before = gate_accounting_peer
    try:
        send_observed(receiver, leg, 42732)
        await barrier(leg.raw, peer)
        count = 65 if case == 'overflow' else 4 if case in ('mismatch', 'combined', 'missing') else 1
        if case == 'failed':
            peer.reject = True
            with pytest.raises(RuntimeError):
                await leg.raw._write('{"type": "finalize"}')
            peer.reject = False
            count = 0
        else:
            if case == 'inside_write':
                original = peer.send

                async def send(value):
                    await original(value)
                    if isinstance(value, str) and value and json.loads(value).get('type') == 'finalize':
                        await consume(peer, peer.acknowledgment())

                monkeypatch.setattr(peer, 'send', send)
            for _ in range(count):
                leg.finalize()
            await barrier(leg.raw, peer)
            if case in ('clean', 'mismatch', 'combined'):
                report = peer.acknowledgment()
                if case == 'mismatch':
                    report['total_audio_proc_ms'] = report['final_audio_proc_ms'] = 120
                elif case == 'combined':
                    report['tokens'] *= count
                await consume(peer, report)
        lost = case in ('mismatch', 'combined', 'failed') or (ordered and case == 'overflow')
        if lost:
            assert gauge('association_lost') == occupancy['association_lost'] + 1
        if case in ('mismatch', 'combined') or (ordered and case == 'overflow'):
            # Cleared queue settles immediately, each discarded control once.
            delta = {key: gate_values(mode)[key] - before[key] for key in before}
            assert delta['sent'] == count
            assert sum(delta[key] for key in ('verified', 'mismatch', 'unverified')) == count
        await close(leg)
        leg.raw._provider_clock.close()  # Idempotent closure.
        delta = {key: gate_values(mode)[key] - before[key] for key in before}
        assert delta['sent'] == count
        expected = (
            'mismatch'
            if case in ('mismatch', 'combined')
            else 'verified' if case in ('clean', 'inside_write') else 'unverified'
        )
        assert delta[expected] == count
        assert sum(delta[key] for key in ('verified', 'mismatch', 'unverified')) == count
        assert {state: gauge(state) for state in states} == occupancy
        assert (
            soniox_wire_metrics.finalize_gate_metrics().association_lost.labels(mode=mode)._value.get()
        ) == lost_before + int(lost)
        if ordered:
            for outcome, previous in ordered_before.items():
                assert (
                    soniox_wire_metrics.ordered_finalize_metrics().labels(outcome=outcome)._value.get()
                ) - previous == delta[outcome]
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_reported_pcm_race_recovers_only_with_association_intact(monkeypatch):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'false')
    metric = soniox_wire_metrics.finalize_gate_metrics().recoveries.labels(mode='reported')
    previous = metric._value.get()
    receiver, _, _, _, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        report = peer.acknowledgment()
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await consume(peer, report)
        assert not leg.raw._provider_clock._association_lost
        assert leg.raw._provider_clock._state == 'uncertain'
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        assert leg.raw._provider_clock._state == 'placeable'
        assert metric._value.get() == previous + 1
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_r16_parity_receipt(monkeypatch):
    """Stable entire frames/payloads/metric deltas for source-pinned comparison."""
    wire_on = os.getenv('R16_WIRE', 'false') == 'true'
    adversarial = os.getenv('R16_ADVERSARIAL', 'false') == 'true'
    idle_reopen = os.getenv('R16_IDLE', 'false') == 'true'
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', str(wire_on).lower())
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'false')
    monkeypatch.setattr(soniox.time, 'monotonic', lambda: 100.0)
    ids = iter(range(1, 100))
    monkeypatch.setattr(soniox_capture_uuid, 'uuid4', lambda: UUID(int=next(ids)))

    def values():
        return {
            (s.name, tuple(sorted(s.labels.items()))): s.value
            for family in REGISTRY.collect()
            for s in family.samples
            if s.name.startswith('omi_') and not s.name.endswith('_created')
        }

    before = values()
    receiver, epoch, processor, store, leg, peer, _ = await managed(monkeypatch, True)
    leg.gate = None
    peer.__class__ = PaddingPeer
    peer.samples = peer.finalizes = 0
    peers = [peer]
    try:
        send_observed(receiver, leg, 42732)
        await barrier(leg.raw, peer)
        await final(peer)
        await tick(receiver, processor, store)
        leg.finalize()
        await barrier(leg.raw, peer)
        ack1 = peer.acknowledgment()
        await consume(peer, ack1)
        leg.finalize()
        await barrier(leg.raw, peer)
        ack2 = peer.acknowledgment()
        if adversarial:
            await consume(peer, ack1)
            leg.finalize()
            await barrier(leg.raw, peer)
        await consume(peer, ack2)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=2)
        rows = await tick(receiver, processor, store)
        if idle_reopen:

            async def connect(callback):
                fresh_peer = PaddingPeer()
                peers.append(fresh_peer)
                return soniox.SafeSonioxSocket(fresh_peer, callback, asyncio.get_running_loop())

            idle = IdleSonioxSocket(leg.raw, connect, leg.raw._stream_transcript, RATE, 20)
            if wire_on:
                idle.set_wire_ledger(epoch)
            peer.__class__ = ClosingPeer
            leg.raw._planned_close = True
            idle._idle_since = 1
            idle._close_task = asyncio.ensure_future(idle._close_idle())
            leg.raw = idle
            send_observed(receiver, leg, RATE)
            assert await leg.complete_send()
            await barrier(idle._transport, peers[-1])
            send_observed(receiver, leg, RATE)
            await barrier(idle._transport, peers[-1])
            await final(peers[-1], speaker=3)
            rows = await tick(receiver, processor, store)
            if wire_on:
                # Main's display origin survives the capture-only refusal fix.
                assert rows[-1]['start'] - rows[0]['start'] == pytest.approx(
                    peer.samples / RATE + 1.2 - 1.871, abs=2 / RATE, rel=0
                )
                assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + 42732 / RATE + 2.2, abs=2 / RATE, rel=0)
        leg.finish()
        for _ in range(8):
            await asyncio.sleep(0)
        await close(leg)
        after = values()
        receipt = dict(
            rows=rows,
            wire=[
                dict(binary=v.hex()) if isinstance(v, bytes) else dict(text=v) for socket in peers for v in socket.sent
            ],
            counters=sorted(
                [name, list(labels), value - before.get((name, labels), 0)]
                for (name, labels), value in after.items()
                if value != before.get((name, labels), 0)
            ),
        )
        target = os.getenv('R16_RECEIPT_PATH')
        if target:
            Path(target).write_text(json.dumps(receipt, sort_keys=True, default=str))
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_both_off_do_not_touch_warmed_gate(monkeypatch):
    gate = soniox_wire_metrics.finalize_gate_metrics()
    before = [
        (sample.name, sample.labels, sample.value)
        for family in gate
        for metric in family.collect()
        for sample in metric.samples
    ]
    monkeypatch.setattr(
        soniox_wire_metrics, 'finalize_gate_metrics', lambda: pytest.fail('Both OFF accessed gate metrics')
    )
    await test_r16_parity_receipt(monkeypatch)
    after = [
        (sample.name, sample.labels, sample.value)
        for family in gate
        for metric in family.collect()
        for sample in metric.samples
    ]
    assert after == before


@pytest.mark.asyncio
async def test_reported_idle_reopen_receipt_after_ambiguous_ack(monkeypatch):
    monkeypatch.setenv('R16_WIRE', 'true')
    monkeypatch.setenv('R16_ADVERSARIAL', 'true')
    monkeypatch.setenv('R16_IDLE', 'true')
    await test_r16_parity_receipt(monkeypatch)
