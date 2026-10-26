"""Synthetic producer clocks and generation-pinned, bounded speaker evidence."""

import time
from types import SimpleNamespace

import pytest

from models.structured import Structured
from tests.unit.test_conversation_speaker_resolution_stage import _conversation, env, VOICES  # noqa: F401
from utils.batch_pipeline import projection
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.projection_parts import bounded_projection_words, split_result
from utils.conversations import speaker_resolution as stage
from utils.other import audio_chunks, storage
from utils.stt.pre_recorded import postprocess_words


def test_legacy_centisecond_rounding_is_not_a_valid_batch_pcm_clock():
    words = [{'text': 'Synthetic.', 'timestamp': [0, 2.345], 'speaker': 'SPEAKER_00'}]
    legacy = postprocess_words(words, 0)[0]
    precise = postprocess_words(words, 0, preserve_timestamps=True)[0]
    assert legacy.end - 2.345 > stage.COVERAGE_TOLERANCE_SECONDS
    assert not stage._window_covered([(0, 2.345)], legacy.start, legacy.end)
    assert stage._window_covered([(0, 2.345)], precise.start, precise.end)


def test_model_eof_tolerance_cannot_extend_projected_part_or_word():
    duration = 2.345
    item = WorkItem('unit', 'synthetic-owner', 1700000000.0, 'gs://synthetic/pcm', duration, Priority.FRESH)
    words = [{'word': 'Synthetic.', 'timestamp': [0.1234, duration + 0.009], 'speaker': 'SPEAKER_00'}]
    payload = {
        'audio_seconds': duration,
        'words': words,
        'speech_spans': [{'start': 0, 'end': duration}],
        'speech_seconds': duration,
        'diarization': {'turns': [{'start': 0, 'end': duration, 'speaker': 'SPEAKER_00'}]},
    }
    part, projected = split_result(item, payload)[0]
    assert part.duration_seconds == duration
    assert projected['audio_seconds'] == duration
    assert projected['words'][0]['timestamp'][1] == duration
    assert words[0]['timestamp'][1] > duration  # input is not mutated


@pytest.mark.parametrize('timestamps', [[2.35, 2.354], [2.345, 2.35], [0, 0]])
def test_words_without_captured_samples_cannot_invent_a_window(timestamps):
    result = bounded_projection_words([{'word': 'Synthetic.', 'timestamp': timestamps}], 2.345)
    assert result[0]['word'] == 'Synthetic.'
    assert result[0]['timestamp'] == [min(timestamps[0], 2.345), min(timestamps[1], 2.345)]
    assert result[0]['timestamp'][0] == result[0]['timestamp'][1]


@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('point', [[1, 1], [2.35, 2.354]])
@pytest.mark.parametrize('with_positive_word', [False, True])
def test_projection_preserves_point_word_text_without_borrowing_voice(monkeypatch, recovery, point, with_positive_word):
    from utils.conversations import deterministic_minimum
    from utils.sync import intake_completion

    monkeypatch.setattr(deterministic_minimum, 'build_deterministic_minimum_structured', lambda *a, **k: Structured())
    monkeypatch.setattr(intake_completion, 'apply_capture_evidence_dark_write', lambda *a: None)
    monkeypatch.setattr(projection, 'cap_dispatch_enabled', lambda *a: False)
    duration = 2.345
    item = WorkItem('unit', 'synthetic-owner', 1700000000.0, 'gs://synthetic/pcm', duration, Priority.FRESH)
    binding = ProjectionBinding(item.owner_id, 'job', 'content', (item.segment_id,))
    payload = {
        'audio_seconds': duration,
        'words': ([{'word': 'Heard.', 'timestamp': [0, 1], 'speaker': 'SPEAKER_00'}] if with_positive_word else [])
        + [{'word': 'Unplaced.', 'timestamp': point, 'speaker': 'SPEAKER_00'}],
        'speech_spans': [{'start': 0, 'end': duration}],
        'speech_seconds': duration,
        'diarization': {'turns': [{'start': 0, 'end': duration, 'speaker': 'SPEAKER_00'}]},
        **({'recovery_version': 1} if recovery else {}),
    }
    part, partition = split_result(item, payload)[0]
    incoming = projection.build_incoming(part, binding, partition)
    segments = incoming['transcript_segments']
    assert [s['text'] for s in segments] == (['Heard.'] if with_positive_word else []) + ['Unplaced.']
    unplaced = segments[-1]
    assert unplaced['start'] == unplaced['end'] == min(point[0], duration)
    assert unplaced['speaker'].startswith('BATCH_UNASSIGNED_')
    assert not unplaced['is_user'] and unplaced['person_id'] is None
    if with_positive_word:
        assert segments[0]['speaker'] != unplaced['speaker']


@pytest.mark.parametrize('end', [2.345, 2.349, 2.354, 2.359])
@pytest.mark.parametrize('recovery', [False, True])
def test_batch_projection_does_not_round_words_past_pcm_eof(monkeypatch, end, recovery):
    from utils.conversations import deterministic_minimum
    from utils.sync import intake_completion

    monkeypatch.setattr(deterministic_minimum, 'build_deterministic_minimum_structured', lambda *a, **k: Structured())
    monkeypatch.setattr(intake_completion, 'apply_capture_evidence_dark_write', lambda *a: None)
    monkeypatch.setattr(projection, 'cap_dispatch_enabled', lambda *a: False)
    item = WorkItem('unit', 'synthetic-owner', 1700000000.0, 'gs://synthetic/pcm', end, Priority.FRESH)
    binding = ProjectionBinding(item.owner_id, 'job', 'content', (item.segment_id,))
    payload = {
        'audio_seconds': end,
        'words': [{'word': 'Synthetic.', 'timestamp': [0.1234, end], 'speaker': 'SPEAKER_00'}],
        'diarization': {'turns': [{'start': 0, 'end': end, 'speaker': 'SPEAKER_00'}]},
    }
    if recovery:
        payload['recovery_version'] = 1
    incoming = projection.build_incoming(item, binding, payload)
    segment = incoming['transcript_segments'][0]
    assert segment['start'] == pytest.approx(0.1234, abs=1e-9)
    assert segment['end'] == pytest.approx(end, abs=1e-9)
    assert stage._window_covered(
        [(item.capture_at, item.capture_at + end)], item.capture_at, item.capture_at + segment['end']
    )


@pytest.fixture
def inventory(monkeypatch):
    chunks, pcm, reads = [], {}, []
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *a, **k: chunks)

    class Blob:
        def __init__(self, path):
            self.path = path

        def download_as_bytes(self, **kwargs):
            reads.append(self.path)
            assert kwargs['if_generation_match'] == 7
            return pcm[self.path]

    monkeypatch.setattr(storage, 'get_private_cloud_sync_bucket', lambda: SimpleNamespace(blob=Blob))
    monkeypatch.setattr(
        storage, 'download_and_decode_chunk_blob', lambda bucket, path, *a, **k: bucket.blob(path).download_as_bytes()
    )

    def add(start, duration=4.0, *, span=True, decoded_duration=None, value=1000):
        path = f'synthetic-{len(chunks)}'
        pcm[path] = value.to_bytes(2, 'little') * round(
            (duration if decoded_duration is None else decoded_duration) * stage.SAMPLE_RATE
        )
        chunks.append(
            {
                'path': path,
                'timestamp': start,
                'generation': 7,
                'size': len(pcm[path]),
                **(
                    {
                        'span': {
                            'start': start,
                            'samples': round(duration * stage.SAMPLE_RATE),
                            'sample_rate': stage.SAMPLE_RATE,
                        }
                    }
                    if span
                    else {}
                ),
            }
        )
        return path

    return add, reads


@pytest.mark.parametrize('reverse', [False, True])
def test_rejected_extent_refuses_intersecting_windows_but_preserves_disjoint_clip(env, inventory, monkeypatch, reverse):
    _, diarizer = env
    add, _ = inventory
    conversation = _conversation([1, 0, 0], seconds=6)
    origin = conversation.started_at.timestamp()
    conversation.transcript_segments[2].start = 24
    conversation.transcript_segments[2].end = 29.8
    segments = list(conversation.transcript_segments)
    if reverse:
        conversation.transcript_segments.reverse()
    # The observed invalid extent contradicts the second window's independence,
    # even when that window was verified before the mismatch was discovered.
    add(origin, 1, decoded_duration=20, value=2000)
    for start in (6, 24):
        for index in range(8):
            add(origin + start + index * 0.725, 0.725)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    stage._resolve('synthetic-owner', conversation, receipt={}, deadline=time.monotonic() + 45)
    assert diarizer.calls == 1
    assert all(not segment.is_user and segment.person_id is None for segment in segments[:2])
    assert segments[2].is_user


def prove(conversation, windows):
    placements = {s.id: stage.AudioPlacement(w, 'sync') for s, w in zip(conversation.transcript_segments, windows)}
    return stage._verified_read_session(
        'synthetic-owner', conversation, [], conversation.transcript_segments, placements, time.monotonic() + 45
    )


def test_unrelated_inventory_does_not_spend_download_budget(inventory):
    add, reads = inventory
    conversation = _conversation([0])
    origin = conversation.started_at.timestamp()
    wanted = add(origin)
    for index in range(40):
        add(origin + 20 + index * 4)
    session = prove(conversation, [(origin, origin + 3.8)])
    assert session is not None
    assert session.downloads == 1
    assert reads == [wanted]


def test_uncovered_window_does_not_veto_proven_window(inventory):
    add, reads = inventory
    conversation = _conversation([0, 1])
    origin = conversation.started_at.timestamp()
    wanted = add(origin)
    session = prove(conversation, [(origin, origin + 3.8), (origin + 4, origin + 7.8)])
    assert session is not None
    assert session.verified_segment_ids == {'s0'}
    assert reads == [wanted]


def test_budget_exhaustion_preserves_only_previously_verified_windows(inventory, monkeypatch):
    monkeypatch.setattr(audio_chunks, 'MAX_SPEAKER_DOWNLOADS', 2)
    add, reads = inventory
    conversation = _conversation([0, 1, 2])
    origin = conversation.started_at.timestamp()
    for index in range(3):
        add(origin + 4 * index)
    session = prove(conversation, [(origin + 4 * i, origin + 4 * i + 3.8) for i in range(3)])
    assert session is not None
    assert session.limit_hit
    assert session.verified_segment_ids == {'s0', 's1'}
    assert session.downloads == len(reads) == 2


def test_overlapping_window_abstains_without_vetoing_disjoint_window(inventory):
    add, _ = inventory
    conversation = _conversation([0, 1])
    origin = conversation.started_at.timestamp()
    add(origin)
    add(origin + 4)
    add(origin + 5)
    session = prove(conversation, [(origin, origin + 3.8), (origin + 4, origin + 7.8)])
    assert session is not None
    assert session.verified_segment_ids == {'s0'}


def test_unknown_opus_end_cannot_be_assumed_from_next_filename(inventory):
    add, reads = inventory
    conversation = _conversation([0])
    origin = conversation.started_at.timestamp()
    # The earlier object's actual decoded extent overlaps the later file.
    add(origin - 2, 8, span=False)
    add(origin)
    assert prove(conversation, [(origin, origin + 3.8)]) is None
    assert len(reads) == 2


@pytest.mark.parametrize('failure', ['hole', 'budget', 'overlap'])
def test_real_resolver_embeds_only_proven_windows(env, inventory, monkeypatch, failure):
    cache, diarizer = env
    add, reads = inventory
    conversation = _conversation([0, 1])
    origin = conversation.started_at.timestamp()
    add(origin)
    if failure == 'budget':
        add(origin + 4)
        monkeypatch.setattr(audio_chunks, 'MAX_SPEAKER_DOWNLOADS', 1)
    elif failure == 'overlap':
        add(origin + 4)
        add(origin + 5)
    stage._resolve('synthetic-owner', conversation, receipt={}, deadline=time.monotonic() + 45)
    assert diarizer.calls == 1
    assert len(stage.decode_cache(cache[conversation.id])) == 1
    assert conversation.speaker_resolution.status == 'unavailable'
    # Partial evidence cannot identify the refused segment through a neighbour.
    refused = conversation.transcript_segments[1]
    assert not refused.is_user and refused.person_id is None
    if failure == 'budget':
        assert len(reads) == 1


@pytest.mark.parametrize('batch', [False, True])
def test_proven_owner_identity_cannot_spread_into_missing_audio(env, inventory, monkeypatch, batch):
    _, diarizer = env
    add, _ = inventory
    conversation = _conversation([0, 0], seconds=6)
    origin = conversation.started_at.timestamp()
    add(origin, 6)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: list(VOICES[0]))
    if batch:
        for segment in conversation.transcript_segments:
            segment.speaker_id_scope = 'final:batch:synthetic-unit'
            segment.speaker_id = 0
            segment.speaker = 'SPEAKER_00'
            segment.speaker_match_source = 'batch_pyannote'
    stage._resolve('synthetic-owner', conversation, receipt={}, deadline=time.monotonic() + 45)
    assert diarizer.calls == 1
    assert conversation.transcript_segments[0].is_user
    assert not conversation.transcript_segments[1].is_user
    assert conversation.transcript_segments[1].person_id is None
