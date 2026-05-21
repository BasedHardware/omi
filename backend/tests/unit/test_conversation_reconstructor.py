import sys
from unittest.mock import MagicMock

from models.transcript_segment import (
    ProviderTranscriptResult,
    ProviderTranscriptUtterance,
    ProviderTranscriptWord,
)
from utils.stt.conversation_reconstructor import ConversationReconstructor, reconstruct_conversation

if 'deepgram' not in sys.modules:
    sys.modules['deepgram'] = MagicMock()

from utils.stt.deepgram_adapter import normalize_deepgram_prerecorded_result


def _word(text, start, end, cluster=None, label=None):
    return ProviderTranscriptWord(
        text=text,
        start=start,
        end=end,
        provider_cluster_id=cluster,
        speaker_label=label,
    )


def test_reconstructs_word_only_provider_result_with_stable_ordering_and_cluster_metadata():
    result = ProviderTranscriptResult(
        provider='test-provider',
        model='async-model',
        words=[
            _word('later', 2.0, 2.5, cluster='cluster-b', label='SPEAKER_01'),
            _word('hello', 0.0, 0.4, cluster='cluster-a', label='SPEAKER_00'),
            _word('world.', 0.5, 1.0, cluster='cluster-a', label='SPEAKER_00'),
        ],
    )

    segments = reconstruct_conversation(result)

    assert [segment.text for segment in segments] == ['Hello world.', 'Later']
    assert segments[0].start == 0.0
    assert segments[0].end == 1.0
    assert segments[0].provider_cluster_id == 'cluster-a'
    assert segments[0].speaker == 'SPEAKER_00'
    assert segments[0].speaker_identity_state == 'unassigned'
    assert segments[0].stt_provider == 'test-provider'
    assert segments[0].stt_model == 'async-model'
    assert segments[1].provider_cluster_id == 'cluster-b'


def test_reconstructs_utterance_only_provider_result_with_explicit_unknown_identity():
    result = ProviderTranscriptResult(
        provider='assemblyai',
        utterances=[
            ProviderTranscriptUtterance(
                text='opaque speaker label',
                start=4.0,
                end=5.0,
                provider_cluster_id='speaker-a',
                speaker_label='A',
            ),
            ProviderTranscriptUtterance(text='no cluster', start=5.2, end=6.0),
        ],
    )

    segments = reconstruct_conversation(result)

    assert [segment.text for segment in segments] == ['Opaque speaker label', 'No cluster']
    assert segments[0].provider_cluster_id == 'speaker-a'
    assert segments[0].provider_speaker_label == 'A'
    assert segments[0].speaker is None
    assert segments[0].speaker_identity_state == 'unknown'
    assert segments[1].provider_cluster_id is None
    assert segments[1].speaker_identity_state == 'unknown'


def test_mixed_utterances_and_words_do_not_duplicate_words_covered_by_utterances():
    result = ProviderTranscriptResult(
        provider='mixed',
        utterances=[
            ProviderTranscriptUtterance(
                text='Hello world.',
                start=0.0,
                end=1.1,
                provider_cluster_id='0',
                speaker_label='SPEAKER_00',
            )
        ],
        words=[
            _word('Hello', 0.0, 0.4, cluster='0', label='SPEAKER_00'),
            _word('world.', 0.5, 1.1, cluster='0', label='SPEAKER_00'),
            _word('Outside.', 2.0, 2.6, cluster='1', label='SPEAKER_01'),
        ],
    )

    segments = reconstruct_conversation(result)

    assert [segment.text for segment in segments] == ['Hello world.', 'Outside.']
    assert segments[0].provider_cluster_id == '0'
    assert segments[1].provider_cluster_id == '1'


def test_reconstructor_preserves_legacy_deepgram_prerecorded_parity():
    deepgram_result = {
        'metadata': {'request_id': 'dg-request-1', 'duration': 3.25},
        'results': {
            'channels': [
                {
                    'detected_language': 'en-US',
                    'alternatives': [
                        {
                            'words': [
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
                        }
                    ],
                }
            ],
            'utterances': [
                {
                    'transcript': 'Hello world.',
                    'start': 0.0,
                    'end': 1.1,
                    'confidence': 0.9,
                    'speaker': 2,
                }
            ],
        },
    }

    result = normalize_deepgram_prerecorded_result(deepgram_result, model='nova-3')
    segments = reconstruct_conversation(result)

    assert len(segments) == 1
    assert segments[0].text == 'Hello world.'
    assert segments[0].speaker == 'SPEAKER_02'
    assert segments[0].speaker_id == 2
    assert segments[0].provider_cluster_id == '2'
    assert segments[0].provider_speaker_label == 'SPEAKER_02'
    assert segments[0].stt_provider == 'deepgram'
    assert segments[0].stt_model == 'nova-3'


def test_overlap_duplicate_candidates_keep_longer_text_once():
    reconstructor = ConversationReconstructor()
    result = ProviderTranscriptResult(
        provider='test-provider',
        utterances=[
            ProviderTranscriptUtterance(
                text='hello',
                start=0.0,
                end=1.0,
                provider_cluster_id='0',
                speaker_label='SPEAKER_00',
            ),
            ProviderTranscriptUtterance(
                text='hello there',
                start=0.5,
                end=1.5,
                provider_cluster_id='0',
                speaker_label='SPEAKER_00',
            ),
        ],
    )

    segments = reconstructor.reconstruct(result)

    assert len(segments) == 1
    assert segments[0].text == 'Hello there'
    assert segments[0].start == 0.0
    assert segments[0].end == 1.5


def test_skip_window_marks_dominant_preskip_cluster_as_user():
    result = ProviderTranscriptResult(
        provider='test-provider',
        words=[
            _word('my', 0.0, 0.2, cluster='me', label='SPEAKER_00'),
            _word('voice', 0.3, 0.6, cluster='me', label='SPEAKER_00'),
            _word('after', 3.0, 3.4, cluster='me', label='SPEAKER_00'),
            _word('guest', 3.5, 4.0, cluster='guest', label='SPEAKER_01'),
        ],
    )

    segments = reconstruct_conversation(result, skip_n_seconds=2)

    assert segments[0].text == 'After'
    assert segments[0].is_user is True
    assert segments[0].speaker_identity_state == 'user'
    assert segments[0].start == 0.0
    assert segments[1].is_user is False
