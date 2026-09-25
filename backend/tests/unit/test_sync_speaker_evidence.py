"""Synthetic PCM only: batch evidence accounting and first-review observability."""

import io
import logging
import wave

import numpy as np
import pytest

from models.transcript_segment import TranscriptSegment
from utils.manual_speaker_assignments import manual_assignment
from utils.sync import pipeline
from utils.observability.speaker_identification import record_speaker_review, SYNC_SPEAKER_REVIEWS
from utils.stt.sync_speaker_evidence import collect_speaker_audio


def wav(seconds: float = 50) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(1000)
        output.writeframes(np.arange(int(seconds * 1000), dtype=np.int16).tobytes())
    return buffer.getvalue()


def test_four_short_turns_pool_eight_seconds_without_gaps():
    result = collect_speaker_audio(wav(), [(0, 2), (4, 6), (8, 10), (12, 14)])
    assert result.available_seconds == 8
    assert [seconds for _, seconds in result.clips] == [8]
    with wave.open(io.BytesIO(result.clips[0][0]), 'rb') as clip:
        samples = np.frombuffer(clip.readframes(clip.getnframes()), dtype=np.int16)
    np.testing.assert_array_equal(samples, np.concatenate([np.arange(a, a + 2000) for a in (0, 4000, 8000, 12000)]))


def test_subsecond_turns_pool_and_duplicate_intervals_do_not_inflate_evidence():
    result = collect_speaker_audio(wav(3), [(0, 0.6), (0, 0.6), (0.2, 0.8), (1, 1.4)])
    assert result.available_seconds == pytest.approx(1.2)
    assert result.clips[0][1] == pytest.approx(1.2)


def test_clamps_bounds_and_reports_insufficient_total():
    result = collect_speaker_audio(wav(1), [(-2, 0.4), (0.6, 20)])
    assert result.available_seconds == 0.8
    assert result.clips == []


def test_budget_and_balanced_clips():
    result = collect_speaker_audio(wav(), [(0, 40)])
    assert result.available_seconds == 40
    assert [seconds for _, seconds in result.clips] == [10, 10, 10]
    assert [seconds for _, seconds in collect_speaker_audio(wav(), [(0, 10.2)]).clips] == [5.1, 5.1]


def test_single_three_second_turn_remains_eligible():
    assert collect_speaker_audio(wav(), [(0, 3)]).clips[0][1] == 3


@pytest.mark.parametrize(
    'is_user,person_id,outcome',
    [(False, 'new', 'corrected'), (True, None, 'corrected'), (False, None, 'corrected'), (False, 'old', 'confirmed')],
)
def test_first_manual_review_clears_source_and_counts_once(is_user, person_id, outcome):
    before = [
        {
            'id': 's',
            'speaker_id': 1,
            'text': 'synthetic',
            'start': 0,
            'end': 2,
            'is_user': False,
            'person_id': 'old',
            'speaker_match_source': 'sync_embedding',
        }
    ]
    conversation = {'id': 'c', 'transcript_segments': before}
    after, receipt, _, _ = manual_assignment(conversation, person_id=person_id, is_user=is_user, speaker_id=1)
    assert after[0]['speaker_match_source'] is None
    counter = SYNC_SPEAKER_REVIEWS.labels(outcome=outcome)
    start = counter._value.get()
    record_speaker_review('test-user', 'c', before, after)
    assert counter._value.get() == start + 1
    again, _, _, _ = manual_assignment(
        {'id': 'c', 'transcript_segments': after, 'manual_speaker_assignments': receipt},
        person_id='later',
        is_user=False,
        speaker_id=1,
    )
    record_speaker_review('test-user', 'c', after, again)
    assert counter._value.get() == start + 1


def test_legacy_labels_are_not_claimed_as_automatic_reviews():
    old = [{'id': 's', 'person_id': 'old'}]
    counter = SYNC_SPEAKER_REVIEWS.labels(outcome='corrected')
    start = counter._value.get()
    record_speaker_review('test-user', 'c', old, [{'id': 's', 'person_id': 'new'}])
    assert counter._value.get() == start


def test_pipeline_pools_and_logs_real_seconds(monkeypatch, caplog):
    monkeypatch.setattr(pipeline, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(pipeline, 'detect_speaker_from_text', lambda *a, **k: None)
    queries = []

    def embed(audio, name):
        queries.append(audio)
        return np.array([[1.0, 0.0]])

    monkeypatch.setattr(pipeline, 'extract_embedding_from_bytes', embed)
    segments = [
        TranscriptSegment(id=str(i), text='synthetic', speaker_id=1, is_user=False, start=i * 4, end=i * 4 + 2)
        for i in range(4)
    ]
    with caplog.at_level(logging.INFO):
        pipeline.identify_speakers_for_segments(
            segments, wav(), {'p': {'name': 'Synthetic', 'embedding': np.array([[1.0, 0.0]])}}, 'test-user'
        )
    assert len(queries) == 1
    assert all(s.person_id == 'p' and s.speaker_match_source == 'sync_embedding' for s in segments)
    assert 'evidence_seconds=8.000' in caplog.text
    assert 'segments=4 clips=1' in caplog.text


def test_insufficient_evidence_is_a_counted_decision(monkeypatch, caplog):
    monkeypatch.setattr(pipeline, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(pipeline, 'detect_speaker_from_text', lambda *a, **k: None)
    segment = TranscriptSegment(text='synthetic', is_user=False, start=0, end=0.5)
    counter = pipeline.SYNC_SPEAKER_DECISIONS.labels(outcome='insufficient_evidence')
    start = counter._value.get()
    with caplog.at_level(logging.INFO):
        pipeline.identify_speakers_for_segments(
            [segment], wav(), {'p': {'name': 'Synthetic', 'embedding': np.array([[1.0, 0.0]])}}, 'test-user'
        )
    assert counter._value.get() == start + 1
    assert 'speaker_id_decision surface=sync' in caplog.text
    assert 'outcome=insufficient_evidence' in caplog.text


@pytest.mark.parametrize('failure', [False, True])
def test_centroid_uses_all_successful_clips(monkeypatch, caplog, failure):
    monkeypatch.setattr(pipeline, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(pipeline, 'detect_speaker_from_text', lambda *a, **k: None)
    owner, other = np.array([[1.0, 0.0]]), np.array([[0.0, 1.0]])
    vectors = iter([owner, owner, other])

    def embed(audio, name):
        value = next(vectors)
        if failure and np.array_equal(value, other):
            raise ValueError('synthetic failure')
        return value

    monkeypatch.setattr(pipeline, 'extract_embedding_from_bytes', embed)
    segment = TranscriptSegment(text='synthetic', is_user=False, start=0, end=30)
    with caplog.at_level(logging.INFO):
        pipeline.identify_speakers_for_segments(
            [segment],
            wav(),
            {'user': {'name': 'User', 'embedding': owner}, 'p': {'name': 'Synthetic', 'embedding': other}},
            'test-user',
        )
    assert segment.is_user
    assert f'clips={2 if failure else 3} evidence_seconds={20 if failure else 30}.000' in caplog.text
    assert f'failed_clips={int(failure)}' in caplog.text


def test_existing_labels_never_gain_automatic_provenance(monkeypatch):
    monkeypatch.setattr(pipeline, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(pipeline, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]]))
    segment = TranscriptSegment(text='synthetic', is_user=False, person_id='existing', start=0, end=3)
    pipeline.identify_speakers_for_segments(
        [segment], wav(), {'p': {'name': 'Synthetic', 'embedding': np.array([[1.0, 0.0]])}}, 'test-user'
    )
    assert segment.person_id == 'existing'
    assert segment.speaker_match_source is None
