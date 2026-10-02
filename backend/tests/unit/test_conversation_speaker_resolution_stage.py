import io
import json
import struct
import time
import wave
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.audio_file import AudioFile
from models.conversation import AudioTimelineProvenance, Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import speaker_resolution as stage

SR = 16000
STARTED = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
VOICES = np.eye(8, 64)


@pytest.fixture(autouse=True)
def empty_manual_receipt(monkeypatch):
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: {})


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
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: True)
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


def test_two_sync_batches_with_no_audio_withdraw_automatic_owner_claims():
    conversation = _conversation([0, 1], pcs=False, scopes=['sync:batch-a', 'sync:batch-b'])
    for segment in conversation.transcript_segments:
        segment.is_user = True
        segment.speaker_identity_status = 'user'
        segment.speaker_match_source = 'sync_embedding'

    stage.resolve_speakers_for_processing('u', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    assert all(not segment.is_user for segment in conversation.transcript_segments)
    assert all(segment.speaker_identity_status == 'ambiguous' for segment in conversation.transcript_segments)


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


def test_manual_name_reaches_prompt_after_earlier_unlabeled_fragments_join_its_voice(env, monkeypatch):
    plan = [0] * 6
    _install_audio(monkeypatch, plan)
    receipt = {'speakers': {'4': {'generation': 1, 'person_id': 'nick', 'is_user': False}}}
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: receipt)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    conversation = _conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert {segment.speaker_id for segment in conversation.transcript_segments} == {4}
    assert all(segment.person_id == 'nick' and not segment.is_user for segment in conversation.transcript_segments)
    assert all(segment.speaker_match_source is None for segment in conversation.transcript_segments)


def test_manual_receipt_is_applied_before_prompt_without_audio_or_resolution(env, monkeypatch):
    receipt = {'speakers': {'0': {'generation': 2, 'person_id': 'nick', 'is_user': False}}}
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: receipt)
    conversation = _conversation([0], pcs=False)
    conversation.transcript_segments[0].is_user = True
    conversation.transcript_segments[0].speaker_match_source = 'sync_embedding'

    assert stage.resolve_speakers_for_processing('u1', conversation) is True

    segment = conversation.transcript_segments[0]
    assert segment.person_id == 'nick'
    assert not segment.is_user
    assert segment.speaker_match_source is None


def test_receipt_acknowledgement_requires_a_successful_read_and_application(env, monkeypatch):
    conversation = _conversation([0], pcs=False)
    assert stage.resolve_speakers_for_processing('u1', conversation) is True  # Confirmed empty.

    def fail_read(uid, conversation_id):
        raise RuntimeError('receipt store unavailable')

    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', fail_read)
    assert stage.resolve_speakers_for_processing('u1', conversation) is False

    monkeypatch.setattr(
        stage.conversations_db,
        'get_manual_speaker_receipt',
        lambda uid, cid: {'speakers': {'0': {'generation': 1, 'person_id': 'nick', 'is_user': False}}},
    )
    assert stage.resolve_speakers_for_processing('u1', conversation) is True
    assert conversation.transcript_segments[0].person_id == 'nick'

    monkeypatch.setattr(
        stage.conversations_db,
        'get_manual_speaker_receipt',
        lambda uid, cid: {'segments': {'retired-segment': {'generation': 1, 'person_id': 'lost', 'is_user': False}}},
    )
    assert stage.resolve_speakers_for_processing('u1', conversation) is False


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


def _entry(duration=4.0, vector=..., window=(1.0, 5.0), scope='sync:0', stamp='s', source_stamp='ss', model=None):
    return stage.CachedEmbedding(
        duration=duration,
        vector=(
            np.ones(4, dtype=np.float32)
            if vector is ...
            else None if vector is None else np.asarray(vector, dtype=np.float32)
        ),
        placement=stage.SegmentPlacement(window, scope, stamp, source_stamp),
        model_stamp=stage.embedding_model_stamp() if model is None else model,
    )


def test_cache_round_trip_and_corrupt_header_is_empty():
    entries = {'a': _entry(1.5, np.arange(4, dtype=np.float32)), 'b': _entry(2.0, scope=None)}

    decoded = stage.decode_cache(stage.encode_cache(entries))

    assert set(decoded) == {'a', 'b'}
    np.testing.assert_allclose(decoded['a'].vector, np.arange(4))
    assert decoded['a'].duration == 1.5
    assert decoded['a'].placement == entries['a'].placement
    assert decoded['b'].placement.source_scope is None
    assert decoded['a'].model_stamp == entries['a'].model_stamp
    assert stage.decode_cache(struct.pack('>I', 2) + b'{}') == {}
    assert stage.decode_cache(None) == {}


def test_decode_cache_fails_open_on_truncated_or_malformed_blob():
    # Header length claims more bytes than the blob actually carries.
    assert stage.decode_cache(struct.pack('>I', 100) + b'{"v":2,"ids":["a"]') == {}
    # Valid header but a matrix buffer that cannot reshape to the declared dim.
    header = (
        b'{"v":2,"ids":["a","b"],"durations":[1.0,1.0],"dim":64,"has_vectors":[true,true],'
        b'"placements":[{"window":[0.0,1.0],"source_scope":"sync:0","input_stamp":"x","source_stamp":"sx"},'
        b'{"window":[1.0,2.0],"source_scope":null,"input_stamp":"y","source_stamp":"sy"}],'
        b'"model_stamps":["m","m"]}'
    )
    blob = struct.pack('>I', len(header)) + header + b'\x00' * 4
    assert stage.decode_cache(blob) == {}
    header = (
        b'{"v":2,"ids":["a","a"],"durations":[1.0,1.0],"dim":2,"has_vectors":[true,true],'
        b'"placements":[{"window":[0.0,1.0],"source_scope":null,"input_stamp":"x","source_stamp":"sx"},'
        b'{"window":[1.0,2.0],"source_scope":null,"input_stamp":"y","source_stamp":"sy"}],'
        b'"model_stamps":["m","m"]}'
    )
    blob = struct.pack('>I', len(header)) + header + np.ones(4, dtype='<f2').tobytes()
    assert stage.decode_cache(blob) == {}
    header = (
        b'{"v":2,"ids":["a"],"durations":[1.0],"dim":2,"has_vectors":[1],'
        b'"placements":[{"window":[0.0,1.0],"source_scope":null,"input_stamp":"x","source_stamp":"sx"}],'
        b'"model_stamps":["m"]}'
    )
    blob = struct.pack('>I', len(header)) + header + np.ones(2, dtype='<f2').tobytes()
    assert stage.decode_cache(blob) == {}
    header = (
        b'{"v":2,"ids":["a"],"durations":[1.0],"dim":2,"has_vectors":[true],'
        b'"placements":[{"window":[0.0,1.0],"source_scope":null,"input_stamp":"x"}],'
        b'"model_stamps":["m"]}'
    )
    blob = struct.pack('>I', len(header)) + header + np.ones(2, dtype='<f2').tobytes()
    assert stage.decode_cache(blob) == {}


def test_proof_only_and_mixed_cache_round_trip():
    proof = _entry(vector=None)

    only = stage.decode_cache(stage.encode_cache({'a': proof}))
    assert only['a'].vector is None
    assert only['a'].placement == proof.placement
    assert only['a'].model_stamp == proof.model_stamp

    mixed = stage.decode_cache(stage.encode_cache({'a': proof, 'b': _entry(2.0)}))
    assert mixed['a'].vector is None
    np.testing.assert_allclose(mixed['b'].vector, np.ones(4))
    assert mixed['a'].placement == proof.placement


def test_v1_cache_entries_cannot_prove_placement_and_decode_empty():
    header = json.dumps({'v': 1, 'ids': ['a'], 'durations': [1.5], 'dim': 4}).encode()
    blob = struct.pack('>I', len(header)) + header + np.ones(4, dtype='<f2').tobytes()
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


def test_legacy_sync_donor_scope_abstains_but_does_not_block_the_rest(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    scopes = [f'sync:job-{i}' for i in range(len(plan))]
    scopes[0] = 'legacy-conversation:donor:0'
    conversation = _conversation(plan, scopes=scopes)

    stage.resolve_speakers_for_processing('u1', conversation)

    legacy = conversation.transcript_segments[0]
    assert legacy.speaker_id == 0
    assert legacy.speaker_id_scope == 'legacy-conversation:donor:0'
    assert conversation.speaker_resolution.status == 'resolved'
    resolved = {s.speaker_id for s in conversation.transcript_segments[1:]}
    assert len(resolved) == 2
    assert 0 not in resolved


def test_mixed_untrusted_segments_abstain_without_gating_trusted_sync(env, monkeypatch):
    plan = [0, 1, 0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    scopes = [f'sync:{i // 3}' for i in range(len(plan))]
    scopes[1] = 'conn-a:0'
    conversation = _conversation(plan, scopes=scopes)

    stage.resolve_speakers_for_processing('u1', conversation)

    live = conversation.transcript_segments[1]
    assert live.speaker_id == 1
    assert live.speaker_id_scope == 'conn-a:0'
    assert all(s.speaker_id_scope == 'conversation:c1' for s in conversation.transcript_segments if s is not live)
    ids = {s.speaker_id for s in conversation.transcript_segments if s is not live}
    assert len(ids) == 2 and 1 not in ids


def test_moved_window_reembeds_the_different_voice(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1, 0, 1, 0, 1]
    _install_audio(monkeypatch, plan)
    stage.resolve_speakers_for_processing('u1', _conversation(plan))
    assert diarizer.calls == len(plan)

    moved = _conversation(plan)
    moved.transcript_segments[0].start += 4.0
    moved.transcript_segments[0].end += 4.0
    stage.resolve_speakers_for_processing('u1', moved)

    assert diarizer.calls == len(plan) + 1
    assert moved.transcript_segments[0].speaker_id == moved.transcript_segments[1].speaker_id


def test_failed_reextraction_drops_the_stale_entry_and_withdraws_its_name(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 3
    _install_audio(monkeypatch, plan)
    stage.resolve_speakers_for_processing('u1', _conversation(plan))

    moved = _conversation(plan)
    s0 = moved.transcript_segments[0]
    s0.start += 8.0
    s0.end += 8.0
    s0.is_user = True
    s0.person_id = 'someone'
    s0.speaker_identity_status = 'user'
    s0.speaker_match_source = stage.MATCH_SOURCE
    s0.speaker_label_source = 'auto'
    diarizer.fail = True

    stage.resolve_speakers_for_processing('u1', moved)

    stale = stage.decode_cache(store['c1'])
    assert stale['s0'].vector is None
    assert stale['s0'].placement.source_scope == 'sync:0'
    assert not s0.is_user
    assert s0.person_id is None
    assert s0.speaker_identity_status == 'unknown'
    assert s0.speaker_match_source is None
    assert s0.speaker_label_source is None


def test_unchanged_reruns_reuse_proof_while_changed_inputs_invalidate(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 4
    audio = _install_audio(monkeypatch, plan)
    resolved = _conversation(plan)
    stage.resolve_speakers_for_processing('u1', resolved)
    calls = diarizer.calls
    assert resolved.transcript_segments[0].speaker_id_scope == 'conversation:c1'
    audio.downloads = 0

    stage.resolve_speakers_for_processing('u1', _conversation(plan))
    assert diarizer.calls == calls
    assert audio.downloads == 0

    stage.resolve_speakers_for_processing('u1', resolved)
    assert diarizer.calls == calls
    assert audio.downloads == 0

    moved = _conversation(plan)
    for segment in moved.transcript_segments:
        segment.speaker_id_scope = 'conversation:c1'
        segment.speaker_match_source = stage.MATCH_SOURCE
    moved.started_at = STARTED + timedelta(hours=1)
    stage.resolve_speakers_for_processing('u1', moved)
    assert diarizer.calls == calls
    assert moved.speaker_resolution.status == 'unavailable'
    assert moved.speaker_resolution.participant_speaker_ids == []
    assert all(s.speaker_match_source is None for s in moved.transcript_segments)
    assert all(s.speaker_id_scope == 'conversation:c1' for s in moved.transcript_segments)

    manifest = _conversation(plan)
    manifest.audio_files = [
        AudioFile(
            id='f1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[STARTED.timestamp()],
            duration=32.0,
        )
    ]
    stage.resolve_speakers_for_processing('u1', manifest)
    assert diarizer.calls == calls * 2
    assert manifest.speaker_resolution.status == 'resolved'


def test_model_change_regenerates_with_the_proven_scope(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    resolved = _conversation(plan)
    stage.resolve_speakers_for_processing('u1', resolved)
    calls = diarizer.calls

    monkeypatch.setenv('CONVERSATION_SPEAKER_EMBEDDING_MODEL_VERSION', 'other-model')
    stage.resolve_speakers_for_processing('u1', resolved)

    assert diarizer.calls == calls * 2
    assert resolved.speaker_resolution.status == 'resolved'
    entry = stage.decode_cache(store['c1'])['s0']
    assert entry.placement.source_scope.startswith('sync:')
    assert entry.model_stamp == stage.embedding_model_stamp()


def test_bare_own_scope_without_proven_cache_stays_untrusted(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['conversation:c1'] * len(plan))

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'
    assert conversation.speaker_resolution.participant_speaker_ids == []
    assert [s.speaker_id for s in conversation.transcript_segments] == list(range(len(plan)))


def _v2_conversation(plan, *, seconds=4.0, scopes):
    conversation = _conversation(plan, seconds=seconds, scopes=scopes)
    total = len(plan) * seconds
    origin = STARTED.timestamp()
    conversation.audio_timeline = AudioTimelineProvenance(version=2)
    conversation.audio_files = [
        AudioFile(
            id='f1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[origin],
            duration=total,
            chunk_spans=[{'start': origin, 'end': origin + total}],
        )
    ]
    return conversation


def test_v2_live_segments_resolve_only_with_the_opt_in(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    people_calls = []
    monkeypatch.setattr(stage.users_db, 'get_people', lambda uid: people_calls.append(uid) or [])
    scopes = [f'conn-a:{i // 3}' for i in range(len(plan))]

    conversation = _v2_conversation(plan, scopes=scopes)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert diarizer.calls == 0
    assert people_calls == []
    assert [s.speaker_id for s in conversation.transcript_segments] == list(range(len(plan)))

    monkeypatch.setenv('CONVERSATION_LIVE_SPEAKER_RESOLUTION_ENABLED', 'true')
    conversation = _v2_conversation(plan, scopes=scopes)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert diarizer.calls == len(plan)
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2


def test_v2_live_opt_in_free_plan_identifies_owner_without_people(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    monkeypatch.setenv('CONVERSATION_LIVE_SPEAKER_RESOLUTION_ENABLED', 'true')
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: False)
    monkeypatch.setattr(stage.users_db, 'get_people', lambda uid: pytest.fail('free plan must not load people'))
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))

    conversation = _v2_conversation(plan, scopes=[f'conn:{i}' for i in range(len(plan))])
    stage.resolve_speakers_for_processing('u1', conversation)

    assert [s.is_user for s, v in zip(conversation.transcript_segments, plan)] == [v == 0 for v in plan]


def test_manual_receipt_wins_with_or_without_live_opt_in(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    receipt = {'speakers': {'4': {'generation': 1, 'person_id': 'nick', 'is_user': False}}}
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: receipt)
    for live in (False, True):
        monkeypatch.setenv('CONVERSATION_LIVE_SPEAKER_RESOLUTION_ENABLED', 'true' if live else 'false')
        conversation = _v2_conversation(plan, scopes=[f'conn:{i}' for i in range(len(plan))])
        stage.resolve_speakers_for_processing('u1', conversation)
        s4 = conversation.transcript_segments[4]
        assert s4.person_id == 'nick'
        assert not s4.is_user


def test_unplaced_segment_reserves_its_numeric_id_and_loses_its_auto_name(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1, 0]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, scopes=['sync:0', 'conn-a:0', 'sync:0'])
    conversation.transcript_segments[0].speaker_id = 5
    conversation.transcript_segments[1].speaker_id = 5
    s1 = conversation.transcript_segments[1]
    s1.is_user = True
    s1.person_id = 'someone'
    s1.speaker_match_source = stage.MATCH_SOURCE

    stage.resolve_speakers_for_processing('u1', conversation)

    assert s1.speaker_id == 5
    assert s1.speaker_id_scope == 'conn-a:0'
    assert not s1.is_user and s1.person_id is None and s1.speaker_match_source is None
    assert all(s.speaker_id != 5 for s in (conversation.transcript_segments[0], conversation.transcript_segments[2]))


def test_a_window_spanning_contiguous_chunks_assembles_exact_audio(env, monkeypatch):
    _, diarizer = env
    plan = [0, 1]
    audio = FakeAudio(plan, seconds=6.0, chunk_seconds=4.0)
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    conversation = _conversation(plan, seconds=6.0)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 2
    assert conversation.speaker_resolution.status == 'resolved'
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2


@pytest.mark.parametrize('dropped', [0, 1])
def test_a_gap_inside_a_window_abstains_even_when_audio_surrounds_it(env, monkeypatch, dropped):
    _, diarizer = env
    audio = FakeAudio([0], seconds=6.0, chunk_seconds=2.0)
    del audio.chunks[dropped]
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    conversation = _conversation([0], seconds=6.0)

    stage.resolve_speakers_for_processing('u1', conversation)

    segment = conversation.transcript_segments[0]
    assert diarizer.calls == 0
    assert segment.speaker_id == 0
    assert segment.speaker_id_scope == 'sync:0'


def test_a_short_decode_abstains_instead_of_embedding_partial_audio(env, monkeypatch):
    _, diarizer = env
    audio = FakeAudio([0], seconds=4.0, chunk_seconds=10.0)
    start, pcm = audio.chunks[0]
    audio.chunks = [(start, pcm[: int(2.0 * SR) * 2])]
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    conversation = _conversation([0], seconds=4.0)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.transcript_segments[0].speaker_id_scope == 'sync:0'


def test_overlapping_chunks_do_not_duplicate_samples(env, monkeypatch):
    _, diarizer = env
    audio = FakeAudio([0], seconds=4.0, chunk_seconds=4.0)
    start, pcm = audio.chunks[0]
    audio.chunks = [
        (start, pcm[: int(3.0 * SR) * 2]),
        (start + 2.0, pcm[int(2.0 * SR) * 2 :]),
    ]
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    conversation = _conversation([0], seconds=4.0)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 1
    assert conversation.speaker_resolution.status == 'resolved'


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


@pytest.mark.parametrize('distances,expected', [((0.40, 0.45), []), ((0.40, 0.63), [0]), ((0.631, 0.645), [])])
def test_resolution_replaces_capture_owner_guesses_with_joint_evidence(env, monkeypatch, distances, expected):
    plan = [0, 1] * 10
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)
    for segment in conversation.transcript_segments:
        segment.is_user = True
        segment.speaker_identity_status = 'user'
        segment.speaker_match_source = 'sync_embedding'
    vectors = np.zeros_like(VOICES)
    for i, d in enumerate(distances):
        vectors[i, :2] = [1 - d, (-1) ** i * np.sqrt(1 - (1 - d) ** 2)]
    monkeypatch.setattr(__import__(__name__, fromlist=['VOICES']), 'VOICES', vectors)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: np.eye(1, 64)[0].tolist())
    stage.resolve_speakers_for_processing('u1', conversation)
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2
    assert {v for s, v in zip(conversation.transcript_segments, plan) if s.is_user} == set(expected)
    if distances == (0.40, 0.45):
        assert all(s.speaker_identity_status == 'ambiguous' for s in conversation.transcript_segments)
    # Persistence/client projection retains unnamed voices and the evidence state.
    restored = Conversation(**conversation.model_dump())
    assert [s.is_user for s in restored.transcript_segments] == [s.is_user for s in conversation.transcript_segments]


def test_manifest_append_on_resolved_object_reembeds_under_proven_scope(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 4
    audio = _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    calls = diarizer.calls

    conversation.audio_files = [
        AudioFile(
            id='f1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[STARTED.timestamp()],
            duration=32.0,
        )
    ]
    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'resolved'
    assert diarizer.calls == calls * 2
    assert audio.downloads == 4
    entries = stage.decode_cache(store['c1'])
    assert {entry.placement.source_scope for entry in entries.values()} == {'sync:0', 'sync:1', 'sync:2'}


def test_model_change_failure_keeps_proof_and_retry_recovers(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    calls = diarizer.calls
    for segment in conversation.transcript_segments:
        assert segment.speaker_id_scope == 'conversation:c1'

    monkeypatch.setenv('CONVERSATION_SPEAKER_EMBEDDING_MODEL_VERSION', 'm2')
    diarizer.fail = True
    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    assert all(s.speaker_match_source is None for s in conversation.transcript_segments)
    assert all(s.speaker_id_scope == 'conversation:c1' for s in conversation.transcript_segments)
    entries = stage.decode_cache(store['c1'])
    assert len(entries) == len(plan)
    assert all(entry.vector is None for entry in entries.values())
    assert {entry.placement.source_scope for entry in entries.values()} == {'sync:0', 'sync:1', 'sync:2'}

    diarizer.fail = False
    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'resolved'
    assert all(entry.vector is not None for entry in stage.decode_cache(store['c1']).values())
    assert diarizer.calls == calls * 2 + stage.MAX_CONSECUTIVE_EMBED_FAILURES


@pytest.mark.parametrize(
    'bad',
    [np.full(64, np.nan), np.zeros(64), np.full(64, np.inf)],
    ids=['nan', 'zero', 'inf'],
)
def test_invalid_extractor_vectors_never_inherit_an_identity(env, monkeypatch, bad):
    store, diarizer = env
    plan = [0, 0]
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', FakeAudio(plan, seconds=12.0))
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    conversation = _conversation(plan, seconds=12.0)

    real = stage.extract_embedding_from_bytes
    calls = {'n': 0}

    def flaky(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return bad
        return real(*args, **kwargs)

    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', flaky)

    stage.resolve_speakers_for_processing('u1', conversation)

    s0, s1 = conversation.transcript_segments
    assert s0.speaker_id == 0 and not s0.is_user
    assert s1.speaker_id == 1 and s1.is_user
    entries = stage.decode_cache(store['c1'])
    assert entries['s0'].vector is None
    assert entries['s0'].placement.source_scope == 'sync:0'
    assert entries['s1'].vector is not None


def _placements(conversation):
    doc = conversation.model_dump(mode='python')
    out = {}
    for s, m in zip(conversation.transcript_segments, doc['transcript_segments']):
        m = dict(m, audio_alignment=s.audio_alignment, audio_capture_run=s.audio_capture_run)
        placement = stage.placement_for_segment(doc, m)
        assert placement is not None
        out[s.id] = placement
    return out


def test_zero_embedding_budget_downloads_nothing(env, monkeypatch):
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '0')
    _, diarizer = env
    audio = _install_audio(monkeypatch, [0, 1] * 4)
    conversation = _conversation([0, 1] * 4)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert audio.downloads == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_embed_missing_reports_budget_and_limit_stops(env, monkeypatch):
    audio = _install_audio(monkeypatch, [0, 1] * 2)
    conversation = _conversation([0, 1] * 2)
    placements = _placements(conversation)
    pending = list(conversation.transcript_segments)

    count, stop = stage._embed_missing('u1', conversation, pending, {}, time.monotonic() - 1, placements)
    assert (count, stop) == (0, 'budget')
    assert audio.downloads == 0

    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '0')
    count, stop = stage._embed_missing('u1', conversation, pending, {}, time.monotonic() + 60, placements)
    assert (count, stop) == (0, 'max_embeddings')
    assert audio.downloads == 0


def test_invalidated_names_are_withdrawn_before_a_failed_cache_upload(env, monkeypatch):
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    assert any(s.is_user and s.speaker_match_source == stage.MATCH_SOURCE for s in conversation.transcript_segments)

    receipt = {'segments': {'s4': {'generation': 1, 'person_id': 'nick', 'is_user': False}}}
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: receipt)
    monkeypatch.setenv('CONVERSATION_SPEAKER_EMBEDDING_MODEL_VERSION', 'm2')
    monkeypatch.setattr(
        stage,
        'upload_speaker_embedding_cache',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('storage down')),
    )

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    labeled = [s for s in conversation.transcript_segments if s.person_id]
    assert len(labeled) == 1 and labeled[0].id == 's4' and labeled[0].person_id == 'nick'
    assert all(
        not s.is_user and s.speaker_match_source != stage.MATCH_SOURCE
        for s in conversation.transcript_segments
        if s.id != 's4'
    )


def test_large_magnitude_vector_normalizes_and_matches(env, monkeypatch):
    store, diarizer = env
    plan = [0, 0]
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', FakeAudio(plan, seconds=12.0))
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    conversation = _conversation(plan, seconds=12.0)

    real = stage.extract_embedding_from_bytes
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', lambda *args, **kwargs: real(*args, **kwargs) * 1e30)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert all(s.is_user for s in conversation.transcript_segments)
    entries = stage.decode_cache(store['c1'])
    assert all(
        entry.vector is not None and np.isfinite(entry.vector).all() and 0.9 < float(np.linalg.norm(entry.vector)) < 1.1
        for entry in entries.values()
    )
