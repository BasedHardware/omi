import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

for mod_name in ['deepgram', 'deepgram.clients', 'deepgram.clients.live', 'deepgram.clients.live.v1']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock

os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')

from models.transcript_segment import ProviderTranscriptResult, ProviderTranscriptWord  # noqa: E402
from utils.stt import provider_service  # noqa: E402
from utils.stt.providers import STTProviderName, STTWorkload, get_prerecorded_provider_name  # noqa: E402


def _provider_result(provider='deepgram', model='nova-3'):
    return ProviderTranscriptResult(
        provider=provider,
        model=model,
        language='en',
        duration=2.0,
        words=[
            ProviderTranscriptWord(
                text='hello',
                start=0.0,
                end=0.4,
                provider_cluster_id='0',
                speaker_label='SPEAKER_00',
            ),
            ProviderTranscriptWord(
                text='world',
                start=0.5,
                end=1.0,
                provider_cluster_id='0',
                speaker_label='SPEAKER_00',
            ),
        ],
    )


def test_provider_service_transcribes_sync_upload_and_finalizes_deepgram_run():
    fake_provider = MagicMock()
    fake_provider.provider_name = STTProviderName.deepgram
    fake_provider.transcribe_url.return_value = (_provider_result(), 'en')

    with patch.object(provider_service, '_deepgram_prerecorded_provider', return_value=fake_provider), patch.object(
        provider_service, 'create_provider_run', return_value='run-sync'
    ) as create_run, patch.object(provider_service, 'finalize_provider_run') as finalize_run:
        response = provider_service.transcribe_url(
            'https://example.test/audio.wav',
            workload=STTWorkload.sync,
            uid='uid-1',
            conversation_id='conversation-1',
            return_language=True,
            language='multi',
            model='nova-3',
            keywords=['Omi'],
        )

    assert response.detected_language == 'en'
    assert [segment.text for segment in response.segments] == ['Hello world']
    assert response.words[0]['stt_provider'] == 'deepgram'
    fake_provider.transcribe_url.assert_called_once()
    assert fake_provider.transcribe_url.call_args.kwargs['keywords'] == ['Omi']
    create_run.assert_called_once()
    assert create_run.call_args.kwargs['workload'] == 'sync'
    finalize_run.assert_called_once()
    assert finalize_run.call_args.kwargs['run_id'] == 'run-sync'
    assert finalize_run.call_args.kwargs['provider'] == 'deepgram'
    assert finalize_run.call_args.kwargs['workload'] == 'sync'
    assert finalize_run.call_args.kwargs['status'] == 'succeeded'
    assert finalize_run.call_args.kwargs['transcript_segment_count'] == 1


def test_provider_service_finalizes_background_run_on_deepgram_default():
    fake_provider = MagicMock()
    fake_provider.provider_name = STTProviderName.deepgram
    fake_provider.transcribe_url.return_value = _provider_result()

    with patch.object(provider_service, '_deepgram_prerecorded_provider', return_value=fake_provider), patch.object(
        provider_service, 'create_provider_run', return_value='run-background'
    ), patch.object(provider_service, 'finalize_provider_run') as finalize_run:
        response = provider_service.transcribe_url(
            'https://example.test/background.wav',
            workload=STTWorkload.background,
            uid='uid-1',
            model='nova-3',
            raw_audio_seconds=9.5,
        )

    assert response.result.provider == 'deepgram'
    finalize_run.assert_called_once()
    assert finalize_run.call_args.kwargs['workload'] == 'background'
    assert finalize_run.call_args.kwargs['provider'] == 'deepgram'
    assert finalize_run.call_args.kwargs['raw_audio_seconds'] == 9.5


def test_prerecorded_ptt_and_realtime_related_workloads_stay_deepgram():
    assert get_prerecorded_provider_name(STTWorkload.ptt) == STTProviderName.deepgram
    assert get_prerecorded_provider_name(STTWorkload.voice_message) == STTProviderName.deepgram


def test_background_routing_can_select_assemblyai_without_moving_latency_critical_workloads(monkeypatch):
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync,background,postprocess,ptt,realtime')

    assert get_prerecorded_provider_name(STTWorkload.sync) == STTProviderName.assemblyai
    assert get_prerecorded_provider_name(STTWorkload.background) == STTProviderName.assemblyai
    assert get_prerecorded_provider_name(STTWorkload.postprocess) == STTProviderName.assemblyai
    assert get_prerecorded_provider_name(STTWorkload.ptt) == STTProviderName.deepgram
    assert get_prerecorded_provider_name(STTWorkload.voice_message) == STTProviderName.deepgram


def test_background_call_sites_use_provider_service_layer():
    backend_root = Path(__file__).resolve().parents[2]
    with open(backend_root / 'routers/sync.py') as f:
        sync_source = f.read()
    with open(backend_root / 'utils/conversations/postprocess_conversation.py') as f:
        postprocess_source = f.read()
    with open(backend_root / 'utils/chat.py') as f:
        chat_source = f.read()

    assert 'from utils.stt.pre_recorded import' not in sync_source
    assert 'stt_provider_service.transcribe_url' in sync_source
    assert 'workload=STTWorkload.sync' in sync_source

    assert 'from utils.stt.pre_recorded import' not in postprocess_source
    assert 'stt_provider_service.transcribe_url' in postprocess_source
    assert 'workload=STTWorkload.postprocess' in postprocess_source

    assert 'from utils.stt.pre_recorded import' not in chat_source
    assert 'workload=STTWorkload.voice_message' in chat_source
    assert 'workload=STTWorkload.ptt' in chat_source


def test_provider_service_uses_assemblyai_for_enabled_sync_workload(monkeypatch):
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync')

    fake_provider = MagicMock()
    fake_provider.provider_name = STTProviderName.assemblyai
    fake_provider.transcribe_url.return_value = (_provider_result(provider='assemblyai', model='universal-2'), 'en')

    with patch.object(provider_service, '_assemblyai_prerecorded_provider', return_value=fake_provider), patch.object(
        provider_service, 'create_provider_run', return_value='run-aai'
    ) as create_run, patch.object(provider_service, 'finalize_provider_run') as finalize_run:
        response = provider_service.transcribe_url(
            'https://example.test/audio.wav',
            workload=STTWorkload.sync,
            uid='uid-1',
            conversation_id='conversation-1',
            return_language=True,
            language='multi',
            model='nova-3',
            keywords=['Omi'],
        )

    assert response.result.provider == 'assemblyai'
    assert response.result.model == 'universal-2'
    assert response.words[0]['stt_provider'] == 'assemblyai'
    fake_provider.transcribe_url.assert_called_once()
    assert fake_provider.transcribe_url.call_args.kwargs['model'] == 'universal-2'
    create_run.assert_called_once()
    assert create_run.call_args.kwargs['provider'] == 'assemblyai'
    assert create_run.call_args.kwargs['model'] == 'universal-2'
    finalize_run.assert_called_once()
    assert finalize_run.call_args.kwargs['provider'] == 'assemblyai'
    assert finalize_run.call_args.kwargs['artifact_refs'] == {}


def test_provider_service_falls_back_to_deepgram_when_assemblyai_fails(monkeypatch):
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync')

    assemblyai_provider = MagicMock()
    assemblyai_provider.provider_name = STTProviderName.assemblyai
    assemblyai_provider.transcribe_url.side_effect = RuntimeError('AssemblyAI failed')

    deepgram_provider = MagicMock()
    deepgram_provider.provider_name = STTProviderName.deepgram
    deepgram_provider.transcribe_url.return_value = _provider_result()

    with patch.object(
        provider_service, '_assemblyai_prerecorded_provider', return_value=assemblyai_provider
    ), patch.object(provider_service, '_deepgram_prerecorded_provider', return_value=deepgram_provider), patch.object(
        provider_service, 'create_provider_run', side_effect=['run-aai', 'run-dg']
    ), patch.object(
        provider_service, 'finalize_provider_run'
    ) as finalize_run:
        response = provider_service.transcribe_url(
            'https://example.test/audio.wav',
            workload=STTWorkload.sync,
            uid='uid-1',
            conversation_id='conversation-1',
            language='multi',
            model='nova-3',
        )

    assert response.result.provider == 'deepgram'
    assert assemblyai_provider.transcribe_url.call_count == 2
    deepgram_provider.transcribe_url.assert_called_once()
    assert deepgram_provider.transcribe_url.call_args.kwargs['model'] == 'nova-3'
    assert finalize_run.call_args_list[0].kwargs['run_id'] == 'run-aai'
    assert finalize_run.call_args_list[0].kwargs['provider'] == 'assemblyai'
    assert finalize_run.call_args_list[0].kwargs['status'] == 'failed'
    assert finalize_run.call_args_list[1].kwargs['run_id'] == 'run-dg'
    assert finalize_run.call_args_list[1].kwargs['provider'] == 'deepgram'
    assert finalize_run.call_args_list[1].kwargs['fallback_count'] == 1
    assert finalize_run.call_args_list[1].kwargs['fallback_provider'] == 'assemblyai'


def test_provider_service_live_assemblyai_smoke_records_ledger_when_credentials_are_present(monkeypatch):
    api_key = os.getenv('ASSEMBLYAI_API_KEY')
    audio_url = os.getenv('ASSEMBLYAI_SMOKE_AUDIO_URL')
    if not api_key or not audio_url:
        pytest.skip('ASSEMBLYAI_API_KEY and ASSEMBLYAI_SMOKE_AUDIO_URL are required for live smoke')

    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync')

    with patch.object(provider_service, 'create_provider_run', return_value='run-aai-live') as create_run, patch.object(
        provider_service, 'finalize_provider_run'
    ) as finalize_run:
        response = provider_service.transcribe_url(
            audio_url,
            workload=STTWorkload.sync,
            uid='uid-live-smoke',
            conversation_id='conversation-live-smoke',
            language='en',
            model='nova-3',
            raw_audio_seconds=1.0,
        )

    assert response.result.provider == 'assemblyai'
    assert response.result.raw_provider_result_id
    create_run.assert_called_once()
    finalize_run.assert_called_once()
    assert finalize_run.call_args.kwargs['provider'] == 'assemblyai'
    assert finalize_run.call_args.kwargs['status'] == 'succeeded'
    assert (
        finalize_run.call_args.kwargs['artifact_refs']['provider_result_id'] == response.result.raw_provider_result_id
    )
