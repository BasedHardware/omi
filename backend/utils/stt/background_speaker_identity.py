import io
import logging
import re
import wave
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from models.transcript_segment import TranscriptSegment

logger = logging.getLogger(__name__)

USER_SELF_PERSON_ID = 'user'
SPEAKER_MATCH_THRESHOLD = 0.45
SPEAKER_IDENTITY_VERSION = 'omi-speaker-identity:v1'
SPEAKER_IDENTITY_SOURCE = 'omi_speaker_embedding'
UNKNOWN_SPEAKER_IDENTITY_SOURCE = 'omi_speaker_embedding:no_match'
TEXT_HINT_SOURCE = 'text_self_introduction'

MIN_CLUSTER_SPAN_SECONDS = 1.0
PREFERRED_CLUSTER_SAMPLE_SECONDS = 5.0
MAX_CLUSTER_SAMPLE_SECONDS = 20.0
MAX_CLUSTER_SPAN_SECONDS = 10.0
OVERLAP_TOLERANCE_SECONDS = 0.1

SELF_INTRODUCTION_HINT_PATTERNS = [
    r"\b(I am|I'm|i am|i'm|My name is|my name is)\s+([A-Z][a-zA-Z]*)\b",
    r"\b([A-Z][a-zA-Z]*)\s+is my name\b",
]


@dataclass
class ClusterSampleSpan:
    start: float
    end: float
    segment_id: str
    duration: float

    def as_dict(self) -> dict:
        return {
            'start': round(self.start, 3),
            'end': round(self.end, 3),
            'segment_id': self.segment_id,
            'duration': round(self.duration, 3),
        }


@dataclass
class ClusterIdentityAssignment:
    provider_cluster_id: str
    speaker_id: Optional[int]
    state: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    is_user: bool = False
    confidence: Optional[float] = None
    distance: Optional[float] = None
    source: str = UNKNOWN_SPEAKER_IDENTITY_SOURCE
    version: str = SPEAKER_IDENTITY_VERSION
    candidates: List[dict] = field(default_factory=list)
    sample_spans: List[ClusterSampleSpan] = field(default_factory=list)
    text_hints: List[dict] = field(default_factory=list)
    reason: Optional[str] = None

    def provenance(self) -> dict:
        data = {
            'provider_cluster_id': self.provider_cluster_id,
            'speaker_id': self.speaker_id,
            'sample_spans': [span.as_dict() for span in self.sample_spans],
            'sample_seconds': round(sum(span.duration for span in self.sample_spans), 3),
        }
        if self.distance is not None:
            data['distance'] = round(self.distance, 6)
        if self.reason:
            data['reason'] = self.reason
        return data


def identify_background_speaker_clusters(
    transcript_segments: List[TranscriptSegment],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    embedding_extractor: Optional[Callable[[bytes, str], np.ndarray]] = None,
    match_threshold: float = SPEAKER_MATCH_THRESHOLD,
) -> Dict[str, ClusterIdentityAssignment]:
    """Assign canonical Omi identity once per provider speaker cluster.

    Text self-introductions are recorded only as hints. Durable assignment
    requires voice evidence from the existing Omi speaker embedding service or
    a later explicit user correction.
    """
    clusters = _group_segments_by_cluster(transcript_segments)
    assignments: Dict[str, ClusterIdentityAssignment] = {}
    matched_person_ids: set[str] = set()

    for cluster_id, cluster_segments in clusters.items():
        text_hints = _collect_text_hints(cluster_segments, cluster_id)
        speaker_id = _cluster_speaker_id(cluster_segments)
        sample_spans = select_representative_cluster_spans(cluster_segments, transcript_segments)
        assignment = ClusterIdentityAssignment(
            provider_cluster_id=cluster_id,
            speaker_id=speaker_id,
            state='unknown',
            sample_spans=sample_spans,
            text_hints=text_hints,
        )

        if not audio_bytes:
            assignment.reason = 'missing_audio'
            assignments[cluster_id] = assignment
            continue
        if not person_embeddings_cache:
            assignment.reason = 'missing_candidate_embeddings'
            assignments[cluster_id] = assignment
            continue
        if not embedding_extractor:
            assignment.reason = 'missing_embedding_extractor'
            assignments[cluster_id] = assignment
            continue
        if not sample_spans:
            assignment.reason = 'no_usable_cluster_spans'
            assignments[cluster_id] = assignment
            continue

        sample_wav = extract_cluster_sample_wav(audio_bytes, sample_spans)
        if not sample_wav:
            assignment.reason = 'sample_extraction_failed'
            assignments[cluster_id] = assignment
            continue

        try:
            query_embedding = embedding_extractor(sample_wav, f'cluster_{_safe_filename(cluster_id)}.wav')
        except Exception as e:
            logger.info('background speaker identity embedding failed cluster=%s: %s', cluster_id, e)
            assignment.reason = 'embedding_extraction_failed'
            assignments[cluster_id] = assignment
            continue

        candidates = _rank_candidates(query_embedding, person_embeddings_cache, matched_person_ids, match_threshold)
        assignment.candidates = _public_candidates(candidates)
        best = candidates[0] if candidates else None
        if not best or best['distance'] >= match_threshold:
            assignment.reason = 'below_threshold'
            assignments[cluster_id] = assignment
            continue

        match_person_id = best['_match_person_id']
        matched_person_ids.add(match_person_id)
        assignment.state = 'user' if match_person_id == USER_SELF_PERSON_ID else 'identified'
        assignment.person_id = None if match_person_id == USER_SELF_PERSON_ID else match_person_id
        assignment.person_name = best.get('person_name')
        assignment.is_user = match_person_id == USER_SELF_PERSON_ID
        assignment.confidence = best['confidence']
        assignment.distance = best['distance']
        assignment.source = SPEAKER_IDENTITY_SOURCE
        assignment.reason = None
        assignments[cluster_id] = assignment

    apply_cluster_identity_assignments(transcript_segments, assignments)
    return assignments


def select_representative_cluster_spans(
    cluster_segments: List[TranscriptSegment],
    all_segments: List[TranscriptSegment],
    preferred_seconds: float = PREFERRED_CLUSTER_SAMPLE_SECONDS,
    max_seconds: float = MAX_CLUSTER_SAMPLE_SECONDS,
) -> List[ClusterSampleSpan]:
    usable_spans = []
    for segment in cluster_segments:
        duration = max(0.0, segment.end - segment.start)
        if duration < MIN_CLUSTER_SPAN_SECONDS:
            continue
        if _has_obvious_overlap(segment, all_segments):
            continue
        if len(segment.text.split()) < 2:
            continue

        end = segment.end
        if duration > MAX_CLUSTER_SPAN_SECONDS:
            center = (segment.start + segment.end) / 2
            start = max(segment.start, center - MAX_CLUSTER_SPAN_SECONDS / 2)
            end = min(segment.end, start + MAX_CLUSTER_SPAN_SECONDS)
        else:
            start = segment.start

        usable_spans.append(
            ClusterSampleSpan(
                start=start,
                end=end,
                segment_id=segment.id,
                duration=end - start,
            )
        )

    usable_spans.sort(key=lambda span: (-span.duration, span.start))

    selected = []
    total = 0.0
    for span in usable_spans:
        if total >= preferred_seconds and selected:
            break
        remaining = max_seconds - total
        if remaining <= 0:
            break
        if span.duration > remaining:
            span = ClusterSampleSpan(
                start=span.start,
                end=span.start + remaining,
                segment_id=span.segment_id,
                duration=remaining,
            )
        selected.append(span)
        total += span.duration

    return sorted(selected, key=lambda span: span.start)


def extract_cluster_sample_wav(audio_bytes: bytes, spans: List[ClusterSampleSpan]) -> Optional[bytes]:
    try:
        with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
            framerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            total_duration = n_frames / framerate
            frames = []
            for span in spans:
                start = max(0.0, min(span.start, total_duration))
                end = max(0.0, min(span.end, total_duration))
                if end - start < MIN_CLUSTER_SPAN_SECONDS:
                    continue
                wf.setpos(int(start * framerate))
                frames.append(wf.readframes(int((end - start) * framerate)))
    except Exception as e:
        logger.info('background speaker identity sample extraction failed: %s', e)
        return None

    frames = [frame for frame in frames if frame]
    if not frames:
        return None

    out = io.BytesIO()
    with wave.open(out, 'wb') as out_wf:
        out_wf.setnchannels(n_channels)
        out_wf.setsampwidth(sampwidth)
        out_wf.setframerate(framerate)
        for frame in frames:
            out_wf.writeframes(frame)
    return out.getvalue()


def apply_cluster_identity_assignments(
    transcript_segments: List[TranscriptSegment],
    assignments: Dict[str, ClusterIdentityAssignment],
) -> None:
    for segment in transcript_segments:
        cluster_id = _segment_cluster_key(segment)
        assignment = assignments.get(cluster_id)
        if not assignment:
            continue

        segment.speaker_identity_state = assignment.state
        segment.speaker_identity_confidence = assignment.confidence
        segment.speaker_identity_source = assignment.source
        segment.speaker_identity_version = assignment.version
        segment.speaker_identity_provenance = assignment.provenance()
        segment.speaker_identity_candidates = assignment.candidates
        segment.speaker_identity_text_hints = assignment.text_hints

        if assignment.is_user:
            segment.is_user = True
            segment.person_id = None
        elif assignment.person_id:
            segment.is_user = False
            segment.person_id = assignment.person_id
        else:
            segment.is_user = False
            segment.person_id = None


def _group_segments_by_cluster(transcript_segments: List[TranscriptSegment]) -> Dict[str, List[TranscriptSegment]]:
    clusters: Dict[str, List[TranscriptSegment]] = {}
    for segment in transcript_segments:
        clusters.setdefault(_segment_cluster_key(segment), []).append(segment)
    return clusters


def _segment_cluster_key(segment: TranscriptSegment) -> str:
    if segment.provider_cluster_id:
        return str(segment.provider_cluster_id)
    if segment.provider_speaker_label:
        return f'provider-label:{segment.provider_speaker_label}'
    return f'legacy-speaker:{segment.speaker_id if segment.speaker_id is not None else 0}'


def _cluster_speaker_id(segments: List[TranscriptSegment]) -> Optional[int]:
    counts = {}
    for segment in segments:
        if segment.speaker_id is None:
            continue
        counts[segment.speaker_id] = counts.get(segment.speaker_id, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _has_obvious_overlap(segment: TranscriptSegment, all_segments: List[TranscriptSegment]) -> bool:
    for other in all_segments:
        if other.id == segment.id:
            continue
        if _segment_cluster_key(other) == _segment_cluster_key(segment):
            continue
        overlap = min(segment.end, other.end) - max(segment.start, other.start)
        if overlap > OVERLAP_TOLERANCE_SECONDS:
            return True
    return False


def _collect_text_hints(segments: List[TranscriptSegment], cluster_id: str) -> List[dict]:
    hints = []
    for segment in segments:
        detected_name = _detect_self_introduction_hint(segment.text)
        if not detected_name:
            continue
        hints.append(
            {
                'source': TEXT_HINT_SOURCE,
                'provider_cluster_id': cluster_id,
                'segment_id': segment.id,
                'detected_name': detected_name,
            }
        )
    return hints


def _detect_self_introduction_hint(text: str) -> Optional[str]:
    for pattern in SELF_INTRODUCTION_HINT_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue
        if _looks_like_quoted_or_reported_speech(text, match.start()):
            continue
        name = match.groups()[-1]
        if name and len(name) >= 2:
            return name.capitalize()
    return None


def _looks_like_quoted_or_reported_speech(text: str, match_start: int) -> bool:
    prefix = text[:match_start].strip().lower()
    if prefix and prefix[-1:] in {'"', "'", '“', '‘'}:
        return True
    recent_prefix = prefix[-40:]
    return bool(re.search(r"\b(said|says|asked|told|quoted|read|wrote|writes)\b", recent_prefix))


def _rank_candidates(
    query_embedding: np.ndarray,
    person_embeddings_cache: Dict[str, dict],
    matched_person_ids: set[str],
    match_threshold: float,
) -> List[dict]:
    candidates = []
    for person_id, data in person_embeddings_cache.items():
        if person_id in matched_person_ids:
            continue
        distance = compare_embeddings(query_embedding, data['embedding'])
        confidence = max(0.0, min(1.0, 1.0 - (distance / match_threshold)))
        candidates.append(
            {
                '_match_person_id': person_id,
                'person_id': None if person_id == USER_SELF_PERSON_ID else person_id,
                'person_name': data.get('name'),
                'is_user': person_id == USER_SELF_PERSON_ID,
                'distance': round(distance, 6),
                'confidence': round(confidence, 6),
                'source': SPEAKER_IDENTITY_SOURCE,
            }
        )
    candidates.sort(key=lambda item: (item['distance'], item['_match_person_id']))
    return candidates[:3]


def compare_embeddings(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    if embedding1.shape[1] != embedding2.shape[1]:
        return 2.0
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    if norm1 == 0 or norm2 == 0:
        return 2.0
    similarity = float(np.dot(embedding1.flatten(), embedding2.flatten()) / (norm1 * norm2))
    return 1.0 - similarity


def _public_candidates(candidates: List[dict]) -> List[dict]:
    public = []
    for candidate in candidates:
        data = dict(candidate)
        data.pop('_match_person_id', None)
        public.append(data)
    return public


def _safe_filename(value: str) -> str:
    return ''.join(ch if ch.isalnum() else '_' for ch in value)[:80] or 'unknown'
