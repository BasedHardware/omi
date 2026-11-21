"""Local-preview leakage keeps durable original audio and a batch obligation."""

import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from google.api_core.exceptions import ServiceUnavailable

from config import server_batch
from utils.audio_timeline import CaptureTimeline
from config.batch_live_preview import capture_snapshot
from database import server_batch_audio
from routers.listen import receiver as receiver_module
from routers.listen import preview_custody
from routers.listen.receiver import ListenReceiver
from routers.listen.conversations import LiveConversationController
from database.listen_continuations import resolve_live_continuation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_durable_outbox import remote, host as archive_host
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.live import register_recording, record_identity
from utils.other import live_audio_archive
from utils.other.live_audio_archive import LiveAudioArchive

ROW = ('users', 'owner', 'conversations', 'conversation')


def capture(**updates):
    return {
        'id': 'conversation',
        'status': 'in_progress',
        'source': 'omi',
        'private_cloud_sync_enabled': True,
        'uses_custom_stt': False,
        'data_protection_level': 'standard',
        'language': 'en',
        'client_platform': 'ios',
        'transcript_segments': [],
        'external_data': {'unrelated': 'preserved'},
        **updates,
    }


def receiver():
    h = archive_host()
    h.request.language = 'auto'
    h.request.local_preview = True
    h.local_preview_batch = True
    h.request.onboarding_mode = False
    h.language = 'en'
    h.state = SimpleNamespace(current_conversation_id='conversation')
    h.server_batch_only = False
    h.use_custom_stt = False
    h.is_multi_channel = False
    h.pusher_enabled = True
    h.client_device_context = SimpleNamespace(platform='ios')
    h.server_batch_initialized = True
    h.language_profile = None
    r = object.__new__(ListenReceiver)
    r.host = h
    r.cloud_live_suppressed = True
    r._cloud_live_deferred_by = 'local_preview'
    r._stt_buffer_start_sample = 0
    r.raw_archive = LiveAudioArchive(h)
    r.initialize_stt = AsyncMock(return_value=False)
    return r


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv('LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED', raising=False)
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')


def bind_claim(monkeypatch, db):
    claim = Mock(
        side_effect=lambda uid, cid, **kw: server_batch_audio.claim_server_batch_lane(
            uid, cid, firestore_client=db, **kw
        )
    )
    monkeypatch.setattr(preview_custody, 'claim_server_batch_lane', claim)
    return claim


@pytest.mark.parametrize('owner', [None, 'batch_live_v1'])
def test_claim_transaction_preserves_metadata_and_is_idempotent(owner):
    db = StrictFirestore({ROW: capture(record_lane_owner=owner)})
    first = server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
    assert server_batch.owned(first)
    assert first['external_data']['unrelated'] == 'preserved'
    assert first['external_data'][server_batch.PREVIEW_CUSTODY_MARKER] is True
    assert first['language'] == 'multi'
    assert first['server_batch_audio_received'] is False
    db.rows[ROW]['server_batch_audio_received'] = True
    again = server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
    assert again['server_batch_audio_received'] is True and again['language'] == 'multi'
    assert len(db.transactions) == 2
    assert len(db.transactions[0].updates) == 1
    assert not db.transactions[1].updates


@pytest.mark.parametrize(
    'change',
    [
        None,
        {'deleted': True},
        {'discarded': True},
        {'is_locked': True},
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'data_protection_level': 'e2ee'},
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'status': 'completed'},
        {'status': 'processing'},
        {'source': 'phone_call'},
        {'external_data': {'onboarding_session_id': 'onboarding'}},
    ],
)
def test_claim_refuses_missing_privacy_and_ownership_races(change):
    db = StrictFirestore({} if change is None else {ROW: capture(**change)})
    before = dict(db.rows)
    assert (
        server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
        is None
    )
    assert db.rows == before and not db.transactions[0].updates


@pytest.mark.asyncio
async def test_promotion_clears_buffer_and_never_initializes_provider(monkeypatch):
    db = StrictFirestore({ROW: capture()})
    claim = bind_claim(monkeypatch, db)
    r = receiver()
    for _ in range(3):
        buffer = bytearray(b'\x00\x00' * 160)
        await r._flush_stt_buffer(buffer)
        assert not buffer and r._stt_buffer_start_sample is None
    assert r.host.server_batch_only and server_batch.owned(r.host.batch_record_capture)
    assert r.host.batch_record_capture['language'] == 'multi'  # Undeclared is never inferred English.
    assert claim.call_count == 1
    r.initialize_stt.assert_not_awaited()
    assert await r._connect_stt_socket(Mock(), 16000) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure',
    [
        'refused',
        'exception',
        'archive_disabled',
        'kill_switch',
        'off_mode',
        'unsupported_language',
        'consent_revoked',
        'preview_revoked',
    ],
)
async def test_failed_or_disabled_claim_keeps_deferred_live_open(monkeypatch, failure):
    r = receiver()
    claim = Mock(return_value=None, side_effect=RuntimeError('unavailable') if failure == 'exception' else None)
    monkeypatch.setattr(preview_custody, 'claim_server_batch_lane', claim)
    fallback = Mock()
    monkeypatch.setattr(preview_custody, 'record_fallback', fallback)
    if failure == 'preview_revoked':
        r.host.local_preview_batch = False
    elif failure == 'unsupported_language':
        r.host.request.websocket.query_params['language'] = 'zh'
        r.host.request.language = r.host.language = 'zh'
    elif failure == 'consent_revoked':
        r.host.private_cloud_sync_enabled = False
    elif failure == 'archive_disabled':
        r.raw_archive.durable = False
    elif failure == 'kill_switch':
        monkeypatch.setenv('LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED', 'false')
    elif failure == 'off_mode':
        r._cloud_live_deferred_by = 'off'
    buffer = bytearray(b'\x00\x00' * 160)
    await r._flush_stt_buffer(buffer)
    assert not r.host.server_batch_only and buffer
    r.initialize_stt.assert_awaited_once()
    assert claim.call_count == (failure in {'refused', 'exception'})
    assert fallback.call_count == (
        failure in {'refused', 'exception', 'archive_disabled', 'unsupported_language', 'consent_revoked'}
    )
    # Even a failed attempt is once per recording; a repeated deferred open cannot re-claim.
    r.cloud_live_suppressed = True
    await r._flush_stt_buffer(buffer)
    assert claim.call_count == (failure in {'refused', 'exception'})


@pytest.mark.asyncio
async def test_original_commit_registers_zero_live_record_and_reconnect_survives_rollback(remote, monkeypatch):
    db = StrictFirestore({ROW: capture()})
    bind_claim(monkeypatch, db)
    for name in ('note_server_batch_audio', 'note_server_batch_audio_received'):
        fn = getattr(server_batch_audio, name)
        monkeypatch.setattr(live_audio_archive, name, lambda *a, _fn=fn: _fn(*a, firestore_client=db))
    r = receiver()
    # Exercise the receive-loop ordering, including a first frame at the pack boundary.
    assert await preview_custody.claim_preview_batch_custody(r)
    packet = b'\x01\x00' * (60 * 16000)
    await r.raw_archive.append(packet, 'conversation', 1000, len(packet) // 2, decoded=packet)
    buffer = bytearray(packet)
    await r._flush_stt_buffer(buffer)
    await r.raw_archive.close()
    row = db.rows[ROW]
    assert row['has_content'] and row['server_batch_audio_received']
    assert row['server_batch_audio_start'] == 1000 and row['server_batch_audio_end'] == 1060
    assert not row['transcript_segments'] and not buffer
    assert remote.list_blobs('audio-outbox/')
    store = MemoryStore()
    assert register_recording('owner', row, store=store, now=1061)
    _, segment = record_identity('owner', 'conversation')
    job = store.rows['jobs', segment]
    assert job['state'] == 'record_pending'
    assert job['record_snapshot']['language'] == 'multi'
    assert job['record_snapshot']['server_batch_only'] is True
    monkeypatch.setenv('LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED', 'false')
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'false')
    reconnect = receiver()
    reconnect.host.server_batch_initialized = False
    reconnect.host.batch_record_capture = capture_snapshot(row)
    assert server_batch.capture_compatible(reconnect.host, row)
    assert server_batch.suppress_live(reconnect.host)
    assert await reconnect._initialize_stt()
    assert reconnect.host.server_batch_only
    reconnect.host.private_cloud_sync_enabled = False
    assert not server_batch.suppress_live(reconnect.host)


@pytest.mark.asyncio
async def test_auto_preview_continuation_lookup_loads_and_validates_durable_owner(monkeypatch):
    now = datetime.now(timezone.utc)
    db = StrictFirestore({ROW: capture(client_device_id=None, finished_at=now)})
    row = server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
    root = ('users', 'owner', 'recording_sessions', 'origin')
    pointer = {'conversation_id': 'conversation', 'recording_session_id': 'session'}
    db.rows[root] = {
        'uid': 'owner',
        'recording_session_id': 'origin',
        'conversation_id': 'conversation',
        'live_continuation': pointer,
    }
    r = receiver()
    h = r.host
    h.server_batch_initialized = False
    h.client_conversation_id = 'origin'
    h.client_device_context.client_device_id = None
    h.conversation_creation_timeout = 120

    # This exercises the controller's pre-load permission, not a manually granted bool.
    async def persistence_call(fn, *args, **kwargs):
        assert kwargs['allow_server_batch'] is True
        result, _ = resolve_live_continuation(*args, **kwargs, firestore_client=db)
        return result

    h.persistence = SimpleNamespace(call=persistence_call)
    controller = SimpleNamespace(host=h, clock=lambda: now)
    assert await LiveConversationController._continuation(controller) == pointer
    assert server_batch.capture_compatible(h, row)
    # Lookup permission cannot admit an ordinary profile-gated batch row or wrong language.
    ordinary = {**row, 'external_data': {'server_batch_only': True}}
    assert not server_batch.capture_compatible(h, ordinary)
    h.request.websocket.query_params['language'] = 'es'
    h.request.language = 'es'
    assert not server_batch.capture_compatible(h, row)


@pytest.mark.parametrize(('lost_replies', 'wrapped'), [(1, False), (3, False), (3, True)])
def test_ambiguous_claim_commit_rereads_without_resetting_received(monkeypatch, lost_replies, wrapped):
    db = StrictFirestore({ROW: capture()})
    calls = []

    def transactional(fn):
        def commit_then_lose_reply(transaction):
            result = fn(transaction)
            calls.append(result)
            if len(calls) <= lost_replies:
                db.rows[ROW]['server_batch_audio_received'] = True
                error = ServiceUnavailable('commit reply lost')
                if wrapped:
                    raise ValueError('SDK retry exhausted') from error
                raise error
            return result

        return commit_then_lose_reply

    monkeypatch.setattr(server_batch_audio.firestore, 'transactional', transactional)
    row = server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
    assert len(calls) == min(lost_replies + 1, 3) and server_batch.owned(row)
    assert row['server_batch_audio_received'] is True
    assert len(db.transactions[0].updates) == 1 and not db.transactions[1].updates


def receiving(packet, monkeypatch):
    r = receiver()
    h = r.host
    h.request.websocket.receive = AsyncMock(
        side_effect=[{'bytes': packet}, {'type': 'websocket.disconnect', 'code': 1000}]
    )
    h.audio_bytes_send = None
    h.limits = SimpleNamespace(ws_receive_timeout=1)
    h.state.active = True
    h.state.last_usage_record_timestamp = None
    h.state.source_position_map = None
    r.capture_timeline = CaptureTimeline(sample_rate=16000)
    r._pending_source_frame = None
    r.recovery_enabled = False
    r.recovery = None
    r.live_hold = None
    r.stt_socket = None
    r.stt_drain_complete = asyncio.Event()
    r._note_audio_activity = Mock()
    r._mark_first_audio = Mock()
    r._capture = Mock()
    r._note_accepted_frame = Mock()
    r._write_ring_buffer_frame = Mock()
    r._teardown_body = AsyncMock()
    monkeypatch.setattr(receiver_module.edge_shadow, 'session_mirror', lambda receiver: None)
    return r


@pytest.mark.asyncio
async def test_receive_claims_before_first_pack_commit_and_never_dials(remote, monkeypatch):
    db = StrictFirestore({ROW: capture()})
    claim = bind_claim(monkeypatch, db)
    for name in ('note_server_batch_audio', 'note_server_batch_audio_received'):
        fn = getattr(server_batch_audio, name)
        monkeypatch.setattr(live_audio_archive, name, lambda *a, _fn=fn: _fn(*a, firestore_client=db))
    packet = b'\x01\x00' * (60 * 16000)
    r = receiving(packet, monkeypatch)
    h = r.host
    append = r.raw_archive.append

    async def append_after_claim(*args, **kwargs):
        assert server_batch.owned(db.rows[ROW]), 'first frame cannot commit before its batch owner exists'
        await append(*args, **kwargs)

    r.raw_archive.append = append_after_claim
    await r.receive_data()
    assert h.state.close_code == 1000 and not h.state.active
    assert db.rows[ROW]['has_content']
    assert db.rows[ROW]['server_batch_audio_end'] - db.rows[ROW]['server_batch_audio_start'] == 60
    assert len(remote.list_blobs('audio-outbox/')) > 0
    assert claim.call_count == 1
    r.initialize_stt.assert_not_awaited()
    r._teardown_body.assert_awaited_once()
    assert not r._teardown_body.await_args.args[0]  # No residual forwarding buffer.


def test_claim_cannot_adopt_a_concurrent_incompatible_language():
    row = capture(record_lane_owner='batch_live_v1', language='es', external_data={'server_batch_only': True})
    db = StrictFirestore({ROW: row})
    assert (
        server_batch_audio.claim_server_batch_lane('owner', 'conversation', language='multi', firestore_client=db)
        is None
    )
    assert db.rows[ROW] == row and not db.transactions[0].updates


@pytest.mark.asyncio
@pytest.mark.parametrize('cancellations', [1, 2])
async def test_cancelled_claim_finishes_first_frame_custody_before_teardown(remote, monkeypatch, cancellations):
    db = StrictFirestore({ROW: capture()})
    for name in ('note_server_batch_audio', 'note_server_batch_audio_received'):
        fn = getattr(server_batch_audio, name)
        monkeypatch.setattr(live_audio_archive, name, lambda *a, _fn=fn: _fn(*a, firestore_client=db))
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def claim(uid, cid, **kwargs):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(3), 'test must release its Firestore worker'
        return server_batch_audio.claim_server_batch_lane(uid, cid, firestore_client=db, **kwargs)

    monkeypatch.setattr(preview_custody, 'claim_server_batch_lane', claim)
    packet = b'\x01\x00' * 160
    r = receiving(packet, monkeypatch)

    async def teardown(buffer, decoded_bytes):
        assert decoded_bytes == len(packet) and bytes(buffer) == packet
        await r._flush_stt_buffer(buffer, force=True)
        assert not buffer

    r._teardown_body.side_effect = teardown
    task = asyncio.create_task(r.receive_data())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        for _ in range(cancellations):
            task.cancel()
            await asyncio.sleep(0)
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=3)
    row = db.rows[ROW]
    assert row['has_content'] and server_batch.owned(row)
    assert row['server_batch_audio_end'] - row['server_batch_audio_start'] == pytest.approx(0.01, abs=1e-6)
    assert remote.list_blobs('audio-outbox/')
    assert register_recording('owner', row, store=MemoryStore())
    r.initialize_stt.assert_not_awaited()
    r._teardown_body.assert_awaited_once()
