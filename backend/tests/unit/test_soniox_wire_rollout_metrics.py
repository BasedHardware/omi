# LIFECYCLE: permanent
"""Rollout counters from actual wire writes, parser callbacks and persistence."""

import asyncio

import pytest
from prometheus_client import REGISTRY

from tests.unit.test_soniox_finalize_padding import setup_peer, send_observed, consume, final
from tests.unit.test_soniox_capture_axis_r10 import close, managed
from tests.unit.test_soniox_wire_ledger import barrier
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE
from utils.stt import soniox_wire_metrics, soniox

PREFIX = 'omi_soniox_wire_ledger_'


def value(suffix, outcome=None):
    labels = {} if outcome is None else {'outcome': outcome}
    return REGISTRY.get_sample_value(PREFIX + suffix + '_total', labels) or 0


def snapshot():
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in REGISTRY.collect()
        for sample in family.samples
        if sample.name.startswith(PREFIX)
    }


@pytest.mark.asyncio
async def test_clean_checkpoint_holes_and_known_window_are_separate_from_pcm(monkeypatch):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    clean = value('finalize_checkpoints', 'clean')
    holes, samples = value('provider_holes'), value('provider_hole_samples')
    granted, refused = value('intervals', 'known'), value('intervals', 'other_refused')
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        assert value('finalize_checkpoints', 'clean') == clean + 1
        assert value('provider_holes') == holes + 1
        assert value('provider_hole_samples') == samples + 1428
        assert epoch.wire_audio_samples == 42732
        assert epoch.wire_provider_samples == 44160
        # Token confined to provider-only padding never becomes a known row.
        await final(peer, first=round(2.68 * RATE), end=round(2.75 * RATE))
        assert known(await tick(receiver, processor, store)) == 0
        assert value('intervals', 'other_refused') == refused + 1
        assert value('intervals', 'known') == granted
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=2)
        assert known(await tick(receiver, processor, store)) == 1
        assert value('intervals', 'known') == granted + 1
        # A valid checkpoint with no padding is clean but registers no hole.
        leg.finalize()
        await barrier(leg.raw, peer)
        position = epoch.wire_provider_samples * 1000 // RATE
        msg = peer.acknowledgment()
        msg['total_audio_proc_ms'] = msg['final_audio_proc_ms'] = position
        await consume(peer, msg)
        assert value('finalize_checkpoints', 'clean') == clean + 2
        assert value('provider_holes') == holes + 1
        assert value('provider_hole_samples') == samples + 1428
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('inflight_ack', [False, True])
async def test_race_refusals_use_native_interval_and_recover_at_clean_checkpoint(monkeypatch, inflight_ack):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    raced = value('finalize_checkpoints', 'raced')
    missing = value('finalize_checkpoints', 'missing_ack')
    refused = value('intervals', 'unplaceable_by_race')
    granted = value('intervals', 'known')
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        msg = peer.acknowledgment()
        original = peer.send
        if inflight_ack:

            async def send(data):
                await original(data)
                if isinstance(data, bytes):
                    await consume(peer, msg)

            monkeypatch.setattr(peer, 'send', send)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        if not inflight_ack:
            await consume(peer, msg)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
        assert value('finalize_checkpoints', 'raced') == raced + 1
        assert value('intervals', 'unplaceable_by_race') == refused + 1
        monkeypatch.setattr(peer, 'send', original)
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=2)
        assert known(await tick(receiver, processor, store)) == 1
        assert value('intervals', 'known') == granted + 1
        assert value('intervals', 'unplaceable_by_race') == refused + 1
        # A delayed token across the old race stays attributed after recovery.
        await final(peer, first=3 * RATE, end=4 * RATE, speaker=3)
        assert known(await tick(receiver, processor, store)) == 1
        assert value('intervals', 'unplaceable_by_race') == refused + 2
    finally:
        await close(leg)
    assert value('finalize_checkpoints', 'missing_ack') == missing


@pytest.mark.asyncio
@pytest.mark.parametrize('ack', ['missing', 'invalid', 'overlapping', 'duplicate'])
async def test_checkpoint_controls_settle_once_at_ack_or_receive_teardown(monkeypatch, ack):
    receiver, _, _, _, leg, peer, _ = await setup_peer(monkeypatch)
    before = {o: value('finalize_checkpoints', o) for o in ('clean', 'raced', 'missing_ack')}
    try:
        send_observed(receiver, leg, RATE)
        leg.finalize()
        if ack == 'overlapping':
            leg.finalize()
        await barrier(leg.raw, peer)
        if ack != 'missing':
            msg = peer.acknowledgment()
            if ack == 'invalid':
                msg.pop('final_audio_proc_ms')
            await consume(peer, msg)
            if ack == 'duplicate':
                await consume(peer, msg)
        await consume(peer, dict(finished=True, tokens=[]))
        await asyncio.wait_for(leg.raw._recv_task, 0.1)
        expected = {
            'clean': int(ack == 'duplicate'),
            'raced': int(ack in ('invalid', 'overlapping')),
            'missing_ack': int(ack in ('missing', 'overlapping')),
        }
        assert {o: value('finalize_checkpoints', o) - before[o] for o in before} == expected
        after = snapshot()
    finally:
        await close(leg)
    assert snapshot() == after


@pytest.mark.asyncio
@pytest.mark.parametrize('warm', [False, True])
async def test_off_emits_no_new_metrics_even_after_on_registration(monkeypatch, warm):
    if warm:
        soniox_wire_metrics.wire_metrics()
    before = snapshot()
    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'false')
    monkeypatch.setattr(soniox_wire_metrics, 'wire_metrics', lambda: pytest.fail('OFF requested wire metrics'))
    receiver, _, processor, store, leg, peer, _ = await managed(monkeypatch, True)
    leg.gate = None
    peer.samples = 0
    try:
        send_observed(receiver, leg, RATE)
        leg.finalize()
        await barrier(leg.raw, peer)
        await final(peer, first=RATE // 5, end=4 * RATE // 5)
        assert known(await tick(receiver, processor, store)) == 1
    finally:
        await close(leg)
    assert snapshot() == before


@pytest.mark.asyncio
async def test_prebind_reported_hole_is_registered_once_on_logical_epoch(monkeypatch):
    from tests.unit.test_soniox_finalize_padding import PaddingPeer

    monkeypatch.setenv('SONIOX_WIRE_LEDGER', 'true')
    holes, samples = value('provider_holes'), value('provider_hole_samples')
    opener = soniox._open_soniox

    async def connect(*args):
        raw = await opener(*args)
        raw._ws.__class__ = PaddingPeer
        raw._ws.samples = raw._ws.finalizes = 0
        await raw._write(b'\2\0' * 42732)
        await raw._write('{"type": "finalize"}')
        await consume(raw._ws, raw._ws.acknowledgment())
        # Report is clean locally, but not registered before epoch binding.
        assert value('provider_holes') == holes
        return raw

    monkeypatch.setattr(soniox, '_open_soniox', connect)
    receiver, epoch, processor, store, leg, peer, _ = await managed(monkeypatch, True)
    leg.gate = None
    try:
        assert value('provider_holes') == holes + 1
        assert value('provider_hole_samples') == samples + 1428
        leg.raw.set_wire_ledger(epoch)
        assert value('provider_holes') == holes + 1
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 1
        assert epoch.wire_audio_samples == 42732 + RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_receive_teardown_settles_metrics_without_anchoring_later_queued_audio(monkeypatch):
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    missing = value('finalize_checkpoints', 'missing_ack')
    refused = value('intervals', 'unplaceable_by_race')
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        # The real receive loop exits with the finalize still unacknowledged.
        await consume(peer, dict(finished=True, tokens=[]))
        await asyncio.wait_for(leg.raw._recv_task, 0.1)
        assert value('finalize_checkpoints', 'missing_ack') == missing + 1
        send_observed(receiver, leg, RATE)
        leg.finalize()
        await barrier(leg.raw, peer)
        # Writes begun after receive termination have no possible ack consumer.
        assert value('finalize_checkpoints', 'missing_ack') == missing + 2
        assert epoch.wire_audio_samples == 42732 + RATE
        assert epoch.send_map.accepted_provider_samples(0, epoch.wire_provider_samples) == 42732
        # Exercise the actual parser/callback/receiver/persistence with a delayed
        # token for that emitted interval; metric settlement grants no window.
        leg.raw._handle_tokens([dict(text='Delayed audio. ', is_final=True, speaker='1', start_ms=3000, end_ms=3200)])
        assert known(await tick(receiver, processor, store)) == 0
        assert value('intervals', 'unplaceable_by_race') == refused + 1
        leg.raw._provider_clock.close()
        assert value('finalize_checkpoints', 'missing_ack') == missing + 2
    finally:
        await close(leg)
