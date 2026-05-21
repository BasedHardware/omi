import sys
from unittest.mock import MagicMock


for mod_name in ['deepgram', 'deepgram.clients', 'deepgram.clients.live', 'deepgram.clients.live.v1']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock
sys.modules['deepgram'].LiveTranscriptionEvents = MagicMock()
sys.modules['deepgram.clients.live.v1'].LiveOptions = MagicMock

from utils.stt.deepgram_adapter import (  # noqa: E402
    DeepgramPrerecordedTranscriptionProvider,
    normalize_deepgram_prerecorded_result,
    provider_result_to_legacy_words,
)
from utils.stt.providers import (  # noqa: E402
    STTProviderName,
    STTWorkload,
    get_prerecorded_provider_name,
    get_streaming_provider_name,
)


def _deepgram_fixture(words=None, utterances=None):
    return {
        'metadata': {'request_id': 'dg-request-1', 'duration': 3.25},
        'results': {
            'channels': [
                {
                    'detected_language': 'en-US',
                    'alternatives': [
                        {
                            'words': (
                                words
                                if words is not None
                                else [
                                    {
                                        'word': 'hello',
                                        'punctuated_word': 'Hello',
                                        'start': 0.0,
                                        'end': 0.4,
                                        'confidence': 0.91,
                                        'speaker': 2,
                                    },
                                    {
                                        'word': 'world',
                                        'punctuated_word': 'world.',
                                        'start': 0.5,
                                        'end': 1.1,
                                        'confidence': 0.88,
                                        'speaker': 2,
                                    },
                                ]
                            ),
                        }
                    ],
                }
            ],
            'utterances': (
                utterances
                if utterances is not None
                else [
                    {
                        'transcript': 'Hello world.',
                        'start': 0.0,
                        'end': 1.1,
                        'confidence': 0.9,
                        'speaker': 2,
                    }
                ]
            ),
        },
    }


def test_deepgram_fixture_normalizes_to_provider_transcript_result():
    result = normalize_deepgram_prerecorded_result(_deepgram_fixture(), model='nova-3')

    assert result.provider == STTProviderName.deepgram.value
    assert result.model == 'nova-3'
    assert result.language == 'en'
    assert result.duration == 3.25
    assert result.raw_provider_result_id == 'dg-request-1'
    assert len(result.words) == 2
    assert result.words[0].text == 'Hello'
    assert result.words[0].provider_cluster_id == '2'
    assert result.words[0].speaker_label == 'SPEAKER_02'
    assert result.utterances[0].provider_cluster_id == '2'


def test_deepgram_result_converts_to_legacy_words_for_existing_callers():
    result = normalize_deepgram_prerecorded_result(_deepgram_fixture(), model='nova-3')

    words = provider_result_to_legacy_words(result)

    assert words == [
        {
            'timestamp': [0.0, 0.4],
            'speaker': 'SPEAKER_02',
            'provider_cluster_id': '2',
            'provider_speaker_label': 'SPEAKER_02',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
            'text': 'Hello',
        },
        {
            'timestamp': [0.5, 1.1],
            'speaker': 'SPEAKER_02',
            'provider_cluster_id': '2',
            'provider_speaker_label': 'SPEAKER_02',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
            'text': 'world.',
        },
    ]


def test_deepgram_adapter_preserves_prerecorded_request_options():
    fake_response = MagicMock()
    fake_response.to_dict.return_value = _deepgram_fixture()
    fake_rest = MagicMock()
    fake_rest.transcribe_url.return_value = fake_response
    fake_client = MagicMock()
    fake_client.listen.rest.v.return_value = fake_rest
    provider = DeepgramPrerecordedTranscriptionProvider(lambda: fake_client, timeout=MagicMock())

    result, detected_language = provider.transcribe_url(
        'https://example.test/audio.wav',
        return_language=True,
        diarize=False,
        language='multi',
        model='nova-3',
        keywords=['Omi', 'custom'],
    )

    call_args = fake_rest.transcribe_url.call_args
    assert call_args.args[0] == {'url': 'https://example.test/audio.wav'}
    assert call_args.args[1]['diarize'] is False
    assert call_args.args[1]['detect_language'] is True
    assert call_args.args[1]['keyterm'] == ['Omi', 'custom']
    assert 'language' not in call_args.args[1]
    assert result.provider == 'deepgram'
    assert detected_language == 'en'


def test_provider_routing_keeps_all_current_workloads_on_deepgram():
    assert get_streaming_provider_name(STTWorkload.ptt) == STTProviderName.deepgram
    assert get_streaming_provider_name(STTWorkload.realtime) == STTProviderName.deepgram

    for workload in [
        STTWorkload.background,
        STTWorkload.postprocess,
        STTWorkload.ptt,
        STTWorkload.sync,
        STTWorkload.voice_message,
    ]:
        assert get_prerecorded_provider_name(workload) == STTProviderName.deepgram
