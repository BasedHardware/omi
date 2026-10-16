"""Both sync versions execute process_segment; prove the last pre-STT gate."""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest

from utils.sync import cap_hold, pipeline
from utils import stt_cap_dispatch as cap


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('queued', [False, True], ids=['sync-v1', 'sync-v2-worker'])
def test_exhaustion_holds_before_url_or_provider_dispatch(tmp_path, monkeypatch, enforce, queued):
    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(
        cap, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    )
    hold, url, stt = Mock(), Mock(return_value='synthetic-url'), Mock(return_value=([], 'en'))
    monkeypatch.setattr(cap_hold, 'hold_segment', hold)
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', url)
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', Mock())
    monkeypatch.setattr(pipeline, 'keyterms', AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', lambda _: ('modulate', None, 'velma-2'))
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    monkeypatch.setattr(pipeline, '_record_empty_segment_as_silence', Mock())
    monkeypatch.setattr(pipeline, 'sync_safety_wal_enabled', lambda: False)
    errors = []
    assert (
        pipeline.process_segment(
            str(path),
            'synthetic',
            {'new_memories': set(), 'updated_memories': set()},
            threading.Lock(),
            errors,
            is_locked=True,
            job_id='queued-job' if queued else None,
        )
        is False
    )
    assert not errors
    if enforce:
        hold.assert_called_once()
        assert hold.call_args.args[2]['timestamp'] == 1792152000
        url.assert_not_called()
        stt.assert_not_called()
    else:
        hold.assert_not_called()
        assert stt.call_count == 2  # Main's bounded empty-result retry remains unchanged.
        cap.funded_allowance.assert_not_called()


def test_hold_failure_cannot_acknowledge_audio_or_dispatch_provider(tmp_path, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(pipeline, 'sync_allowed', lambda *_: False)
    monkeypatch.setattr(cap_hold, 'hold_segment', Mock(side_effect=RuntimeError('synthetic upload failed')))
    stt = Mock()
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    errors = []
    pipeline.process_segment(str(tmp_path / '1792152000.wav'), 'synthetic', {}, threading.Lock(), errors)
    assert errors
    stt.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
def test_full_capture_hold_precedes_vad_and_has_default_off_parity(tmp_path, monkeypatch, enforce):
    from utils.sync import cap_hold
    from models.conversation_enums import ConversationSource

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(cap_hold, 'sync_allowed', Mock(return_value=False))
    hold = Mock()
    monkeypatch.setattr(cap_hold, 'hold_segment', hold)
    paths = [str(tmp_path / '1792152000.wav')]
    assert cap_hold.hold_capture_if_exhausted('synthetic', paths, ConversationSource.omi) is enforce
    if enforce:
        assert hold.call_args.args[2] == {'timestamp': 1792152000, 'source': 'omi', 'full_capture': True}
    else:
        hold.assert_not_called()
        cap_hold.sync_allowed.assert_not_called()


def test_hold_manifest_fences_concurrent_recovery_and_stale_release(monkeypatch):
    from contextlib import nullcontext
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync import cap_hold

    path = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    client = StrictFirestore({path: {'state': 'held', 'lease_until': 0}})
    ref = client.document('/'.join(path))
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    first = cap_hold.claim('synthetic', ref, 100)
    assert first and first['lease_token']
    assert cap_hold.claim('synthetic', ref, 101) is None
    next_claim = cap_hold.claim('synthetic', ref, 2000)
    cap_hold.release('synthetic', ref, first['lease_token'])
    assert client.rows[path]['lease_token'] == next_claim['lease_token']
    cap_hold.release('synthetic', ref, next_claim['lease_token'])
    assert client.rows[path]['lease_until'] == 0


def test_hold_persists_encrypted_audio_before_manifest_and_never_expires(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from utils.sync import cap_hold
    from utils.encryption import decrypt_audio_file, decrypt
    import json

    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\0' * 32000)
    order = []
    ref, blob, bucket = Mock(), Mock(), Mock()
    ref.get.return_value.exists = False
    blob.upload_from_string.side_effect = lambda *args, **kwargs: order.append('upload')
    ref.create.side_effect = lambda *args, **kwargs: order.append('manifest')
    monkeypatch.setattr(cap_hold, 'holds', lambda _: SimpleNamespace(document=lambda _: ref))
    monkeypatch.setattr(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket)
    bucket.blob.return_value = blob
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    monkeypatch.setattr(cap_hold, 'owner_storage_write_gate', lambda *_: nullcontext())
    monkeypatch.setattr(cap_hold, 'funded_allowance', lambda _: SimpleNamespace(reason='plan_allowance_exhausted'))
    meta = {'timestamp': 1792152000, 'source': 'omi', 'full_capture': True}
    assert cap_hold.hold_segment('synthetic', str(path), meta) == 1
    assert order == ['upload', 'manifest']
    assert decrypt_audio_file(blob.upload_from_string.call_args.args[0], 'synthetic') == path.read_bytes()
    manifest = ref.create.call_args.args[0]
    assert manifest['audio_path'].startswith('chunks/synthetic/cap-held/')
    assert json.loads(decrypt(manifest['metadata'], 'synthetic')) == meta
    assert 'expires_at' not in manifest
    ref.create.reset_mock()
    blob.upload_from_string.side_effect = RuntimeError('synthetic unavailable')
    with pytest.raises(RuntimeError):
        cap_hold.hold_segment('synthetic', str(path), meta)
    ref.create.assert_not_called()
