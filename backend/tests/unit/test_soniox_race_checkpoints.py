# LIFECYCLE: permanent
"""R15 ordered finalize proof through managed parser, receiver and persistence."""

import pytest
from prometheus_client import REGISTRY

from tests.unit.test_soniox_finalize_padding import setup_peer, send_observed, consume, final
from tests.unit.test_soniox_capture_axis_r10 import close
from tests.unit.test_soniox_wire_ledger import barrier
from tests.unit.test_capture_window_merge_union_r5 import tick, known
from tests.unit.test_audio_timeline_round3 import RATE, T0


@pytest.mark.asyncio
@pytest.mark.parametrize('offset', [0, 1, 944, 960, 976, 1904, 1919])
@pytest.mark.parametrize('controls', [1, 2, 5])
async def test_raced_fifo_checkpoints_place_observed_post_finalize_audio(monkeypatch, offset, controls):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        length = 23 * 1920 + offset
        send_observed(receiver, leg, length)
        reports = []
        for i in range(controls):
            if i:
                send_observed(receiver, leg, [1, 944, 1920, 1904][i - 1])
            leg.finalize()
            await barrier(leg.raw, peer)
            reports.append(peer.acknowledgment())
        origin = peer.samples
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        # Unverified prediction cannot grant a window, even before a mismatch.
        assert (
            known(epoch.translate([dict(text='Pending.', start=(origin + 3200) / RATE, end=(origin + 12800) / RATE)]))
            == 0
        )
        for report in reports:
            await consume(peer, report)
        await final(peer)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 1
        assert epoch.wire_provider_samples == peer.samples
        capture = length + sum([1, 944, 1920, 1904][: controls - 1])
        assert rows[-1]['audio_capture_start'] == pytest.approx(T0 + capture / RATE + 0.2, abs=2 / RATE, rel=0)
        assert rows[-1]['audio_capture_end'] == pytest.approx(T0 + capture / RATE + 0.8, abs=2 / RATE, rel=0)
        assert epoch.wire_audio_samples == capture + RATE
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['different', 'missing', 'fractional', 'combined'])
async def test_mismatch_invalidates_interval_and_future_on_same_socket(monkeypatch, bad):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    before = REGISTRY.get_sample_value('omi_soniox_ordered_finalize_checkpoints_total', {'outcome': 'mismatch'}) or 0
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        report = peer.acknowledgment()
        if bad == 'different':
            report['total_audio_proc_ms'] = report['final_audio_proc_ms'] = 2791
        elif bad == 'missing':
            report.pop('final_audio_proc_ms')
        elif bad == 'fractional':
            report['total_audio_proc_ms'] = report['final_audio_proc_ms'] = 2760.5
        else:
            report['tokens'] *= 2
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        first, end = peer.samples - 12800, peer.samples - 3200
        await consume(peer, report)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
        assert (
            REGISTRY.get_sample_value('omi_soniox_ordered_finalize_checkpoints_total', {'outcome': 'mismatch'})
            == before + 1
        )
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=2)
        assert known(await tick(receiver, processor, store)) == 0
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=3)
        assert known(await tick(receiver, processor, store)) == 0
        # Later clean-looking reports cannot repair lost control association.
        await final(peer, first=first, end=end, speaker=4)
        assert known(await tick(receiver, processor, store)) == 0
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('inside_send', [False, True])
@pytest.mark.parametrize('mismatch', [False, True])
async def test_ack_inside_audio_await_and_back_to_back_controls(monkeypatch, inside_send, mismatch):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        reports = []
        for _ in range(2):
            leg.finalize()
            await barrier(leg.raw, peer)
            reports.append(peer.acknowledgment())
        if mismatch:
            reports[0]['total_audio_proc_ms'] += 1
        original = peer.send

        async def send(value):
            await original(value)
            if isinstance(value, bytes):
                for report in reports:
                    await consume(peer, report)

        if inside_send:
            monkeypatch.setattr(peer, 'send', send)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        if not inside_send:
            for report in reports:
                await consume(peer, report)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == int(not mismatch)
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_missing_ack_teardown_invalidates_pending_map_and_late_writes(monkeypatch):
    import asyncio

    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        await consume(peer, dict(finished=True, tokens=[]))
        await asyncio.wait_for(leg.raw._recv_task, 0.1)
        assert known(await tick(receiver, processor, store)) == 0
        assert epoch.send_map.last_provider_sample == 42732
        # Finalize begun after receive termination cannot re-enable prediction.
        leg.finalize()
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        assert epoch.send_map.last_provider_sample == 42732
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_clean_looking_report_cannot_reanchor_below_disproven_prediction(monkeypatch):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        leg.finalize()
        await barrier(leg.raw, peer)
        # Peer contradicts the prediction: actual padding is zero.
        peer.samples = 42732
        bad = peer.acknowledgment()
        await consume(peer, bad)
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        leg.finalize()
        await barrier(leg.raw, peer)
        peer.samples = 42732 + RATE
        clean = peer.acknowledgment()
        # Use an integer-ms provider anchor, still below rejected predictions.
        peer.samples = 58736
        clean['total_audio_proc_ms'] = clean['final_audio_proc_ms'] = 3671
        await consume(peer, clean)
        assert leg.raw._provider_clock._association_lost
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        rows = await tick(receiver, processor, store)
        assert known(rows) == 0
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_off_receipt_with_ledger_on_and_raced_clean_checkpoints(monkeypatch):
    import asyncio
    import json
    import os
    from pathlib import Path
    from uuid import UUID
    from tests.unit.test_soniox_capture_axis_r10 import soniox_capture_uuid
    from utils.stt import soniox

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
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        await barrier(leg.raw, peer)
        await final(peer)
        await tick(receiver, processor, store)
        leg.finalize()
        await barrier(leg.raw, peer)
        ack = peer.acknowledgment()
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await consume(peer, ack)
        await final(peer, speaker=2)
        await tick(receiver, processor, store)
        leg.finalize()
        await barrier(leg.raw, peer)
        await consume(peer, peer.acknowledgment())
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer, speaker=3)
        rows = await tick(receiver, processor, store)
        leg.finish()
        for _ in range(8):
            await asyncio.sleep(0)
        after = values()
        receipt = dict(
            rows=rows,
            wire=[dict(binary=v.hex()) if isinstance(v, bytes) else dict(text=v) for v in peer.sent],
            counters=sorted(
                [name, list(labels), value - before.get((name, labels), 0)]
                for (name, labels), value in after.items()
                if value != before.get((name, labels), 0)
            ),
        )
        assert not any('ordered_finalize' in r[0] for r in receipt['counters'])
        target = os.getenv('R15_RECEIPT_PATH')
        if target:
            Path(target).write_text(json.dumps(receipt, sort_keys=True, default=str))
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['normal', 'recovery', 'idle'])
async def test_ordered_feature_preserves_complete_wire_frames(monkeypatch, path):
    from tests.unit.test_soniox_finalize_padding import (
        test_on_off_byte_identical_audio_and_control_transcript,
        test_on_off_idle_close_reopen_wire_transcript,
    )

    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    if path == 'idle':
        await test_on_off_idle_close_reopen_wire_transcript(monkeypatch)
    else:
        await test_on_off_byte_identical_audio_and_control_transcript(monkeypatch, path == 'recovery')


@pytest.mark.asyncio
async def test_bounded_prediction_queue_overflow_never_grants_capture(monkeypatch):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, processor, store, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        for _ in range(65):
            leg.finalize()
        await barrier(leg.raw, peer)
        assert len(leg.raw._provider_clock._predictions) == 0
        send_observed(receiver, leg, RATE)
        await barrier(leg.raw, peer)
        await final(peer)
        assert known(await tick(receiver, processor, store)) == 0
        assert epoch.send_map.last_provider_sample == 42732
    finally:
        await close(leg)


@pytest.mark.asyncio
async def test_feature_off_has_no_metrics_after_ordered_clock_is_warm(monkeypatch):
    from utils.stt import soniox_wire_metrics

    soniox_wire_metrics.ordered_finalize_metrics()
    before = REGISTRY.get_sample_value('omi_soniox_ordered_finalize_checkpoints_total', {'outcome': 'verified'})
    monkeypatch.setattr(
        soniox_wire_metrics, 'ordered_finalize_metrics', lambda: pytest.fail('OFF registered ordered metrics')
    )
    await test_off_receipt_with_ledger_on_and_raced_clean_checkpoints(monkeypatch)
    assert REGISTRY.get_sample_value('omi_soniox_ordered_finalize_checkpoints_total', {'outcome': 'verified'}) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['prebind', 'idle', 'idle_pending'])
async def test_ordered_feature_preserves_unknown_prefix_and_idle_origins(monkeypatch, path):
    from tests.unit.test_soniox_finalize_padding import (
        test_prebind_finalize_padding_and_no_audio_finalizes_grant_no_capture,
        test_idle_reopen_freezes_provider_origin_with_padding_and_separate_pcm_diagnostics,
    )

    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    if path == 'prebind':
        await test_prebind_finalize_padding_and_no_audio_finalizes_grant_no_capture(monkeypatch)
    else:
        await test_idle_reopen_freezes_provider_origin_with_padding_and_separate_pcm_diagnostics(
            monkeypatch, path == 'idle_pending'
        )


@pytest.mark.asyncio
async def test_failed_finalize_write_cannot_grant_speculative_mapping(monkeypatch):
    monkeypatch.setenv('SONIOX_ORDERED_FINALIZE', 'true')
    receiver, epoch, _, _, leg, peer, _ = await setup_peer(monkeypatch)
    try:
        send_observed(receiver, leg, 42732)
        await barrier(leg.raw, peer)
        peer.reject = True
        with pytest.raises(RuntimeError, match='local wire failure'):
            await leg.raw._write('{"type": "finalize"}')
        assert epoch.send_map.last_provider_sample == 42732
        assert leg.raw._provider_clock._uncertain
        assert epoch.wire_audio_samples == 42732
    finally:
        await close(leg)
