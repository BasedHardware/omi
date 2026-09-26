import io
import struct
import time
import wave
from datetime import datetime, timezone

import numpy as np
import pytest

from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import speaker_resolution as stage

SR = 16000
STARTED = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
VOICES = np.eye(8, 64)


def _conversation(plan, *, seconds=4.0, pcs=True, scopes=None):
    segments = [
        TranscriptSegment(
            id=f's{i}',
            text='hello',
            speaker=f'SPEAKER_{i}',
            speaker_id=i,
            speaker_id_scope=(scopes[i] if scopes else f'sync:{i // 3}'),
            is_user=False,
            start=i * seconds,
            end=i * seconds + seconds - 0.2,
        )
        for i in range(len(plan))
    ]
    return Conversation(
        id='c1',
        created_at=STARTED,
        started_at=STARTED,
        finished_at=STARTED,
        structured=Structured(),
        transcript_segments=segments,
        private_cloud_sync_enabled=pcs,
    )


class FakeAudio:
    """Stored chunks whose samples encode which voice is speaking."""

    def __init__(self, plan, seconds=4.0, chunk_seconds=20.0):
        total = len(plan) * seconds
        samples = np.zeros(int(total * SR), dtype=np.int16)
        for i, voice in enumerate(plan):
            samples[int(i * seconds * SR) : int((i * seconds + seconds - 0.2) * SR)] = (voice + 1) * 1000
        self.chunks = [
            (STARTED.timestamp() + start, samples[int(start * SR) : int((start + chunk_seconds) * SR)].tobytes())
            for start in np.arange(0, total, chunk_seconds)
        ]
        self.downloads = 0

    def __call__(self, uid, conversation_id, wanted, sample_rate=SR):
        for index, (start, pcm) in enumerate(self.chunks):
            following = self.chunks[index + 1][0] if index + 1 < len(self.chunks) else None
            if wanted(start, following):
                self.downloads += 1
                yield start, pcm


class FakeDiarizer:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def __call__(self, wav, filename='audio.wav', *, client=None, timeout=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError('diarizer down')
        with wave.open(io.BytesIO(wav)) as reader:
            frames = reader.readframes(reader.getnframes())
        values = np.frombuffer(frames, dtype=np.int16)
        voice = int(np.bincount(values[values > 0] // 1000).argmax()) - 1
        return VOICES[voice].reshape(1, -1).astype(np.float32)


@pytest.fixture
def env(monkeypatch):
    store = {}
    monkeypatch.setattr(stage, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', lambda uid, cid: store.get(cid))
    monkeypatch.setattr(stage, 'upload_speaker_embedding_cache', lambda uid, cid, data: store.__setitem__(cid, data))
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: {})
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: None)
    monkeypatch.setattr(stage.users_db, 'get_people', lambda uid: [])
    diarizer = FakeDiarizer()
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', diarizer)
    return store, diarizer


def _install_audio(monkeypatch, plan):
    audio = FakeAudio(plan)
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    return audio


def test_fragmented_conversation_is_rewritten_to_one_id_per_voice(env, monkeypatch):
    plan = [0, 1, 2, 0, 1, 0] * 4
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    ids_by_voice = {}
    for segment, voice in zip(conversation.transcript_segments, plan):
        ids_by_voice.setdefault(voice, set()).add(segment.speaker_id)
        assert segment.speaker == f'SPEAKER_{segment.speaker_id}'
        assert segment.speaker_id_scope == 'conversation:c1'
    assert all(len(ids) == 1 for ids in ids_by_voice.values())
    resolution = conversation.speaker_resolution
    assert resolution.status == 'resolved'
    assert sorted(resolution.participant_speaker_ids) == sorted(next(iter(i)) for i in ids_by_voice.values())


def test_cache_means_a_growing_conversation_embeds_each_segment_once(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    stage.resolve_speakers_for_processing('u1', _conversation(plan))
    first_calls = diarizer.calls

    audio = _install_audio(monkeypatch, plan)
    stage.resolve_speakers_for_processing('u1', _conversation(plan))

    assert first_calls == len(plan)
    assert diarizer.calls == first_calls
    assert audio.downloads == 0
    assert set(stage.decode_cache(store['c1'])) == {f's{i}' for i in range(len(plan))}


def test_owner_voiceprint_marks_the_owner_voice(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    for segment, voice in zip(conversation.transcript_segments, plan):
        assert segment.is_user is (voice == 0)
        if voice == 0:
            assert segment.speaker_match_source == stage.MATCH_SOURCE


def test_receipt_keeps_the_labeled_id_on_the_whole_voice(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    monkeypatch.setattr(
        stage.conversations_db,
        'get_manual_speaker_receipt',
        lambda uid, cid: {'speakers': {'4': {'generation': 1, 'person_id': 'nick', 'is_user': False}}},
    )
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert {s.speaker_id for s, v in zip(conversation.transcript_segments, plan) if v == 0} == {4}


def test_without_stored_audio_fragmented_ids_are_marked_uncountable(env, monkeypatch):
    plan = [0, 1, 0, 1]
    conversation = _conversation(plan, pcs=False)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    assert conversation.speaker_resolution.participant_speaker_ids == []
    assert [s.speaker_id for s in conversation.transcript_segments] == [0, 1, 2, 3]


def test_without_stored_audio_one_capture_scope_keeps_its_counts(env, monkeypatch):
    plan = [0, 1, 0, 1]
    conversation = _conversation(plan, pcs=False, scopes=['live:0'] * 4)
    for segment, voice in zip(conversation.transcript_segments, plan):
        segment.speaker_id = voice

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'capture'
    assert conversation.speaker_resolution.participant_speaker_ids == []  # 7.6s each, under 10s


def test_diarizer_outage_fails_open_on_capture_ids(env, monkeypatch):
    _, diarizer = env
    diarizer.fail = True
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == stage.MAX_CONSECUTIVE_EMBED_FAILURES
    assert conversation.speaker_resolution.status == 'unavailable'
    assert [s.speaker_id for s in conversation.transcript_segments] == list(range(len(plan)))


def test_unexpected_error_never_breaks_processing(env, monkeypatch):
    def boom(uid, cid):
        raise RuntimeError('gcs down')

    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', boom)
    conversation = _conversation([0, 1, 0, 1])

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'


def test_kill_switch_leaves_the_conversation_untouched(env, monkeypatch):
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    conversation = _conversation([0, 1])

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution is None


def test_cache_round_trip_and_corrupt_header_is_empty():
    entries = {'a': (1.5, np.arange(4, dtype=np.float32)), 'b': (2.0, np.ones(4, dtype=np.float32))}

    decoded = stage.decode_cache(stage.encode_cache(entries))

    assert set(decoded) == {'a', 'b'}
    np.testing.assert_allclose(decoded['a'][1], np.arange(4))
    assert stage.decode_cache(struct.pack('>I', 2) + b'{}') == {}
    assert stage.decode_cache(None) == {}


def test_decode_cache_fails_open_on_truncated_or_malformed_blob():
    # Header length claims more bytes than the blob actually carries.
    assert stage.decode_cache(struct.pack('>I', 100) + b'{"v":1,"ids":["a"]') == {}
    # Valid header but a matrix buffer that cannot reshape to the declared dim.
    header = b'{"v":1,"ids":["a","b"],"durations":[1.0,1.0],"dim":64}'
    blob = struct.pack('>I', len(header)) + header + b'\x00' * 4
    assert stage.decode_cache(blob) == {}


def test_started_at_anchors_a_naive_datetime_to_utc(monkeypatch):
    monkeypatch.setenv('TZ', 'America/Los_Angeles')
    time.tzset()
    try:
        conversation = _conversation([], scopes=[])
        conversation.started_at = datetime(2026, 9, 25, 12, 0, 0)  # no tzinfo
        conversation.created_at = conversation.started_at

        assert stage._started_at(conversation) == datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    finally:
        monkeypatch.delenv('TZ', raising=False)
        time.tzset()


def test_a_long_segment_overlapping_short_ones_is_still_embedded(env, monkeypatch):
    _, diarizer = env
    # s0 spans 0-50s (midpoint 25) but starts before s1 (4-7s, midpoint 5.5), so
    # start order is not midpoint order; chunk 0-20s holds only s1's midpoint.
    plan = [0, 1, 0]
    _install_audio(monkeypatch, [0] * 13)
    conversation = _conversation(plan)
    for segment, (start, end) in zip(conversation.transcript_segments, [(0.0, 50.0), (4.0, 7.0), (30.0, 33.0)]):
        segment.start, segment.end = start, end

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == len(plan)


def test_live_scopes_are_not_resolved_until_their_audio_timeline_is_trusted(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['conn-a:0', 'conn-a:0', 'conn-b:0', 'conn-b:0'])

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'
    assert [s.speaker_id for s in conversation.transcript_segments] == [0, 1, 2, 3]


def test_a_resolved_conversation_that_grew_by_sync_resolves_again(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    conversation.transcript_segments[-1].speaker_id_scope = 'sync:new-chunk'
    conversation.transcript_segments[-1].speaker_id = 900

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'resolved'
    assert conversation.transcript_segments[-1].speaker_id == conversation.transcript_segments[1].speaker_id


def test_a_run_cut_short_reports_uncountable_then_resumes_to_resolved(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '4')
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    assert conversation.transcript_segments[-1].speaker_id == len(plan) - 1
    assert conversation.transcript_segments[-1].speaker_id_scope.startswith('sync:')

    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '1500')
    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == len(plan)
    assert conversation.speaker_resolution.status == 'resolved'
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2
