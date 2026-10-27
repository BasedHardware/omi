"""Desktop no-live admission, immutable custody and durable batch handoff."""

import asyncio
import json
import struct
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import server_batch
from config.batch_live_preview import capture_snapshot
from database import conversations, recording_sessions
from models.conversation_enums import ConversationStatus
from routers.listen import receiver as receiver_module
from routers.listen.receiver import ListenReceiver
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_durable_outbox import remote, Socket, _window_harness, _sent_receipts, host as archive_host
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.live import register_recording, record_identity
from utils.conversations import finalizer, lifecycle
from utils.other import live_audio_archive
from utils.other.audio_outbox import read_pcm
from utils.other.live_audio_archive import LiveAudioArchive
import routers.pusher as pusher

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
    )


@pytest.fixture(autouse=True)
def policy_env(monkeypatch):
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
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
def test_kill_switch_restores_live_without_releasing_existing_batch_obligation(monkeypatch, raw):
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', raw)
    assert not server_batch.eligible(capture(), 'owner')
    assert not server_batch.suppress_live(host())
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


@pytest.mark.parametrize('platform', ['ios', 'android'])
def test_mobile_percent_is_nested_in_actual_batch_admission(monkeypatch, platform):
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '100')
    assert not server_batch.selected('owner', platform, 'omi')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    assert server_batch.selected('owner', platform, 'omi')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', 'bad')
    assert not server_batch.selected('owner', platform, 'omi')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '50')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '25')
    from config.policy import resolve_batch_policy

    for index in range(100):
        owner = f'synthetic-{index}'
        assert not server_batch.selected(owner, platform, 'omi') or resolve_batch_policy(owner).batch_enabled


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
        return conversations.note_server_batch_audio(owner, conversation, start, end, firestore_client=db)

    monkeypatch.setattr(live_audio_archive, 'note_server_batch_audio', note)
    packet = b'\x00\x00' * 160
    await archive.append(packet, 'conversation', 1000, 160, decoded=packet)
    assert 'has_content' not in db.rows[ROW]
    await archive.close()
    row = db.rows[ROW]
    assert order == ['committed'] and row['has_content'] and not row['transcript_segments']
    assert row['started_at'].timestamp() == 1000
    assert row['finished_at'].timestamp() == 1000.01
    assert conversations.note_server_batch_audio('owner', 'conversation', 1001, 1002, firestore_client=db)
    assert conversations.note_server_batch_audio('owner', 'conversation', 999, 1000, firestore_client=db)
    assert db.rows[ROW]['started_at'].timestamp() == 999
    assert db.rows[ROW]['finished_at'].timestamp() == 1002
    assert not recording_sessions.tombstone_and_delete_empty_conversation(
        'owner', 'conversation', None, firestore_client=db
    )


@pytest.mark.asyncio
async def test_zero_preview_finalizer_registers_exact_language_bounds_before_completion(monkeypatch):
    row = capture()
    row.update(
        status='processing',
        started_at=datetime.fromtimestamp(1000, timezone.utc),
        finished_at=datetime.fromtimestamp(1002, timezone.utc),
        language='es',
        has_content=True,
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
