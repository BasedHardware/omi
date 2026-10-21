"""Durable ownership, short live custody and provider replay boundaries."""

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest

from utils.observability import held_content as held_metrics
from utils.sync import cap_hold, cap_hold_lifecycle, cap_hold_redrive, live_cap_hold as live, live_cap_staging
from utils.sync.live_cap_publication import Publication
from utils.sync import live_cap_codec
from utils.stt import pre_recorded

_EMPTY_FLEET = {
    'pending_count': 0,
    'pending_seconds': 0.0,
    'oldest_listed_at': None,
    'undated_pending': 0,
    'backlog_items': 0,
}


@pytest.fixture(autouse=True)
def _fleet_snapshot_stays_local(monkeypatch):
    monkeypatch.setattr(cap_hold_redrive.store, 'fleet_snapshot', lambda firestore_client=None: dict(_EMPTY_FLEET))


@pytest.fixture
def fragment_sink(monkeypatch, tmp_path):
    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='omi', websocket=SimpleNamespace(send_json=AsyncMock())),
        state=SimpleNamespace(),
        session_id='socket',
    )
    sink = live.LiveHeldAudio(host)
    staged, sealed = {}, []
    monkeypatch.setattr(cap_hold, 'ensure_summary', Mock())
    monkeypatch.setattr(cap_hold, 'record_audio', Mock())
    monkeypatch.setattr(live, 'fragments_enabled', lambda: True)
    monkeypatch.setattr(
        live.live_cap_capacity,
        'acquire',
        lambda uid, month, identity: live.live_cap_capacity.Capacity(uid, month, identity),
    )
    monkeypatch.setattr(live.live_cap_capacity, 'release', Mock())
    monkeypatch.setattr(
        cap_hold, 'recovery_directory', lambda uid: __import__('tempfile').TemporaryDirectory(dir=tmp_path)
    )
    monkeypatch.setattr(
        live_cap_codec, 'encode', lambda path, pcm, rate, **kwargs: __import__('pathlib').Path(path).write_bytes(pcm)
    )

    def append(uid, path, group, fragment, meta, seconds):
        parts = staged.setdefault(group.identity, {})
        parts.setdefault(fragment.identity, (meta, seconds))

    def seal(uid, identity, **kwargs):
        if identity not in [item[0] for item in sealed]:
            sealed.append((identity, list(staged[identity].values())))
        return True

    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(return_value={'audio_size': 36}))
    monkeypatch.setattr(live_cap_staging, 'append', Mock(side_effect=append))
    monkeypatch.setattr(live_cap_staging, 'seal', Mock(side_effect=seal))
    yield sink, staged, sealed
    cap_hold_lifecycle.ACTIVE.discard(sink)


async def test_fragment_bound_keeps_one_retained_source_per_minute_and_consumes_after_receipt(fragment_sink):
    sink, staged, sealed = fragment_sink
    maximum = 0
    for second in range(120):
        await sink.append_async(b'\1\0' * 100, 100, 1000 + second, 'conversation')
        maximum = max(maximum, sink.buffered_seconds())
        await sink.flush()
    await sink.close()
    assert maximum <= 15
    assert len(staged) == len(sealed) == 2
    assert all(len(parts) == 4 for parts in staged.values())
    assert [sum(part[1] for part in parts) for _, parts in sealed] == [60, 60]
    assert sink.seconds == 120
    assert live.live_cap_capacity.release.call_args.args[0].used == 2


async def test_failed_fragment_does_not_consume_slot_and_retry_reuses_identity(fragment_sink):
    sink, staged, sealed = fragment_sink
    sink.append(b'\1\0' * 100, 100, 1000, 'conversation')
    append = live_cap_staging.append
    original = append.side_effect
    append.side_effect = TimeoutError('ambiguous publication')
    with pytest.raises(TimeoutError):
        await sink.flush(force=True)
    source = append.call_args.args[3]
    assert sink.capacity.used == 0 and sink._capacity_uncertain
    assert sink.seconds == 0 and sink.buffered_seconds() == 1
    append.side_effect = original
    await sink.close()
    assert append.call_args.args[3] is source
    assert sink.seconds == 1 and len(sealed) == 1
    assert live.live_cap_capacity.release.call_args.args[0].used == 1


async def test_shutdown_flushes_partial_and_awaits_inflight_publication(fragment_sink):
    sink, staged, sealed = fragment_sink
    entered, release = asyncio.Event(), asyncio.Event()
    sink.append(b'\1\0' * 100, 100, 1000, 'conversation')
    original = sink._flush

    async def blocked(**kwargs):
        entered.set()
        await release.wait()
        await original(**kwargs)

    sink._flush = blocked
    shutdown = asyncio.create_task(cap_hold_lifecycle.flush_active(timeout=2))
    await entered.wait()
    assert not shutdown.done() and not sealed
    release.set()
    await shutdown
    assert sink.seconds == 1 and len(sealed) == 1
    assert sink not in cap_hold_lifecycle.ACTIVE


async def test_sweep_awaits_worker_and_does_not_create_consent(monkeypatch):
    snap = SimpleNamespace(id='current', reference=SimpleNamespace(path='users/owner/processing_backlog/current'))
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: [snap] if kind == 'choices' else [])
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    entered, release = asyncio.Event(), asyncio.Event()

    async def run(uid, **kwargs):
        assert uid == 'owner' and kwargs['max_items'] == 1 and not kwargs['continuation']
        assert 0 < kwargs['time_budget'] <= 900
        entered.set()
        await release.wait()

    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'run', run)
    choose = Mock(side_effect=AssertionError('sweep created consent'))
    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'choose', choose)
    sweep = asyncio.create_task(cap_hold_redrive.sweep())
    await entered.wait()
    assert not sweep.done()
    release.set()
    assert (await sweep)['visited'] == 1
    choose.assert_not_called()


async def test_sweep_kill_switch_does_not_read_or_dispatch(monkeypatch):
    monkeypatch.setenv('CAP_HOLD_DURABLE_REDRIVE_ENABLED', 'false')
    discover = Mock(side_effect=AssertionError('disabled sweep queried'))
    snapshot = Mock(side_effect=AssertionError('disabled sweep aggregated'))
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', discover)
    monkeypatch.setattr(cap_hold_redrive.store, 'fleet_snapshot', snapshot)
    assert await cap_hold_redrive.sweep() == {'disabled': True}
    snapshot.assert_not_called()


def test_retry_observing_purged_receipt_counts_post_delete_publication(monkeypatch):
    manifest = live.live_cap_manifest
    writes: list[tuple] = []

    class Tx:
        def create(self, *args, **kwargs):
            raise AssertionError('an existing receipt published a manifest')

        def update(self, _ref, patch):
            writes.append(('update', dict(patch)))

        def set(self, _ref, payload, merge=False):
            writes.append(('set', sorted(payload)))

    receipt = {'state': 'purged'}
    ref = SimpleNamespace(get=lambda transaction=None: SimpleNamespace(exists=True, to_dict=lambda: dict(receipt)))
    monkeypatch.setattr(manifest.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(manifest, 'get_firestore_client', lambda: SimpleNamespace(transaction=Tx))
    monkeypatch.setattr(manifest, 'external_write_fence', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(manifest.cap_hold, 'holds', lambda uid: SimpleNamespace(document=lambda identity: ref))
    monkeypatch.setattr(manifest.cap_hold, 'summary_ref', lambda uid: SimpleNamespace())
    upload = Mock(side_effect=AssertionError('an existing receipt uploaded audio'))
    monkeypatch.setattr(manifest.cap_hold, 'upload_held_audio', upload)

    source = Publication('synthetic')
    assert source.is_retry('synthetic') is False
    before = held_metrics.ERASURE.labels(outcome='post_delete_publication')._value.get()
    manifest.publish('synthetic', 'unused', source, {'timestamp': 1000}, 60)
    assert held_metrics.ERASURE.labels(outcome='post_delete_publication')._value.get() == before + 1
    assert writes == []  # The tombstone wins: no manifest and no summary movement.
    upload.assert_not_called()

    # A held receipt without the marker was already counted by the writer that
    # created it: receipt and summary increment commit in one transaction, so
    # only the marker is stamped and the summary never moves again.
    receipt['state'] = 'held'
    manifest.publish('synthetic', 'unused', source, {'timestamp': 1000}, 60)
    assert held_metrics.ERASURE.labels(outcome='post_delete_publication')._value.get() == before + 1
    assert writes == [('update', {'usage_applied': True})]
    upload.assert_not_called()

    receipt['usage_applied'] = True
    manifest.publish('synthetic', 'unused', source, {'timestamp': 1000}, 60)
    assert writes == [('update', {'usage_applied': True})]
    upload.assert_not_called()


async def test_sweep_publishes_one_fleet_snapshot_and_clears_an_empty_backlog(monkeypatch):
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: [])
    calls = []

    def snapshot(firestore_client=None):
        calls.append(firestore_client)
        return dict(_EMPTY_FLEET)

    monkeypatch.setattr(cap_hold_redrive.store, 'fleet_snapshot', snapshot)
    held_metrics.OLDEST_AGE.set(9)
    held_metrics.UNDATED_PENDING.set(9)
    held_metrics.BACKLOG.set(9)
    await cap_hold_redrive.sweep()
    assert calls == [None]
    assert held_metrics.OLDEST_AGE._value.get() == 0
    assert held_metrics.PENDING_COUNT._value.get() == 0
    assert held_metrics.UNDATED_PENDING._value.get() == 0
    assert held_metrics.BACKLOG._value.get() == 0


@pytest.mark.parametrize('provider', ['modulate', 'parakeet'])
def test_held_provider_disables_nested_billable_retry(monkeypatch, provider):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://127.0.0.1:1')
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.side_effect = TimeoutError('ambiguous provider reply')
    monkeypatch.setattr(pre_recorded.httpx, 'Client', Mock(return_value=client))
    fn = (
        pre_recorded.modulate_prerecorded_from_bytes
        if provider == 'modulate'
        else pre_recorded.parakeet_prerecorded_from_bytes
    )
    with pre_recorded.held_single_attempt(), pytest.raises(RuntimeError):
        fn(b'pcm', diarize=False)
    assert client.post.call_count == 1
    assert not pre_recorded._held_single_attempt.get()


def test_composed_encrypted_sources_decode_each_fragment_clock(tmp_path, monkeypatch):
    rate = 24000
    layouts, payload = [], b''
    # Include padding-prone sub-packet tails: independently trim every fragment.
    for index, frames in enumerate([27, rate // 2, 3 * rate]):
        source = tmp_path / f'{index}.opus'
        live_cap_codec.encode(str(source), b'\0\0' * frames, rate, max_bytes=32 * 1024)
        part = source.read_bytes()
        layouts.append({'bytes': len(part), 'frames': frames})
        payload += part

    def read(uid, row, path):
        __import__('pathlib').Path(path).write_bytes(payload)

    monkeypatch.setattr(cap_hold, '_read_single_audio', read)
    result = tmp_path / 'all.wav'
    cap_hold.read_audio(
        'synthetic',
        {
            'audio_path': 'source',
            'audio_codec': 'ogg_opus',
            'sample_rate': rate,
            'source_frames': sum(p['frames'] for p in layouts),
            'opus_fragments': layouts,
        },
        str(result),
    )
    with wave.open(str(result)) as source:
        assert source.getnframes() == sum(p['frames'] for p in layouts)


def test_provider_result_survives_ingest_crash_without_another_dispatch(monkeypatch):
    from utils.sync import cap_recovery_provider as provider

    receipt = {'state': 'dispatched', 'attempt': 1}
    context = {'hold_id': 'h', 'piece': 'p', 'lease_token': 'lease', 'attempt': 1, 'receipt': receipt}

    def checkpoint(uid, ctx, updates):
        receipt.update(updates)
        return True

    monkeypatch.setattr(provider.sync_cap_recovery, 'provider_checkpoint', checkpoint)
    dispatch = Mock(return_value=([{'text': 'hello', 'timestamp': [0, 1]}], 'en'))
    first = provider.transcribe('synthetic', context, dispatch)
    assert 'provider_started_at' in receipt and 'provider_completed_at' in receipt
    assert 'hello' not in receipt['provider_result']
    # Simulate a process/ingest failure after the durable response, then restart.
    assert provider.transcribe('synthetic', context, dispatch) == first
    dispatch.assert_called_once()


def test_empty_provider_result_remains_reconcilable_instead_of_infinite_cached_replay(monkeypatch):
    from utils.sync import cap_recovery_provider as provider

    saved = {}
    monkeypatch.setattr(
        provider.sync_cap_recovery, 'provider_checkpoint', lambda uid, context, updates: saved.update(updates) or True
    )
    assert provider.transcribe('synthetic', {'receipt': {}}, lambda: ([], 'en')) == ([], 'en')
    assert saved['provider_empty'] and 'provider_result' not in saved


async def test_shutdown_deadline_observes_cancelled_sinks(monkeypatch, caplog):
    class Sink:
        async def close(self):
            await asyncio.Event().wait()

    sink = Sink()
    monkeypatch.setattr(cap_hold_lifecycle, 'ACTIVE', {sink})
    await asyncio.wait_for(cap_hold_lifecycle.flush_active(timeout=0.01), timeout=1)
    assert 'outcome=shutdown_flush_timeout sinks=1' in caplog.text


async def test_shutdown_failure_is_observed_without_a_false_success(monkeypatch, caplog):
    class Sink:
        async def close(self):
            raise RuntimeError('failed flush')

    sink = Sink()
    monkeypatch.setattr(cap_hold_lifecycle, 'ACTIVE', {sink})
    await cap_hold_lifecycle.flush_active(timeout=1)
    assert sink in cap_hold_lifecycle.ACTIVE
    assert 'outcome=shutdown_flush_failed exception_type=RuntimeError' in caplog.text


async def test_scheduler_http_endpoint_awaits_work_and_requires_oidc(monkeypatch):
    from fastapi import FastAPI
    import httpx
    from routers import sync

    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', 'http://synthetic/task')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'synthetic@example.invalid')
    app = FastAPI()
    app.include_router(sync.router)
    called = AsyncMock(return_value={'visited': 1, 'sealed': 1})
    monkeypatch.setattr(sync.cap_hold_redrive, 'sweep', called)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        refused = await client.post('/v2/cap-hold-recovery/sweep')
        assert refused.status_code == 403
        called.assert_not_awaited()
        app.dependency_overrides[sync.verify_cloud_tasks_oidc] = lambda: 0
        response = await client.post('/v2/cap-hold-recovery/sweep')
        assert response.status_code == 200
        assert response.json() == {'visited': 1, 'sealed': 1}
        called.assert_awaited_once()


async def test_expired_writer_rolls_only_uncommitted_fragment_into_new_source(fragment_sink):
    sink, staged, sealed = fragment_sink
    for second in range(15):
        await sink.append_async(b'\1\0' * 100, 100, 1000 + second, 'conversation')
    await sink.flush()
    original = live_cap_staging.append.side_effect
    calls = [0]

    def expired(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise live_cap_staging.SourceSealed('sweeper sealed idle writer')
        return original(*args, **kwargs)

    live_cap_staging.append.side_effect = expired
    await sink.append_async(b'\2\0' * 100, 100, 1015, 'conversation')
    await sink.close()
    assert sink.seconds == 16 and len(sealed) == 2
    assert live.live_cap_capacity.release.call_args.args[0].used == 2


def test_noisy_fifteen_second_fragment_obeys_size_ceiling(tmp_path):
    import os

    path = tmp_path / 'noise.opus'
    pcm = os.urandom(15 * 16000 * 2)
    live_cap_codec.encode(str(path), pcm, 16000, max_bytes=live_cap_staging.MAX_FRAGMENT_BYTES)
    assert path.stat().st_size <= 32 * 1024


async def test_lost_capacity_reply_after_expired_full_block_reconciles_on_retry(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    for second in range(15):
        await sink.append_async(b'\1\0' * 100, 100, 1000 + second, 'conversation')
    await sink.flush()
    sink.capacity.used = live.live_cap_capacity.BLOCK_GROUPS
    original_append = live_cap_staging.append.side_effect
    append_calls = [0]

    def expired(*args, **kwargs):
        append_calls[0] += 1
        if append_calls[0] == 1:
            raise live_cap_staging.SourceSealed('idle writer sealed')
        return original_append(*args, **kwargs)

    live_cap_staging.append.side_effect = expired
    acquisitions = []

    def acquire(uid, month, identity):
        acquisitions.append(identity)
        if len(acquisitions) == 1:
            raise TimeoutError('committed acquisition reply lost')
        return live.live_cap_capacity.Capacity(uid, month, identity)

    monkeypatch.setattr(live.live_cap_capacity, 'acquire', acquire)
    await sink.append_async(b'\2\0' * 100, 100, 1015, 'conversation')
    with pytest.raises(TimeoutError):
        await sink.flush(force=True)
    assert sink.buffered_seconds() == 1 and sink.capacity_identity == acquisitions[0]
    await sink.close()
    assert acquisitions == [acquisitions[0], acquisitions[0]]
    assert sink.seconds == 16 and len(sealed) == 2
    assert live.live_cap_capacity.release.call_args.args[0].used == 1


@pytest.mark.parametrize('cancel_publication', [False, True])
async def test_shutdown_parked_executor_keeps_scratch_until_upload_completion(
    fragment_sink, monkeypatch, tmp_path, cancel_publication
):
    import threading
    from pathlib import Path

    sink, _, _ = fragment_sink
    entered, release = threading.Event(), threading.Event()
    paths = []
    original = cap_hold.upload_held_audio

    def parked(uid, path, *args, **kwargs):
        paths.append(Path(path))
        entered.set()
        assert release.wait(5)
        assert Path(path).exists(), 'scratch was deleted while executor still owned it'
        return original(uid, path, *args, **kwargs)

    monkeypatch.setattr(cap_hold, 'upload_held_audio', parked)
    sink.append(b'\1\0' * 100, 100, 1000, 'conversation')
    shutdown = asyncio.create_task(cap_hold_lifecycle.flush_active(timeout=0.05))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        await asyncio.wait_for(shutdown, timeout=0.2)
        assert paths[0].exists() and not sink._custody.done()
        if cancel_publication:
            # Event-loop shutdown may cancel even the shielded inner task.
            # Its executor leaf must still retain scratch through real IO.
            sink._custody.cancel()
            with pytest.raises(asyncio.CancelledError):
                await sink._custody
            assert paths[0].exists()
    finally:
        release.set()
        if not cancel_publication:
            await sink._custody
        else:

            async def cleaned():
                while paths[0].exists():
                    await asyncio.sleep(0.001)

            await asyncio.wait_for(cleaned(), timeout=2)
    assert not paths[0].exists()
    await sink.close()
    assert sink.seconds == 1
    assert live.live_cap_capacity.release.call_args.args[0].used == 1
    assert len(paths) == 1  # Cancellation adopts the completed upload; no fresh identity/put.


async def test_shutdown_cancellation_resistant_close_cannot_extend_deadline(monkeypatch):
    release = asyncio.Event()

    class Sink:
        async def close(self):
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

    sink = Sink()
    monkeypatch.setattr(cap_hold_lifecycle, 'ACTIVE', {sink})
    await asyncio.wait_for(cap_hold_lifecycle.flush_active(timeout=0.01), timeout=0.2)
    assert cap_hold_lifecycle.CLOSING
    release.set()
    await asyncio.gather(*cap_hold_lifecycle.CLOSING)


async def test_sweep_progresses_five_owners_concurrently(monkeypatch):
    snaps = [SimpleNamespace(reference=SimpleNamespace(path=f'users/{i}/processing_backlog/current')) for i in range(5)]
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: snaps if kind == 'choices' else [])
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    entered = set()
    all_entered = asyncio.Event()
    completed = []

    async def run(uid, *, continuation, max_items, time_budget):
        assert max_items == 1 and not continuation and 0 < time_budget <= 900
        entered.add(uid)
        if len(entered) == 5:
            all_entered.set()
        await asyncio.wait_for(all_entered.wait(), timeout=1)
        completed.append(uid)

    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'run', run)
    assert (await cap_hold_redrive.sweep())['visited'] == 5
    assert len(completed) == 5


async def test_sweep_rotates_owners_before_fast_owner_gets_another_turn(monkeypatch):
    snaps = [SimpleNamespace(reference=SimpleNamespace(path=f'users/{i}/processing_backlog/current')) for i in range(5)]
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: snaps if kind == 'choices' else [])
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    turns, seen = [], {str(i): 0 for i in range(5)}

    async def run(uid, *, continuation, max_items, time_budget):
        assert max_items == 1
        assert continuation == (seen[uid] > 0)
        assert max(seen.values()) - min(seen.values()) <= 1
        turns.append(uid)
        seen[uid] += 1
        await asyncio.sleep(0)
        return seen[uid] < 3

    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'run', run)
    assert (await cap_hold_redrive.sweep())['visited'] == 5
    assert len(turns) == 15
    assert all(set(turns[offset : offset + 5]) == set(seen) for offset in range(0, 15, 5))


async def test_paced_owner_does_not_stop_other_owners_or_custody_maintenance(monkeypatch):
    snaps = [
        SimpleNamespace(id=str(i), reference=SimpleNamespace(path=f'users/{i}/processing_backlog/current'))
        for i in range(2)
    ]
    staging = SimpleNamespace(id='source', reference=SimpleNamespace(path='users/0/stt_cap_holds/source'))
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', lambda kind: snaps if kind == 'choices' else [staging])
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    calls = []

    async def run(uid, **kwargs):
        calls.append(uid)
        return uid == '1' and calls.count(uid) < 3

    seal = Mock(return_value=True)
    cleanup = Mock()
    monkeypatch.setattr(cap_hold_redrive.live_cap_staging, 'seal', seal)
    monkeypatch.setattr(cap_hold_redrive.live_cap_staging, 'cleanup', cleanup)
    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'run', run)
    assert await cap_hold_redrive.sweep() == {'sealed': 1, 'visited': 2}
    assert calls.count('0') == 1 and calls.count('1') == 3
    seal.assert_called_once()
    cleanup.assert_called_once()


@pytest.mark.parametrize('size', [900 * 1024, 100 * 1024])
def test_oversized_and_aggregate_cache_budget_preserve_usable_result(monkeypatch, size):
    from database import sync_cap_recovery as store
    from utils.sync import cap_recovery_provider as provider

    old = 'old-ciphertext' * 50000
    receipt = {'state': 'dispatched', 'attempt': 1}
    row = {'piece_receipts': {'old': {'provider_result': old}, 'p': receipt}}
    context = {'receipt': receipt, 'piece': 'p'}

    def checkpoint(uid, ctx, updates):
        receipt.update(store.bounded_provider_updates(row, 'p', updates))
        return True

    monkeypatch.setattr(provider.sync_cap_recovery, 'provider_checkpoint', checkpoint)
    words = [{'text': 'x' * size, 'timestamp': [0, 1]}]
    dispatch = Mock(return_value=(words, 'en'))
    assert provider.transcribe('synthetic', context, dispatch) == (words, 'en')
    dispatch.assert_called_once()
    assert receipt['provider_cache_omitted'] and 'provider_result' not in receipt
    assert row['piece_receipts']['old']['provider_result'] == old


def test_sweep_rejects_nested_or_unrelated_collection_group_owners():
    for path in (
        'other/u/processing_backlog/current',
        'users/u/nested/x/processing_backlog/current',
        'users/u/processing_backlog/not-current',
    ):
        assert (
            cap_hold_redrive.owner(SimpleNamespace(reference=SimpleNamespace(path=path)), 'processing_backlog') is None
        )
    assert (
        cap_hold_redrive.owner(
            SimpleNamespace(reference=SimpleNamespace(path='users/u/stt_cap_holds/h')), 'stt_cap_holds'
        )
        == 'u'
    )


async def test_sweep_excludes_unenrolled_owner_but_preserves_custody_maintenance(monkeypatch):
    snap = SimpleNamespace(reference=SimpleNamespace(path='users/other/processing_backlog/current'))
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:chosen')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    discover = Mock(side_effect=lambda kind: [snap] if kind == 'choices' else [])
    monkeypatch.setattr(cap_hold_redrive.store, 'discover', discover)
    worker = AsyncMock(side_effect=AssertionError('unenrolled owner dispatched'))
    monkeypatch.setattr(cap_hold_redrive.processing_backlog_worker, 'run', worker)
    assert await cap_hold_redrive.sweep() == {'sealed': 0, 'visited': 0}
    assert [call.args[0] for call in discover.call_args_list] == ['staging', 'cleanup', 'choices']
    worker.assert_not_called()
