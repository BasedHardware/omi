import io
import sys
import wave
from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
speaker_embedding_mod = MagicMock()
speaker_embedding_mod.extract_embedding_from_bytes = MagicMock()
sys.modules.setdefault('utils.stt.speaker_embedding', speaker_embedding_mod)
firestore_v1_mod = sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())
firestore_v1_mod.FieldFilter = MagicMock()

firestore_mod = MagicMock()
firestore_mod.Query.DESCENDING = 'DESCENDING'
sys.modules.setdefault('google.cloud.firestore', firestore_mod)

google_cloud_mod = sys.modules.setdefault('google.cloud', MagicMock())
google_cloud_mod.firestore = firestore_mod

from models.transcript_segment import TranscriptSegment
from utils.stt.background_speaker_identity import ClusterIdentityAssignment, SPEAKER_IDENTITY_SOURCE
from utils.self_voice_review import (
    SegmentQuality,
    build_self_voice_review_candidate,
    confirm_self_voice_candidate,
    delete_confirmed_self_voice_sample,
    reject_self_voice_candidate,
    skip_self_voice_candidate,
)


def _segment(segment_id, start, end, cluster='cluster-a', text='hello this is a clean sentence'):
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker='SPEAKER_01',
        is_user=False,
        start=start,
        end=end,
        provider_cluster_id=cluster,
        provider_speaker_label='SPEAKER_01',
        speaker_identity_state='unknown',
    )


def _user_assignment(confidence=0.82):
    return ClusterIdentityAssignment(
        provider_cluster_id='cluster-a',
        speaker_id=1,
        state='user',
        is_user=True,
        confidence=confidence,
        distance=0.1,
        source=SPEAKER_IDENTITY_SOURCE,
    )


def _wav_bytes(duration_seconds=6, sample_rate=16000):
    samples = np.zeros(int(duration_seconds * sample_rate), dtype=np.int16)
    out = io.BytesIO()
    with wave.open(out, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return out.getvalue()


class FakeReviewDb:
    DEFAULT_CANDIDATE_TTL_DAYS = 30

    def __init__(self):
        self.candidates = {}
        self.negative_markers = set()
        self.confirmed = []
        self.rejected = []
        self.skipped = []
        self.deleted = []

    def candidate_id_from_source(self, conversation_id, provider_cluster_id, segment_ids):
        return f'{conversation_id}:{provider_cluster_id}:{"-".join(segment_ids)}'

    def marker_id_from_source(self, conversation_id, provider_cluster_id):
        return f'{conversation_id}:{provider_cluster_id}'

    def get_candidate(self, _uid, candidate_id):
        return self.candidates.get(candidate_id)

    def has_negative_marker(self, _uid, marker_id):
        return marker_id in self.negative_markers

    def recently_shown_source_exists(self, *_args, **_kwargs):
        return False

    def upsert_candidate(self, _uid, candidate):
        self.candidates[candidate['candidate_id']] = candidate
        return True

    def mark_candidate_confirmed(self, _uid, candidate_id, embedding_version):
        self.candidates[candidate_id]['review_status'] = 'confirmed'
        self.candidates[candidate_id]['confirmed_sample'] = {
            'candidate_id': candidate_id,
            'embedding_version': embedding_version,
            'revisable': True,
        }
        self.confirmed.append((candidate_id, embedding_version))

    def mark_candidate_rejected(self, _uid, candidate):
        marker_id = self.marker_id_from_source(
            candidate['source']['conversation_id'], candidate['source']['provider_cluster_id']
        )
        self.negative_markers.add(marker_id)
        self.candidates[candidate['candidate_id']]['review_status'] = 'rejected'
        self.candidates[candidate['candidate_id']]['negative_review_marker'] = {'marker_id': marker_id}
        self.rejected.append(candidate['candidate_id'])
        return marker_id

    def mark_candidate_skipped(self, _uid, candidate_id, cooldown_until, reviewed_at=None):
        self.candidates[candidate_id]['review_status'] = 'pending'
        self.candidates[candidate_id]['last_review_action'] = 'skipped'
        self.candidates[candidate_id]['cooldown_until'] = cooldown_until
        self.skipped.append((candidate_id, cooldown_until, reviewed_at))

    def delete_confirmed_sample(self, _uid, candidate_id):
        if self.candidates[candidate_id]['review_status'] != 'confirmed':
            return False
        self.candidates[candidate_id]['review_status'] = 'deleted'
        self.deleted.append(candidate_id)
        return True


def test_candidate_creation_stores_state_without_transcript_text(monkeypatch):
    from utils import self_voice_review

    fake_db = FakeReviewDb()
    monkeypatch.setattr(self_voice_review, 'review_db', fake_db)
    segments = [_segment('s1', 0.0, 6.0)]

    result = build_self_voice_review_candidate(
        uid='uid',
        conversation_id='conv',
        provider_cluster_id='cluster-a',
        cluster_segments=segments,
        all_segments=segments,
        identity_assignment=_user_assignment(),
        quality_by_segment_id={'s1': SegmentQuality(voiced_seconds=5.5, vad_confidence=0.9, noise_score=0.1)},
        audio_artifact_ref='gs://bucket/clip.wav',
        audio_retention_allowed=True,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert result.candidate is not None
    candidate = result.candidate
    assert candidate['candidate_id'] == 'conv:cluster-a:s1'
    assert candidate['confidence_bucket'] == 'high'
    assert candidate['quality_scores']['sample_seconds'] == 6.0
    assert candidate['quality_scores']['voiced_ratio'] == pytest.approx(0.917)
    assert candidate['retention']['transcript_text_stored'] is False
    assert 'text' not in candidate['source']
    assert 'transcript' not in candidate['source']
    assert fake_db.candidates[candidate['candidate_id']]['review_status'] == 'pending'


def test_candidate_quality_filters_overlap_short_low_vad_noise_and_retention(monkeypatch):
    from utils import self_voice_review

    fake_db = FakeReviewDb()
    monkeypatch.setattr(self_voice_review, 'review_db', fake_db)

    clean = [_segment('s1', 0.0, 6.0)]
    no_audio = build_self_voice_review_candidate(
        'uid', 'conv', 'cluster-a', clean, clean, _user_assignment(), audio_retention_allowed=False
    )
    assert no_audio.reason == 'audio_unavailable_or_retention_disallowed'

    short = [_segment('s2', 0.0, 3.0)]
    short_result = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-a',
        short,
        short,
        _user_assignment(),
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    )
    assert short_result.reason == 'sample_too_short'

    overlap = [_segment('s3', 0.0, 6.0)]
    all_segments = overlap + [_segment('other', 2.0, 3.0, cluster='cluster-b')]
    overlap_result = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-a',
        overlap,
        all_segments,
        _user_assignment(),
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    )
    assert overlap_result.reason == 'no_clean_voiced_window'

    low_vad = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-low-vad',
        [_segment('s4', 0.0, 6.0, cluster='cluster-low-vad')],
        [_segment('s4', 0.0, 6.0, cluster='cluster-low-vad')],
        _user_assignment(),
        {'s4': {'voiced_seconds': 5.5, 'vad_confidence': 0.5}},
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    )
    assert low_vad.reason == 'low_vad_confidence'

    noisy = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-noisy',
        [_segment('s5', 0.0, 6.0, cluster='cluster-noisy')],
        [_segment('s5', 0.0, 6.0, cluster='cluster-noisy')],
        _user_assignment(),
        {'s5': {'voiced_seconds': 5.5, 'vad_confidence': 0.9, 'noise_score': 0.8}},
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    )
    assert noisy.reason == 'noisy_clip'


def test_dedupe_reject_marker_and_recently_shown_suppress_candidates(monkeypatch):
    from utils import self_voice_review

    fake_db = FakeReviewDb()
    monkeypatch.setattr(self_voice_review, 'review_db', fake_db)
    segments = [_segment('s1', 0.0, 6.0)]
    kwargs = {
        'uid': 'uid',
        'conversation_id': 'conv',
        'provider_cluster_id': 'cluster-a',
        'cluster_segments': segments,
        'all_segments': segments,
        'identity_assignment': _user_assignment(),
        'quality_by_segment_id': {'s1': {'voiced_seconds': 5.5, 'vad_confidence': 0.9}},
        'audio_artifact_ref': 'ref',
        'audio_retention_allowed': True,
    }

    assert build_self_voice_review_candidate(**kwargs).candidate is not None
    assert build_self_voice_review_candidate(**kwargs).reason == 'already_confirmed_or_pending'

    fake_db.candidates.clear()
    fake_db.negative_markers.add('conv:cluster-a')
    assert build_self_voice_review_candidate(**kwargs).reason == 'rejected_source'

    fake_db.negative_markers.clear()
    fake_db.recently_shown_source_exists = lambda *_args, **_kwargs: True
    assert build_self_voice_review_candidate(**kwargs).reason == 'recently_shown'


def test_confirm_reject_skip_and_delete_actions(monkeypatch):
    from utils import self_voice_review

    fake_db = FakeReviewDb()
    fake_users_db = MagicMock()
    monkeypatch.setattr(self_voice_review, 'review_db', fake_db)
    monkeypatch.setattr(self_voice_review, 'users_db', fake_users_db)
    segments = [_segment('s1', 0.0, 6.0)]
    candidate = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-a',
        segments,
        segments,
        _user_assignment(),
        {'s1': {'voiced_seconds': 5.5, 'vad_confidence': 0.9}},
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    ).candidate

    skipped = skip_self_voice_candidate('uid', candidate['candidate_id'], now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert skipped['review_status'] == 'pending'
    assert skipped['last_review_action'] == 'skipped'
    assert fake_db.candidates[candidate['candidate_id']]['cooldown_until'].year == 2026

    embedding = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    confirmed = confirm_self_voice_candidate('uid', candidate['candidate_id'], embedding=embedding)
    assert confirmed['review_status'] == 'confirmed'
    fake_users_db.set_user_speaker_embedding.assert_called_once_with('uid', [1.0, 2.0, 3.0])
    assert fake_db.candidates[candidate['candidate_id']]['confirmed_sample']['revisable'] is True
    assert delete_confirmed_self_voice_sample('uid', candidate['candidate_id']) is True

    second = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-b',
        [_segment('s2', 10.0, 16.0, cluster='cluster-b')],
        [_segment('s2', 10.0, 16.0, cluster='cluster-b')],
        _user_assignment(),
        {'s2': {'voiced_seconds': 5.5, 'vad_confidence': 0.9}},
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    ).candidate
    rejected = reject_self_voice_candidate('uid', second['candidate_id'])
    assert rejected['review_status'] == 'rejected'
    assert rejected['negative_marker_id'] == 'conv:cluster-b'
    assert fake_db.candidates[second['candidate_id']]['negative_review_marker']['marker_id'] == 'conv:cluster-b'


def test_confirm_can_extract_embedding_from_audio(monkeypatch):
    from utils import self_voice_review

    fake_db = FakeReviewDb()
    fake_users_db = MagicMock()
    monkeypatch.setattr(self_voice_review, 'review_db', fake_db)
    monkeypatch.setattr(self_voice_review, 'users_db', fake_users_db)
    segments = [_segment('s1', 0.0, 6.0)]
    candidate = build_self_voice_review_candidate(
        'uid',
        'conv',
        'cluster-a',
        segments,
        segments,
        _user_assignment(),
        {'s1': {'voiced_seconds': 5.5, 'vad_confidence': 0.9}},
        audio_artifact_ref='ref',
        audio_retention_allowed=True,
    ).candidate

    def fake_extractor(audio_bytes, filename):
        assert audio_bytes == _wav_bytes()
        assert filename.endswith('.wav')
        return np.array([[4.0, 5.0]], dtype=np.float32)

    confirm_self_voice_candidate(
        'uid', candidate['candidate_id'], audio_bytes=_wav_bytes(), embedding_extractor=fake_extractor
    )

    fake_users_db.set_user_speaker_embedding.assert_called_once_with('uid', [4.0, 5.0])


def test_candidate_storage_rejects_transcript_and_raw_audio_payloads():
    from database.self_voice_review import _reject_forbidden_candidate_keys

    with pytest.raises(ValueError, match='forbidden keys'):
        _reject_forbidden_candidate_keys(
            {
                'candidate_id': 'candidate',
                'source': {'conversation_id': 'conv', 'transcript_text': 'this must not be stored'},
            }
        )

    with pytest.raises(ValueError, match='forbidden keys'):
        _reject_forbidden_candidate_keys({'candidate_id': 'candidate', 'raw_audio': b'not allowed'})
