"""Native desktop listen -> production PCM relay -> immutable original custody."""

from fakes.firestore import get_mock_firestore
from fakes.listen_pusher_wire import ScriptedPusherPeer, install_fake_firestore_transactions
from fakes.stt import install_streaming_stt_fake
from listen_test_helpers import is_conversation_session_event, is_ready_event, receive_until, seed_listen_user

from contextlib import nullcontext
import json
from types import SimpleNamespace
import pytest


@pytest.fixture
def remote(client, monkeypatch):
    # Import backend-bound helpers only after client installs fake constructors.
    # Collection-time imports otherwise leave sibling tests with real Redis aliases.
    from tests.unit.test_audio_durable_outbox import Bucket
    from utils.other import storage

    bucket = Bucket()
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: nullcontext())
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *a: False)
    return bucket


@pytest.mark.parametrize(
    'platform,source,mobile_percent,byok,consent,disabled',
    [
        ('macos', 'desktop', '0', False, True, True),
        ('windows', 'desktop', '0', False, True, True),
        ('ios', 'phone', '0', False, True, True),
        ('android', 'omi', '0', False, True, True),
        ('ios', 'phone', '100', False, True, True),
        ('android', 'omi', '100', False, True, True),
        ('macos', 'desktop', '0', True, True, True),
        ('macos', 'desktop', '0', False, False, True),
        ('macos', 'desktop', '0', False, True, False),
    ],
)
def test_native_desktop_custody_or_exact_live_rollback(
    client, test_uid, monkeypatch, remote, consent, disabled, platform, source, mobile_percent, byok
):
    from config.server_batch import owned
    from database.conversations import prepare_conversation_for_read
    from tests.unit.test_audio_durable_outbox import Blob
    from utils.other.raw_audio import decode_capture
    import routers.listen.runtime as runtime
    import utils.pusher as pusher_client

    async def finalization(*args):
        return None

    peer = ScriptedPusherPeer(finalization).start()
    try:
        # TestClient cancels its portal transports at context exit. Bound only
        # this loopback peer's dead-transport close handshake, preserving every
        # production send, custody commit and finalization admission operation.
        connect = pusher_client.websockets.connect
        target = peer.api_url.replace('http://', 'ws://') + '/'

        def loopback_connect(uri, *args, **kwargs):
            if str(uri).startswith(target):
                kwargs['close_timeout'] = 0.01
            return connect(uri, *args, **kwargs)

        monkeypatch.setattr(pusher_client.websockets, 'connect', loopback_connect)
        monkeypatch.setattr(Blob, 'exists', lambda self: self.data is not None, raising=False)
        install_fake_firestore_transactions(monkeypatch, get_mock_firestore())
        monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'true' if disabled else 'false')
        monkeypatch.setenv('HOSTED_PUSHER_API_URL', peer.api_url)
        monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
        monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
        monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
        monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', mobile_percent)
        monkeypatch.setattr(runtime, 'PUSHER_ENABLED', True)
        if byok:
            monkeypatch.setattr(runtime, 'get_byok_keys', lambda: {'soniox': 'synthetic-test-key'})
        monkeypatch.setattr(pusher_client, 'PusherAPI', peer.api_url)
        breaker = pusher_client.get_circuit_breaker()
        breaker._state = pusher_client.CircuitState.CLOSED
        breaker._failures.clear()
        breaker._probe_in_progress = False
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)
        user = get_mock_firestore().collection('users').document(test_uid)
        user.update({'private_cloud_sync_enabled': consent, 'data_protection_level': 'standard'})
        sockets = install_streaming_stt_fake(monkeypatch)
        data = b'\x80' * 480 + b'\x90' * 480 + b'\x70' * 480
        with client.websocket_connect(
            f'/v4/listen?language=en&sample_rate=8000&codec=pcm8&source={source}&vad_gate=disabled',
            headers={'Authorization': 'Bearer dev-token', 'X-App-Platform': platform},
        ) as websocket:
            session = receive_until(websocket, is_conversation_session_event)
            receive_until(websocket, is_ready_event)
            websocket.send_bytes(data)
            if consent:
                peer.wait_for_frames(101, 1)
            else:
                receive_until(websocket, lambda value: isinstance(value, list) and bool(value))

        row = user.collection('conversations').document(session['conversation_id']).get().to_dict()
        assert row is not None
        decoded = prepare_conversation_for_read(row, test_uid)
        if disabled and consent and not byok and (platform in {'macos', 'windows'} or mobile_percent == '100'):
            assert owned(row) and not decoded.get('transcript_segments')
            assert row['has_content']
            assert not sockets
            expected = b'\x00\x00' * 480 + b'\x00\x10' * 480 + b'\x00\xf0' * 480
            assert b''.join(frame.raw[12:] for frame in peer.frames_of_type(101)) == expected
            manifests = remote.list_blobs('audio-outbox/')
            assert manifests
            media = []
            for blob in manifests:
                manifest = json.loads(blob.data)
                original = remote.blob(manifest['media']['path'])
                # Original PCM8 bytes, independent of decoded PCM relay above.
                media.append(decode_capture(original.data, original.metadata, output_rate=8000))
            assert b''.join(media) == expected
        else:
            assert sockets and any(socket.sent_chunks for socket in sockets)
            assert decoded.get('transcript_segments')
            assert not owned(row)
    finally:
        peer.close()
