import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from models.conversation_enums import PostProcessingStatus
from utils.conversations.postprocess_conversation import _minimum_audio_duration, _transcript_span_seconds

postprocess_module = importlib.import_module('utils.conversations.postprocess_conversation')

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROUTERS_DIR = BACKEND_DIR / 'routers'


def _router_imports_of_postprocess_conversation() -> list[str]:
    """Cheap text scan: full AST over routers exceeds the fast-unit CPU budget."""
    offenders: list[str] = []
    needle = 'postprocess_conversation'
    for path in sorted(ROUTERS_DIR.rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        if needle not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if needle not in stripped:
                continue
            if stripped.startswith('import ') or stripped.startswith('from '):
                offenders.append(f'{path.relative_to(BACKEND_DIR)}:{lineno} {stripped}')
    return offenders


def test_transcript_based_minimum_duration_never_drops_below_ten_seconds():
    segments = [SimpleNamespace(start=0.0, end=15.0)]

    assert _minimum_audio_duration(segments) == 10.0


def test_transcript_based_minimum_duration_allows_the_transcript_padding_window():
    segments = [SimpleNamespace(start=0.0, end=25.0)]

    assert _minimum_audio_duration(segments) == 15.0


def test_transcript_span_uses_timestamp_extrema_not_list_order():
    segments = [
        SimpleNamespace(start=40.0, end=50.0),
        SimpleNamespace(start=0.0, end=10.0),
    ]

    assert _transcript_span_seconds(segments) == 50.0
    assert _minimum_audio_duration(segments) == 40.0


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
    status.assert_called_once_with(
        'user-1',
        'conversation-1',
        PostProcessingStatus.canceled,
        fail_reason='Audio duration is too short, seems wrong (audio_s=14.00 min_required_s=15.00).',
    )


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


def test_no_router_imports_orphaned_postprocess_conversation_util():
    """Reachability ratchet: Jules #11345 tightened a util with no live caller.

    If a router re-imports this module, restore a client contract that does not
    strip quiet-timer seconds from the WAV before upload, then update this test.
    """
    offenders = _router_imports_of_postprocess_conversation()
    assert not offenders, 'orphaned postprocess_conversation util imported by routers:\n' + '\n'.join(offenders)
