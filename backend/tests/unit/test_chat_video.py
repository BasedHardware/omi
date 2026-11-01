"""Chat video as stills: real FFmpeg decode, keyframe choice, storage, and the file tool's view."""

import asyncio
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

# Imported at collection: the fast-unit guard times the call phase, not first imports.
import utils.http_client  # noqa: F401  (prepare_video's STT semaphore)
from database import chat as chat_db
from routers import chat_video
from models.chat import FileChat
from utils import encryption
from utils.media import video_frames, video_upload
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


def test_short_clip_candidates_reach_the_end_at_most_four_per_second(tmp_path):
    digest = digest_video(_clip(tmp_path, 'testsrc=size=160x90:rate=30', 2), executable=_ffmpeg())
    times = digest.strip.times
    assert times[0] == 0 and times[-1] == pytest.approx(1.9, abs=0.05)
    assert min(b - a for a, b in zip(times, times[1:])) >= 0.25 - 0.01
    assert [video_frames.candidate_count(d) for d in (0, 0.1, 1.01, 2, 12.1, 600)] == [1, 1, 4, 8, 48, 48]


def test_static_clip_stops_at_three_frames(tmp_path):
    data = _clip(tmp_path, 'color=c=gray:size=320x320:rate=30', 5)
    digest = digest_video(data, executable=_ffmpeg())
    assert len(digest.sheet_times) == 3


def test_long_clip_keeps_candidate_cap(tmp_path):
    # Long clips decode keyframes only; -g 20 is a phone-like keyframe every 2 s.
    data = _clip(tmp_path, 'testsrc2=size=320x180:rate=10', 200, '-g', '20')
    digest = digest_video(data, executable=_ffmpeg())
    # Keyframes at least one step (199.9 / 47 s) apart on a 2 s grid: bounded, and the tail
    # falls short of the end by at most one step plus one keyframe interval.
    assert 30 <= len(digest.strip.times) <= MAX_CANDIDATES
    assert 200 - 199.9 / 47 - 2 <= digest.strip.times[-1] <= 200
    # Labels are the keyframes' own timestamps (every 2 s), never interpolated guesses.
    assert all(abs(t / 2 - round(t / 2)) < 0.01 for t in digest.strip.times)


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
    huge = BytesIO()
    Image.new('L', (4096, 2049)).save(huge, 'PNG')
    with pytest.raises(VideoFramesError, match='too large'):
        digest_frames([huge.getvalue()], [0], 1)
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


def _video_client(monkeypatch, calls):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def fake_store(uid, name, frames, times, duration, audio_path):
        calls.append((uid, name, len(frames), times, duration, audio_path and audio_path.read_bytes()))
        file, _ = _video_file()
        row = file.model_dump()
        row['size'] = 10
        return row

    monkeypatch.setattr(video_upload, 'video_from_frames', fake_store)
    app = FastAPI()
    app.include_router(chat_video.router)
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/v2/files/video')
    uid_dependency = next(d.call for d in route.dependant.dependencies if d.name == 'uid')
    app.dependency_overrides[uid_dependency] = lambda: 'u'
    return TestClient(app)


def test_device_frames_route_validates_and_hides_private_fields(monkeypatch, tmp_path):
    calls = []
    client = _video_client(monkeypatch, calls)
    frames = [('frames', (f'f{i}.jpg', _jpeg((i, 0, 0)), 'image/jpeg')) for i in range(2)]
    form = {'frame_times': '[0, 1.5]', 'duration_seconds': '2', 'name': '../clip.mov'}
    ok = client.post('/v2/files/video', files=frames + [('audio', ('a.m4a', b'aac', 'audio/mp4'))], data=form)
    assert ok.status_code == 200, ok.text
    (body,) = ok.json()
    assert body['video']['transcript'] == '' and body['video']['strip_file_id'] == ''
    assert body['video']['duration_seconds'] == 12
    ((uid, name, count, times, duration, audio),) = calls
    assert (uid, name, count, times, duration, audio) == ('u', 'clip.mov', 2, [0, 1.5], 2.0, b'aac')
    assert not list(Path(tempfile.gettempdir()).glob('*_audio'))  # temp audio removed

    for bad in ('[0]', '{"a": 1}', 'nope', '[0, true]', '[NaN, 1]', '[0, 1e999]', '[0, 1' + '0' * 400 + ']', '[-1, 1]'):
        response = client.post('/v2/files/video', files=frames, data={**form, 'frame_times': bad})
        assert response.status_code == 400, bad
    too_many = [('frames', (f'f{i}.jpg', b'x', 'image/jpeg')) for i in range(MAX_CANDIDATES + 1)]
    response = client.post(
        '/v2/files/video', files=too_many, data={**form, 'frame_times': json.dumps(list(range(MAX_CANDIDATES + 1)))}
    )
    assert response.status_code == 400 and len(calls) == 1


def test_uploaded_clip_route_maps_unreadable_video_to_400(monkeypatch, tmp_path):
    from fastapi import HTTPException

    def unreadable(uid, path, name):
        raise VideoFramesError('no video stream')

    monkeypatch.setattr(video_upload, 'video_from_file', unreadable)
    assert chat_video.is_video_upload('IMG_1.MOV', None) and chat_video.is_video_upload('x', 'video/mp4')
    assert not chat_video.is_video_upload('a.png', 'image/png')
    with pytest.raises(HTTPException) as error:
        chat_video.store_uploaded_clip('u', tmp_path / 'clip.mp4', 'clip.mp4')
    assert error.value.status_code == 400


def test_all_intra_long_clip_falls_back_to_per_target_seeks(tmp_path, monkeypatch):
    # Every frame a keyframe: the keyframe pass would decode the whole clip, so when its
    # budget runs out the sampler seeks to each target instead.
    monkeypatch.setattr(video_frames, 'KEYFRAME_PASS_SECONDS', 0.001)
    data = _clip(tmp_path, 'testsrc2=size=160x90:rate=2', 130, '-g', '1')
    digest = digest_video(data, executable=_ffmpeg())
    times = digest.strip.times
    assert len(times) >= MAX_CANDIDATES - 2 and times[-1] > 128.5 and list(times) == sorted(set(times))
    # Labels are the decoded frames' own times: a 2 fps clip only has frames every 0.5 s.
    assert all(abs(t * 2 - round(t * 2)) < 0.01 for t in times)


def test_ffmpeg_stderr_is_drained_with_a_retained_line_cap():
    import re
    import sys

    noisy = [sys.executable, '-c', 'import sys\nfor i in range(20000): sys.stderr.write(f"Stream #{i} x\\n")']
    kept = video_frames._run_keeping(noisy, re.compile(rb'Stream #'), timeout=30)
    assert len(kept) == video_frames._MAX_KEPT_LINES
    slow = [sys.executable, '-c', 'import time; time.sleep(30)']
    with pytest.raises(subprocess.TimeoutExpired):
        video_frames._run_keeping(slow, re.compile(rb'x'), timeout=1.0)


def test_video_thumbnail_is_the_opening_frame_not_the_overview(tmp_path):
    # Filmstrip: a red first cell, then a blue one.
    grid = Image.new('RGB', (128, 48), (0, 0, 255))
    grid.paste(Image.new('RGB', (64, 48), (255, 0, 0)), (0, 0))
    output = BytesIO()
    grid.save(output, 'JPEG')
    strip = video_frames.Filmstrip(jpeg=output.getvalue(), times=(0.0, 1.0), columns=2, cell_width=64, cell_height=48)
    thumbnail = tmp_path / 'sheet_thumbnail.jpeg'
    Image.new('RGB', (128, 128), (0, 255, 0)).save(thumbnail, 'JPEG')  # the overview grid's shrink

    chat_file.FileChatTool._write_poster(strip, thumbnail)

    with Image.open(thumbnail) as poster:
        assert poster.size == (64, 48)
        red, green, blue = poster.convert('RGB').getpixel((32, 24))
        assert red > 200 and green < 60 and blue < 60


def test_video_thumbnail_keeps_the_overview_when_the_strip_is_unreadable(tmp_path):
    strip = video_frames.Filmstrip(jpeg=b'not a jpeg', times=(0.0,), columns=1, cell_width=64, cell_height=48)
    thumbnail = tmp_path / 'sheet_thumbnail.jpeg'
    Image.new('RGB', (128, 128), (0, 255, 0)).save(thumbnail, 'JPEG')

    chat_file.FileChatTool._write_poster(strip, thumbnail)

    with Image.open(thumbnail) as kept:
        assert kept.size == (128, 128)
