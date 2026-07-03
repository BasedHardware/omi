import asyncio
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _load_playback(request):
    cloud_tasks_module = ModuleType("utils.cloud_tasks")
    cloud_tasks_module.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)
    storage_module = ModuleType("utils.other.storage")
    for name in (
        "download_audio_chunks_and_merge",
        "download_legacy_merged_wav",
        "download_playback_artifact",
        "enqueue_conversation_audio_merge",
        "get_merged_audio_signed_url",
        "get_or_create_merged_audio",
        "get_playback_artifact_signed_url",
        "is_playback_unavailable",
    ):
        setattr(storage_module, name, MagicMock())
    storage_module._PRECACHE_FILE_SEM = MagicMock()
    with stub_modules({"utils.cloud_tasks": cloud_tasks_module, "utils.other.storage": storage_module}):
        module = load_module_fresh("utils.sync.playback", os.path.join(str(BACKEND), "utils", "sync", "playback.py"))
        request.module.playback = module
        yield


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


class FakeFuture:
    def __init__(self, result=None):
        self._result = result
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)
        callback(self)

    def result(self):
        return self._result


async def _response_body(response):
    body = b''
    async for chunk in response.body_iterator:
        body += chunk
    return body


def test_parse_range_header_variants():
    assert playback.parse_range_header("bytes=0-4", 10) == (0, 4)
    assert playback.parse_range_header("bytes=5-", 10) == (5, 9)
    assert playback.parse_range_header("bytes=-3", 10) == (7, 9)
    assert playback.parse_range_header("bytes=8-99", 10) == (8, 9)
    assert playback.parse_range_header("items=0-1", 10) is None
    assert playback.parse_range_header("bytes=10-11", 10) is None
    assert playback.parse_range_header("bytes=8-7", 10) is None
    assert playback.parse_range_header("bytes=nope", 10) is None


def test_artifact_urls_shapes_and_enqueue(monkeypatch):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(
        playback,
        'get_playback_artifact_signed_url',
        lambda uid, conversation_id, audio_file_id: {'mp3': 'https://mp3'}.get(audio_file_id),
    )
    monkeypatch.setattr(
        playback,
        'get_merged_audio_signed_url',
        lambda uid, conversation_id, audio_file_id: {'legacy': 'https://wav'}.get(audio_file_id),
    )
    monkeypatch.setattr(
        playback,
        'is_playback_unavailable',
        lambda uid, conversation_id, audio_file_id: audio_file_id == 'gone',
    )
    enqueues = []
    monkeypatch.setattr(
        playback,
        'enqueue_conversation_audio_merge',
        lambda uid, conversation_id, audio_files, caller: enqueues.append((uid, conversation_id, audio_files, caller)),
    )

    result = playback.get_audio_signed_urls(
        'u',
        'c',
        [
            {'id': 'mp3', 'duration': 1},
            {'id': 'legacy', 'duration': 2},
            {'id': 'gone', 'duration': 3},
            {'id': 'pending', 'duration': 4},
        ],
    )

    assert result == {
        "audio_files": [
            {
                "id": "mp3",
                "status": "cached",
                "signed_url": "https://mp3",
                "content_type": "audio/mpeg",
                "duration": 1,
            },
            {
                "id": "legacy",
                "status": "cached",
                "signed_url": "https://wav",
                "content_type": "audio/wav",
                "duration": 2,
            },
            {"id": "gone", "status": "unavailable", "signed_url": None, "duration": 3},
            {"id": "pending", "status": "pending", "signed_url": None, "duration": 4},
        ],
        "poll_after_ms": playback.AUDIO_URLS_POLL_AFTER_MS,
    }
    assert enqueues == [('u', 'c', [{'id': 'pending', 'duration': 4}], 'sync_urls')]


def test_inline_urls_first_sync_remaining_background_and_no_content_type(monkeypatch):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: False)
    calls_by_id = {}

    def fake_signed_url(uid, conversation_id, audio_file_id):
        calls_by_id[audio_file_id] = calls_by_id.get(audio_file_id, 0) + 1
        if audio_file_id == 'cached':
            return 'https://cached'
        if audio_file_id == 'first' and calls_by_id[audio_file_id] > 1:
            return 'https://first'
        return None

    precache_calls = []
    scheduled = []
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', fake_signed_url)
    monkeypatch.setattr(
        playback,
        'precache_audio_file',
        lambda uid, conversation_id, audio_file, caller='precache_endpoint', fill_gaps=True: precache_calls.append(
            (audio_file['id'], caller)
        ),
    )
    monkeypatch.setattr(playback, 'submit_with_context', lambda executor, fn, *args, **kwargs: scheduled.append(fn))

    result = playback.get_audio_signed_urls(
        'u',
        'c',
        [
            {'id': 'cached', 'duration': 1},
            {'id': 'first', 'duration': 2},
            {'id': 'later', 'duration': 3},
        ],
    )

    assert result == {
        "audio_files": [
            {"id": "cached", "status": "cached", "signed_url": "https://cached", "duration": 1},
            {"id": "first", "status": "cached", "signed_url": "https://first", "duration": 2},
            {"id": "later", "status": "pending", "signed_url": None, "duration": 3},
        ]
    }
    assert 'content_type' not in result['audio_files'][0]
    assert precache_calls == [('first', 'sync_urls_first')]
    assert len(scheduled) == 1

    def immediate_submit(executor, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return FakeFuture()

    monkeypatch.setattr(playback, 'submit_with_context', immediate_submit)
    scheduled[0]()
    assert precache_calls == [('first', 'sync_urls_first'), ('later', 'sync_urls_bg')]


def test_precache_service_no_audio_dispatch_and_inline(monkeypatch):
    assert playback.precache_audio_files('u', 'c', []) == {
        "status": "no_audio",
        "message": "No audio files in conversation",
    }

    enqueues = []
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(
        playback,
        'enqueue_conversation_audio_merge',
        lambda uid, conversation_id, audio_files, caller: enqueues.append((audio_files, caller)),
    )
    audio_files = [{'id': 'a', 'chunk_timestamps': [1.0]}]
    assert playback.precache_audio_files('u', 'c', audio_files) == {"status": "started", "audio_file_count": 1}
    assert enqueues == [(audio_files, 'precache_endpoint')]

    precache_calls = []
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(
        playback,
        'precache_audio_file',
        lambda uid, conversation_id, audio_file, caller='precache_endpoint': precache_calls.append(
            (audio_file['id'], caller)
        ),
    )

    def immediate_submit(executor, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return FakeFuture()

    monkeypatch.setattr(playback, 'submit_with_context', immediate_submit)
    assert playback.precache_audio_files('u', 'c', audio_files) == {"status": "started", "audio_file_count": 1}
    assert precache_calls == [('a', 'precache_endpoint')]


def test_download_artifact_mp3_legacy_and_miss(monkeypatch):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(playback, 'download_playback_artifact', lambda *args: b'mp3')
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', lambda *args: None)
    monkeypatch.setattr(playback, 'download_legacy_merged_wav', lambda *args: None)
    enqueues = []
    monkeypatch.setattr(playback, 'enqueue_conversation_audio_merge', lambda *args, **kwargs: enqueues.append(args))

    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest(), 'wav'
    )
    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    assert response.media_type == 'audio/mpeg'
    assert response.headers['content-length'] == '3'
    assert 'conversation_c_audio_a.mp3' in response.headers['content-disposition']
    assert enqueues == []

    monkeypatch.setattr(playback, 'download_playback_artifact', lambda *args: None)
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', lambda *args: 'https://legacy')
    monkeypatch.setattr(playback, 'download_legacy_merged_wav', lambda *args: b'wav')
    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest(), 'wav'
    )
    assert response.media_type == 'audio/wav'
    assert 'conversation_c_audio_a.wav' in response.headers['content-disposition']

    get_or_create_calls = []
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', lambda *args: None)
    monkeypatch.setattr(
        playback, 'get_or_create_merged_audio', lambda *args, **kwargs: get_or_create_calls.append(args)
    )
    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest(), 'wav'
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert response.body == b'{"status":"pending","poll_after_ms":3000}'
    assert len(enqueues) == 1
    assert get_or_create_calls == []


def test_download_inline_wav_pcm_and_ranges(monkeypatch):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: False)
    get_or_create_calls = []
    merge_calls = []

    def fake_get_or_create(**kwargs):
        get_or_create_calls.append(kwargs)
        return b'abcdef', False

    def fake_merge(*args, **kwargs):
        merge_calls.append((args, kwargs))
        return b'pcm'

    monkeypatch.setattr(playback, 'get_or_create_merged_audio', fake_get_or_create)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', fake_merge)

    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest({'Range': 'bytes=1-3'}), 'wav'
    )
    assert response.status_code == 206
    assert response.media_type == 'audio/wav'
    assert response.headers['content-length'] == '3'
    assert response.headers['content-range'] == 'bytes 1-3/6'
    assert asyncio.run(_response_body(response)) == b'bcd'
    assert get_or_create_calls[0]['caller'] == 'sync_download'

    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest({'Range': 'bytes=99-100'}), 'wav'
    )
    assert response.status_code == 416
    assert response.headers['content-range'] == 'bytes */6'

    response = playback.download_audio_file_response(
        'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest(), 'pcm'
    )
    assert response.status_code == 200
    assert response.media_type == 'application/octet-stream'
    assert merge_calls == [(('u', 'c', [1.0]), {'fill_gaps': True, 'sample_rate': playback.AUDIO_SAMPLE_RATE})]


def test_download_errors_preserve_contract(monkeypatch):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: False)
    with pytest.raises(HTTPException) as exc:
        playback.download_audio_file_response('u', 'c', 'a', {'id': 'a'}, FakeRequest(), 'wav')
    assert exc.value.status_code == 500
    assert exc.value.detail == "Audio file has no chunk timestamps"

    monkeypatch.setattr(
        playback, 'get_or_create_merged_audio', lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError)
    )
    with pytest.raises(HTTPException) as exc:
        playback.download_audio_file_response(
            'u', 'c', 'a', {'id': 'a', 'chunk_timestamps': [1.0]}, FakeRequest(), 'wav'
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Audio chunks not found in storage"


def test_build_playback_artifact_encodes_mp3(monkeypatch):
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', lambda *args, **kwargs: b'\0\0' * 10)

    class FakeSegment:
        def __init__(self, data, sample_width, frame_rate, channels):
            assert data == b'\0\0' * 10
            assert sample_width == 2
            assert frame_rate == playback.AUDIO_SAMPLE_RATE
            assert channels == 1

        def export(self, buf, format, bitrate):
            assert format == 'mp3'
            assert bitrate == '48k'
            buf.write(b'mp3-data')

    monkeypatch.setattr(playback, 'AudioSegment', FakeSegment)
    assert playback.build_playback_artifact('u', 'c', [1.0]) == b'mp3-data'

    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', lambda *args, **kwargs: b'')
    assert playback.build_playback_artifact('u', 'c', [1.0]) == b''
