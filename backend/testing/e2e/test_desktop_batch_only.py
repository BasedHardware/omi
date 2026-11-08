"""Native desktop listen -> production PCM relay -> immutable original custody."""

from fakes.firestore import get_mock_firestore
from fakes.listen_pusher_wire import ScriptedPusherPeer, install_fake_firestore_transactions
from fakes.stt import install_streaming_stt_fake
from listen_test_helpers import is_conversation_session_event, is_ready_event, receive_until, seed_listen_user

from contextlib import nullcontext
import asyncio
import json
import threading
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
    'platform,source,mobile_percent,byok,consent,disabled,restore',
    [
        ('macos', 'desktop', '0', False, True, True, False),
        ('windows', 'desktop', '0', False, True, True, False),
        ('ios', 'phone', '0', False, True, True, False),
        ('android', 'omi', '0', False, True, True, False),
        ('ios', 'phone', '100', False, True, True, False),
        ('android', 'omi', '100', False, True, True, False),
        ('macos', 'desktop', '0', True, True, True, False),
        ('macos', 'desktop', '0', False, False, True, False),
        ('macos', 'desktop', '0', False, True, False, False),
        ('ios', 'phone', '100', False, True, True, 'success'),
        ('android', 'omi', '100', False, True, True, 'success'),
        ('android', 'omi', '100', False, True, True, 'failure'),
        ('android', 'omi', '100', False, True, True, 'hide_during_dial'),
    ],
)
def test_native_desktop_custody_or_exact_live_rollback(
    client,
    test_uid,
    monkeypatch,
    remote,
    consent,
    disabled,
    platform,
    source,
    mobile_percent,
    byok,
    restore,
    language='en',
    auto_percent='0',
    learned=None,
):
    from config.server_batch import owned
    from database.conversations import prepare_conversation_for_read
    from tests.unit.test_audio_durable_outbox import Blob
    from utils.other.raw_audio import decode_capture
    import routers.listen.runtime as runtime
    import utils.pusher as pusher_client
    from routers.listen.visible_restore import VisibleRestore, VISIBLE_DWELL_SECONDS
    from routers.listen import receiver as receiver_module

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
        monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', auto_percent)
        monkeypatch.setenv('SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT', '100' if restore else '0')
        if restore:
            # Advance only the policy's visibility timestamp, leaving real
            # socket/harness timeouts alone. Unit tests cover the 15s boundary.
            original_observe = VisibleRestore.observe

            def elapsed_visible(self, payload):
                original_observe(self, payload)
                if self.presence.policy.state == 'visible':
                    self.presence.policy.changed_at -= VISIBLE_DWELL_SECONDS

            monkeypatch.setattr(VisibleRestore, 'observe', elapsed_visible)
        monkeypatch.setattr(runtime, 'PUSHER_ENABLED', True)
        if byok:
            monkeypatch.setattr(runtime, 'get_byok_keys', lambda: {'soniox': 'synthetic-test-key'})
        monkeypatch.setattr(pusher_client, 'PusherAPI', peer.api_url)
        breaker = pusher_client.get_circuit_breaker()
        breaker._state = pusher_client.CircuitState.CLOSED
        breaker._failures.clear()
        breaker._probe_in_progress = False
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=language == 'en')
        if learned is not None:
            monkeypatch.setenv('STT_LEARNED_LANGUAGE_PROFILE', 'true')
            monkeypatch.setattr(runtime, 'get_live_language_sessions', lambda uid: [learned] * 3)
        user = get_mock_firestore().collection('users').document(test_uid)
        user.update({'private_cloud_sync_enabled': consent, 'data_protection_level': 'standard'})
        if language != 'en':
            from utils.stt.streaming import STTService

            # Refused auto-language sessions need an allowed multilingual live
            # provider; the default fake deliberately offers only Parakeet.
            sockets = install_streaming_stt_fake(
                monkeypatch, failover_selection=(STTService.modulate, 'multi', 'velma-2')
            )
        else:
            sockets = install_streaming_stt_fake(monkeypatch, die_on_first_send=restore == 'failure')
        dial_started, dial_connected = threading.Event(), threading.Event()
        release_dial = []
        if restore:
            connect_preview = receiver_module.process_audio_modulate

            async def controlled_preview_dial(*args, **kwargs):
                loop = asyncio.get_running_loop()
                released = loop.create_future()

                def release():
                    if not released.done():
                        released.set_result(None)

                release_dial.append(lambda: loop.call_soon_threadsafe(release))
                dial_started.set()
                if restore == 'hide_during_dial':
                    await released
                raw = await connect_preview(*args, **kwargs)
                dial_connected.set()
                return raw

            monkeypatch.setattr(receiver_module, 'process_audio_modulate', controlled_preview_dial)
        data = b'\x80' * 480 + b'\x90' * 480 + b'\x70' * 480
        language_query = '' if language is None else f'language={language}&'
        with client.websocket_connect(
            f'/v4/listen?{language_query}sample_rate=8000&codec=pcm8&source={source}&vad_gate=disabled',
            headers={'Authorization': 'Bearer dev-token', 'X-App-Platform': platform},
        ) as websocket:
            session = receive_until(websocket, is_conversation_session_event)
            receive_until(websocket, is_ready_event)
            if restore:
                websocket.send_json({'type': 'client_state', 'foreground': True, 'transcript_visible': True})
            websocket.send_bytes(data)
            if consent:
                peer.wait_for_frames(101, 1)
            else:
                receive_until(websocket, lambda value: isinstance(value, list) and bool(value))
            if restore:
                assert dial_started.wait(5)
                if restore == 'hide_during_dial':
                    websocket.send_json({'type': 'client_state', 'foreground': False, 'transcript_visible': False})
                    websocket.send_bytes(data)
                    # Real receiver must process hide + retain another frame
                    # before the provider is released. The inline dial fails here.
                    peer.wait_for_frames(101, 2, timeout=5)
                    release_dial[0]()
                    assert dial_connected.wait(5)
                else:
                    assert dial_connected.wait(5)
                    websocket.send_bytes(data)
                    peer.wait_for_frames(101, 2)
                    if restore == 'success':
                        receive_until(websocket, lambda value: isinstance(value, list) and bool(value))
                websocket.send_json({'type': 'client_state', 'foreground': False, 'transcript_visible': False})
                websocket.send_bytes(data)
                peer.wait_for_frames(101, 3)

        row = user.collection('conversations').document(session['conversation_id']).get().to_dict()
        assert row is not None
        decoded = prepare_conversation_for_read(row, test_uid)
        language_admitted = language == 'en' or (auto_percent == '100' and learned == {'en': 100})
        if (
            disabled
            and consent
            and not byok
            and language_admitted
            and (platform in {'macos', 'windows'} or mobile_percent == '100')
        ):
            assert owned(row)
            if language is None:
                assert decoded['language'] == 'multi'  # No declared-English manifest bypass.
            if restore == 'success':
                assert decoded.get('transcript_segments')
            else:
                assert not decoded.get('transcript_segments')
            assert row['has_content']
            if restore:
                assert len(sockets) == 1 and sockets[0].provider == 'modulate'
                assert len(sockets[0].sent_chunks) == (0 if restore == 'hide_during_dial' else 1)
            else:
                assert not sockets
            expected = b'\x00\x00' * 480 + b'\x00\x10' * 480 + b'\x00\xf0' * 480
            if restore:
                expected *= 3  # Opening/hidden/failing preview cannot stop PCM or originals.
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


@pytest.mark.parametrize('platform', ['ios', 'android'])
@pytest.mark.parametrize('language', ['auto', None])
@pytest.mark.parametrize(
    'auto_percent,learned', [('0', {'en': 100}), ('100', {'en': 100}), ('100', {'en': 50, 'ja': 50})]
)
def test_auto_mobile_preserves_original_custody_and_exclusions(
    client, test_uid, monkeypatch, remote, platform, auto_percent, learned, language
):
    # The auto/multi-language variants need the harness's multi-language live
    # vendor (Modulate), which the default registry withdraws (ramp 0); run
    # them on the explicit enabled-targets registry like the listen E2E.
    from tests.unit.fixtures.live_stt_registry import enabled_live_targets

    enabled_live_targets(monkeypatch)
    test_native_desktop_custody_or_exact_live_rollback(
        client,
        test_uid,
        monkeypatch,
        remote,
        True,
        True,
        platform,
        'omi',
        '100',
        False,
        False,
        language=language,
        auto_percent=auto_percent,
        learned=learned,
    )
