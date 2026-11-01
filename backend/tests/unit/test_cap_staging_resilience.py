"""A GCS outage cannot revoke custody or end a live listen session."""

import asyncio
import logging
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from threading import Event

import pytest
import requests
from google.api_core.exceptions import Forbidden, ServiceUnavailable, TooManyRequests

from routers.listen.receiver import ListenReceiver
from routers.listen.contracts import ListenSessionState
from utils.observability import held_content as metrics
from utils.sync import cap_hold, live_cap_hold as live, live_cap_journal as journal, live_cap_staging, live_cap_upload
from utils.sync.live_cap_publication import Publication
from utils.sync import cap_hold_lifecycle
from utils.sync import live_cap_manifest
from tests.unit.test_cap_publication_retry import store, delays, UID


@pytest.fixture
def custody(store, monkeypatch):
    monkeypatch.setattr(journal, 'external_write_fence', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(live.cap_hold, 'ensure_summary', Mock())
    monkeypatch.setattr(
        live.live_cap_capacity, 'acquire', lambda uid, month, key: live.live_cap_capacity.Capacity(uid, month, key)
    )
    monkeypatch.setattr(live.live_cap_capacity, 'release', Mock())
    monkeypatch.setattr(live, '_encode_audio', lambda uid, data, rate, fragmented: data)
    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID, source='phone', websocket=SimpleNamespace(send_json=AsyncMock())),
        state=SimpleNamespace(close_code=1000, conversation_sample_ranges=[]),
        session_id='synthetic-session',
    )
    sink = live.LiveHeldAudio(host)
    yield sink
    cap_hold_lifecycle.ACTIVE.discard(sink)


@pytest.mark.parametrize(
    'error', [requests.exceptions.ReadTimeout('transient'), ServiceUnavailable('503'), Forbidden('403')]
)
async def test_failed_gcs_hands_off_then_redrive_publishes_once(custody, store, delays, monkeypatch, error):
    original_upload = cap_hold.upload_held_audio
    failed = Mock(side_effect=error)
    monkeypatch.setattr(cap_hold, 'upload_held_audio', failed)
    pcm = b'\x01\x02' * 8000
    custody.append(pcm, 16000, 1_700_000_000, 'conversation')
    await custody.flush(force=True)
    assert custody.host.state.close_code == 1000
    assert not custody.pending and not custody.buffers
    assert failed.call_count == (1 if isinstance(error, Forbidden) else 2)
    identity, row = next((key, row) for key, row in store.docs.items() if row.get('stage_pending'))
    assert pcm not in row['stage_pending']
    assert journal.decrypt_audio_chunk(row['stage_pending'], UID)[0] == pcm
    assert row['writer_until'] == 0 and row['state'] == 'staging'
    assert 'summary' not in store.docs
    with pytest.raises(type(error)):
        live_cap_staging.seal(UID, identity)
    assert store.docs[identity]['stage_pending'] == row['stage_pending']
    assert store.docs[identity]['state'] == 'staging' and 'summary' not in store.docs

    captured = []

    def recovered(uid, path, fragment_id, metadata, **kwargs):
        captured.append(Path(path).read_bytes())
        fields = original_upload(uid, path, fragment_id, metadata, immutable=True)
        fields['audio_size'] = len(captured[-1]) + 32
        return fields

    monkeypatch.setattr(cap_hold, 'upload_held_audio', recovered)
    assert live_cap_staging.seal(UID, identity)
    assert not live_cap_staging.seal(UID, identity)
    assert captured == [pcm]
    assert store.docs[identity]['state'] == 'held'
    assert 'stage_pending' not in store.docs[identity]
    assert store.docs['summary']['seconds'] == 0.5
    assert store.docs['summary']['count'] == 1
    await custody.close()


async def test_both_stores_unavailable_retains_pcm_until_retry(custody, monkeypatch, caplog):
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=requests.exceptions.ReadTimeout('gcs')))
    handoff = Mock(side_effect=ServiceUnavailable('journal'))
    monkeypatch.setattr(journal, 'defer', handoff)
    custody.append(b'\1\0' * 16000, 16000, 100, 'conversation')
    before = metrics.STAGING_RETRY.labels(outcome='retained')._value.get()
    await custody.flush(force=True)
    await custody.flush(force=True)
    assert custody.pending_bytes == 32000 and custody.host.state.close_code == 1000
    assert metrics.STAGING_RETRY.labels(outcome='retained')._value.get() == before + 2
    warnings = [r for r in caplog.records if 'outcome=staging_retained' in r.getMessage()]
    assert len(warnings) == 1 and warnings[0].levelno == logging.WARNING
    # Every retained attempt is counted, even while warning repeats are limited.
    custody._warning_times['staging_retained'] -= live.WARNING_INTERVAL_SECONDS
    await custody.flush(force=True)
    assert metrics.STAGING_RETRY.labels(outcome='retained')._value.get() == before + 3
    assert sum('outcome=staging_retained' in r.getMessage() for r in caplog.records) == 2
    handoff.side_effect = None
    await custody.close()
    assert not custody.pending and handoff.call_count == 4


async def test_permanent_updater_and_observer_warnings_are_limited_and_idle_gauge_refreshes(
    custody, monkeypatch, caplog
):
    custody.append(b'\1\0' * 8000, 16000, 100, 'conversation')
    metrics.PCM_CUSTODY_SECONDS.set(0)
    monkeypatch.setattr(custody, '_flush', AsyncMock(side_effect=ValueError('permanent failure')))
    stop = asyncio.Event()
    calls = 0

    async def emit():
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
        await custody.flush(force=True)

    receiver = SimpleNamespace(_cap_hold_stop=stop, _emit_stt_cap_live_held=emit)
    await asyncio.wait_for(custody.run_updates(receiver), 4)
    assert calls == 2 and custody.buffered_seconds() == 0.5
    assert metrics.PCM_CUSTODY_SECONDS._value.get() == 0.5
    messages = [r for r in caplog.records if r.name == live.__name__]
    assert all(r.levelno == logging.WARNING for r in messages)
    assert sum('outcome=update_deferred' in r.getMessage() for r in messages) == 1
    assert sum('outcome=publication_failed' in r.getMessage() for r in messages) == 1


async def test_updater_contains_unexpected_exception_and_keeps_running(custody):
    stop = asyncio.Event()
    called = asyncio.Event()
    receiver = SimpleNamespace(_cap_hold_stop=stop, cap_admission=SimpleNamespace(funded_paused=True))

    async def emit():
        called.set()
        raise requests.exceptions.ReadTimeout('unexpected task error')

    receiver._emit_stt_cap_live_held = emit
    task = asyncio.create_task(custody.run_updates(receiver))
    await asyncio.wait_for(called.wait(), 2)
    await asyncio.sleep(0)
    assert not task.done() and custody.host.state.close_code == 1000
    stop.set()
    await asyncio.wait_for(task, 0.1)


async def test_session_and_pod_bounds_force_handoff_without_eviction(custody, monkeypatch):
    monkeypatch.setattr(live, 'MAX_POD_PENDING_SECONDS', 1)
    handoff = Mock()
    monkeypatch.setattr(journal, 'defer', handoff)
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=Forbidden('403')))
    second = live.LiveHeldAudio(custody.host)
    custody.append(b'\1\0' * 16000, 16000, 100, 'conversation')
    await second.append_async(b'\2\0' * 16000, 16000, 101, 'conversation')
    assert live.pod_pending_seconds() <= 1
    assert custody.buffered_seconds() == 0 and second.buffered_seconds() == 1
    await second.close()
    assert handoff.call_count == 2 and live.pod_pending_seconds() == 0
    with pytest.raises(RuntimeError, match='custody bound'):
        custody.append(b'\0' * (16 * 32000), 16000, 102, 'conversation')


@pytest.mark.parametrize(
    'code,expected', [(408, True), (429, True), (500, True), (503, True), (401, False), (403, False), (404, False)]
)
def test_http_retry_classification(code, expected):
    error = requests.exceptions.HTTPError(response=SimpleNamespace(status_code=code))
    assert live_cap_upload.transient(error) is expected


@pytest.mark.parametrize('error', [TooManyRequests('429'), ServiceUnavailable('503'), ConnectionResetError('reset')])
async def test_transient_upload_retry_emits_success(error):
    source = Publication(UID)
    upload = Mock(side_effect=[error, {'audio_generation': 1}])
    before = metrics.STAGING_RETRY.labels(outcome='retried_ok')._value.get()
    await live_cap_upload.prepare(source, upload)
    assert upload.call_count == 2
    assert metrics.STAGING_RETRY.labels(outcome='retried_ok')._value.get() == before + 1


@pytest.mark.parametrize('shutdown', [False, True])
async def test_close_and_sigterm_handoff_late_upload_within_budget(custody, store, monkeypatch, shutdown):
    release = Event()

    def stalled(*args, **kwargs):
        assert release.wait(3)
        raise requests.exceptions.ReadTimeout('late GCS failure')

    monkeypatch.setattr(cap_hold, 'upload_held_audio', stalled)
    monkeypatch.setattr(live_cap_upload, 'UPLOAD_ATTEMPT_SECONDS', 0.01)
    monkeypatch.setattr(live_cap_upload.random, 'uniform', lambda *_: 0)
    custody.append(b'\1\0' * 8000, 16000, 100, 'conversation')
    try:
        if shutdown:
            await asyncio.wait_for(cap_hold_lifecycle.flush_active(timeout=0.5), 0.6)
        else:
            await asyncio.wait_for(custody.close(), 0.5)
        assert not custody.pending
        assert any(row.get('stage_pending') for row in store.docs.values())
        assert custody.host.state.close_code == 1000
    finally:
        release.set()


async def test_real_receiver_final_flush_does_not_close_1011(custody, store, monkeypatch):
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=requests.exceptions.ReadTimeout('GCS blip')))
    host = custody.host
    host.state = ListenSessionState()
    host.request.codec, host.request.sample_rate = 'pcm16', 16000
    host.request.websocket.receive = AsyncMock(side_effect=asyncio.TimeoutError)
    host.limits = SimpleNamespace(ws_receive_timeout=1.0)
    host.is_multi_channel, host.use_custom_stt = False, True
    host.audio_bytes_send = None
    host.transcripts = SimpleNamespace(enqueue=lambda segments: None)
    host.start_live_transcription = lambda: None
    host.spawn = lambda coro, name=None: asyncio.create_task(coro, name=name)
    receiver = ListenReceiver(host, [], {})
    receiver.live_hold = custody
    custody.append(b'\1\0' * 8000, 16000, 100, 'conversation')
    await receiver.receive_data()
    assert host.state.close_code != 1011
    assert not custody.pending
    assert any(row.get('stage_pending') for row in store.docs.values())


async def test_standalone_journal_and_ambiguous_original_receipt_count_once(custody, store, delays, monkeypatch):
    custody.fragmented, custody.bound = False, 60
    original_upload = cap_hold.upload_held_audio
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=Forbidden('403')))
    custody.append(b'\1\0' * 8000, 16000, 100, 'conversation')
    await custody.flush(force=True)
    identity, row = next((key, row) for key, row in store.docs.items() if row.get('stage_pending'))
    assert not identity.startswith('late:')
    metadata = journal.json.loads(journal.decrypt(row['stage_metadata'], UID))
    source = Publication(UID, identity=identity)
    # A late original publisher observes the journal instead of counting a
    # second receipt. The journal stays recoverable through marker stamping.
    live_cap_manifest.publish(UID, '', source, metadata, 0.5)
    assert store.docs[identity]['stage_pending'] and 'summary' not in store.docs

    def recovered(uid, path, fragment_id, metadata, **kwargs):
        return original_upload(uid, path, fragment_id, metadata, immutable=True)

    monkeypatch.setattr(cap_hold, 'upload_held_audio', recovered)
    assert live_cap_staging.seal(UID, identity)
    assert not live_cap_staging.seal(UID, identity)
    assert store.docs['summary']['count'] == 1
    assert store.docs['summary']['seconds'] == 0.5


async def test_durable_audio_does_not_fail_close_for_quota_refund(custody, monkeypatch):
    custody.capacity = live.live_cap_capacity.Capacity(UID, '2026-10', 'reservation')
    monkeypatch.setattr(live.live_cap_capacity, 'release', Mock(side_effect=ServiceUnavailable('refund')))
    await custody.close()
    assert custody.host.state.close_code == 1000


async def test_journal_failure_at_bound_never_discards_owned_pcm(custody, monkeypatch):
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(side_effect=Forbidden('403')))
    monkeypatch.setattr(journal, 'defer', Mock(side_effect=ServiceUnavailable('journal')))
    custody.bound = 1
    custody.append(b'\1\0' * 16000, 16000, 100, 'conversation')
    with pytest.raises(live.StagingDeferred):
        await custody.append_async(b'\2\0' * 160, 16000, 101, 'conversation')
    assert custody.pending_bytes == 32000 and custody.buffered_seconds() == 1
