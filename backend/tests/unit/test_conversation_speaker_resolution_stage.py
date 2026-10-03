import io
import os
import struct
import subprocess
import time
import types
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from models.audio_file import AudioFile, ChunkSpan
from models.conversation import AudioTimelineProvenance, Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import speaker_resolution as stage
from utils.metrics import OMI_AUDIO_PLACEMENT_TOTAL, OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL

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

    def __init__(self, plan, seconds=4.0, chunk_seconds=20.0, offset=0.0):
        total = len(plan) * seconds
        samples = np.zeros(int(total * SR), dtype=np.int16)
        for i, voice in enumerate(plan):
            samples[int(i * seconds * SR) : int((i * seconds + seconds - 0.2) * SR)] = (voice + 1) * 1000
        self.chunks = [
            (
                STARTED.timestamp() + offset + start,
                samples[int(start * SR) : int((start + chunk_seconds) * SR)].tobytes(),
            )
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


BASELINE_STAGE_SHA = '6b23e737acdfc0635fb33f3a6e956edd30645e64'
_STAGE_OVERRIDE_ENV = 'OMI_TEST_STAGE_MODULE'


def _load_baseline_stage():
    source = subprocess.run(
        ['git', 'show', f'{BASELINE_STAGE_SHA}:backend/utils/conversations/speaker_resolution.py'],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType('speaker_resolution_pinned_baseline')
    exec(compile(source, 'speaker_resolution.py', 'exec'), module.__dict__)
    return module


def _patch_stage_deps(monkeypatch, module, store, diarizer):
    monkeypatch.setattr(module, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(module, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(module, 'download_speaker_embedding_cache', lambda uid, cid: store.get(cid))
    monkeypatch.setattr(module, 'upload_speaker_embedding_cache', lambda uid, cid, data: store.__setitem__(cid, data))
    monkeypatch.setattr(module, 'extract_embedding_from_bytes', diarizer)


@pytest.fixture
def stage_override(monkeypatch, env):
    """Literal red proof: OMI_TEST_STAGE_MODULE=baseline pins the stage to the
    pre-implementation module loaded verbatim from the pinned base commit."""
    if os.environ.get(_STAGE_OVERRIDE_ENV) != 'baseline':
        return None
    store, diarizer = env
    baseline = _load_baseline_stage()
    _patch_stage_deps(monkeypatch, baseline, store, diarizer)
    monkeypatch.setattr(
        baseline, 'iter_audio_chunk_pcm', lambda *args, **kwargs: stage.iter_audio_chunk_pcm(*args, **kwargs)
    )
    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', baseline.resolve_speakers_for_processing)
    return baseline


def _install_audio(monkeypatch, plan, seconds=4.0, offset=0.0):
    audio = FakeAudio(plan, seconds=seconds, offset=offset)
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    return audio


def _span_flags(monkeypatch):
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'true')
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'false')


def _capture_shifted_conversation(plan, *, seconds=4.0, shift=180.0, manifest=True):
    """Live-scoped segments whose capture window sits ``shift`` seconds past the provider origin."""
    conversation = _conversation(plan, seconds=seconds, scopes=[f'conn-{i}:0' for i in range(len(plan))])
    origin = STARTED.timestamp()
    for segment in conversation.transcript_segments:
        segment.audio_capture_start = origin + shift + segment.start
        segment.audio_capture_end = origin + shift + segment.end
    if manifest:
        total = len(plan) * seconds
        conversation.audio_files = [
            AudioFile(
                id='af1',
                uid='u1',
                conversation_id='c1',
                chunk_timestamps=[origin + shift],
                duration=total,
                chunk_spans=[ChunkSpan(start=origin + shift, end=origin + shift + total)],
            )
        ]
    return conversation


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


def test_legacy_sync_donor_scope_does_not_block_conversation_resolution(env, monkeypatch):
    plan = [0, 1] * 6
    _install_audio(monkeypatch, plan)
    scopes = [f'sync:job-{i}' for i in range(len(plan))]
    scopes[0] = 'legacy-conversation:donor:0'
    conversation = _conversation(plan, scopes=scopes)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'resolved'
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2


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


def test_span_flagged_live_conversation_resolves_on_the_capture_clock(env, monkeypatch):
    """Red proof: span-stored live audio resolves once storage and consumer flags are on."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == len(plan)
    ids_by_voice = {}
    for segment, voice in zip(conversation.transcript_segments, plan):
        ids_by_voice.setdefault(voice, set()).add(segment.speaker_id)
    assert all(len(ids) == 1 for ids in ids_by_voice.values())
    assert len({next(iter(ids)) for ids in ids_by_voice.values()}) == 2
    resolution = conversation.model_dump()['speaker_resolution']
    assert resolution['status'] == 'resolved'
    assert sorted(resolution['participant_speaker_ids']) == sorted(next(iter(i)) for i in ids_by_voice.values())

    first_calls = diarizer.calls
    stage.resolve_speakers_for_processing('u1', conversation)
    assert diarizer.calls == first_calls
    assert any(key.startswith('capture-span:') for key in stage.decode_cache(store['c1']))


def test_span_resolution_mixed_sync_and_capture_scopes_resolve(env, stage_override, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0, 1] * 4
    sync_audio = FakeAudio(plan[:4])
    live_audio = FakeAudio(plan[4:], offset=196.0)

    def combined(uid, conversation_id, wanted, sample_rate=SR):
        yield from sync_audio(uid, conversation_id, wanted, sample_rate=sample_rate)
        yield from live_audio(uid, conversation_id, wanted, sample_rate=sample_rate)

    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', combined)
    conversation = _capture_shifted_conversation(plan, manifest=False)
    origin = STARTED.timestamp()
    for segment in conversation.transcript_segments[:4]:
        segment.speaker_id_scope = f'sync:upload-{segment.id}'
        segment.audio_capture_start = segment.audio_capture_end = None
    conversation.audio_files = [
        AudioFile(
            id='af1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[origin],
            duration=16.0,
            chunk_spans=[ChunkSpan(start=origin, end=origin + 16.0)],
        ),
        AudioFile(
            id='af2',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[origin + 196.0],
            duration=16.0,
            chunk_spans=[ChunkSpan(start=origin + 196.0, end=origin + 212.0)],
        ),
    ]

    stage.resolve_speakers_for_processing('u1', conversation)

    serialized = conversation.model_dump()['speaker_resolution']
    assert serialized['status'] == 'resolved'
    ids_by_voice = {}
    for segment, voice in zip(conversation.transcript_segments, plan):
        ids_by_voice.setdefault(voice, set()).add(segment.speaker_id)
        assert segment.speaker_id_scope == 'conversation:c1'
    assert all(len(ids) == 1 for ids in ids_by_voice.values())
    assert sorted(serialized['participant_speaker_ids']) == sorted(next(iter(i)) for i in ids_by_voice.values())
    assert diarizer.calls == len(plan)
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2


def test_span_resolution_refuses_before_any_embedding_when_a_required_segment_is_unplaceable(env, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    conversation.transcript_segments[3].audio_capture_start = None
    conversation.transcript_segments[3].audio_capture_end = None

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_span_resolution_refuses_when_the_manifest_has_an_uncovered_hole(env, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    origin = STARTED.timestamp()
    conversation.audio_files = [
        AudioFile(
            id='af1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[origin + 180.0],
            duration=16.0,
            chunk_spans=[ChunkSpan(start=origin + 180.0, end=origin + 196.0)],
        )
    ]

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_consumer_off_preserves_capture_span_cache_and_never_reembeds(env, monkeypatch):
    """Rollback guard: OFF must not prune capture-span keys or re-embed at legacy coordinates."""
    store, diarizer = env
    conversation = _conversation([0, 1] * 4)
    blob = stage.encode_cache(
        {
            'capture-span:s0:1700000100.0:1700000103.8': (3.8, np.ones(64, dtype=np.float32)),
            's1': (3.8, np.zeros(64, dtype=np.float32)),
        }
    )
    store['c1'] = blob
    _install_audio(monkeypatch, [0, 1] * 4)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert store['c1'] == blob
    assert conversation.speaker_resolution.status == 'unavailable'


def test_shifted_capture_window_reembeds_only_the_shifted_entry(env, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    first_calls = diarizer.calls

    segment = conversation.transcript_segments[2]
    segment.audio_capture_start += 5.0
    segment.audio_capture_end += 5.0
    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == first_calls + 1


def test_span_on_unplaceable_live_segment_cannot_reuse_bare_v1_cache(env, monkeypatch):
    """A bare legacy cache entry must not admit an unplaceable live segment."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    for segment in conversation.transcript_segments:
        segment.audio_capture_start = segment.audio_capture_end = None
    blob = stage.encode_cache({f's{i}': (3.8, np.ones(64, dtype=np.float32)) for i in range(len(plan))})
    store['c1'] = blob

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'
    assert store['c1'] == blob


def test_span_on_partial_capture_endpoint_refuses_even_with_v1_cache(env, monkeypatch):
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    for segment in conversation.transcript_segments:
        segment.audio_capture_end = None
    blob = stage.encode_cache({f's{i}': (3.8, np.ones(64, dtype=np.float32)) for i in range(len(plan))})
    store['c1'] = blob

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'
    assert store['c1'] == blob


@pytest.mark.parametrize('scope', ['conversation:c1', 'legacy-conversation:donor:0'])
def test_span_on_unplaceable_own_or_legacy_scope_reuses_historical_bare_cache(env, monkeypatch, scope):
    """Historically resolved scopes keep their v1 entries readable when the
    segment carries no capture window at all."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _conversation(plan, scopes=[scope] * len(plan))
    seed = {f's{i}': (3.8, VOICES[plan[i]]) for i in range(len(plan))}
    store['c1'] = stage.encode_cache(seed)

    stage.resolve_speakers_for_processing('u1', conversation)

    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'resolved'
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 2


@pytest.mark.parametrize('mode', ['sync', 'v2'])
def test_span_on_placeable_sync_and_v2_segments_with_capture_fields_reuse_bare_cache(env, monkeypatch, mode):
    """Sync/v2-placeable segments embed under their bare id even when private
    capture fields ride along; a second run embeds nothing."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan)
    scopes = [f'sync:upload-{i}' for i in range(len(plan))] if mode == 'sync' else ['conn:0'] * len(plan)
    conversation = _conversation(plan, scopes=scopes)
    origin = STARTED.timestamp()
    total = len(plan) * 4.0
    for segment in conversation.transcript_segments:
        segment.audio_capture_start = origin + segment.start
        segment.audio_capture_end = origin + segment.end
    conversation.audio_files = [
        AudioFile(
            id='af1',
            uid='u1',
            conversation_id='c1',
            chunk_timestamps=[origin],
            duration=total,
            chunk_spans=[ChunkSpan(start=origin, end=origin + total)],
        )
    ]
    if mode == 'v2':
        conversation.audio_timeline = AudioTimelineProvenance(version=2)

    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    first_calls = diarizer.calls
    assert first_calls == len(plan)
    keys = set(stage.decode_cache(store['c1']))
    assert keys == {f's{i}' for i in range(len(plan))}

    stage.resolve_speakers_for_processing('u1', conversation)
    assert diarizer.calls == first_calls
    assert set(stage.decode_cache(store['c1'])) == keys


def test_on_then_off_cache_intact_refuses_without_touching_the_cache(env, monkeypatch):
    """A real ON->OFF rollback: the capture-span cache stays byte-identical and
    nothing re-embeds at legacy coordinates."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    cached_blob = store['c1']
    calls_after_on = diarizer.calls

    monkeypatch.delenv('LIVE_SPEAKER_SPAN_RESOLUTION')
    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'capture'
    assert diarizer.calls == calls_after_on
    assert store['c1'] == cached_blob


@pytest.mark.parametrize('missing', ['absent', 'corrupt'])
def test_on_then_off_missing_or_corrupt_cache_refuses_before_any_embedding(env, monkeypatch, missing):
    """Rollback with a vanished or undecodable cache: OFF must refuse rather
    than embed previously-resolved capture segments at provider coordinates."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    calls_after_on = diarizer.calls
    if missing == 'absent':
        del store['c1']
    else:
        store['c1'] = b'\x00\x01\x02corrupt'

    monkeypatch.delenv('LIVE_SPEAKER_SPAN_RESOLUTION')
    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'capture'
    assert diarizer.calls == calls_after_on


def test_shadow_placement_metrics_count_per_segment_and_reason_metrics_once_per_outcome(env, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)

    def placed(reason, outcome):
        before = (
            OMI_AUDIO_PLACEMENT_TOTAL.labels(reason=reason)._value.get(),
            OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL.labels(outcome=outcome, reason=reason)._value.get(),
        )
        conversation = _capture_shifted_conversation(plan)
        stage.resolve_speakers_for_processing('u1', conversation)
        return (
            OMI_AUDIO_PLACEMENT_TOTAL.labels(reason=reason)._value.get() - before[0],
            OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL.labels(outcome=outcome, reason=reason)._value.get()
            - before[1],
        )

    assert placed('capture_span', 'resolved') == (len(plan), 1)


def test_off_shadow_metrics_measure_capture_readiness_without_changing_behavior(env, monkeypatch):
    """Consumer OFF: advisory locate still counts capture_span per embeddable
    segment while legacy resolution keeps sync-only behavior."""
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'false')
    _, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    before = OMI_AUDIO_PLACEMENT_TOTAL.labels(reason='capture_span')._value.get()

    conversation = _capture_shifted_conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)

    assert OMI_AUDIO_PLACEMENT_TOTAL.labels(reason='capture_span')._value.get() == before + len(plan)
    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_span_on_single_live_scope_unplaceable_is_unavailable_not_capture(env, monkeypatch):
    """One capture scope would normally fall back to 'capture'; a consumer-ON
    refusal for an unplaceable embeddable segment must serialize
    'unavailable' instead."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan, manifest=False)
    for segment in conversation.transcript_segments:
        segment.speaker_id_scope = 'conn:0'

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.model_dump()['speaker_resolution']['status'] == 'unavailable'
    assert diarizer.calls == 0
    assert 'c1' not in store


@pytest.mark.parametrize('lost', ['endpoint', 'endpoint_and_cache'])
def test_span_on_resolved_own_scope_with_lost_endpoint_or_cache_is_unavailable(env, monkeypatch, lost):
    """After an ON resolution, an own-scope segment that loses its capture
    endpoint is unplaceable whether or not the cache survived; the
    consumer-ON refusal must report 'unavailable', not the single-scope
    'capture' fallback."""
    _span_flags(monkeypatch)
    store, diarizer = env
    plan = [0, 1] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    conversation = _capture_shifted_conversation(plan)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert conversation.speaker_resolution.status == 'resolved'
    calls_after_on = diarizer.calls

    conversation.transcript_segments[2].audio_capture_start = None
    conversation.transcript_segments[2].audio_capture_end = None
    if lost == 'endpoint_and_cache':
        del store['c1']

    stage.resolve_speakers_for_processing('u1', conversation)

    assert conversation.speaker_resolution.status == 'unavailable'
    assert diarizer.calls == calls_after_on
