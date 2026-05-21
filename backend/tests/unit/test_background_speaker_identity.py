import io
import wave

import numpy as np

from models.message_event import SpeakerLabelSuggestionEvent
from models.transcript_segment import TranscriptSegment
from utils.stt.background_speaker_identity import (
    SPEAKER_IDENTITY_SOURCE,
    SPEAKER_IDENTITY_VERSION,
    identify_background_speaker_clusters,
    select_representative_cluster_spans,
)


def _segment(segment_id, start, end, cluster='cluster-a', speaker='SPEAKER_01', text='hello from speaker'):
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker=speaker,
        is_user=False,
        start=start,
        end=end,
        provider_cluster_id=cluster,
        provider_speaker_label=speaker,
        speaker_identity_state='unassigned',
    )


def _wav_bytes(duration_seconds=30, sample_rate=16000):
    samples = np.zeros(int(duration_seconds * sample_rate), dtype=np.int16)
    out = io.BytesIO()
    with wave.open(out, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return out.getvalue()


def test_cluster_sampling_prefers_clean_spans_and_caps_total_duration():
    cluster_segments = [
        _segment('short', 0.0, 0.5),
        _segment('overlap', 1.0, 8.0),
        _segment('clean-long', 9.0, 24.0),
        _segment('clean-second', 24.5, 33.0),
    ]
    all_segments = cluster_segments + [_segment('other-overlap', 2.0, 3.0, cluster='cluster-b')]

    spans = select_representative_cluster_spans(cluster_segments, all_segments)

    assert [span.segment_id for span in spans] == ['clean-long']
    assert sum(span.duration for span in spans) == 10.0
    assert all(span.segment_id != 'overlap' for span in spans)
    assert all(span.duration >= 1.0 for span in spans)


def test_cluster_identity_applies_one_voice_assignment_to_all_cluster_segments():
    alice_embedding = np.array([[1.0, 0.0]], dtype=np.float32)
    bob_embedding = np.array([[0.0, 1.0]], dtype=np.float32)
    segments = [
        _segment('a1', 0.0, 3.0, cluster='cluster-a', speaker='SPEAKER_01'),
        _segment('a2', 3.5, 6.5, cluster='cluster-a', speaker='SPEAKER_01'),
        _segment('b1', 7.0, 10.0, cluster='cluster-b', speaker='SPEAKER_02'),
    ]
    cache = {
        'person-alice': {'embedding': alice_embedding, 'name': 'Alice'},
        'person-bob': {'embedding': bob_embedding, 'name': 'Bob'},
    }

    def fake_extract(_audio, _filename):
        return alice_embedding

    assignments = identify_background_speaker_clusters(segments, _wav_bytes(), cache, embedding_extractor=fake_extract)

    assert assignments['cluster-a'].person_id == 'person-alice'
    assert assignments['cluster-a'].confidence == 1.0
    assert segments[0].person_id == 'person-alice'
    assert segments[1].person_id == 'person-alice'
    assert segments[0].speaker_identity_source == SPEAKER_IDENTITY_SOURCE
    assert segments[0].speaker_identity_version == SPEAKER_IDENTITY_VERSION
    assert segments[0].speaker_identity_provenance['provider_cluster_id'] == 'cluster-a'
    assert segments[0].speaker_identity_candidates[0]['person_id'] == 'person-alice'


def test_low_confidence_cluster_remains_explicitly_unknown_with_candidate_metadata():
    query_embedding = np.array([[1.0, 0.0]], dtype=np.float32)
    distant_embedding = np.array([[0.0, 1.0]], dtype=np.float32)
    segments = [_segment('a1', 0.0, 3.0)]
    cache = {'person-distant': {'embedding': distant_embedding, 'name': 'Distant'}}

    assignments = identify_background_speaker_clusters(
        segments,
        _wav_bytes(),
        cache,
        embedding_extractor=lambda _audio, _filename: query_embedding,
    )

    assert assignments['cluster-a'].state == 'unknown'
    assert assignments['cluster-a'].reason == 'below_threshold'
    assert segments[0].speaker_identity_state == 'unknown'
    assert segments[0].person_id is None
    assert segments[0].speaker_identity_candidates[0]['person_id'] == 'person-distant'
    assert segments[0].speaker_identity_confidence is None


def test_text_self_introduction_is_hint_only_without_voice_assignment():
    segments = [_segment('intro', 0.0, 3.0, text='I am Alice and I joined the call.')]

    assignments = identify_background_speaker_clusters(segments, audio_bytes=None, person_embeddings_cache={})

    assert assignments['cluster-a'].state == 'unknown'
    assert assignments['cluster-a'].text_hints[0]['detected_name'] == 'Alice'
    assert segments[0].person_id is None
    assert segments[0].speaker_identity_state == 'unknown'
    assert segments[0].speaker_identity_text_hints[0]['source'] == 'text_self_introduction'


def test_user_sentinel_is_not_persisted_as_durable_person_identity():
    user_embedding = np.array([[1.0, 0.0]], dtype=np.float32)
    segments = [_segment('me', 0.0, 4.0)]
    cache = {'user': {'embedding': user_embedding, 'name': 'User'}}

    identify_background_speaker_clusters(
        segments,
        _wav_bytes(),
        cache,
        embedding_extractor=lambda _audio, _filename: user_embedding,
    )

    assert segments[0].is_user is True
    assert segments[0].person_id is None
    assert segments[0].speaker_identity_state == 'user'
    assert segments[0].speaker_identity_candidates[0]['person_id'] is None
    assert segments[0].speaker_identity_candidates[0]['is_user'] is True


def test_speaker_label_suggestion_event_preserves_legacy_shape_and_accepts_cluster_metadata():
    legacy = SpeakerLabelSuggestionEvent(
        speaker_id=1,
        person_id='person-1',
        person_name='Alice',
        segment_id='segment-1',
    ).to_json()

    assert legacy['type'] == 'speaker_label_suggestion'
    assert legacy['version'] == 1
    assert legacy['speaker_id'] == 1
    assert legacy['person_id'] == 'person-1'

    extended = SpeakerLabelSuggestionEvent(
        speaker_id=1,
        person_id='person-1',
        person_name='Alice',
        segment_id='segment-1',
        version=2,
        provider_cluster_id='cluster-a',
        speaker_identity_state='identified',
        confidence=0.91,
        source=SPEAKER_IDENTITY_SOURCE,
        provenance={'sample_seconds': 6.0},
        candidates=[{'person_id': 'person-1', 'confidence': 0.91}],
    ).to_json()

    assert extended['version'] == 2
    assert extended['provider_cluster_id'] == 'cluster-a'
    assert extended['provenance']['sample_seconds'] == 6.0
