from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Union

import numpy as np

from database import self_voice_review as review_db
from database import users as users_db
from models.transcript_segment import TranscriptSegment
from utils.stt.background_speaker_identity import (
    ClusterIdentityAssignment,
    ClusterSampleSpan,
    USER_SELF_PERSON_ID,
    select_representative_cluster_spans,
)
from utils.stt.speaker_embedding import extract_embedding_from_bytes

MIN_REVIEW_SAMPLE_SECONDS = 5.0
MAX_REVIEW_SAMPLE_SECONDS = 10.0
MIN_VOICED_RATIO = 0.65
MIN_VAD_CONFIDENCE = 0.75
MAX_NOISE_SCORE = 0.35
SKIP_COOLDOWN_DAYS = 14
SELF_VOICE_REVIEW_VERSION = 'self-voice-review:v1'
SELF_VOICE_EMBEDDING_SOURCE = 'self_voice_review_confirm'


@dataclass
class SegmentQuality:
    voiced_seconds: Optional[float] = None
    vad_confidence: Optional[float] = None
    noise_score: Optional[float] = None


@dataclass
class CandidateSelectionResult:
    candidate: Optional[dict] = None
    reason: Optional[str] = None
    spans: list[ClusterSampleSpan] = field(default_factory=list)


def build_self_voice_review_candidate(
    uid: str,
    conversation_id: str,
    provider_cluster_id: str,
    cluster_segments: list[TranscriptSegment],
    all_segments: list[TranscriptSegment],
    identity_assignment: Optional[ClusterIdentityAssignment] = None,
    quality_by_segment_id: Optional[dict[str, Union[SegmentQuality, dict]]] = None,
    audio_artifact_ref: Optional[str] = None,
    audio_retention_allowed: bool = False,
    now: Optional[datetime] = None,
) -> CandidateSelectionResult:
    now = now or _utc_now()
    quality_by_segment_id = quality_by_segment_id or {}

    if not audio_retention_allowed or not audio_artifact_ref:
        return CandidateSelectionResult(reason='audio_unavailable_or_retention_disallowed')

    spans = select_representative_cluster_spans(
        cluster_segments,
        all_segments,
        preferred_seconds=MIN_REVIEW_SAMPLE_SECONDS,
        max_seconds=MAX_REVIEW_SAMPLE_SECONDS,
    )
    quality = _score_candidate_quality(spans, quality_by_segment_id)
    if not spans:
        return CandidateSelectionResult(reason='no_clean_voiced_window', spans=spans)
    if quality['sample_seconds'] < MIN_REVIEW_SAMPLE_SECONDS:
        return CandidateSelectionResult(reason='sample_too_short', spans=spans)
    if quality['vad_confidence'] is not None and quality['vad_confidence'] < MIN_VAD_CONFIDENCE:
        return CandidateSelectionResult(reason='low_vad_confidence', spans=spans)
    if quality['voiced_ratio'] is not None and quality['voiced_ratio'] < MIN_VOICED_RATIO:
        return CandidateSelectionResult(reason='low_voiced_ratio', spans=spans)
    if quality['noise_score'] is not None and quality['noise_score'] > MAX_NOISE_SCORE:
        return CandidateSelectionResult(reason='noisy_clip', spans=spans)

    segment_ids = [span.segment_id for span in spans]
    candidate_id = review_db.candidate_id_from_source(conversation_id, provider_cluster_id, segment_ids)
    negative_marker_id = review_db.marker_id_from_source(conversation_id, provider_cluster_id)
    if review_db.get_candidate(uid, candidate_id):
        return CandidateSelectionResult(reason='already_confirmed_or_pending', spans=spans)
    if review_db.has_negative_marker(uid, negative_marker_id):
        return CandidateSelectionResult(reason='rejected_source', spans=spans)
    if review_db.recently_shown_source_exists(uid, conversation_id, provider_cluster_id, now=now):
        return CandidateSelectionResult(reason='recently_shown', spans=spans)

    confidence_bucket = _confidence_bucket(identity_assignment, quality)
    if confidence_bucket is None:
        return CandidateSelectionResult(reason='not_self_voice_candidate', spans=spans)

    candidate = {
        'candidate_id': candidate_id,
        'source': {
            'conversation_id': conversation_id,
            'provider_cluster_id': provider_cluster_id,
            'segment_ids': segment_ids,
            'sample_spans': [span.as_dict() for span in spans],
        },
        'confidence_bucket': confidence_bucket,
        'quality_scores': quality,
        'review_status': 'pending',
        'reviewed_at': None,
        'cooldown_until': None,
        'retention': {
            'audio_artifact_ref': audio_artifact_ref,
            'audio_retention_allowed': True,
            'transcript_text_stored': False,
            'expires_at': now + timedelta(days=review_db.DEFAULT_CANDIDATE_TTL_DAYS),
        },
        'negative_review_marker': None,
        'created_at': now,
        'updated_at': now,
        'expires_at': now + timedelta(days=review_db.DEFAULT_CANDIDATE_TTL_DAYS),
        'version': SELF_VOICE_REVIEW_VERSION,
    }
    review_db.upsert_candidate(uid, candidate)
    return CandidateSelectionResult(candidate=candidate, spans=spans)


def confirm_self_voice_candidate(
    uid: str,
    candidate_id: str,
    audio_bytes: Optional[bytes] = None,
    embedding: Optional[np.ndarray] = None,
    embedding_extractor: Callable[[bytes, str], np.ndarray] = extract_embedding_from_bytes,
) -> dict:
    candidate = _require_candidate(uid, candidate_id)
    if candidate.get('review_status') not in ('pending', 'skipped'):
        raise ValueError('candidate is not confirmable')

    retention = candidate.get('retention') or {}
    if not retention.get('audio_retention_allowed') and embedding is None:
        raise ValueError('candidate audio is not available for confirmation')

    if embedding is None:
        if not audio_bytes:
            raise ValueError('audio_bytes or embedding is required to confirm self voice')
        embedding = embedding_extractor(audio_bytes, f'self_voice_review_{candidate_id}.wav')

    users_db.set_user_speaker_embedding(uid, embedding.reshape(1, -1).flatten().tolist())
    review_db.mark_candidate_confirmed(uid, candidate_id, SELF_VOICE_EMBEDDING_SOURCE)
    return {'candidate_id': candidate_id, 'review_status': 'confirmed'}


def reject_self_voice_candidate(uid: str, candidate_id: str) -> dict:
    candidate = _require_candidate(uid, candidate_id)
    if candidate.get('review_status') == 'confirmed':
        raise ValueError('confirmed candidate must be deleted instead of rejected')
    marker_id = review_db.mark_candidate_rejected(uid, candidate)
    return {'candidate_id': candidate_id, 'review_status': 'rejected', 'negative_marker_id': marker_id}


def skip_self_voice_candidate(
    uid: str,
    candidate_id: str,
    now: Optional[datetime] = None,
    cooldown_days: int = SKIP_COOLDOWN_DAYS,
) -> dict:
    _require_candidate(uid, candidate_id)
    now = now or _utc_now()
    cooldown_until = now + timedelta(days=cooldown_days)
    review_db.mark_candidate_skipped(uid, candidate_id, cooldown_until, reviewed_at=now)
    return {
        'candidate_id': candidate_id,
        'review_status': 'pending',
        'last_review_action': 'skipped',
        'cooldown_until': cooldown_until,
    }


def delete_confirmed_self_voice_sample(uid: str, candidate_id: str) -> bool:
    return review_db.delete_confirmed_sample(uid, candidate_id)


def _require_candidate(uid: str, candidate_id: str) -> dict:
    candidate = review_db.get_candidate(uid, candidate_id)
    if not candidate:
        raise ValueError('self voice review candidate not found')
    return candidate


def _score_candidate_quality(
    spans: list[ClusterSampleSpan],
    quality_by_segment_id: dict[str, Union[SegmentQuality, dict]],
) -> dict:
    sample_seconds = round(sum(span.duration for span in spans), 3)
    voiced_seconds = 0.0
    vad_values = []
    noise_values = []
    has_voiced_signal = False

    for span in spans:
        quality = _quality_for_segment(quality_by_segment_id.get(span.segment_id))
        if not quality:
            continue
        if quality.voiced_seconds is not None:
            has_voiced_signal = True
            voiced_seconds += min(max(quality.voiced_seconds, 0.0), span.duration)
        if quality.vad_confidence is not None:
            vad_values.append(quality.vad_confidence)
        if quality.noise_score is not None:
            noise_values.append(quality.noise_score)

    voiced_ratio = None
    if has_voiced_signal and sample_seconds > 0:
        voiced_ratio = round(voiced_seconds / sample_seconds, 3)

    return {
        'sample_seconds': sample_seconds,
        'voiced_ratio': voiced_ratio,
        'vad_confidence': round(sum(vad_values) / len(vad_values), 3) if vad_values else None,
        'noise_score': round(sum(noise_values) / len(noise_values), 3) if noise_values else None,
        'overlapped_speech': False,
    }


def _quality_for_segment(value: Optional[Union[SegmentQuality, dict]]) -> Optional[SegmentQuality]:
    if value is None:
        return None
    if isinstance(value, SegmentQuality):
        return value
    return SegmentQuality(
        voiced_seconds=value.get('voiced_seconds'),
        vad_confidence=value.get('vad_confidence'),
        noise_score=value.get('noise_score'),
    )


def _confidence_bucket(assignment: Optional[ClusterIdentityAssignment], quality: dict) -> Optional[str]:
    if assignment is None:
        return None
    if assignment.person_id:
        return None
    if assignment.state == 'user' and assignment.confidence is not None and assignment.confidence >= 0.7:
        return 'high'

    for candidate in assignment.candidates:
        if not candidate.get('is_user') and candidate.get('person_id') != USER_SELF_PERSON_ID:
            continue
        confidence = candidate.get('confidence')
        distance = candidate.get('distance')
        if confidence is not None and confidence >= 0.35:
            return 'low'
        if distance is not None and distance < 0.45:
            return 'low'

    if quality['sample_seconds'] >= MIN_REVIEW_SAMPLE_SECONDS:
        return 'low'
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
