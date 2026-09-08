"""Conversation-level playback artifact: one dense MP3 per conversation + spans.

Covers the span math (wall_offset relative to started_at, artifact_offset with
inter-part gaps collapsed), the audio_files fingerprint, the /urls
conversation_audio entry states, staleness-driven re-enqueue, and the v1
duration estimate fix (PCM16 mono 16kHz = 32000 bytes/sec).

The span-math vectors here are mirrored verbatim in the Dart mapper test
(app/test/unit/audio_timeline_mapper_test.dart) so backend build and client
seek arithmetic can never drift apart.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _load_playback(request):
    cloud_tasks_module = ModuleType("utils.cloud_tasks")
    cloud_tasks_module.is_audio_merge_dispatch_enabled = MagicMock(return_value=True)
    storage_module = ModuleType("utils.other.storage")
    for name in (
        "compute_audio_files_fingerprint",
        "download_audio_chunks_and_merge",
        "download_legacy_merged_wav",
        "download_playback_artifact",
        "enqueue_conversation_artifact_build",
        "enqueue_conversation_audio_merge",
        "get_conversation_playback_signed_url",
        "get_conversation_playback_unavailable_fingerprint",
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


class _FakeAudioSegment:
    """Stands in for pydub.AudioSegment so span tests don't need ffmpeg."""

    def __init__(self, data=None, sample_width=None, frame_rate=None, channels=None):
        self.data = data

    def export(self, buf, format=None, bitrate=None):
        buf.write(b'MP3')


# ---------------------------------------------------------------------------
# build_conversation_playback_artifact — span math
# ---------------------------------------------------------------------------

# Shared vectors (mirrored in the Dart mapper test):
#   started_at = 990.0
#   part A: single chunk at ts 1000.0, PCM 320,000 bytes = 10.0s
#   part B: single chunk at ts 1200.0, PCM 160,000 bytes = 5.0s
# Expected spans:
#   A: wall_offset 10.0, artifact_offset 0.0, len 10.0
#   B: wall_offset 210.0, artifact_offset 10.0, len 5.0  (190s gap collapsed)
_PART_PCM = {1000.0: b'\x01' * 320_000, 1200.0: b'\x02' * 160_000}


def _fake_download(uid, conversation_id, timestamps, fill_gaps=True, sample_rate=16000):
    first = sorted(timestamps)[0]
    if first not in _PART_PCM:
        raise FileNotFoundError(f'no chunks at {first}')
    return _PART_PCM[first]


def test_span_math_collapses_inter_part_gap(monkeypatch):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', _fake_download)

    audio_files = [
        {'id': 'A', 'chunk_timestamps': [1000.0]},
        {'id': 'B', 'chunk_timestamps': [1200.0]},
    ]
    mp3, spans = playback.build_conversation_playback_artifact('u', 'c', audio_files, 990.0)

    assert mp3 == b'MP3'
    assert spans == [
        {'file_id': 'A', 'wall_offset': 10.0, 'artifact_offset': 0.0, 'len': 10.0},
        {'file_id': 'B', 'wall_offset': 210.0, 'artifact_offset': 10.0, 'len': 5.0},
    ]
    assert round(sum(s['len'] for s in spans), 3) == 15.0
    assert round(spans[-1]['wall_offset'] + spans[-1]['len'], 3) == 215.0


def test_parts_sorted_by_first_chunk_timestamp(monkeypatch):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', _fake_download)

    # Input deliberately unordered; spans must come out in wall order.
    audio_files = [
        {'id': 'B', 'chunk_timestamps': [1200.0]},
        {'id': 'A', 'chunk_timestamps': [1000.0]},
    ]
    _, spans = playback.build_conversation_playback_artifact('u', 'c', audio_files, 990.0)
    assert [s['file_id'] for s in spans] == ['A', 'B']


def test_missing_part_is_skipped_and_offsets_stay_contiguous(monkeypatch):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', _fake_download)

    audio_files = [
        {'id': 'A', 'chunk_timestamps': [1000.0]},
        {'id': 'GONE', 'chunk_timestamps': [1100.0]},  # not in _PART_PCM -> FileNotFoundError
        {'id': 'B', 'chunk_timestamps': [1200.0]},
    ]
    _, spans = playback.build_conversation_playback_artifact('u', 'c', audio_files, 990.0)
    assert [s['file_id'] for s in spans] == ['A', 'B']
    assert spans[1]['artifact_offset'] == 10.0  # contiguous despite the skipped part


def test_all_parts_missing_raises_file_not_found(monkeypatch):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', _fake_download)

    with pytest.raises(FileNotFoundError):
        playback.build_conversation_playback_artifact('u', 'c', [{'id': 'GONE', 'chunk_timestamps': [1.0]}], 0.0)


# ---------------------------------------------------------------------------
# /urls conversation_audio entry
# ---------------------------------------------------------------------------


def _urls_setup(monkeypatch, *, stamp=None, signed_url=None, unavailable_fp=None):
    monkeypatch.setattr(playback, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(playback, 'get_playback_artifact_signed_url', lambda uid, cid, fid: 'https://part')
    monkeypatch.setattr(playback, 'get_merged_audio_signed_url', lambda uid, cid, fid: None)
    monkeypatch.setattr(playback, 'is_playback_unavailable', lambda uid, cid, fid: False)
    monkeypatch.setattr(playback, 'enqueue_conversation_audio_merge', lambda *a, **k: None)
    monkeypatch.setattr(playback, 'compute_audio_files_fingerprint', lambda audio_files: 'fp-current')
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', lambda uid, cid: signed_url)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda uid, cid: unavailable_fp)
    enqueues = []
    monkeypatch.setattr(
        playback,
        'enqueue_conversation_artifact_build',
        lambda uid, cid, fingerprint, caller: enqueues.append((uid, cid, fingerprint, caller)),
    )
    conversation = {'conversation_audio': stamp} if stamp else {}
    return conversation, enqueues


_AUDIO_FILES = [{'id': 'A', 'duration': 1}]


def test_urls_conversation_audio_cached(monkeypatch):
    stamp = {
        'audio_files_fingerprint': 'fp-current',
        'duration': 215.0,
        'captured_duration': 15.0,
        'spans': [{'file_id': 'A', 'wall_offset': 10.0, 'artifact_offset': 0.0, 'len': 10.0}],
    }
    conversation, enqueues = _urls_setup(monkeypatch, stamp=stamp, signed_url='https://conv-mp3')

    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)

    assert result['conversation_audio'] == {
        'status': 'cached',
        'signed_url': 'https://conv-mp3',
        'content_type': 'audio/mpeg',
        'duration': 215.0,
        'captured_duration': 15.0,
        'spans': stamp['spans'],
    }
    assert result['poll_after_ms'] is None
    assert enqueues == []


def test_urls_conversation_audio_stale_fingerprint_pending_and_reenqueued(monkeypatch):
    stamp = {'audio_files_fingerprint': 'fp-old', 'duration': 1.0, 'captured_duration': 1.0, 'spans': []}
    conversation, enqueues = _urls_setup(monkeypatch, stamp=stamp, signed_url='https://conv-mp3')

    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)

    assert result['conversation_audio'] == {'status': 'pending', 'signed_url': None, 'spans': []}
    # All parts are cached, but the pending conversation artifact keeps polling alive.
    assert result['poll_after_ms'] == playback.AUDIO_URLS_POLL_AFTER_MS
    assert enqueues == [('u', 'c', 'fp-current', 'sync_urls')]


def test_urls_conversation_audio_expired_blob_pending(monkeypatch):
    # Fingerprint matches but the blob is gone (30-day lifecycle) -> pending + re-enqueue.
    stamp = {'audio_files_fingerprint': 'fp-current', 'duration': 1.0, 'captured_duration': 1.0, 'spans': []}
    conversation, enqueues = _urls_setup(monkeypatch, stamp=stamp, signed_url=None)

    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)

    assert result['conversation_audio']['status'] == 'pending'
    assert enqueues == [('u', 'c', 'fp-current', 'sync_urls')]


def test_urls_conversation_audio_unavailable_only_for_matching_fingerprint(monkeypatch):
    conversation, enqueues = _urls_setup(monkeypatch, unavailable_fp='fp-current')
    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)
    assert result['conversation_audio'] == {'status': 'unavailable', 'signed_url': None, 'spans': []}
    assert enqueues == []

    # Marker written for an older fingerprint is ignored -> pending + re-enqueue.
    conversation, enqueues = _urls_setup(monkeypatch, unavailable_fp='fp-stale')
    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)
    assert result['conversation_audio']['status'] == 'pending'
    assert enqueues == [('u', 'c', 'fp-current', 'sync_urls')]


# ---------------------------------------------------------------------------
# v1 duration estimate fix (PCM16 mono 16kHz = 32000 bytes/sec)
# ---------------------------------------------------------------------------


def test_finalize_audio_file_group_duration_uses_32000_bytes_per_second():
    # Source-structure assertion (database/conversations.py needs a live
    # Firestore client to import): 320,000 bytes must be estimated as 10.0s,
    # not the historical 20.0s from the /16000 (8kHz) constant.
    source = (BACKEND / 'database' / 'conversations.py').read_text()
    assert 'last_chunk_size / 32000.0' in source
    assert 'last_chunk_size / 16000.0' not in source


# ---------------------------------------------------------------------------
# Handler v2 source-structure assertions (routers/sync.py imports the world)
# ---------------------------------------------------------------------------


def test_conversation_merge_handler_structure():
    source = (BACKEND / 'routers' / 'sync.py').read_text()

    # v2 payloads branch to the conversation-merge handler. The dispatch runs OUTSIDE
    # the payload-parse try/except (which 200-drops invalid payloads) so transient
    # failures in _run_conversation_merge_job propagate to a 500 Cloud Tasks retry
    # instead of being masked as invalid_payload and permanently losing the artifact.
    assert "schema_version = payload.get('schema_version')" in source
    assert 'if schema_version == 2:' in source
    assert '_run_conversation_merge_job' in source
    # The v2 dispatch must come AFTER the invalid-payload except block, not inside it.
    dispatch_pos = source.index('return await _run_conversation_merge_job(payload, task_retry_count)')
    invalid_payload_pos = source.index("'reason': 'invalid_payload'")
    assert invalid_payload_pos < dispatch_pos

    # Dedicated run-lock namespace for the conversation-level build.
    assert "f'audio:{conversation_id}:conversation'" in source

    # Freshness re-check from the doc: stale payload fingerprint -> superseded ack.
    assert "'superseded'" in source

    # Upload precedes the doc stamp so a stamped fingerprint implies a servable blob.
    body = source.split('async def _run_conversation_merge_job', 1)[1]
    upload_pos = body.index('upload_conversation_playback_artifact')
    stamp_pos = body.index("'conversation_audio': {")
    assert upload_pos < stamp_pos

    # Both durations are stamped.
    assert "'captured_duration': captured_duration" in body
    assert "'duration': wall_duration" in body
