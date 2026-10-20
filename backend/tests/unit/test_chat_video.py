"""Chat video as stills: real FFmpeg decode, keyframe choice, storage, and the file tool's view."""

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

# Imported at collection: the fast-unit guard times the call phase, not first imports.
import utils.http_client  # noqa: F401  (prepare_video's STT semaphore)
from database import chat as chat_db
from models.chat import FileChat
from utils import encryption
from utils.media import video_frames
from utils.messaging.adapters.media import (
    VOICE_REPLY,
    ChatMediaStore,
    MediaPreparationError,
    prepare_video,
)
from utils.messaging.contracts import Artifact, InboundAttachment
from utils.other import chat_file, storage
from utils.retrieval.tools import file_tools
from utils.media.video_frames import (
    MAX_CANDIDATES,
    VideoFramesError,
    describe,
    digest_frames,
    digest_video,
    select_keyframes,
    window_sheet,
)


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _clip(tmp_path: Path, source: str, seconds: float, *extra: str) -> bytes:
    path = tmp_path / 'clip.mp4'
    subprocess.run(
        [_ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', f'{source}:duration={seconds}', *extra]
        + ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-shortest', str(path)],
        check=True,
        timeout=60,
    )
    return path.read_bytes()


def _jpeg(color, size=(64, 48)) -> bytes:
    output = BytesIO()
    Image.new('RGB', size, color).save(output, 'JPEG')
    return output.getvalue()


def test_moving_clip_yields_numbered_sheet_and_filmstrip(tmp_path):
    data = _clip(tmp_path, 'testsrc=size=320x180:rate=15', 5)
    digest = digest_video(data, executable=_ffmpeg())
    assert digest.duration == pytest.approx(5, abs=0.1)
    assert 3 <= len(digest.sheet_times) <= 6 and digest.sheet_times[0] == 0
    assert list(digest.sheet_times) == sorted(digest.sheet_times)
    # Four candidates a second over five seconds, every one in the filmstrip.
    assert len(digest.strip.times) == 20 and digest.strip.columns == 8
    with Image.open(BytesIO(digest.sheet)) as sheet:
        assert sheet.format == 'JPEG' and sheet.width <= 3 * 384 + 8
    with Image.open(BytesIO(digest.strip.jpeg)) as strip:
        assert strip.size == (8 * digest.strip.cell_width, 3 * digest.strip.cell_height)


def test_static_clip_stops_at_three_frames(tmp_path):
    data = _clip(tmp_path, 'color=c=gray:size=320x320:rate=30', 5)
    digest = digest_video(data, executable=_ffmpeg())
    assert len(digest.sheet_times) == 3


def test_long_clip_keeps_candidate_cap(tmp_path):
    data = _clip(tmp_path, 'testsrc2=size=320x180:rate=10', 200)
    digest = digest_video(data, executable=_ffmpeg())
    assert len(digest.strip.times) <= MAX_CANDIDATES and digest.strip.times[-1] <= 200


@pytest.mark.parametrize('payload', [b'not a video' * 50, b''])
def test_unreadable_or_audio_only_input_is_typed(tmp_path, payload):
    with pytest.raises(VideoFramesError):
        digest_video(payload, executable=_ffmpeg())
    audio = tmp_path / 'tone.m4a'
    subprocess.run([_ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=d=1', str(audio)], check=True)
    with pytest.raises(VideoFramesError):
        digest_video(audio.read_bytes(), executable=_ffmpeg())


def test_keyframes_prefer_change_then_time_spread():
    red, blue = Image.new('RGB', (32, 32), (255, 0, 0)), Image.new('RGB', (32, 32), (0, 0, 255))
    frames = [red] * 5 + [blue] + [red] * 5
    assert select_keyframes(frames) == [0, 5, 10]
    assert select_keyframes([red, blue]) == [0, 1]


def test_window_sheet_takes_evenly_spaced_frames_inside_the_span():
    times = [i * 0.5 for i in range(16)]
    strip = video_frames.filmstrip([Image.new('RGB', (40, 30), (i * 15, 0, 0)) for i in range(16)], times)
    sheet, chosen = window_sheet(strip.jpeg, strip.times, strip.columns, 40, 30, 2, 5)
    assert chosen[0] == 2 and chosen[-1] == 5 and len(chosen) == 6
    _, outside = window_sheet(strip.jpeg, strip.times, strip.columns, 40, 30, 30, 40)
    assert outside == (7.5,)
    with pytest.raises(VideoFramesError):
        window_sheet(strip.jpeg, strip.times, strip.columns, 400, 300, 0, 1)


def test_client_frames_are_validated():
    frames = [_jpeg((10 * i, 0, 0)) for i in range(4)]
    digest = digest_frames(frames, [0, 1, 2, 3], 3.2)
    assert digest.duration == 3.2 and digest.sheet_times[0] == 0
    with pytest.raises(VideoFramesError):
        digest_frames(frames, [0, 1, 2], 3)
    with pytest.raises(VideoFramesError):
        digest_frames(frames, [0, 2, 1, 3], 3)
    with pytest.raises(VideoFramesError):
        digest_frames([b'GIF89a' + b'0' * 20] * 4, [0, 1, 2, 3], 3)
    with pytest.raises(VideoFramesError):
        digest_frames([frames[0]] * (MAX_CANDIDATES + 1), list(range(MAX_CANDIDATES + 1)), 60)
    mixed = digest_frames([_jpeg((0, 0, 0), (64, 48)), _jpeg((255, 255, 255), (48, 64))], [0, 1], 1)
    assert mixed.strip.cell_width == mixed.strip.cell_height == 64


def test_describe_names_length_frames_and_speech():
    note = describe(5.2, (0, 1.5, 4.75), 'look at this')
    assert note.startswith('[Video, 5 s: 3 frames (0:00.0, 0:01.5, 0:04.8)')
    assert 'start_seconds' in note and note.endswith('Audio transcript: look at this]')
    assert 'No speech' in describe(130, (0, 65), '', tool_hint=False)
    assert '1:05' in describe(130, (0, 65), '') and 'search_files_tool' not in describe(1, (0,), '', tool_hint=False)


class _Media:
    def __init__(self, digest=None, transcript=''):
        self.digest, self.transcript, self.stored = digest, transcript, []

    def video_digest(self, data, hint):
        if self.digest is None:
            raise VideoFramesError('no video stream')
        return self.digest

    def transcribe(self, data, uid):
        if not self.transcript:
            raise MediaPreparationError('media_transcription', VOICE_REPLY)
        return self.transcript

    def ingest_video(self, uid, attachment, digest, transcript):
        self.stored.append(transcript)
        return Artifact('sheet', 'image/jpeg', len(digest.sheet), 'clip.jpg')


def _digest():
    return digest_frames([_jpeg((0, 0, 0)), _jpeg((255, 255, 255))], [0, 4], 4)


@pytest.mark.parametrize(
    'has_frames,transcript,expect',
    [(True, 'hello there', 'both'), (True, '', 'frames'), (False, 'hello there', 'speech'), (False, '', 'refuse')],
)
def test_channel_video_uses_frames_and_speech_independently(has_frames, transcript, expect):
    media = _Media(_digest() if has_frames else None, transcript)
    attachment = InboundAttachment('ref', 'video-note.mp4', 'video/mp4', 10, True, 4)
    if expect == 'refuse':
        with pytest.raises(MediaPreparationError) as error:
            asyncio.run(prepare_video(media, attachment, b'clip', 'u'))
        assert error.value.reply == VOICE_REPLY
        return
    artifact, note = asyncio.run(prepare_video(media, attachment, b'clip', 'u'))
    if expect == 'speech':
        assert artifact is None and note == 'hello there' and not media.stored
        return
    assert artifact.file_store_ref == 'sheet' and note.startswith('[Video, 4 s: 2 frames')
    assert ('Audio transcript: hello there' in note) == (expect == 'both')
    assert media.stored == [transcript]


def test_channel_video_is_stored_as_sheet_with_encrypted_transcript(monkeypatch):
    uploads, rows = [], []

    def create(*, file, purpose):
        name, stream = file
        uploads.append((name, purpose))
        return SimpleNamespace(id=f'oa-{len(uploads)}', filename=name)

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=create))
    monkeypatch.setattr(storage, 'upload_multi_chat_files', lambda paths, uid: {})
    monkeypatch.setattr(chat_db, 'add_multi_files', lambda uid, files: rows.extend(files))
    digest = _digest()
    artifact = ChatMediaStore().ingest_video(
        'u', InboundAttachment('ref', 'video-note.mp4', 'video/mp4'), digest, 'hello'
    )
    assert uploads == [('video-note.jpg', 'vision'), ('filmstrip.jpg', 'vision')]
    (row,) = rows
    assert artifact.name == row['name'] == 'video-note.jpg' and row['mime_type'] == 'image/jpeg'
    assert row['video']['strip_file_id'] == 'oa-2' and row['video']['frame_times'] == [0, 4]
    assert row['video']['transcript'] != 'hello'
    assert encryption.decrypt(row['video']['transcript'], 'u') == 'hello'
    assert chat_file._openai_file_ids([row]) == ['oa-1', 'oa-2']


def _video_file(strip_id='strip'):
    strip = video_frames.filmstrip([Image.new('RGB', (40, 30), (i * 20, 0, 0)) for i in range(12)], range(12))
    return (
        FileChat(
            id='f',
            name='clip.jpg',
            mime_type='image/jpeg',
            openai_file_id='sheet',
            created_at=datetime.now(timezone.utc),
            video=dict(
                duration_seconds=12,
                frame_times=[0, 6, 11],
                strip_file_id=strip_id,
                strip_times=list(strip.times),
                strip_columns=strip.columns,
                strip_cell_width=40,
                strip_cell_height=30,
                transcript=encryption.encrypt('we fixed it', 'u'),
            ),
        ),
        strip.jpeg,
    )


def test_file_tool_shows_overview_or_window_with_transcript(monkeypatch):
    file, strip = _video_file()
    reads = []

    def content(file_id):
        reads.append(file_id)
        return SimpleNamespace(read=lambda: strip if file_id == 'strip' else _jpeg((1, 2, 3)))

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(content=content))
    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'u'
    (overview,) = tool._completion_messages_sync('what happens?', [file])
    parts = overview['content']
    assert reads == ['sheet'] and parts[1]['type'] == 'text' and parts[2]['type'] == 'image_url'
    assert '3 frames (0:00.0, 0:06.0, 0:11.0)' in parts[1]['text'] and 'we fixed it' in parts[1]['text']
    assert 'search_files_tool' not in parts[1]['text']

    (closer,) = tool._completion_messages_sync('what at 3s?', [file], (2, 5))
    note = closer['content'][1]['text']
    assert reads[-1] == 'strip' and 'Frames from 2-5 s.' in note and '4 frames (0:02.0, 0:03.0, 0:04.0, 0:05.0)' in note
    assert closer['content'][2]['image_url']['url'].startswith('data:image/jpeg;base64,')

    without_strip, _ = _video_file(strip_id='')
    (fallback,) = tool._completion_messages_sync('what at 3s?', [without_strip], (2, 5))
    assert reads[-1] == 'sheet' and 'Frames from' not in fallback['content'][1]['text']


def test_async_file_messages_carry_the_video_note(monkeypatch):
    file, _ = _video_file()

    class Content:
        def read(self):
            return _jpeg((1, 2, 3))

    class Files:
        async def content(self, file_id):
            return Content()

    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: SimpleNamespace(files=Files()))
    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'u'
    (message,) = asyncio.run(tool._completion_messages('q', [file]))
    assert 'we fixed it' in message['content'][1]['text']


@pytest.mark.parametrize(
    'start,end,window', [(None, None, None), (3, None, (3.0, 8.0)), (None, 4, (0.0, 4.0)), (-2, 1, (0.0, 1.0))]
)
def test_search_files_tool_passes_the_video_window(monkeypatch, start, end, window):
    calls = []

    class Tool:
        def __init__(self, uid, session):
            pass

        def process_chat_with_file(self, question, ids, video_window=None):
            calls.append(video_window)
            return 'seen'

    monkeypatch.setattr(file_tools, 'FileChatTool', Tool)
    monkeypatch.setattr(
        file_tools.chat_db, 'get_chat_session_by_id', lambda uid, sid: dict(id=sid, file_ids=['f'], message_ids=[])
    )
    monkeypatch.setattr(file_tools, 'ChatSession', lambda **kw: SimpleNamespace(file_ids=kw['file_ids']))
    config = {'configurable': {'user_id': 'u', 'chat_session_id': 's'}}
    args = {'question': 'q', 'file_ids': ['f']}
    if start is not None:
        args['start_seconds'] = start
    if end is not None:
        args['end_seconds'] = end
    assert file_tools.search_files_tool.invoke(args, config=config) == 'seen'
    assert calls == [window]


def test_client_dump_hides_transcript_and_filmstrip():
    file, _ = _video_file()
    dumped = file.client_dump()
    assert dumped['video'] == {'duration_seconds': 12}
    assert json.dumps(dumped, default=str).count('we fixed it') == 0
