"""Observational custody PCM accounting must never affect the commit or ACK."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY, generate_latest

from routers import pusher
from utils import metrics
from database import record_audio, record_token_lease_metrics
from utils import pusher_record_barrier
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_record_token_lease import PATH, ROW, NOW, POD

PCM = b'\x01\x00' * 32


def commit_args():
    return dict(
        uid='test-user',
        payload=PCM,
        frames=[{'sequence': 1}],
        conversation_id=None,
        start=1.0,
        sample_rate=16000,
        custody_root='test-root',
        protection_level=None,
        audio_custody=1,
        timeline_v2=False,
        websocket=SimpleNamespace(send_bytes=AsyncMock()),
        durable_queue=MagicMock(),
        budget=MagicMock(),
        queue_wait_timeout=None,
        on_committed=MagicMock(),
    )


def receipt():
    return SimpleNamespace(conversation_id=None, samples=32, to_dict=lambda: {'committed': True})


def value():
    return REGISTRY.get_sample_value('omi_pusher_storage_pcm_inflight_bytes')


def test_metrics_registered_zero_initialized_and_in_source_backed_inventory():
    inventory = json.loads(
        (Path(__file__).resolve().parents[2] / 'charts/monitoring/metric-inventory.prod.json').read_text()
    )
    for name in ('omi_pusher_storage_pcm_inflight_bytes', 'omi_pusher_storage_pcm_budget_limit_bytes'):
        assert name in inventory['declared_metrics']
        assert REGISTRY.get_sample_value(name) == 0
        assert f'# TYPE {name} gauge'.encode() in generate_latest()
    assert metrics.PUSHER_STORAGE_PCM_INFLIGHT_BYTES is pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES


@pytest.mark.parametrize('outcome', ['success', 'exception', 'cancel'])
async def test_commit_pcm_gauge_balances_and_preserves_outcomes(monkeypatch, outcome):
    baseline = value()
    entered, release = asyncio.Event(), asyncio.Event()
    result = receipt()
    error = OSError('synthetic storage failure')
    args = commit_args()

    async def storage(executor, fn, *positional, **kwargs):
        assert executor is pusher.storage_executor
        assert fn is pusher.commit_pcm_window
        assert positional[1] is PCM
        assert value() == baseline + len(PCM)
        entered.set()
        await release.wait()
        if outcome == 'exception':
            raise error
        return result

    monkeypatch.setattr(pusher, 'run_blocking', storage)
    task = asyncio.create_task(pusher._commit_durable_audio_window(**args))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert value() == baseline + len(PCM)
        if outcome == 'cancel':
            task.cancel()
        else:
            release.set()
        if outcome == 'success':
            assert await task is result
            args['websocket'].send_bytes.assert_awaited_once()
            args['budget'].release.assert_called_once_with(len(PCM))
            args['on_committed'].assert_called_once_with()
        else:
            with pytest.raises(asyncio.CancelledError if outcome == 'cancel' else OSError) as caught:
                await task
            if outcome == 'exception':
                assert caught.value is error
            args['websocket'].send_bytes.assert_not_awaited()
            args['budget'].release.assert_not_called()
            args['on_committed'].assert_not_called()
        assert value() == baseline
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('failed_metric', ['inc', 'dec'])
@pytest.mark.parametrize('storage_fails', [False, True])
async def test_metric_failure_cannot_change_storage_or_ack(monkeypatch, failed_metric, storage_fails):
    gauge = MagicMock()
    getattr(gauge, failed_metric).side_effect = RuntimeError('synthetic metric failure')
    monkeypatch.setattr(pusher, 'PUSHER_STORAGE_PCM_INFLIGHT_BYTES', gauge)
    result = receipt()
    error = OSError('synthetic storage failure')
    storage = AsyncMock(side_effect=error) if storage_fails else AsyncMock(return_value=result)
    monkeypatch.setattr(pusher, 'run_blocking', storage)
    args = commit_args()
    if storage_fails:
        with pytest.raises(OSError) as caught:
            await pusher._commit_durable_audio_window(**args)
        assert caught.value is error
        args['websocket'].send_bytes.assert_not_awaited()
    else:
        assert await pusher._commit_durable_audio_window(**args) is result
        args['websocket'].send_bytes.assert_awaited_once()
    storage.assert_awaited_once()
    gauge.inc.assert_called_once_with(len(PCM))
    if failed_metric == 'inc':
        gauge.dec.assert_not_called()
    else:
        gauge.dec.assert_called_once_with(len(PCM))


async def test_empty_window_does_not_observe_or_submit(monkeypatch):
    gauge, storage = MagicMock(), AsyncMock()
    monkeypatch.setattr(pusher, 'PUSHER_STORAGE_PCM_INFLIGHT_BYTES', gauge)
    monkeypatch.setattr(pusher, 'run_blocking', storage)
    args = commit_args()
    args['frames'] = []
    assert await pusher._commit_durable_audio_window(**args) is None
    gauge.inc.assert_not_called()
    gauge.dec.assert_not_called()
    storage.assert_not_awaited()


@pytest.mark.parametrize('writer', ['begin', 'renew'])
@pytest.mark.parametrize('outcome', ['success', 'exception', 'refused'])
@pytest.mark.parametrize('closed', [False, True])
async def test_late_append_counts_only_after_durable_commit(monkeypatch, writer, outcome, closed):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setattr(record_audio.time, 'time', lambda: NOW)
    client = StrictFirestore(
        {
            PATH: {**ROW, 'record_audio_closed': closed},
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
        }
    )
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(pusher_record_barrier, 'producer_identity', lambda: POD)
    barrier = pusher_record_barrier.PusherRecordBarrier('synthetic')
    baseline = record_token_lease_metrics.LATE_APPEND._value.get()
    if writer == 'begin':
        await barrier.begin_recording('record')
    else:
        barrier.upload_sessions['record'] = 's'
        barrier.registered_sessions.add('record')  # This fixture models a committed registration.
        await barrier.renew_recording('record')
    assert 'record' in barrier.late_appends
    assert record_token_lease_metrics.LATE_APPEND._value.get() == baseline
    # An older in-flight window that began before this observation cannot
    # consume it just because its unrelated storage call settles later.
    barrier.append_committed('record', observed=False)
    assert record_token_lease_metrics.LATE_APPEND._value.get() == baseline
    args = commit_args()
    args.update(conversation_id='record', on_committed=lambda: barrier.append_committed('record'))
    args['durable_queue'].full.return_value = False
    args['durable_queue'].deliver_pending = AsyncMock()
    committed = SimpleNamespace(conversation_id='record', samples=32, to_dict=lambda: {'committed': True})
    storage = (
        AsyncMock(side_effect=OSError('synthetic object failure'))
        if outcome == 'exception'
        else AsyncMock(return_value=committed)
    )
    monkeypatch.setattr(pusher, 'run_blocking', storage)
    monkeypatch.setattr(
        pusher,
        'storage_pcm_budget',
        SimpleNamespace(limit=1 if outcome == 'refused' else 0, admit=lambda *a, **kw: False),
    )
    try:
        if outcome == 'exception':
            with pytest.raises(OSError):
                await pusher._commit_durable_audio_window(**args)
        else:
            result = await pusher._commit_durable_audio_window(**args)
            assert result is (committed if outcome == 'success' else None)
        assert record_token_lease_metrics.LATE_APPEND._value.get() == baseline + (outcome == 'success')
        if outcome == 'success':
            barrier.append_committed('record')
            assert record_token_lease_metrics.LATE_APPEND._value.get() == baseline + 1
        else:
            args['on_committed'] = MagicMock()
            assert 'record' in barrier.late_appends
    finally:
        barrier._forget_lease('record')
