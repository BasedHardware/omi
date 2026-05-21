import io
import os
import sys
from types import SimpleNamespace
import wave
from unittest.mock import MagicMock

import numpy as np

os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')

for mod_name in ['deepgram', 'deepgram.clients', 'deepgram.clients.live', 'deepgram.clients.live.v1']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock

if 'google.api_core.exceptions' not in sys.modules:
    sys.modules['google'] = MagicMock()
    sys.modules['google.api_core'] = MagicMock()
    sys.modules['google.api_core.exceptions'] = MagicMock(NotFound=Exception)
    sys.modules['google.cloud'] = MagicMock()
    sys.modules['google.cloud.firestore'] = MagicMock()
    sys.modules['google.cloud.firestore_v1'] = MagicMock(FieldFilter=MagicMock)
sys.modules['google.cloud.firestore'].Increment = lambda value: value
database_client_stub = sys.modules.setdefault('database._client', SimpleNamespace())
database_client_stub.db = getattr(database_client_stub, 'db', MagicMock())
database_client_stub.document_id_from_seed = getattr(database_client_stub, 'document_id_from_seed', MagicMock())
sys.modules.setdefault('database.conversations', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('database.redis_db', SimpleNamespace(r=MagicMock()))


class _DesktopBackgroundConversationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


sys.modules.setdefault(
    'utils.conversations.desktop_background',
    SimpleNamespace(
        DesktopBackgroundConversationError=_DesktopBackgroundConversationError,
        append_background_chunk_to_in_progress_conversation=MagicMock(),
        append_segments_to_in_progress_conversation=MagicMock(),
        create_in_progress_desktop_conversation=MagicMock(return_value='conv-1'),
        finish_desktop_background_conversation=MagicMock(return_value={'id': 'conv-1', 'status': 'completed'}),
        get_background_chunk_record=MagicMock(return_value=None),
    ),
)
sys.modules.setdefault(
    'utils.chat', SimpleNamespace(resolve_voice_message_language=lambda _uid, language: language or 'en')
)
sys.modules.setdefault('utils.analytics', SimpleNamespace(record_usage=lambda *_args, **_kwargs: None))
sys.modules.setdefault('utils.byok', SimpleNamespace(get_byok_key=lambda _provider: None))
sys.modules.setdefault(
    'utils.fair_use',
    SimpleNamespace(
        is_hard_restricted=lambda *_args, **_kwargs: False,
        record_speech_ms=lambda *_args, **_kwargs: None,
    ),
)
sys.modules.setdefault(
    'utils.subscription',
    SimpleNamespace(
        has_transcription_credits=lambda *_args, **_kwargs: True,
        is_trial_paywalled=lambda *_args, **_kwargs: False,
    ),
)


def _pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_data)
    return buffer.getvalue()


sys.modules.setdefault('utils.speaker_identification', SimpleNamespace(_pcm_to_wav_bytes=_pcm_to_wav_bytes))
sys.modules.setdefault('utils.stt.speaker_embedding', SimpleNamespace(extract_embedding_from_bytes=MagicMock()))
sys.modules.setdefault(
    'utils.stt.provider_service',
    SimpleNamespace(
        resolve_prerecorded_provider_for_request=MagicMock(),
        transcribe_bytes=MagicMock(),
        update_provider_run_identity_metrics=MagicMock(),
    ),
)
sys.modules.setdefault(
    'utils.voice_duration_limiter',
    SimpleNamespace(
        compute_pcm_duration_ms=lambda byte_length, sample_rate, channels: int(
            byte_length * 1000 / (sample_rate * channels * 2)
        )
    ),
)
sys.modules.setdefault('utils.other.hume', MagicMock())
import utils.other as _utils_other

setattr(_utils_other, 'hume', sys.modules['utils.other.hume'])
_endpoints_stub = SimpleNamespace(
    get_current_user_uid=lambda: 'test-uid',
    with_rate_limit=lambda dep, _policy: dep,
)
sys.modules.setdefault('utils.other.endpoints', _endpoints_stub)
setattr(_utils_other, 'endpoints', _endpoints_stub)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.transcript_segment import ProviderTranscriptResult, TranscriptSegment
from routers import desktop_background
from utils.stt.providers import STTProviderName, STTWorkload

sys.modules.pop('utils.stt.provider_service', None)
if 'utils.stt' in sys.modules and hasattr(sys.modules['utils.stt'], 'provider_service'):
    delattr(sys.modules['utils.stt'], 'provider_service')


def _client(monkeypatch, *, segments=None, person_embeddings_cache=None):
    app = FastAPI()
    app.include_router(desktop_background.router)
    for route in app.routes:
        if hasattr(route, 'dependant'):
            for dep in route.dependant.dependencies:
                if dep.call is not None:
                    app.dependency_overrides[dep.call] = lambda: 'test-uid'

    monkeypatch.setattr(desktop_background, 'is_trial_paywalled', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(desktop_background, 'is_hard_restricted', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(desktop_background, 'has_transcription_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(desktop_background, 'record_speech_ms', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_background, 'record_usage', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_background, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(desktop_background, 'resolve_voice_message_language', lambda _uid, language: language or 'en')
    monkeypatch.setattr(
        desktop_background.conversations_db,
        'get_conversation',
        lambda _uid, _cid: {'id': _cid, 'status': 'in_progress'},
    )
    monkeypatch.setattr(desktop_background, 'get_background_chunk_record', MagicMock(return_value=None))
    monkeypatch.setattr(
        desktop_background,
        'append_background_chunk_to_in_progress_conversation',
        MagicMock(return_value=SimpleNamespace(appended=True, duplicate=False, segments=[], chunk_record=None)),
    )
    monkeypatch.setattr(
        desktop_background,
        'finish_desktop_background_conversation',
        MagicMock(return_value={'id': 'conv-1', 'status': 'completed'}),
    )
    if not hasattr(desktop_background.redis_db, 'r'):
        monkeypatch.setattr(desktop_background.redis_db, 'r', MagicMock(), raising=False)
    monkeypatch.setattr(desktop_background.redis_db.r, 'get', lambda _key: None)
    monkeypatch.setattr(desktop_background.redis_db.r, 'set', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        desktop_background,
        '_build_person_embeddings_cache',
        lambda _uid: person_embeddings_cache or {},
    )
    monkeypatch.setattr(desktop_background, 'update_provider_run_identity_metrics', MagicMock())

    default_segments = segments or [
        TranscriptSegment(
            id='seg-1',
            text='Hello world.',
            speaker='SPEAKER_00',
            speaker_id=0,
            is_user=False,
            start=0.5,
            end=1.2,
            provider_cluster_id='A',
            provider_speaker_label='ASSEMBLYAI_SPEAKER_A',
            stt_provider='assemblyai',
            stt_model='universal-2',
        )
    ]

    def _transcribe_bytes(audio_bytes, **_kwargs):
        return SimpleNamespace(
            result=ProviderTranscriptResult(provider='assemblyai', model='universal-2', words=[], utterances=[]),
            detected_language='en',
            segments=[segment.model_copy(deep=True) for segment in default_segments],
            run_id='run-1',
        )

    mock_transcribe = MagicMock(side_effect=_transcribe_bytes)
    monkeypatch.setattr(desktop_background, 'transcribe_bytes', mock_transcribe)
    return TestClient(app), mock_transcribe


def test_desktop_capabilities_reports_assemblyai_background_when_key_available(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.setenv('ASSEMBLYAI_API_KEY', 'server-aai-key')
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.assemblyai,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is True
    assert data['provider'] == 'assemblyai'
    assert data['primary_provider'] == 'assemblyai'
    assert data['effective_provider'] == 'assemblyai'
    assert data['mode'] == 'assemblyai_primary'
    assert data['fallback_provider'] == 'deepgram'
    assert data['fallback_enabled'] is True
    assert data['fallback_available'] is True
    assert data['workload'] == 'background'
    assert data['reason'] is None


def test_desktop_capabilities_allows_background_batch_with_deepgram_fallback(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.delenv('ASSEMBLYAI_PRERECORDED_STT_FALLBACK_ENABLED', raising=False)
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.assemblyai,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is True
    assert data['provider'] == 'assemblyai'
    assert data['primary_provider'] == 'assemblyai'
    assert data['effective_provider'] == 'deepgram'
    assert data['mode'] == 'deepgram_fallback'
    assert data['fallback_provider'] == 'deepgram'
    assert data['fallback_enabled'] is True
    assert data['fallback_available'] is True
    assert data['reason'] == 'fallback_deepgram_available'


def test_desktop_capabilities_reports_missing_assemblyai_key_when_fallback_disabled(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_FALLBACK_ENABLED', 'false')
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.assemblyai,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is False
    assert data['provider'] == 'assemblyai'
    assert data['effective_provider'] is None
    assert data['mode'] == 'disabled'
    assert data['fallback_provider'] is None
    assert data['fallback_enabled'] is False
    assert data['reason'] == 'missing_assemblyai_api_key'


def test_desktop_capabilities_reports_no_usable_batch_provider_without_any_key(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.assemblyai,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is False
    assert data['primary_provider'] == 'assemblyai'
    assert data['effective_provider'] is None
    assert data['fallback_provider'] == 'deepgram'
    assert data['fallback_available'] is False
    assert data['reason'] == 'missing_assemblyai_api_key'


def test_desktop_capabilities_uses_byok_assemblyai(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.setattr(
        desktop_background, 'get_byok_key', lambda provider: 'aai-user-key' if provider == 'assemblyai' else None
    )
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.assemblyai,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is True
    assert data['effective_provider'] == 'assemblyai'
    assert data['mode'] == 'assemblyai_primary'


def test_desktop_capabilities_uses_byok_deepgram_fallback(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)
    monkeypatch.setattr(
        desktop_background, 'get_byok_key', lambda provider: 'dg-user-key' if provider == 'deepgram' else None
    )
    monkeypatch.setattr(
        desktop_background,
        'resolve_prerecorded_provider_for_request',
        lambda _workload: STTProviderName.deepgram,
    )

    response = client.get('/v2/desktop/capabilities')

    assert response.status_code == 200
    data = response.json()['background_batch']
    assert data['enabled'] is True
    assert data['effective_provider'] == 'deepgram'
    assert data['mode'] == 'deepgram_fallback'


def test_background_transcribe_returns_segments_with_offset(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=12000',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['provider'] == 'assemblyai'
    assert data['run_id'] == 'run-1'
    assert data['segments'][0]['start'] == 12.5
    assert data['segments'][0]['end'] == 13.2
    assert data['segments'][0]['speaker_id'] == 0
    assert data['segments'][0]['speaker'] == 'SPEAKER_00'


def test_finish_background_conversation_uses_explicit_conversation_id(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post('/v2/desktop/background-conversation/conv-1/finish')

    assert response.status_code == 200
    assert response.json()['id'] == 'conv-1'
    desktop_background.finish_desktop_background_conversation.assert_called_once_with('test-uid', 'conv-1')


def test_finish_background_conversation_maps_validation_error(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    desktop_background.finish_desktop_background_conversation.side_effect = (
        desktop_background.DesktopBackgroundConversationError('conversation is not in_progress', status_code=409)
    )

    response = client.post('/v2/desktop/background-conversation/conv-1/finish')

    assert response.status_code == 409
    assert response.json()['detail'] == 'conversation is not in_progress'


def test_background_transcribe_wraps_linear16_pcm_as_wav(monkeypatch):
    client, mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0&sample_rate=16000',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    audio_arg = mock_transcribe.call_args.args[0]
    assert audio_arg[:4] == b'RIFF'
    assert b'WAVE' in audio_arg[:16]
    assert mock_transcribe.call_args.kwargs['workload'].value == 'background'


def test_background_transcribe_persists_segments(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    desktop_background.append_background_chunk_to_in_progress_conversation.assert_called_once()


def test_background_transcribe_requires_chunk_id_when_persisting(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'chunk_id is required when persist=true'


def test_background_transcribe_duplicate_chunk_returns_success_without_appending(monkeypatch):
    client, mock_transcribe = _client(monkeypatch)
    payload = b'\x01\x00' * 1600
    payload_hash = desktop_background._background_chunk_payload_hash(payload, 16000, 1, 'linear16', 0)
    monkeypatch.setattr(
        desktop_background,
        'get_background_chunk_record',
        MagicMock(
            return_value={
                'payload_hash': payload_hash,
                'provider': 'assemblyai',
                'run_id': 'run-previous',
                'chunk_duration_ms': 100,
            }
        ),
    )

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=payload,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['duplicate'] is True
    assert data['segments'] == []
    assert data['provider'] == 'assemblyai'
    assert data['run_id'] == 'run-previous'
    mock_transcribe.assert_not_called()
    desktop_background.append_background_chunk_to_in_progress_conversation.assert_not_called()


def test_background_transcribe_rejects_conflicting_duplicate_chunk(monkeypatch):
    client, mock_transcribe = _client(monkeypatch)
    monkeypatch.setattr(
        desktop_background,
        'get_background_chunk_record',
        MagicMock(return_value={'payload_hash': 'different', 'provider': 'assemblyai'}),
    )

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 409
    assert response.json()['detail'] == 'chunk_id payload mismatch'
    mock_transcribe.assert_not_called()
    desktop_background.append_background_chunk_to_in_progress_conversation.assert_not_called()


def test_background_transcribe_can_skip_persist_without_conversation(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    record_speech_ms = MagicMock()
    record_usage = MagicMock()
    monkeypatch.setattr(desktop_background, 'record_speech_ms', record_speech_ms)
    monkeypatch.setattr(desktop_background, 'record_usage', record_usage)

    response = client.post(
        '/v2/desktop/background-transcribe?chunk_start_ms=0&persist=false',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    desktop_background.append_background_chunk_to_in_progress_conversation.assert_not_called()
    record_speech_ms.assert_called_once()
    record_usage.assert_called_once()


def test_cluster_speaker_mapping_assigns_distinct_ids(monkeypatch):
    segments = [
        TranscriptSegment(text='One', is_user=False, start=0.0, end=1.0, provider_cluster_id='A'),
        TranscriptSegment(text='Two', is_user=False, start=1.0, end=2.0, provider_cluster_id='B'),
    ]
    client, _mock_transcribe = _client(monkeypatch, segments=segments)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    data = response.json()
    assert [segment['speaker_id'] for segment in data['segments']] == [0, 1]
    assert [segment['speaker'] for segment in data['segments']] == ['SPEAKER_00', 'SPEAKER_01']
    assert data['speaker_diagnostics']['provider_cluster_count'] == 2
    assert data['speaker_diagnostics']['mapped_speaker_ids'] == [0, 1]


def test_background_transcribe_multi_chunk_offsets_persist_and_keep_speaker_map(monkeypatch):
    client, mock_transcribe = _client(monkeypatch)
    speaker_map_store = {}

    def _redis_get(key):
        return speaker_map_store.get(key)

    def _redis_set(key, value, **_kwargs):
        speaker_map_store[key] = value

    monkeypatch.setattr(desktop_background.redis_db.r, 'get', _redis_get)
    monkeypatch.setattr(desktop_background.redis_db.r, 'set', _redis_set)

    responses = [
        [TranscriptSegment(text='First.', is_user=False, start=0.1, end=1.0, provider_cluster_id='A')],
        [TranscriptSegment(text='Second.', is_user=False, start=0.1, end=1.0, provider_cluster_id='B')],
        [TranscriptSegment(text='Third.', is_user=False, start=0.1, end=1.0, provider_cluster_id='A')],
    ]

    def _transcribe_bytes(_audio_bytes, **_kwargs):
        return SimpleNamespace(
            result=ProviderTranscriptResult(provider='assemblyai', model='universal-2', words=[], utterances=[]),
            detected_language='en',
            segments=[segment.model_copy(deep=True) for segment in responses.pop(0)],
            run_id='run-multi',
        )

    mock_transcribe.side_effect = _transcribe_bytes

    for chunk_start_ms in (0, 14000, 28000):
        response = client.post(
            f'/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-id-{chunk_start_ms}&chunk_start_ms={chunk_start_ms}',
            content=b'\x01\x00' * 1600,
            headers={'Content-Type': 'application/octet-stream'},
        )
        assert response.status_code == 200
        assert response.json()['provider'] == 'assemblyai'

    appended_segments = [
        call.args[4][0]
        for call in desktop_background.append_background_chunk_to_in_progress_conversation.call_args_list
    ]
    assert [segment.start for segment in appended_segments] == [0.1, 14.1, 28.1]
    assert [segment.end for segment in appended_segments] == [1.0, 15.0, 29.0]
    assert [segment.speaker_id for segment in appended_segments] == [0, 1, 0]
    assert [segment.speaker for segment in appended_segments] == ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_00']


def test_background_transcribe_identifies_assemblyai_speaker_with_omi_user_embedding(monkeypatch):
    user_embedding = np.array([[1.0, 0.0]], dtype=np.float32)
    segments = [
        TranscriptSegment(
            text='This is my voice.',
            is_user=False,
            start=0.0,
            end=3.0,
            provider_cluster_id='A',
            provider_speaker_label='ASSEMBLYAI_SPEAKER_A',
            speaker_identity_state='unassigned',
            stt_provider='assemblyai',
            stt_model='universal-2',
        )
    ]
    client, _mock_transcribe = _client(
        monkeypatch,
        segments=segments,
        person_embeddings_cache={'user': {'embedding': user_embedding, 'name': 'User'}},
    )
    monkeypatch.setattr(desktop_background, 'extract_embedding_from_bytes', lambda _audio, _filename: user_embedding)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=12000',
        content=b'\x01\x00' * 16000 * 4,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 200
    data = response.json()
    segment = data['segments'][0]
    assert segment['stt_provider'] == 'assemblyai'
    assert segment['provider_cluster_id'] == 'A'
    assert segment['is_user'] is True
    assert segment['person_id'] is None
    assert segment['speaker_identity_state'] == 'user'
    assert segment['speaker_identity_source'] == 'omi_speaker_embedding'
    assert segment['speaker_identity_provenance']['provider_cluster_id'] == 'A'
    assert segment['start'] == 12.0
    desktop_background.update_provider_run_identity_metrics.assert_called_once()


def test_byok_background_routing_uses_deepgram_when_only_deepgram_key(monkeypatch):
    from utils.stt import provider_service

    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda provider: {'deepgram': 'dg-user-key'}.get(provider))

    provider = provider_service.resolve_prerecorded_provider_for_request(STTWorkload.background)

    assert provider == STTProviderName.deepgram


def test_background_transcribe_rejects_empty_body(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'',
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 400


def test_background_transcribe_rejects_stereo_pcm_for_v1(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0&channels=2',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'channels must be 1'


def test_background_transcribe_rejects_malformed_content_length(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=conv-1&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream', 'Content-Length': 'not-an-int'},
    )

    assert response.status_code == 422


def test_background_transcribe_rejects_invalid_conversation(monkeypatch):
    client, _mock_transcribe = _client(monkeypatch)
    monkeypatch.setattr(desktop_background.conversations_db, 'get_conversation', lambda _uid, _cid: None)

    response = client.post(
        '/v2/desktop/background-transcribe?conversation_id=missing&chunk_id=chunk-001&chunk_start_ms=0',
        content=b'\x01\x00' * 1600,
        headers={'Content-Type': 'application/octet-stream'},
    )

    assert response.status_code == 404
