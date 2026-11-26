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
from fastapi import HTTPException

import database.conversations as conversations_db
from utils import plugin_backup_audio as backup
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
        "list_audio_chunks",
    ):
        setattr(storage_module, name, MagicMock())
    storage_module._PRECACHE_FILE_SEM = MagicMock()
    storage_module.get_playback_failure_retry_epoch = MagicMock(return_value=None)
    storage_module.is_playback_unavailable.return_value = False
    with stub_modules({"utils.cloud_tasks": cloud_tasks_module, "utils.other.storage": storage_module}):
        module = load_module_fresh("utils.sync.playback", os.path.join(str(BACKEND), "utils", "sync", "playback.py"))
        request.module.playback = module
        with stub_modules({'utils.sync.playback': module}):
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


def _fake_download(uid, conversation_id, timestamps, fill_gaps=True, sample_rate=16000, *, raw_memo=None):
    first = sorted(timestamps)[0]
    if first not in _PART_PCM:
        raise FileNotFoundError(f'no chunks at {first}')
    return _PART_PCM[first]


def test_span_math_collapses_inter_part_gap(monkeypatch):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    download = MagicMock(wraps=_fake_download)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', download)

    audio_files = [
        {'id': 'A', 'chunk_timestamps': [1000.0]},
        {'id': 'B', 'chunk_timestamps': [1200.0]},
    ]
    mp3, spans = playback.build_conversation_playback_artifact('u', 'c', audio_files, 990.0)

    first_read, second_read = download.call_args_list
    assert first_read.kwargs['raw_memo'] is not None
    assert first_read.kwargs['raw_memo'] is second_read.kwargs['raw_memo']
    assert mp3 == b'MP3'
    assert spans == [
        {'file_id': 'A', 'wall_offset': 10.0, 'artifact_offset': 0.0, 'len': 10.0},
        {'file_id': 'B', 'wall_offset': 210.0, 'artifact_offset': 10.0, 'len': 5.0},
    ]
    assert round(sum(s['len'] for s in spans), 3) == 15.0
    assert round(spans[-1]['wall_offset'] + spans[-1]['len'], 3) == 215.0


@pytest.mark.parametrize('equal_start', [False, True])
def test_parts_sorted_by_first_chunk_timestamp(monkeypatch, equal_start):
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', _fake_download)

    # Input deliberately unordered; spans must come out in wall order.
    audio_files = [
        {'id': 'B', 'chunk_timestamps': [1000.0 if equal_start else 1200.0]},
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


def test_null_recording_pieces_stay_on_the_legacy_playback_path(monkeypatch):
    # Rows written through the Conversation model carry recording_pieces: None; they are not v3.
    from utils.conversations.v3 import audio

    stamp = {'audio_files_fingerprint': 'fp-current', 'duration': 1.0, 'captured_duration': 1.0, 'spans': []}
    conversation, enqueues = _urls_setup(monkeypatch, stamp=stamp, signed_url='https://conv-mp3')
    conversation['recording_pieces'] = None
    monkeypatch.setattr(audio, 'playback_snapshot', lambda *a: pytest.fail('ordinary row took the v3 path'))
    result = playback.get_audio_signed_urls('u', 'c', _AUDIO_FILES, conversation=conversation)
    assert result['conversation_audio']['status'] == 'cached'
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
    audio_file = conversations_db._finalize_audio_file_group(
        'uid', 'conversation', [{'timestamp': 1000.0, 'size': 320000}], []
    )
    assert audio_file.duration == 10.0


def test_finalize_audio_file_group_handles_explicit_none_size():
    # A legacy chunk dict can carry an explicit `size: None` (not merely a
    # missing key), which a bare `.get('size', 0)` default does not catch --
    # `None > 0` then raises TypeError and aborts the whole conversation's
    # audio finalization. Falls back to the same 5.0s estimate as a missing
    # or zero size.
    chunk_group = [
        {'timestamp': 1000.0, 'size': 5000},
        {'timestamp': 1005.0, 'size': None},
    ]
    audio_file = conversations_db._finalize_audio_file_group('uid', 'conversation', chunk_group, [])
    assert audio_file.duration == 10.0


# ---------------------------------------------------------------------------
# capture-skew playback timing: persisted normalized starts drive wall offsets
# ---------------------------------------------------------------------------


def _chunk(timestamp, playback_start=..., samples=160000):
    span = {'start': timestamp, 'samples': samples, 'sample_rate': 16000}
    if playback_start is not ...:
        span['playback_start'] = playback_start
    return {'timestamp': timestamp, 'path': f'chunks/u/c/{timestamp}.opus', 'size': 3200, 'span': span}


def test_finalize_audio_file_group_sets_playback_start_when_every_chunk_carries_it():
    audio_file = conversations_db._finalize_audio_file_group(
        'uid',
        'conversation',
        [_chunk(1171.0, playback_start=1000.0), _chunk(1201.0, playback_start=1030.0)],
        [],
    )

    assert audio_file.playback_start == 1000.0
    assert audio_file.chunk_timestamps == [1171.0, 1201.0]  # raw keys unchanged


def test_finalize_audio_file_group_drops_playback_start_when_a_chunk_lacks_it():
    # One legacy chunk in the group leaves the part's wall basis undefined —
    # mixing clocks would misplace every chunk after it.
    audio_file = conversations_db._finalize_audio_file_group(
        'uid',
        'conversation',
        [_chunk(1171.0, playback_start=1000.0), _chunk(1201.0)],
        [],
    )

    assert audio_file.playback_start is None
    assert audio_file.chunk_spans is not None


def test_finalize_audio_file_group_without_spans_has_no_playback_start():
    audio_file = conversations_db._finalize_audio_file_group(
        'uid',
        'conversation',
        [{'timestamp': 1000.0, 'size': 3200}, {'timestamp': 1005.0, 'size': 3200}],
        [],
    )

    assert audio_file.playback_start is None


def test_skewed_part_wall_offset_uses_persisted_playback_start(monkeypatch):
    """A +171 s skewed private-cloud chunk yields wall_offset ~0, not ~171.

    Chunk keys stay on the raw capture clock; the part's persisted normalized
    playback start is what the conversation's server-clock started_at compares
    against. A part without the persisted basis keeps the legacy raw math.
    """
    pcm = {1171.0: b'\x01' * 320_000, 1300.0: b'\x02' * 320_000}

    def fake_download(uid, conversation_id, timestamps, fill_gaps=True, sample_rate=16000, *, raw_memo=None):
        first = sorted(timestamps)[0]
        if first not in pcm:
            raise FileNotFoundError(f'no chunks at {first}')
        return pcm[first]

    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, 'download_audio_chunks_and_merge', fake_download)

    audio_files = [
        # Skewed capture: raw keys at +171 s, normalized start persisted.
        {'id': 'SKEWED', 'chunk_timestamps': [1171.0], 'playback_start': 1000.0},
        # Legacy capture on the same conversation: no persisted basis.
        {'id': 'LEGACY', 'chunk_timestamps': [1300.0]},
    ]
    _mp3, spans = playback.build_conversation_playback_artifact('u', 'c', audio_files, 1000.0)

    assert spans == [
        {'file_id': 'SKEWED', 'wall_offset': 0.0, 'artifact_offset': 0.0, 'len': 10.0},
        {'file_id': 'LEGACY', 'wall_offset': 300.0, 'artifact_offset': 10.0, 'len': 10.0},
    ]


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
    upload_pos = body.index('playback_build.ensure_conversation_artifact')
    stamp_pos = body.index("'conversation_audio': {")
    assert upload_pos < stamp_pos

    # Both durations are stamped.
    assert "'captured_duration': captured_duration" in body
    assert "'duration': wall_duration" in body


def _v3_fixture(monkeypatch):
    from datetime import datetime, timezone
    from copy import deepcopy
    from utils.conversations.v3 import audio

    at = datetime.fromtimestamp(1000, timezone.utc)
    source = {'id': 'file', 'chunk_timestamps': [1000.0], 'duration': 10}
    row = {
        'id': 'c',
        'started_at': at,
        'audio_files': [{**source, 'id': 'alias', 'recording_id': 'r', 'recording_file_id': 'file'}],
        'recording_pieces': [
            {'recording_id': 'r', 'audio_file_id': 'file', 'start': a, 'end': b} for a, b in [(1, 3), (6, 8)]
        ],
    }
    recording = {'id': 'r', 'recording': True, 'claims': [{'conversation_id': 'c'}], 'audio_files': [source]}
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid: deepcopy({'c': row, 'r': recording}.get(cid))
    )
    return audio, row, recording


def test_v3_dense_artifact_trims_pieces_and_neighbour_speech(monkeypatch):
    audio, row, recording = _v3_fixture(monkeypatch)
    captured = []

    class CaptureSegment(_FakeAudioSegment):
        def export(self, buf, **kw):
            captured.append(self.data)
            super().export(buf, **kw)

    monkeypatch.setattr(playback, 'AudioSegment', CaptureSegment)
    pcm = b''.join(bytes([i]) * 32000 for i in range(10))
    monkeypatch.setattr(playback, '_merge_playback_sources', lambda *a: pcm)
    snapshot = audio.playback_snapshot('u', row)
    _, spans = audio.build_artifact('u', snapshot)
    assert captured == [pcm[32000:96000] + pcm[192000:256000]]
    assert spans == [
        {'file_id': 'file', 'wall_offset': 1.0, 'artifact_offset': 0.0, 'len': 2.0},
        {'file_id': 'file', 'wall_offset': 6.0, 'artifact_offset': 2.0, 'len': 2.0},
    ]
    assert sum(s['len'] for s in spans) == 4
    # Deletions use the recording clock and must invalidate and trim the artifact.
    from datetime import timedelta

    recording['deleted_spans'] = [
        {'start': row['started_at'] + timedelta(seconds=2), 'end': row['started_at'] + timedelta(seconds=3)}
    ]
    changed = audio.playback_snapshot('u', row)
    assert changed['_v3_playback_fingerprint'] != snapshot['_v3_playback_fingerprint']
    _, spans = audio.build_artifact('u', changed)
    assert sum(s['len'] for s in spans) == 3
    row['recording_pieces'][0]['end'] = 2.5
    assert audio.playback_snapshot('u', row)['_v3_playback_fingerprint'] != changed['_v3_playback_fingerprint']


@pytest.mark.parametrize('cached', [False, True])
def test_v3_urls_only_serves_conversation_artifact(monkeypatch, cached):
    audio, row, _ = _v3_fixture(monkeypatch)
    fingerprint = audio.playback_snapshot('u', row)['_v3_playback_fingerprint']
    if cached:
        row.update(
            conversation_audio={'audio_files_fingerprint': fingerprint, 'spans': []},
            conversation_audio_artifact_fingerprint=fingerprint,
        )
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', lambda *a, **kw: 'exact')
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *a: None)
    monkeypatch.setattr(playback, 'get_playback_artifact_signed_url', lambda *a: pytest.fail('covering file leaked'))
    enqueues = []
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', lambda *a, **kw: enqueues.append(a))
    result = playback.get_audio_signed_urls('u', 'c', row['audio_files'], row)
    assert result['audio_files'] == (
        [] if cached else [{'id': 'alias', 'status': 'pending', 'signed_url': None, 'duration': 10}]
    )
    if not cached:
        assert result['audio_files'] and all(
            f['status'] == 'pending' and not f['signed_url'] for f in result['audio_files']
        )
        assert result['poll_after_ms']
    assert result['conversation_audio']['status'] == ('cached' if cached else 'pending')
    assert bool(enqueues) is not cached


def test_v3_missing_recording_piece_does_not_hide_playable_piece(monkeypatch):
    audio, row, _ = _v3_fixture(monkeypatch)
    row['recording_pieces'].append({'recording_id': 'gone', 'audio_file_id': 'gone', 'start': 0, 'end': 2})
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, '_merge_playback_sources', lambda *a: b'\0' * 320000)
    _, spans = audio.build_artifact('u', audio.playback_snapshot('u', row))
    assert sum(s['len'] for s in spans) == 4


def test_backup_manifest_uses_exact_artifact_or_pending(monkeypatch):
    from types import SimpleNamespace

    _, row, _ = _v3_fixture(monkeypatch)
    monkeypatch.setattr(backup, 'get_conversation', lambda *a: row)
    monkeypatch.setattr(
        backup, 'plugin_transport', lambda *a: SimpleNamespace(decode=lambda *a: {'sub': 'u', 'conversation_id': 'c'})
    )
    monkeypatch.setattr(backup, 'enforce_account_deletion_http_access', lambda *a: None)
    monkeypatch.setattr(backup, 'get_available_app_by_id', lambda *a: True)
    monkeypatch.setattr(backup, 'is_user_app_enabled', lambda *a: True)
    monkeypatch.setattr(backup, 'get_audio_signed_urls', playback.get_audio_signed_urls)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *a: None)
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', lambda *a, **kw: None)
    result = backup.backup_audio_manifest('plugin', 'c', 'Bearer synthetic')
    assert result['audio_files'][0]['status'] == 'pending'
    assert result['audio_files'][0]['signed_url'] is None
    assert result['poll_after_ms']
    assert result['conversation_audio']['status'] == 'pending'


def test_v3_download_never_returns_covering_recording(monkeypatch):
    from types import SimpleNamespace

    _, row, _ = _v3_fixture(monkeypatch)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *a: None)
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', lambda *a, **kw: None)
    monkeypatch.setattr(playback, '_get_artifact_download_payload', lambda *a, **kw: pytest.fail('covering audio'))
    result = playback.download_audio_file_response(
        'u', 'c', 'alias', row['audio_files'][0], SimpleNamespace(headers={}), 'wav'
    )
    assert result.status_code == 202


@pytest.mark.parametrize(
    'url, status',
    [
        ('https://storage.googleapis.com/synthetic/conversation-exact.mp3?X-Goog-Signature=x', 307),
        ('https://elsewhere.example/conversation-exact.mp3', 502),
        ('http://storage.googleapis.com/synthetic/conversation-exact.mp3', 502),
    ],
)
def test_v3_download_redirects_only_to_cloud_storage(monkeypatch, url, status):
    from types import SimpleNamespace

    _, row, _ = _v3_fixture(monkeypatch)
    monkeypatch.setattr(
        playback,
        'get_audio_signed_urls',
        lambda *a, **kw: {'conversation_audio': {'status': 'cached', 'signed_url': url}},
    )
    try:
        result = playback.download_audio_file_response(
            'u', 'c', 'alias', row['audio_files'][0], SimpleNamespace(headers={}), 'wav'
        )
    except HTTPException as exc:
        result = SimpleNamespace(status_code=exc.status_code, headers={})
    assert result.status_code == status
    if status == 307:
        assert result.headers['location'] == url


def test_cached_backup_artifact_keeps_legacy_audio_files_protocol(monkeypatch):
    from types import SimpleNamespace

    audio, row, _ = _v3_fixture(monkeypatch)
    fingerprint = audio.playback_snapshot('u', row)['_v3_playback_fingerprint']
    row.update(
        conversation_audio={'audio_files_fingerprint': fingerprint, 'spans': []},
        conversation_audio_artifact_fingerprint=fingerprint,
    )
    monkeypatch.setattr(backup, 'get_conversation', lambda *a: row)
    monkeypatch.setattr(
        backup, 'plugin_transport', lambda *a: SimpleNamespace(decode=lambda *a: {'sub': 'u', 'conversation_id': 'c'})
    )
    monkeypatch.setattr(backup, 'enforce_account_deletion_http_access', lambda *a: None)
    monkeypatch.setattr(backup, 'get_available_app_by_id', lambda *a: True)
    monkeypatch.setattr(backup, 'is_user_app_enabled', lambda *a: True)
    monkeypatch.setattr(backup, 'get_audio_signed_urls', playback.get_audio_signed_urls)
    url = 'https://storage.googleapis.com/synthetic/conversation-exact.mp3?token=short-lived'
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', lambda *a, **kw: url)
    result = backup.backup_audio_manifest('plugin', 'c', 'Bearer synthetic')
    assert len(result['audio_files']) == 1
    assert result['audio_files'][0]['signed_url'] == url
    assert result['audio_files'][0]['content_type'] == 'audio/mpeg'
    assert result['audio_files'][0]['id'].startswith('conversation-')
    assert result['audio_files'][0]['id'] != 'alias'


def test_v3_permanent_unavailable_stops_poll_enqueues_and_piece_change_heals(monkeypatch):
    audio, row, _ = _v3_fixture(monkeypatch)
    fingerprint = audio.playback_snapshot('u', row)['_v3_playback_fingerprint']
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *a: fingerprint)
    enqueued = []
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', lambda *a, **kw: enqueued.append(a))
    for _ in range(2):
        result = playback.get_audio_signed_urls('u', 'c', row['audio_files'], row)
        assert result['audio_files'][0]['status'] == 'unavailable'
        assert result['conversation_audio']['status'] == 'unavailable'
    assert not enqueued
    row['recording_pieces'][0]['end'] = 2
    assert playback.get_audio_signed_urls('u', 'c', row['audio_files'], row)['audio_files'][0]['status'] == 'pending'
    assert len(enqueued) == 1


@pytest.mark.parametrize('missing', ['metadata', 'chunks', 'short_pcm'])
def test_v3_temporarily_missing_piece_never_exports_partial_artifact(monkeypatch, missing):
    audio, row, recording = _v3_fixture(monkeypatch)
    second = {'id': 'later', 'chunk_timestamps': [1010.0], 'duration': 5}
    recording['audio_files'].append(second)
    row['audio_files'].append({**second, 'id': 'later-alias', 'recording_id': 'r', 'recording_file_id': 'later'})
    row['recording_pieces'].append({'recording_id': 'r', 'audio_file_id': 'later', 'start': 0, 'end': 2})
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    ready = False

    def pcm(uid, rid, timestamps, *args):
        if timestamps == [1010.0] and not ready:
            if missing == 'chunks':
                raise FileNotFoundError('not ready')
            if missing == 'short_pcm':
                return b'\0' * 32000
        return b'\0' * 320000

    monkeypatch.setattr(playback, '_merge_playback_sources', pcm)
    if missing == 'metadata':
        second['chunk_timestamps'] = []
    snapshot = audio.playback_snapshot('u', row)
    with pytest.raises(RuntimeError, match='v3_piece_not_ready'):
        audio.build_artifact('u', snapshot)
    ready = True
    second['chunk_timestamps'] = [1010.0]
    _mp3, spans = audio.build_artifact('u', audio.playback_snapshot('u', row))
    assert sum(s['len'] for s in spans) == 6


def test_v3_artifact_wall_clock_uses_normalized_playback_start(monkeypatch):
    audio, row, recording = _v3_fixture(monkeypatch)
    recording['audio_files'][0].update(chunk_timestamps=[1171.0], playback_start=1000.0)
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, '_merge_playback_sources', lambda *a: b'\0' * 320000)
    _, spans = audio.build_artifact('u', audio.playback_snapshot('u', row))
    assert [s['wall_offset'] for s in spans] == [1.0, 6.0]


def test_v3_fully_deleted_piece_needs_no_source_download(monkeypatch):
    audio, row, _ = _v3_fixture(monkeypatch)
    snapshot = audio.playback_snapshot('u', row)
    snapshot['_v3_playback_parts'][0]['intervals'] = []
    snapshot['_v3_playback_parts'][0]['source'] = {'id': 'gone', 'chunk_timestamps': [999.0]}

    def merge(uid, rid, timestamps, *args):
        assert timestamps != [999.0], 'fully deleted piece must not require source bytes'
        return b'\0' * 320000

    monkeypatch.setattr(playback, '_merge_playback_sources', merge)
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    _, spans = audio.build_artifact('u', snapshot)
    assert sum(s['len'] for s in spans) == 2


def test_v3_merged_legacy_audio_without_alias_stays_playable(monkeypatch):
    audio, row, _ = _v3_fixture(monkeypatch)
    # A merge copies legacy audio into the merged conversation: no recording alias, pieces keyed by the
    # conversation's own id and the copied file id.
    row['audio_files'].append(
        {'id': 'legacy', 'chunk_timestamps': [1000.0], 'duration': 10, 'recording_id': None, 'recording_file_id': None}
    )
    row['recording_pieces'].append({'recording_id': 'c', 'audio_file_id': 'legacy', 'start': 0, 'end': 2})
    monkeypatch.setattr(playback, 'AudioSegment', _FakeAudioSegment)
    monkeypatch.setattr(playback, '_merge_playback_sources', lambda *a: b'\0' * 320000)
    snapshot = audio.playback_snapshot('u', row)
    assert all('source' in part for part in snapshot['_v3_playback_parts'])
    _, spans = audio.build_artifact('u', snapshot)
    assert sum(s['len'] for s in spans) == 6
    assert {s['file_id'] for s in spans} == {'file', 'legacy'}
