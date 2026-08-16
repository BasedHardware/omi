import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from models.conversation_enums import PostProcessingStatus
from utils.conversations.postprocess_conversation import _minimum_audio_duration

postprocess_module = importlib.import_module('utils.conversations.postprocess_conversation')


def test_transcript_based_minimum_duration_never_drops_below_ten_seconds():
    segments = [SimpleNamespace(start=0.0, end=15.0)]

    assert _minimum_audio_duration(segments) == 10.0


def test_transcript_based_minimum_duration_allows_the_transcript_padding_window():
    segments = [SimpleNamespace(start=0.0, end=25.0)]

    assert _minimum_audio_duration(segments) == 15.0


def test_postprocess_conversation_cancels_audio_shorter_than_transcript_window():
    conversation = SimpleNamespace(
        id='conversation-1',
        discarded=False,
        postprocessing=SimpleNamespace(status=PostProcessingStatus.not_started),
        transcript_segments=[SimpleNamespace(start=0.0, end=25.0)],
    )
    status = MagicMock()

    with (
        patch.object(postprocess_module, '_get_conversation_by_id', return_value={'id': 'conversation-1'}),
        patch.object(postprocess_module, 'deserialize_conversation', return_value=conversation),
        patch.object(
            postprocess_module.AudioSegment,
            'from_wav',
            return_value=SimpleNamespace(duration_seconds=14.0),
        ),
        patch.object(postprocess_module.conversations_db, 'set_postprocessing_status', status),
    ):
        result = postprocess_module.postprocess_conversation(
            'conversation-1', '/tmp/audio.wav', 'user-1', False, 'streaming-model'
        )

    assert result == (500, 'Audio duration is too short, seems wrong.')
    status.assert_called_once_with('user-1', 'conversation-1', PostProcessingStatus.canceled)


def test_postprocess_conversation_marks_allowed_audio_in_progress_before_processing():
    conversation = SimpleNamespace(
        id='conversation-1',
        discarded=False,
        postprocessing=SimpleNamespace(status=PostProcessingStatus.not_started),
        transcript_segments=[SimpleNamespace(start=0.0, end=25.0, text='hello', speaker='speaker-1')],
    )
    status = MagicMock()

    with (
        patch.object(postprocess_module, '_get_conversation_by_id', return_value={'id': 'conversation-1'}),
        patch.object(postprocess_module, 'deserialize_conversation', return_value=conversation),
        patch.object(
            postprocess_module.AudioSegment,
            'from_wav',
            return_value=SimpleNamespace(duration_seconds=15.0, frame_rate=16000),
        ),
        patch.object(postprocess_module, 'vad_is_empty', return_value=[]),
        patch.object(postprocess_module, 'upload_postprocessing_audio', side_effect=RuntimeError('stop')),
        patch.object(postprocess_module.conversations_db, 'set_postprocessing_status', status),
    ):
        result = postprocess_module.postprocess_conversation(
            'conversation-1', '/tmp/audio.wav', 'user-1', False, 'streaming-model'
        )

    assert result == (500, 'stop')
    assert status.call_args_list == [
        call('user-1', 'conversation-1', PostProcessingStatus.in_progress),
        call('user-1', 'conversation-1', PostProcessingStatus.failed, fail_reason='stop'),
    ]
