"""Both sync versions execute process_segment; prove the last pre-STT gate."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import wave

import pytest

from utils.sync import cap_hold, pipeline
from utils import stt_cap_dispatch as cap


@pytest.fixture(autouse=True)
def initialized_summary(monkeypatch):
    # This suite tests hold leaves; summary migration has separate transaction tests.
    monkeypatch.setattr(cap_hold, 'ensure_summary', lambda uid: {'version': 2, 'seconds': 0, 'count': 0})


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize('queued', [False, True], ids=['sync-v1', 'sync-v2-worker'])
def test_exhaustion_holds_before_url_or_provider_dispatch(tmp_path, monkeypatch, enforce, queued, ladder):
    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(
        cap, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    )
    hold = Mock(side_effect=lambda *a, **kw: kw['receipt'].update(id='held', seconds=1))
    url, stt = Mock(return_value='synthetic-url'), Mock(return_value=([], 'en'))
    monkeypatch.setattr(cap_hold, 'hold_segment', hold)
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', url)
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
    if enforce or ladder:
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
    monkeypatch.setattr(pipeline, 'sync_allowed', lambda *_, **kwargs: False)
    monkeypatch.setattr(cap_hold, 'hold_segment', Mock(side_effect=RuntimeError('synthetic upload failed')))
    stt = Mock()
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    errors = []
    pipeline.process_segment(str(tmp_path / '1792152000.wav'), 'synthetic', {}, threading.Lock(), errors)
    assert errors
    stt.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
def test_recovery_pins_checkpointed_provider_only_with_enforcement(tmp_path, monkeypatch, enforce):
    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(pipeline, 'sync_allowed', lambda *_, **kwargs: True)
    monkeypatch.setattr(pipeline, 'funded_allowance', lambda *_, **kwargs: SimpleNamespace(reason='available'))
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', Mock(return_value='synthetic-url'))
    monkeypatch.setattr(pipeline, 'keyterms', AsyncMock(return_value=[]))
    selection = Mock(return_value=('modulate', None, 'velma-2'))
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', selection)
    stt = Mock(return_value=([], 'en'))
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    monkeypatch.setattr(pipeline, '_record_empty_segment_as_silence', Mock())
    errors = []
    service = ('parakeet', 'multi', 'parakeet')
    checkpoint = Mock(return_value=True)
    monkeypatch.setattr(pipeline.cap_recovery_provider.sync_cap_recovery, 'provider_checkpoint', checkpoint)
    assert not pipeline.process_segment(
        str(path),
        'synthetic',
        {},
        threading.Lock(),
        errors,
        cap_recovery=True,
        cap_recovery_service=service,
        cap_recovery_checkpoint={'hold_id': 'h', 'piece': 'p', 'lease_token': 'l', 'attempt': 1, 'receipt': {}},
    )
    assert not errors
    assert stt.call_count == (1 if enforce else 0)
    assert checkpoint.call_count == (2 if enforce else 0)
    for call in stt.call_args_list:
        if enforce:
            assert call.kwargs['selected_service'] == service
        else:
            assert 'selected_service' not in call.kwargs
    selection.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
async def test_full_capture_hold_precedes_vad_and_has_default_off_parity(tmp_path, monkeypatch, enforce):
    from utils.sync import cap_hold
    from models.conversation_enums import ConversationSource

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(
        cap_hold,
        'funded_allowance',
        Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted')),
    )
    hold = AsyncMock()
    monkeypatch.setattr(cap_hold, '_hold_capture', hold)
    paths = [str(tmp_path / '1792152000.wav')]
    assert await cap_hold.hold_capture_if_exhausted('synthetic', paths, ConversationSource.omi) is enforce
    if enforce:
        assert hold.call_args.args[2] == {
            'timestamp': 1792152000,
            'source': 'omi',
            'origin': 'sync',
            'full_capture': True,
            'file_name': '1792152000.wav',
            'source_frame_map': None,
        }
    else:
        hold.assert_not_called()
        cap_hold.funded_allowance.assert_not_called()


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
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 2000)
    assert not cap_hold.checkpoint('synthetic', ref, first['lease_token'], {'state': 'completed'})
    assert cap_hold.checkpoint('synthetic', ref, next_claim['lease_token'], {'finalized': True})
    cap_hold.release('synthetic', ref, first['lease_token'])
    assert client.rows[path]['lease_token'] == next_claim['lease_token']
    cap_hold.release('synthetic', ref, next_claim['lease_token'])
    assert client.rows[path]['lease_until'] == 0


@pytest.mark.parametrize('state', ['completed', 'retained', 'purged', 'staging', 'sealing', 'superseded'])
def test_claim_leaves_terminal_and_unsealed_rows_alone(monkeypatch, state):
    from contextlib import nullcontext
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync import cap_hold

    path = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    client = StrictFirestore({path: {'state': state, 'lease_until': 0}})
    ref = client.document('/'.join(path))
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    assert cap_hold.claim('synthetic', ref, 100) is None
    assert client.rows[path] == {'state': state, 'lease_until': 0}


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
    uploaded = []
    ref, blob, bucket = Mock(), Mock(), Mock()
    ref.get.return_value.exists = False

    def upload(stream, **kwargs):
        uploaded.append(stream.read())
        order.append('upload')

    blob.upload_from_file.side_effect = upload

    class _Batch:
        def create(self, document, data):
            document.create(data)
            order.append('manifest')

        def set(self, document, data, merge=False):
            order.append('summary')

        def commit(self):
            return None

    class _Ref:
        def collection(self, name):
            return self

        def document(self, name):
            return self

    class _Client:
        def batch(self):
            return _Batch()

        def collection(self, name):
            return _Ref()

    ref.create.side_effect = lambda *args, **kwargs: None
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: _Client())
    monkeypatch.setattr(cap_hold, 'holds', lambda _: SimpleNamespace(document=lambda _: ref))
    monkeypatch.setattr(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket)
    bucket.blob.return_value = blob
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    monkeypatch.setattr(cap_hold, 'owner_storage_write_gate', lambda *_: nullcontext())
    monkeypatch.setattr(
        cap_hold, 'funded_allowance', lambda _, **kw: SimpleNamespace(reason='plan_allowance_exhausted')
    )
    meta = {'timestamp': 1792152000, 'source': 'omi', 'full_capture': True}
    assert cap_hold.hold_segment('synthetic', str(path), meta) == 1
    assert order == ['upload', 'manifest', 'summary']
    assert decrypt_audio_file(uploaded[0], 'synthetic') == path.read_bytes()
    manifest = ref.create.call_args.args[0]
    assert manifest['audio_path'].startswith('chunks/synthetic/cap-held/')
    assert json.loads(decrypt(manifest['metadata'], 'synthetic')) == {**meta, 'origin': 'sync'}
    assert 'expires_at' not in manifest
    ref.create.reset_mock()
    blob.upload_from_file.side_effect = RuntimeError('synthetic unavailable')
    with pytest.raises(RuntimeError):
        cap_hold.hold_segment('synthetic', str(path), meta)
    ref.create.assert_not_called()


@pytest.mark.parametrize('corrupt', [False, True])
def test_large_hold_streams_bounded_authenticated_chunks(tmp_path, monkeypatch, corrupt):
    from contextlib import nullcontext
    from pathlib import Path
    from cryptography.exceptions import InvalidTag

    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x01\x02' * cap_hold.AUDIO_CHUNK_BYTES)
    expected = path.read_bytes()
    ref, blob, bucket = Mock(), Mock(), Mock()
    ref.get.return_value.exists = False
    uploaded = []
    blob.upload_from_file.side_effect = lambda stream, **kw: uploaded.append(stream.read())
    bucket.blob.return_value = blob

    class _Batch:
        def create(self, document, data):
            document.create(data)

        def set(self, document, data, merge=False):
            return None

        def commit(self):
            return None

    class _Ref:
        def collection(self, name):
            return self

        def document(self, name):
            return self

    class _Client:
        def batch(self):
            return _Batch()

        def collection(self, name):
            return _Ref()

    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: _Client())
    monkeypatch.setattr(cap_hold, 'holds', lambda _: SimpleNamespace(document=lambda _: ref))
    monkeypatch.setattr(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    monkeypatch.setattr(cap_hold, 'owner_storage_write_gate', lambda *_: nullcontext())
    monkeypatch.setattr(
        cap_hold, 'funded_allowance', lambda _, **kw: SimpleNamespace(reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(Path, 'read_bytes', Mock(side_effect=AssertionError('whole-file buffer')))
    encrypt_chunk = Mock(wraps=cap_hold.encrypt_audio_chunk)
    monkeypatch.setattr(cap_hold, 'encrypt_audio_chunk', encrypt_chunk)
    cap_hold.hold_segment('synthetic', str(path), {'timestamp': 1792152000, 'source': 'omi'})
    assert encrypt_chunk.call_count == 3
    assert max(len(call.args[0]) for call in encrypt_chunk.call_args_list) <= cap_hold.AUDIO_CHUNK_BYTES
    encrypted = uploaded[0]
    if corrupt:
        encrypted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    blob.download_to_file.side_effect = lambda output: output.write(encrypted)
    output = tmp_path / 'recovered.wav'
    manifest = ref.create.call_args.args[0]
    if corrupt:
        with pytest.raises(InvalidTag):
            cap_hold.read_audio('synthetic', manifest, str(output))
        assert not output.exists()
    else:
        cap_hold.read_audio('synthetic', manifest, str(output))
        with output.open('rb') as recovered:
            assert recovered.read() == expected
    blob.delete.assert_not_called()


async def test_capture_hold_coordinates_db_and_storage_leaves(monkeypatch):
    from models.conversation_enums import ConversationSource

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(
        cap_hold, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='allowance_unavailable'))
    )
    monkeypatch.setattr(cap_hold, 'describe', Mock(return_value=('held', 20, {'source': 'omi'})))
    monkeypatch.setattr(cap_hold, '_exists', Mock(return_value=False))
    monkeypatch.setattr(cap_hold, 'upload_held_audio', Mock(return_value={'audio_path': 'synthetic'}))
    monkeypatch.setattr(cap_hold, '_publish', Mock(return_value=True))
    calls = []

    async def leaf(pool, fn, *args, **kwargs):
        calls.append((pool, fn))
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap_hold, 'run_blocking', leaf)
    receipts, admission = {}, {}
    assert await cap_hold.hold_capture_if_exhausted(
        'synthetic', ['1792152000.wav'], ConversationSource.omi, receipts=receipts, admission=admission
    )
    assert calls == [
        (cap_hold.db_executor, cap_hold.funded_allowance),
        (cap_hold.storage_executor, cap_hold.describe),
        (cap_hold.db_executor, cap_hold._exists),
        (cap_hold.storage_executor, cap_hold.upload_held_audio),
        (cap_hold.db_executor, cap_hold._publish),
    ]
    assert admission == {'reason': 'allowance_unavailable'}
    assert receipts['held']['reason'] == 'allowance_unavailable'


@pytest.mark.parametrize('payload_bytes', [20, 100 * 1024, 900 * 1024])
def test_production_pipeline_result_crash_restart_and_cache_capacity_never_force_charge(
    tmp_path, monkeypatch, payload_bytes
):
    from utils.conversations import lifecycle

    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(pipeline, 'sync_allowed', lambda *_, **kwargs: True)
    monkeypatch.setattr(pipeline, 'funded_allowance', lambda *_, **kwargs: SimpleNamespace(reason='available'))
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', Mock(return_value='synthetic-url'))
    monkeypatch.setattr(pipeline, 'keyterms', AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, 'get_closest_conversation_to_timestamps', Mock(return_value=None))
    monkeypatch.setattr(pipeline, 'sync_enabled_for', lambda *_: False)
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', Mock())
    monkeypatch.setattr(pipeline, 'apply_capture_evidence_dark_write', Mock())
    monkeypatch.setattr(pipeline, 'record_capture_evidence_metric', Mock())
    completed = Mock()
    monkeypatch.setattr(pipeline, 'complete_sync_intake', completed)
    ingest = Mock(side_effect=lambda uid, incoming, **kw: (incoming, True, incoming['transcript_segments']))
    monkeypatch.setattr(lifecycle, 'ingest_sync_conversation', ingest)
    words = [{'text': 'x' * payload_bytes, 'timestamp': [0, 1]}]
    provider_post = Mock(return_value=(words, 'en'))
    monkeypatch.setattr(pipeline, 'prerecorded', provider_post)
    persisted = {'state': 'dispatched', 'attempt': 1, 'provider': 'modulate', 'model': 'velma-2'}
    previous = {'provider_result': 'old-ciphertext' * 50000} if payload_bytes == 100 * 1024 else {}

    def checkpoint(uid, ctx, updates):
        row = {'piece_receipts': {'p': persisted, 'previous': previous}}
        persisted.update(pipeline.cap_recovery_provider.sync_cap_recovery.bounded_provider_updates(row, 'p', updates))
        ctx['receipt'].update(persisted)
        return True

    monkeypatch.setattr(pipeline.cap_recovery_provider.sync_cap_recovery, 'provider_checkpoint', checkpoint)
    parser = Mock(side_effect=RuntimeError('crash after provider checkpoint'))
    monkeypatch.setattr(pipeline, 'postprocess_words', parser)

    def process():
        errors = []
        ok = pipeline.process_segment(
            str(path),
            'synthetic',
            {},
            threading.Lock(),
            errors,
            cap_recovery=True,
            cap_recovery_service=('modulate', None, 'velma-2'),
            cap_recovery_checkpoint={
                'hold_id': 'h',
                'piece': 'p',
                'lease_token': 'l',
                'attempt': 1,
                'receipt': dict(persisted),
            },
        )
        assert parser.call_args.args[0] == words
        return ok, errors

    if payload_bytes == 20:
        # Crash at the next production boundary after a durable checkpoint.
        assert process()[1] and persisted['provider_result']
        ingest.assert_not_called()
    parser.side_effect = None
    parser.return_value = [
        pipeline.TranscriptSegment(text='usable response', start=0, end=1, speaker='SPEAKER_00', is_user=False)
    ]
    ok, errors = process()
    assert ok and not errors
    ingest.assert_called_once()
    completed.assert_called_once()
    provider_post.assert_called_once()
    if payload_bytes > 20:
        assert persisted['provider_cache_omitted'] and 'provider_result' not in persisted
        if previous:
            assert previous['provider_result'] == 'old-ciphertext' * 50000


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize(
    'origin,lanes,checked',
    [('live', 'live', True), ('sync', 'live', False), ('batch', 'live', False), ('live', 'sync,batch', False)],
)
def test_recovered_segment_rechecks_original_lane_without_reholding(
    tmp_path, monkeypatch, ladder, origin, lanes, checked
):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    allowance = Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    monkeypatch.setattr(cap, 'funded_allowance', allowance)
    provider = Mock(side_effect=AssertionError('denied recovery reached provider'))
    monkeypatch.setattr(pipeline, 'prerecorded', provider)
    hold = Mock(side_effect=AssertionError('recovery must not overwrite original hold'))
    monkeypatch.setattr(cap_hold, 'hold_segment', hold)
    errors = []
    result = pipeline.process_segment(
        str(tmp_path / '1792152000.wav'),
        'synthetic',
        {},
        threading.Lock(),
        errors,
        cap_recovery=True,
        cap_dispatch_lane=origin,
    )
    assert result is False and not errors
    assert allowance.call_count == int(checked)
    if checked:
        allowance.assert_called_with('synthetic', lane=origin)
    provider.assert_not_called()
    hold.assert_not_called()


@pytest.mark.parametrize('queued', [False, True], ids=['sync-v1', 'sync-v2-worker'])
@pytest.mark.parametrize('kill', [False, True])
def test_default_offline_gate_holds_outside_all_legacy_scopes(tmp_path, monkeypatch, queued, kill):
    # Existing helper drives the real process_segment and spies on both URL/STT.
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false' if kill else 'true')
    from config import stt_cap_dispatch as policy

    monkeypatch.setattr(policy, '_cohort_resolver', lambda: '')
    test_exhaustion_holds_before_url_or_provider_dispatch(
        tmp_path, monkeypatch, enforce=not kill, queued=queued, ladder=False
    )


@pytest.mark.parametrize('boundary', ['probe', 'retry', 'multilingual'])
def test_late_denial_holds_without_spending_next_provider_call(tmp_path, monkeypatch, boundary):
    from pathlib import Path
    from utils.stt import batch_language
    from utils.observability.stt_cap_dispatch import DispatchPath

    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    path = tmp_path / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', lambda _: 'synthetic-url')
    monkeypatch.setattr(pipeline, 'keyterms', AsyncMock(return_value=[]))
    hold = Mock()
    monkeypatch.setattr(cap_hold, 'defer_segment', hold)
    denied = {
        'probe': DispatchPath.LANGUAGE_PROBE,
        'retry': DispatchPath.EMPTY_RETRY,
        'multilingual': DispatchPath.MULTILINGUAL,
    }[boundary]
    seen = []

    def allowed(*args, **kwargs):
        seen.append(kwargs.get('path'))
        return kwargs.get('path') != denied

    monkeypatch.setattr(pipeline, 'sync_allowed', allowed)
    monkeypatch.setattr(pipeline, 'funded_allowance', lambda *a, **k: SimpleNamespace(reason='available'))

    probe_client = Mock(side_effect=AssertionError('denied LID must not reach the provider'))
    monkeypatch.setattr(batch_language.httpx, 'Client', probe_client)
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-key')

    def select(language, path, *, selector, before_probe, **kwargs):
        if boundary == 'probe':
            batch_language.detect(Path(path).read_bytes(), before_probe=before_probe)
        else:
            before_probe()
        return 'parakeet', 'en', 'parakeet'

    monkeypatch.setattr(batch_language, 'resolve_file', select)
    stt = Mock(return_value=([], 'en'))
    alternate = Mock(side_effect=AssertionError('denied fallback must not run'))
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    monkeypatch.setattr(pipeline, 'modulate_prerecorded_from_bytes', alternate)
    monkeypatch.setattr(pipeline, 'sync_safety_wal_enabled', lambda: False)
    monkeypatch.setattr(pipeline.minimal_redrive, 'paid_recovery_enabled', lambda _: True)

    def recover(path, *, transcribe, authorize, observe):
        authorize()
        return transcribe(b'synthetic')

    monkeypatch.setattr(pipeline.empty_recovery, 'recover', recover)
    # A probe denial must also deny the following STT boundary, as a real
    # exhausted snapshot would. The probe itself must never spend.
    if boundary == 'probe':
        original = allowed

        def allowed(*args, **kwargs):
            if denied in seen:
                return False
            return original(*args, **kwargs)

        monkeypatch.setattr(pipeline, 'sync_allowed', allowed)
    errors = []
    outcome = {}
    assert not pipeline.process_segment(str(path), 'synthetic', {}, threading.Lock(), errors, deferred_outcome=outcome)
    assert not errors
    assert denied in seen
    hold.assert_called_once()
    assert outcome['cap_held'] is True
    assert stt.call_count == {'probe': 0, 'retry': 1, 'multilingual': 2}[boundary]
    alternate.assert_not_called()
    probe_client.assert_not_called()
