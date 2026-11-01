"""Desktop no-live admission, immutable custody and durable batch handoff."""

import asyncio
import json
import struct
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import server_batch
from config.policy import resolve_batch_policy
from config.batch_live_preview import capture_snapshot
from database.batch_pipeline_projection import ProjectionStore
from database import conversations, recording_sessions, server_batch_audio
from models.conversation_enums import ConversationStatus
from routers.listen import receiver as receiver_module
from routers.listen.receiver import ListenReceiver
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_durable_outbox import remote, Socket, _window_harness, _sent_receipts, host as archive_host
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.live import register_recording, record_identity
from utils.conversations import finalizer, lifecycle
from utils.other import live_audio_archive
from utils.other.audio_outbox import AudioReceipt, read_pcm
from utils.other.live_audio_archive import LiveAudioArchive
import routers.pusher as pusher

from database import llm_usage
from database.listen_continuations import resolve_live_continuation
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.test_recording_sessions import _FakeFirestore, _DocumentRef, _CollectionRef
from utils import fair_use
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.projection import record_speech

ROW = ('users', 'owner', 'conversations', 'conversation')


def capture(**changes):
    return dict(
        id='conversation',
        source='desktop',
        client_platform='macos',
        language='en',
        private_cloud_sync_enabled=True,
        uses_custom_stt=False,
        data_protection_level='standard',
        record_lane_owner='batch_live_v1',
        external_data={server_batch.MARKER: True},
        status='in_progress',
        transcript_segments=[],
        server_batch_audio_received=False,
        **changes,
    )


def host(row=None):
    return SimpleNamespace(
        request=SimpleNamespace(uid='owner', source='desktop', language='en', onboarding_mode=False),
        batch_record_capture=capture_snapshot(row or capture()),
        private_cloud_sync_enabled=True,
        use_custom_stt=False,
        is_multi_channel=False,
        pusher_enabled=True,
        language='en',
        language_profile=SimpleNamespace(primary='en', expected=('en',)),
    )


@pytest.fixture(autouse=True)
def policy_env(monkeypatch):
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', '')
    monkeypatch.delenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_PLATFORMS', raising=False)


@pytest.mark.parametrize(
    'change',
    [
        {'source': 'omi'},
        {'source': 'phone_call'},
        {'client_platform': 'ios'},
        {'uses_custom_stt': True},
        {'private_cloud_sync_enabled': False},
        {'data_protection_level': 'e2ee'},
        {'language': 'multi'},
        {'language': 'auto'},
        {'language': ''},
        {'language': 'zh'},
        {'deleted': True},
    ],
)
def test_admission_preserves_other_sessions_and_languages(change):
    assert server_batch.eligible(capture(), 'owner')
    row = capture()
    row.update(change)
    assert not server_batch.eligible(row, 'owner')


@pytest.mark.parametrize('raw', ['false', '0', 'OFF', 'no'])
def test_kill_switch_restores_new_live_but_keeps_reserved_capture_provider_free(monkeypatch, raw):
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', raw)
    assert not server_batch.eligible(capture(), 'owner')
    assert server_batch.suppress_live(host())
    assert not server_batch.request_eligible(host())
    assert server_batch.owned(capture())


def test_reservation_is_durable_before_provider_admission_without_mobile_cohort(monkeypatch):
    row = capture()
    row.pop('record_lane_owner')
    row['external_data'] = {}
    persist = Mock()
    monkeypatch.setattr(lifecycle.conversations_db, 'upsert_conversation_with_lifecycle', persist)
    assert lifecycle.create_in_progress_conversation('owner', row, server_batch_requested=True)
    assert server_batch.owned(row)
    assert server_batch.suppress_live(host(row))
    persist.assert_called_once_with('owner', row)


@pytest.mark.parametrize(
    'platform,source,expected',
    [
        ('macos', 'desktop', True),
        ('windows', 'desktop', True),
        ('linux', 'desktop', False),
        ('ios', 'phone', False),
        ('android', 'omi', False),
        ('web', 'desktop', False),
        ('macos', 'phone_call', False),
    ],
)
def test_platform_defaults(platform, source, expected):
    row = capture()
    row.update(client_platform=platform, source=source)
    assert server_batch.eligible(row, 'owner') is expected


def test_validated_provider_byok_keeps_live_even_on_reserved_reconnect():
    h = host()
    h.server_batch_byok = True
    assert not server_batch.request_eligible(h)
    assert not server_batch.suppress_live(h)


@pytest.mark.parametrize(
    'profile',
    [None, SimpleNamespace(primary='en', expected=('en', 'zh')), SimpleNamespace(primary='es', expected=('es',))],
)
def test_unknown_or_unqualified_language_profile_preserves_live(profile):
    h = host()
    h.language_profile = profile
    assert not server_batch.request_eligible(h)
    assert not server_batch.suppress_live(h)


def test_admitted_socket_rollover_survives_mobile_cohort_rollback(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '100')
    h = host()
    h.request.source = 'omi'
    h.client_device_context = SimpleNamespace(platform='ios')
    h.server_batch_initialized = True
    h.server_batch_only = False
    assert not server_batch.request_eligible(h)  # No mid-socket conversion of a live control.
    h.server_batch_only = True
    assert server_batch.request_eligible(h)
    row = capture()
    row.update(source='omi', client_platform='ios', external_data={})
    row.pop('record_lane_owner')
    monkeypatch.setattr(lifecycle.conversations_db, 'upsert_conversation_with_lifecycle', Mock())
    assert lifecycle.create_in_progress_conversation(
        'owner', row, server_batch_requested=True, server_batch_continuation=True
    )
    assert server_batch.owned(row)  # BATCH_PIPELINE_ENABLED is false: this is a prior admission's continuation.


@pytest.mark.parametrize('platform', ['ios', 'android'])
def test_mobile_percent_is_nested_in_actual_batch_admission(monkeypatch, platform):
    row = capture()
    row.update(client_platform=platform, source='omi')

    def admitted(owner):
        return server_batch.eligible(row, owner, batch_admitted=resolve_batch_policy(owner).batch_enabled)

    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '100')
    assert not admitted('owner')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    assert admitted('owner')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', 'bad')
    assert not admitted('owner')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '50')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '25')
    for index in range(100):
        owner = f'synthetic-{index}'
        assert not admitted(owner) or resolve_batch_policy(owner).batch_enabled


@pytest.mark.parametrize(
    'change,expected',
    [
        ({}, True),
        ({'private_cloud_sync_enabled': False}, False),
        ({'uses_custom_stt': True}, False),
        ({'deleted': True}, False),
        ({'record_lane_owner': 'legacy_final_pass_v1'}, False),
    ],
)
def test_completion_cas_retains_empty_transcript_and_fences_privacy_races(monkeypatch, change, expected):
    admitted = capture()
    admitted['status'] = 'processing'
    current = {**admitted, **change}
    db = StrictFirestore({ROW: current})
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'stop_quiet_check_for_conversation', Mock())
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', Mock())
    monkeypatch.setattr(conversations, 'serving_for', lambda *args: False)
    assert lifecycle.complete_server_batch_capture('owner', 'conversation', admitted) is expected
    assert db.rows[ROW]['status'] == ('completed' if expected else 'processing')
    assert db.rows[ROW]['transcript_segments'] == []


@pytest.mark.asyncio
async def test_no_provider_for_whole_session_reinit_reconnect_and_idle_reopen(monkeypatch):
    h = host()
    fake = SimpleNamespace(host=h, cloud_live_suppressed=False)
    monkeypatch.setattr(
        receiver_module, 'capture_batch_preview', Mock(side_effect=AssertionError('provider selection'))
    )
    for _ in range(3):
        assert await ListenReceiver._initialize_stt(fake)
        assert h.server_batch_only
        for packet in (b'\x01\x00' * 160, b'\x00\x00' * 160):
            buffer = bytearray(packet)
            await ListenReceiver._flush_stt_buffer(fake, buffer, force=True)
            assert buffer == b''
        assert await ListenReceiver._open_deferred_stream(fake)
        for same_provider in (False, True):
            assert await ListenReceiver._connect_stt_socket(fake, Mock(), 16000, same_provider=same_provider) is None
    # A new receiver after client reconnect consumes the persisted admission.
    reconnect = SimpleNamespace(host=host(capture()), cloud_live_suppressed=False)
    assert await ListenReceiver._initialize_stt(reconnect)
    assert reconnect.host.server_batch_only


@pytest.mark.asyncio
@pytest.mark.parametrize('consent', [True, False])
async def test_disabled_policy_passes_exact_audio_to_existing_flush(monkeypatch, consent):
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'false')
    h = host()
    h.batch_record_capture = None
    h.private_cloud_sync_enabled = consent
    h.server_batch_only = server_batch.suppress_live(h)
    fake = SimpleNamespace(host=h, cloud_live_suppressed=False)
    seen = []

    async def legacy(receiver, buffer, *, force):
        seen.append(bytes(buffer))

    monkeypatch.setattr(receiver_module.legacy_recovery, 'flush_stt_buffer', legacy)
    packet = bytes(range(256)) * 4
    await ListenReceiver._flush_stt_buffer(fake, bytearray(packet), force=True)
    assert seen == [packet]


@pytest.mark.asyncio
async def test_desktop_pcm_every_frame_commits_at_real_pusher_custody_boundary(remote, monkeypatch):
    _window_harness(remote, monkeypatch)
    # No transcript opcode is sent. Both speech-shaped samples and PCM silence count.
    payloads = [struct.pack('<160h', *[n] * 160) for n in range(30)]
    sock = Socket(
        [
            struct.pack('<I', 103) + b'conversation',
            *(struct.pack('<Id', 101, 1000 + n * 0.01) + pcm for n, pcm in enumerate(payloads)),
        ]
    )
    await pusher._websocket_util_trigger(sock, 'owner', 16000, client_kind='macos', audio_custody=1)
    receipts = _sent_receipts(sock)
    persisted = b''.join(read_pcm('owner', receipt) for receipt in receipts)
    assert persisted == b''.join(payloads)
    assert len(persisted) == sum(map(len, payloads))
    frames = [frame for receipt in receipts for frame in json.loads(remote.blob(receipt.manifest_path).data)['frames']]
    assert len(frames) == len(payloads)


@pytest.mark.asyncio
async def test_original_commit_keeps_zero_live_conversation_and_exact_capture_bounds(remote, monkeypatch):
    db = StrictFirestore({ROW: capture()})
    h = archive_host()
    h.server_batch_only = True
    archive = LiveAudioArchive(h)
    order = []

    def note(owner, conversation, start, end):
        assert remote.list_blobs('raw-live/') and remote.list_blobs('audio-outbox/')
        order.append('committed')
        return server_batch_audio.note_server_batch_audio(owner, conversation, start, end, firestore_client=db)

    monkeypatch.setattr(live_audio_archive, 'note_server_batch_audio', note)
    monkeypatch.setattr(
        live_audio_archive,
        'note_server_batch_audio_received',
        lambda owner, conversation: server_batch_audio.note_server_batch_audio_received(
            owner, conversation, firestore_client=db
        ),
    )
    packet = b'\x00\x00' * 160
    await archive.append(packet, 'conversation', 1000, 160, decoded=packet)
    assert 'has_content' not in db.rows[ROW]
    await archive.close()
    row = db.rows[ROW]
    assert order == ['committed'] and row['has_content'] and not row['transcript_segments']
    assert row['started_at'].timestamp() == 1000
    assert row['finished_at'].timestamp() == 1000.01
    assert server_batch_audio.note_server_batch_audio('owner', 'conversation', 1001, 1002, firestore_client=db)
    assert server_batch_audio.note_server_batch_audio('owner', 'conversation', 999, 1000, firestore_client=db)
    assert db.rows[ROW]['started_at'].timestamp() == 999
    assert db.rows[ROW]['finished_at'].timestamp() == 1002
    assert not recording_sessions.tombstone_and_delete_empty_conversation(
        'owner', 'conversation', None, firestore_client=db
    )


@pytest.mark.asyncio
async def test_zero_sample_original_keeps_custody_without_poisoning_later_capture(remote, monkeypatch):
    h = archive_host()
    h.request.codec = 'opus'
    h.server_batch_only = True
    note = Mock(side_effect=AssertionError('zero-sample bounds are unknowable'))
    monkeypatch.setattr(live_audio_archive, 'note_server_batch_audio', note)
    monkeypatch.setattr(live_audio_archive, 'note_server_batch_audio_received', lambda *a: True)
    archive = LiveAudioArchive(h)
    await archive.append(b'undecodable-original', 'conversation', 1000, 0)
    await archive.close()
    note.assert_not_called()
    assert not archive.failed and not archive.uncommitted
    assert remote.list_blobs('raw-live/') and remote.list_blobs('audio-outbox/')
    assert h.events and h.events[0].receipt['samples'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('zero_times', [(), (999,), (1002,), (999, 1002), (1000.5,)])
async def test_zero_sample_packets_do_not_expand_or_shrink_batch_span(remote, monkeypatch, zero_times):
    db = StrictFirestore({ROW: capture()})
    h = archive_host()
    h.server_batch_only = True
    archive = LiveAudioArchive(h)
    monkeypatch.setattr(
        live_audio_archive,
        'note_server_batch_audio_received',
        lambda owner, conversation: server_batch_audio.note_server_batch_audio_received(
            owner, conversation, firestore_client=db
        ),
    )
    monkeypatch.setattr(
        live_audio_archive,
        'note_server_batch_audio',
        lambda owner, conversation, start, end: server_batch_audio.note_server_batch_audio(
            owner, conversation, start, end, firestore_client=db
        ),
    )
    packet = b'\x01\x00' * 16000
    originals = []
    for timestamp in zero_times:
        if timestamp < 1000:
            await archive.append(b'\xff', 'conversation', timestamp, 0)
            originals.append(b'\xff')
    await archive.append(packet, 'conversation', 1000, 16000, decoded=packet)
    originals.append(packet)
    for timestamp in zero_times:
        if timestamp >= 1000:
            await archive.append(b'\xff', 'conversation', timestamp, 0)
            originals.append(b'\xff')
    await archive.close()
    receipt = AudioReceipt(**h.events[0].receipt)
    assert remote.blob(receipt.path).data == b''.join(originals)
    manifest = json.loads(remote.blob(receipt.manifest_path).data)
    assert len(manifest['frames']) == len(originals)
    assert sum(frame['samples'] for frame in manifest['frames']) == 16000
    assert sum(frame['bytes'] for frame in manifest['frames']) == len(b''.join(originals))
    row = db.rows[ROW]
    assert row['server_batch_audio_start'] == row['started_at'].timestamp() == 1000
    assert row['server_batch_audio_end'] == row['finished_at'].timestamp() == 1001
    store = MemoryStore()
    assert register_recording('owner', row, store=store, now=1002)
    _, segment = record_identity('owner', 'conversation')
    snapshot = store.rows['jobs', segment]['record_snapshot']
    assert snapshot['started_at'].timestamp() == 1000
    assert snapshot['finished_at'].timestamp() == 1001


@pytest.mark.asyncio
async def test_first_audio_marker_failure_keeps_buffered_original_for_shutdown_commit(remote, monkeypatch):
    h = archive_host()
    h.server_batch_only = True
    monkeypatch.setattr(
        live_audio_archive, 'note_server_batch_audio_received', Mock(side_effect=RuntimeError('metadata unavailable'))
    )
    monkeypatch.setattr(live_audio_archive, 'note_server_batch_audio', lambda *a: True)
    archive = LiveAudioArchive(h)
    packet = b'\x01\x00' * 160
    with pytest.raises(RuntimeError, match='metadata unavailable'):
        await archive.append(packet, 'conversation', 1000, 160, decoded=packet)
    assert bytes(archive.packs[0].data) == packet
    await archive.close()
    assert not archive.uncommitted
    receipt = AudioReceipt(**h.events[0].receipt)
    assert read_pcm('owner', receipt) == packet


@pytest.mark.asyncio
async def test_zero_preview_finalizer_registers_exact_language_bounds_before_completion(monkeypatch):
    row = capture()
    row.update(
        status='processing',
        started_at=datetime.fromtimestamp(1000, timezone.utc),
        finished_at=datetime.fromtimestamp(1002, timezone.utc),
        language='es',
        has_content=True,
        server_batch_audio_start=1000,
        server_batch_audio_end=1002,
    )
    store = MemoryStore()
    model = SimpleNamespace(status=ConversationStatus.processing, transcript_segments=[])
    monkeypatch.setattr(finalizer, '_load_admitted_conversation', AsyncMock(return_value=(None, row, model)))
    monkeypatch.setattr(
        finalizer, 'register_recording', lambda owner, data: register_recording(owner, data, store=store, now=1)
    )

    def complete(*args):
        pending = store.rows['jobs', record_identity('owner', 'conversation')[1]]
        assert pending['state'] == 'record_pending'
        assert pending['record_snapshot']['language'] == 'es'
        assert pending['record_snapshot']['started_at'].timestamp() == 1000
        assert pending['record_snapshot']['finished_at'].timestamp() == 1002
        return True

    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_server_batch_capture', complete)
    monkeypatch.setattr(finalizer.lifecycle_service, 'claim_finalization_fanout', lambda *args: {'status': 'claimed'})
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', lambda *args: True)
    monkeypatch.setattr(
        finalizer, '_episode_at_finalization_start', AsyncMock(side_effect=AssertionError('preview work'))
    )
    result = await finalizer.finalize_persisted_conversation(
        'owner', 'conversation', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
    )
    assert result is finalizer.ConversationFinalizationDisposition.completed


@pytest.mark.asyncio
async def test_closed_empty_capture_never_registers_pending_batch(monkeypatch):
    row = capture(server_batch_audio_closed=True)
    row['status'] = 'processing'
    model = SimpleNamespace(status=ConversationStatus.processing, transcript_segments=[])
    monkeypatch.setattr(finalizer, '_load_admitted_conversation', AsyncMock(return_value=(None, row, model)))
    register = Mock(side_effect=AssertionError('no batch input'))
    cleanup = Mock(return_value=True)
    monkeypatch.setattr(finalizer, 'register_recording', register)
    monkeypatch.setattr(finalizer.lifecycle_service, 'delete_empty_recording_conversation', cleanup)
    result = await finalizer.finalize_persisted_conversation(
        'owner', 'conversation', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
    )
    assert result is finalizer.ConversationFinalizationDisposition.fenced
    register.assert_not_called()
    cleanup.assert_called_once_with('owner', 'conversation', None, allow_empty_server_batch=True)


@pytest.mark.asyncio
async def test_unclosed_empty_capture_cannot_delete_or_enqueue(monkeypatch):
    row = capture()
    row['status'] = 'processing'
    model = SimpleNamespace(status=ConversationStatus.processing, transcript_segments=[])
    monkeypatch.setattr(finalizer, '_load_admitted_conversation', AsyncMock(return_value=(None, row, model)))
    register, cleanup = Mock(), Mock()
    monkeypatch.setattr(finalizer, 'register_recording', register)
    monkeypatch.setattr(finalizer.lifecycle_service, 'delete_empty_recording_conversation', cleanup)
    with pytest.raises(RuntimeError, match='archive is not closed'):
        await finalizer.finalize_persisted_conversation(
            'owner', 'conversation', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
        )
    register.assert_not_called()
    cleanup.assert_not_called()


@pytest.mark.parametrize('photos', [[], [{'description': 'synthetic photo'}]])
def test_no_audio_server_capture_cannot_register_batch_even_from_another_caller(photos):
    store = MemoryStore()
    row = capture()
    row['photos'] = photos
    assert not register_recording('owner', row, store=store, now=1)
    assert not store.rows


@pytest.mark.asyncio
@pytest.mark.parametrize('active', [False, True])
async def test_real_controller_closes_empty_archive_and_only_removes_inactive_no_input_generation(monkeypatch, active):

    db = _FakeFirestore({ROW: capture()})
    monkeypatch.setattr(recording_sessions.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recording_sessions, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(server_batch_audio, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a, **kw: db.documents.get(ROW))
    monkeypatch.setattr(conversations, 'delete_conversation_photos', lambda *a: None)
    erase = Mock()
    monkeypatch.setattr(lifecycle, 'delete_conversation_audio_files', erase)
    h = host()
    h.state = SimpleNamespace(current_conversation_id='conversation', first_audio_byte_timestamp=None, active=active)
    h.recording_session_ids_by_conversation = {}
    h.receiver = SimpleNamespace(raw_archive=LiveAudioArchive(h))

    async def call(fn, *args, **kwargs):
        kwargs.pop('read_site', None)
        return fn(*args, **kwargs)

    h.persistence = SimpleNamespace(call=call)
    controller = LiveConversationController(h)
    controller.schedule_finalization = AsyncMock()
    assert await controller.process_conversation('conversation') is (not active)
    assert (ROW in db.documents) is active
    controller.schedule_finalization.assert_not_awaited()
    erase.assert_not_called()


@pytest.mark.asyncio
async def test_late_first_frame_after_close_cannot_delete_capture_before_commit(remote, monkeypatch):

    db = _FakeFirestore({ROW: capture()})
    monkeypatch.setattr(recording_sessions.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recording_sessions, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(server_batch_audio, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a, **kw: db.documents.get(ROW))
    monkeypatch.setattr(conversations, 'delete_conversation_photos', lambda *a: None)
    monkeypatch.setattr(lifecycle, 'delete_conversation_audio_files', Mock())
    h = archive_host()
    h.server_batch_only = True
    h.state = SimpleNamespace(current_conversation_id='conversation', first_audio_byte_timestamp=None, active=True)
    h.recording_session_ids_by_conversation = {}
    archive = LiveAudioArchive(h)
    h.receiver = SimpleNamespace(raw_archive=archive)
    close = archive.close
    packet = b'\x00\x00' * 160

    async def close_then_receive():
        await close()
        await archive.append(packet, 'conversation', 1000, 160, decoded=packet)

    archive.close = close_then_receive

    async def call(fn, *args, **kwargs):
        kwargs.pop('read_site', None)
        return fn(*args, **kwargs)

    h.persistence = SimpleNamespace(call=call)
    controller = LiveConversationController(h)
    controller.schedule_finalization = AsyncMock(return_value=True)
    assert not await controller.process_conversation('conversation')
    assert db.documents[ROW]['server_batch_audio_received'] is True
    controller.schedule_finalization.assert_not_awaited()
    await close()
    assert db.documents[ROW]['server_batch_audio_start'] == 1000
    assert db.documents[ROW]['server_batch_audio_end'] == 1000.01
    receipts = [AudioReceipt(**event.receipt) for event in h.events]
    assert b''.join(read_pcm('owner', receipt) for receipt in receipts) == packet
    archive.close = close
    h.state.active = False
    assert await controller.process_conversation('conversation')
    controller.schedule_finalization.assert_awaited_once_with('conversation')


@pytest.mark.asyncio
async def test_photo_only_capture_keeps_ordinary_photo_finalization(monkeypatch):
    row = capture(server_batch_audio_closed=True)
    row.update(status='processing', photos=[{'description': 'synthetic photo'}], has_content=True)
    model = SimpleNamespace(status=ConversationStatus.processing, transcript_segments=[], photos=row['photos'])
    monkeypatch.setattr(finalizer, '_load_admitted_conversation', AsyncMock(return_value=(None, row, model)))
    ordinary = AsyncMock(side_effect=ValueError('ordinary photo pipeline'))
    cleanup = Mock()
    monkeypatch.setattr(finalizer, '_episode_at_finalization_start', ordinary)
    monkeypatch.setattr(finalizer.lifecycle_service, 'delete_empty_recording_conversation', cleanup)
    with pytest.raises(ValueError, match='ordinary photo pipeline'):
        await finalizer.finalize_persisted_conversation(
            'owner', 'conversation', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
        )
    ordinary.assert_awaited_once()
    cleanup.assert_not_called()


def test_archive_close_barrier_requires_owned_existing_capture():
    db = StrictFirestore({ROW: capture()})
    assert server_batch_audio.close_server_batch_audio('owner', 'conversation', firestore_client=db)
    assert db.rows[ROW]['server_batch_audio_closed'] is True
    db.rows[ROW]['deleted'] = True
    assert not server_batch_audio.close_server_batch_audio('owner', 'conversation', firestore_client=db)


@pytest.mark.parametrize('received', [True, False])
def test_empty_server_batch_display_cleanup_never_erases_original_custody(monkeypatch, received):
    erase = Mock()
    monkeypatch.setattr(lifecycle, 'delete_conversation_audio_files', erase)
    row = capture()
    row.update(server_batch_audio_received=received, server_batch_audio_closed=True)
    lifecycle._discard_unreferenced_audio('owner', 'conversation', row)
    erase.assert_not_called()


@pytest.mark.parametrize('received', [False, True, None])
@pytest.mark.parametrize('expired', [True, False])
def test_lease_cleanup_requires_proven_no_audio_and_expired_bound_session(monkeypatch, received, expired):

    monkeypatch.setattr(
        _DocumentRef, 'parent', property(lambda r: _CollectionRef(r.firestore, r.path[:-1])), raising=False
    )
    monkeypatch.setattr(
        _CollectionRef, 'parent', property(lambda r: _DocumentRef(r.firestore, r.path[:-1])), raising=False
    )
    now = datetime.now(timezone.utc)
    row = capture()
    row.update(finished_at=now - timedelta(minutes=10), server_batch_audio_received=received)
    row['external_data']['recording_session_id'] = 'session'
    session = {
        'uid': 'owner',
        'conversation_id': 'conversation',
        'recording_session_id': 'session',
        'lifecycle_phase': 'in_progress',
        'lease_expires_at': now + timedelta(seconds=-1 if expired else 1),
    }
    db = _FakeFirestore({ROW: row, ('users', 'owner', 'recording_sessions', 'session'): session})
    monkeypatch.setattr(recording_sessions.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recording_sessions, '_now', lambda: now)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    removed = recording_sessions.tombstone_and_delete_empty_conversation(
        'owner',
        'conversation',
        'session',
        firestore_client=db,
        recovery_cutoff=now - timedelta(minutes=2),
        require_expired_recording_lease=True,
    )
    assert removed is (received is False and expired)
    assert (ROW not in db.documents) is removed


def test_reserved_capture_language_must_match_reconnecting_request():
    row = capture()
    row['language'] = 'es'
    assert not server_batch.suppress_live(host(row))


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['language', 'byok', 'consent'])
async def test_legacy_resume_rolls_incompatible_policy_into_fresh_capture(change):
    row = capture()
    if change == 'language':
        row['language'] = 'es'
    h = host(row)
    if change == 'byok':
        h.server_batch_byok = True
    elif change == 'consent':
        h.private_cloud_sync_enabled = False
    h.client_conversation_id = None
    h.client_device_context = SimpleNamespace(client_device_id=None)
    h._policy_resume_candidate = row
    h.persistence = SimpleNamespace(call=AsyncMock(side_effect=AssertionError('must roll over before binding')))
    controller = LiveConversationController(h)
    controller.create_new_in_progress_conversation = AsyncMock()
    await controller.prepare()
    controller.create_new_in_progress_conversation.assert_awaited_once_with(rollover=True)


@pytest.mark.parametrize('change', ['language', 'byok'])
def test_incompatible_policy_replaces_continuation_pointer_without_rebinding_original(change):

    now = datetime.now(timezone.utc)
    old = {
        **capture(),
        'language': 'es' if change == 'language' else 'en',
        'client_device_id': None,
        'finished_at': now,
    }
    new = {**capture(), 'id': 'new', 'client_device_id': None, 'finished_at': now}
    if change == 'byok':
        new['external_data'] = {}
        new.pop('record_lane_owner')
    root = ('users', 'owner', 'recording_sessions', 'origin')
    original = {'uid': 'owner', 'recording_session_id': 'origin', 'conversation_id': 'conversation'}
    original['live_continuation'] = {'conversation_id': 'conversation', 'recording_session_id': 'original-session'}
    db = StrictFirestore({ROW: old, ('users', 'owner', 'conversations', 'new'): new, root: original})
    pointer, retired = resolve_live_continuation(
        'owner',
        'origin',
        source='desktop',
        device_id=None,
        now=now,
        timeout=120,
        language='en',
        allow_server_batch=change != 'byok',
        proposed={'conversation_id': 'new', 'recording_session_id': 'new-session'},
        firestore_client=db,
    )
    assert pointer == {'conversation_id': 'new', 'recording_session_id': 'new-session'}
    assert retired is None
    assert db.rows[root]['conversation_id'] == 'conversation'
    assert db.rows[ROW]['language'] == old['language']


@pytest.mark.parametrize('server_only', [True, False])
def test_batch_accounting_replaces_live_charge_only_for_server_only_capture(monkeypatch, server_only):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')

    binding = ProjectionBinding('owner', 'job', 'content', ('unit',), native_record=True)
    db = StrictFirestore(
        {
            ('test_results', 'unit'): {'projection': {'state': 'ready', 'speech_seconds': 3.5}},
            ('test_jobs', 'unit'): {'priority': 0},
            ('test_intakes', 'job'): {'server_batch_only': server_only},
        }
    )
    store = ProjectionStore(SimpleNamespace(client=db, namespace='test'))
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *a, **kw: 'synthetic')
    speech = Mock()
    monkeypatch.setattr(fair_use, 'record_speech_ms', speech)
    accounting = store.prepare_accounting(binding, 1000)
    assert accounting['completed'] is not server_only
    if not server_only:
        assert accounting['updates'] == {}
        record_speech(binding, accounting, 1000)
        speech.assert_not_called()
        return
    assert accounting['updates']['transcription_seconds'].value == 3
    assert accounting['updates']['speech_seconds'].value == 3
    record_speech(binding, accounting, 1000)
    assert speech.call_args.args == ('owner', 3500)
    assert speech.call_args.kwargs['idempotency_key'] == binding.content_id

    # Exercise the actual hourly/monthly writer and its existing once-ledger fence.
    ledger_ref = sync_content_ledger_ref(db, 'owner', 'content')
    db.rows[ledger_ref.path] = {}
    writer = Mock()
    writer.update.side_effect = lambda ref, changes: db.rows[ref.path].update(changes)
    store._commit_usage(writer, ledger_ref, {}, binding, accounting, 3.5, 1000)
    assert writer.set.call_count == 2
    hourly, monthly = writer.set.call_args_list
    assert hourly.args[0].path[-2] == 'hourly_usage'
    assert monthly.args[1]['totals']['speech_seconds'].value == 3
    assert monthly.args[1]['totals']['transcription_seconds'].value == 3
    store._commit_usage(writer, ledger_ref, db.rows[ledger_ref.path], binding, accounting, 3.5, 1001)
    assert writer.set.call_count == 2


@pytest.mark.parametrize('status', ['in_progress', 'processing'])
def test_closed_empty_cleanup_fences_unclosed_and_committed_audio(monkeypatch, status):

    db = _FakeFirestore({ROW: capture()})
    rows = db.documents
    monkeypatch.setattr(recording_sessions.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    rows[ROW]['status'] = status
    kwargs = dict(firestore_client=db, allow_empty_server_batch=True)
    assert not recording_sessions.tombstone_and_delete_empty_conversation('owner', 'conversation', None, **kwargs)
    rows[ROW].update(server_batch_audio_closed=True, server_batch_audio_start=1, server_batch_audio_end=2)
    assert not recording_sessions.tombstone_and_delete_empty_conversation('owner', 'conversation', None, **kwargs)
    rows[ROW].pop('server_batch_audio_start')
    rows[ROW].pop('server_batch_audio_end')
    assert recording_sessions.tombstone_and_delete_empty_conversation('owner', 'conversation', None, **kwargs)
    assert ROW not in rows


@pytest.mark.parametrize('received', [True, None, False])
def test_closed_empty_cleanup_requires_explicit_never_received_proof(monkeypatch, received):

    row = capture()
    row.update(server_batch_audio_closed=True, server_batch_audio_received=received)
    db = _FakeFirestore({ROW: row})
    monkeypatch.setattr(recording_sessions.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(recording_sessions, 'stop_quiet_check_for_conversation', lambda *a, **kw: None)
    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'owner', 'conversation', None, firestore_client=db, allow_empty_server_batch=True
    )
    assert deleted is (received is False)
    assert (ROW in db.documents) is (received is not False)
