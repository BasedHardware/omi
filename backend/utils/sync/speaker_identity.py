"""Speaker identity for sync and the pusher's transcription shadow pass.

Keep this module independent of the sync pipeline's local VAD dependency.
"""

from __future__ import annotations

import logging
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import config.speaker_match_scores as match_scores
import utils.stt.speaker_match as match_policy

import numpy as np

from config.speaker_prior import pinned_speaker_prior_enabled
from database import users as users_db
from database.auth import get_user_name
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from utils.observability.speaker_identification import SYNC_SPEAKER_DECISIONS
from utils.speaker_permissions import named_speaker_prompts_allowed
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.speaker_match import arbitrate_owner_matches, mean_embedding, select_speaker_match, voice_candidates
from utils.stt.sync_speaker_evidence import collect_speaker_audio
from utils.stt.voiceprints import usable_person_voiceprint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeakerIdentityDependencies:
    """Allow the sync pipeline's existing test seams to reach shared logic."""

    users_db: Any = users_db
    get_user_name: Any = get_user_name
    usable_person_voiceprint: Any = usable_person_voiceprint
    speaker_embedding_configured: Any = speaker_embedding_configured
    collect_speaker_audio: Any = collect_speaker_audio
    extract_embedding_from_bytes: Any = extract_embedding_from_bytes
    mean_embedding: Any = mean_embedding
    compare_embeddings: Any = compare_embeddings
    select_speaker_match: Any = select_speaker_match
    detect_speaker_from_text: Any = detect_speaker_from_text
    process_speaker_assigned_segments: Any = process_speaker_assigned_segments
    speaker_decisions: Any = SYNC_SPEAKER_DECISIONS
    logger: Any = logger


_DEFAULT_DEPS = SpeakerIdentityDependencies()

USER_SELF_PERSON_ID = 'user'


class PersonEmbeddingsCache(dict):
    """Batch-scoped candidate snapshot, including permission for text introductions."""

    def __init__(self, named_allowed: bool):
        super().__init__()
        self.named_allowed = named_allowed


def build_person_embeddings_cache(
    uid: str, *, dependencies: SpeakerIdentityDependencies = _DEFAULT_DEPS
) -> Dict[str, dict]:
    """Build a cache of person embeddings for speaker identification.

    Loads the user's own speaker embedding and all people with stored embeddings.
    Returns dict mapping person_id -> {embedding: np.ndarray, name: str}.
    """
    users_db = dependencies.users_db
    get_user_name = dependencies.get_user_name
    usable_person_voiceprint = dependencies.usable_person_voiceprint
    # An entitlement read failure must fail closed for non-owner candidates only:
    # sync still replaces the cache, and the owner's own voiceprint must survive
    # it or free-plan owner recognition goes dark for the batch.
    try:
        named_allowed = named_speaker_prompts_allowed(uid)
    except Exception as error:
        logger.warning('sync speaker entitlement read failed type=%s', type(error).__name__)
        named_allowed = False
    cache = PersonEmbeddingsCache(named_allowed)

    # Load user's own speaker embedding
    embedding_list = users_db.get_user_speaker_embedding(uid)
    if embedding_list:
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        cache[USER_SELF_PERSON_ID] = {'embedding': user_embedding, 'name': get_user_name(uid)}

    if not cache.named_allowed:
        return cache
    # Load paid non-owner candidates only after resolving the batch entitlement.
    people = users_db.get_people(uid)
    for person in people or []:
        emb = usable_person_voiceprint(person)
        if emb and person.get('id'):
            cache[person['id']] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': person.get('name') or 'Unknown',
                'pinned': person.get('pinned') is True,
            }

    return cache


def identify_speakers_for_segments(
    transcript_segments: List['TranscriptSegment'],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    uid: str,
    language: Optional[str] = None,
    *,
    owner_reserved: bool = False,
    dependencies: SpeakerIdentityDependencies = _DEFAULT_DEPS,
) -> None:
    """Identify speakers in transcript segments using voice embeddings and text detection.

    Modifies segments in-place by assigning person_id and is_user fields.

    Steps:
    1. Voice embedding matching (requires audio_bytes, a non-empty cache, and
       HOSTED_SPEAKER_EMBEDDING_API_URL):
       For each speaker, pool distinct audio into bounded clips, average their
       embeddings, and match against person_embeddings_cache.
    2. Text-based detection ("I am X") runs independently for all unmatched speakers.
    3. Apply assignments via process_speaker_assigned_segments.
    """
    named_allowed = getattr(person_embeddings_cache, 'named_allowed', None)
    if named_allowed is None:
        named_allowed = named_speaker_prompts_allowed(uid)
    if not named_allowed:
        person_embeddings_cache = {k: v for k, v in person_embeddings_cache.items() if k == USER_SELF_PERSON_ID}
    users_db = dependencies.users_db
    speaker_embedding_configured = dependencies.speaker_embedding_configured
    collect_speaker_audio = dependencies.collect_speaker_audio
    extract_embedding_from_bytes = dependencies.extract_embedding_from_bytes
    mean_embedding = dependencies.mean_embedding
    compare_embeddings = dependencies.compare_embeddings
    select_speaker_match = dependencies.select_speaker_match
    detect_speaker_from_text = dependencies.detect_speaker_from_text
    process_speaker_assigned_segments = dependencies.process_speaker_assigned_segments
    logger = dependencies.logger
    SYNC_SPEAKER_DECISIONS = dependencies.speaker_decisions
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}
    voice_assignments: list[tuple[TranscriptSegment, str]] = []
    text_assignments: list[tuple[TranscriptSegment, str]] = []

    # Group all available evidence by diarized speaker.
    speaker_segments: Dict[int, List[TranscriptSegment]] = {}
    for seg in transcript_segments:
        sid = seg.speaker_id if seg.speaker_id is not None else 0
        speaker_segments.setdefault(sid, []).append(seg)

    # Voice embedding matching (only when audio and cached embeddings are available)
    # Track matched person_ids so each person is only assigned to one speaker
    # (diarization tells us speakers are distinct — no person can be two speakers).
    matched_person_ids: set = set()
    prior = False

    if audio_bytes and person_embeddings_cache and speaker_embedding_configured():
        # Collect every voice before reserving the owner. Longest-first remains
        # the ordering for named-person deduplication only.
        sorted_speakers = sorted(
            speaker_segments.items(),
            key=lambda kv: max(s.end - s.start for s in kv[1]),
            reverse=True,
        )

        voice_distances = {}
        voice_decisions = {}
        voice_details = {}
        for speaker_id, segments in sorted_speakers:
            best_seg = max(segments, key=lambda s: s.end - s.start)
            seg_duration = best_seg.end - best_seg.start

            try:
                evidence = collect_speaker_audio(audio_bytes, [(seg.start, seg.end) for seg in segments])
            except (ValueError, EOFError, wave.Error):
                evidence = None
            embeddings = []
            evidence_seconds = 0.0
            failed_clips = 0
            for clip_wav, seconds in evidence.clips if evidence is not None else []:
                try:
                    embeddings.append(extract_embedding_from_bytes(clip_wav, "sync_speaker.wav"))
                    evidence_seconds += seconds
                except Exception as error:
                    failed_clips += 1
                    logger.info('Speaker ID: embedding failed speaker=%s type=%s', speaker_id, type(error).__name__)
            if not embeddings:
                outcome = (
                    'audio_error'
                    if evidence is None
                    else 'embedding_error' if failed_clips else 'insufficient_evidence'
                )
                SYNC_SPEAKER_DECISIONS.labels(outcome=outcome).inc()
                logger.info(
                    'speaker_id_decision surface=sync speaker=%s clip_seconds=%.1f '
                    'best=None best_distance=inf runner_up_distance=inf accepted=False '
                    'segments=%d clips=0 evidence_seconds=0 available_seconds=%.3f '
                    'failed_clips=%d outcome=%s evidence_policy=pooled_v1',
                    speaker_id,
                    seg_duration,
                    len(segments),
                    evidence.available_seconds if evidence is not None else 0.0,
                    failed_clips,
                    outcome,
                )
                continue
            query_embedding = mean_embedding(embeddings) if len(embeddings) > 1 else embeddings[0]

            # Keep assigned candidates in the ambiguity comparison. Removing the
            # owner after a first match must not make a similar household voice
            # look unambiguous; apply one-person/one-speaker dedup only afterward.
            distances = {
                person_id: compare_embeddings(query_embedding, data['embedding'])
                for person_id, data in person_embeddings_cache.items()
            }
            voice_distances[speaker_id] = distances
            voice_decisions[speaker_id] = select_speaker_match(distances)
            voice_details[speaker_id] = (
                seg_duration,
                len(embeddings),
                evidence_seconds,
                evidence.available_seconds if evidence is not None else 0.0,
                failed_clips,
            )

        decisions = arbitrate_owner_matches(voice_distances, voice_decisions, owner_reserved=owner_reserved)
        prior = pinned_speaker_prior_enabled()
        pinned = {pid for pid, data in person_embeddings_cache.items() if data.get('pinned')}
        for speaker_id, decision in decisions.items():
            segments = speaker_segments[speaker_id]
            best_seg = max(segments, key=lambda s: s.end - s.start)
            seg_duration, clip_count, evidence_seconds, available_seconds, failed_clips = voice_details[speaker_id]
            accepted = decision.person_id is not None and decision.person_id not in matched_person_ids
            outcome = (
                'ambiguous'
                if decision.owner_contended
                else 'accepted' if accepted else 'duplicate_person' if decision.accepted else 'no_match'
            )
            try:
                if match_scores.enabled():
                    row = match_scores.summarize(
                        speaker_id,
                        voice_distances[speaker_id],
                        decision,
                        evidence_seconds,
                        'sync',
                        threshold=match_policy.SPEAKER_MATCH_THRESHOLD,
                        margin_threshold=match_policy.SPEAKER_MATCH_MARGIN,
                        scope=best_seg.speaker_id_scope or '',
                        outcome=outcome,
                        accepted=accepted,
                    )
                    for segment in segments:
                        segment.speaker_match_scores = row
            except Exception:
                match_scores.record_failure(logger)
            for segment in segments:
                if segment.speaker_match_source == 'sync_embedding':
                    # Reprocessing may revisit our own earlier automatic accept.
                    # It must not survive a newly contended decision. Reviewed
                    # labels have their provenance cleared by the manual writer.
                    segment.is_user = False
                    segment.person_id = None
            if not accepted:
                # Pinned prior (flagged): record what the voice resembles; a pinned near-miss is
                # flagged for the suggestion card. Never an automatic label.
                candidates = (
                    voice_candidates(voice_distances[speaker_id], decision, pinned, exclude=(USER_SELF_PERSON_ID,))
                    if prior
                    else None
                )
                for segment in segments:
                    if not segment.is_user and not segment.person_id:
                        segment.speaker_identity_status = (
                            SpeakerIdentityStatus.ambiguous
                            if decision.owner_contended
                            else SpeakerIdentityStatus.no_match
                        )
                        segment.speaker_match_source = 'sync_embedding'
                        if candidates is not None:
                            segment.voice_candidates = candidates
            SYNC_SPEAKER_DECISIONS.labels(outcome=outcome).inc()
            logger.info(
                'speaker_id_decision surface=sync speaker=%s clip_seconds=%.1f '
                'best_distance=%.3f runner_up_distance=%.3f accepted=%s '
                'segments=%d clips=%d evidence_seconds=%.3f available_seconds=%.3f '
                'failed_clips=%d outcome=%s evidence_policy=pooled_v1',
                speaker_id,
                seg_duration,
                decision.best_distance,
                decision.runner_up_distance,
                accepted,
                len(segments),
                clip_count,
                evidence_seconds,
                available_seconds,
                failed_clips,
                outcome,
            )
            if accepted and decision.person_id is not None:
                person_id = decision.person_id
                speaker_to_person_map[speaker_id] = (person_id, person_embeddings_cache[person_id]['name'])
                if best_seg.id is not None:
                    segment_person_assignment_map[best_seg.id] = person_id
                matched_person_ids.add(person_id)
                voice_assignments.extend(
                    (segment, person_id) for segment in segments if not segment.is_user and not segment.person_id
                )

    # Text-based detection runs independently for all unmatched speakers.
    # For speaker_id > 0 (diarized): update both speaker_to_person_map and per-segment map.
    # For speaker_id <= 0 (undiarized): only assign per-segment (avoid mapping all speaker_id=0
    # segments to one person when diarization is inactive).
    for speaker_id, segments in speaker_segments.items():
        if not named_allowed:
            break
        if speaker_id in speaker_to_person_map:
            continue
        for seg in segments:
            detected_name = detect_speaker_from_text(seg.text, language=language)
            if detected_name:
                person = users_db.get_person_by_name(uid, detected_name)
                if person and person.get('id'):
                    text_assignments.extend(
                        (target, person['id'])
                        for target in (segments if speaker_id > 0 else [seg])
                        if not target.is_user and not target.person_id
                    )
                    # Per-segment assignment always applies
                    if seg.id is not None:
                        segment_person_assignment_map[seg.id] = person['id']
                    # Update speaker map only when diarization is active
                    if speaker_id > 0:
                        speaker_to_person_map[speaker_id] = (person['id'], person.get('name') or detected_name)
                    logger.info('speaker_id_decision surface=sync speaker=%s source=text accepted=True', speaker_id)
                    if speaker_id > 0:
                        break  # One match per diarized speaker is enough

    # Apply all assignments to segments
    if speaker_to_person_map or segment_person_assignment_map:
        process_speaker_assigned_segments(
            transcript_segments,
            segment_person_assignment_map,
            speaker_to_person_map,
        )

    # The assignment helper preserves pre-existing labels. Only mark labels this
    # voice decision actually supplied, never an existing manual/provider label.
    for segment, person_id in voice_assignments:
        if (person_id == USER_SELF_PERSON_ID and segment.is_user) or segment.person_id == person_id:
            segment.speaker_match_source = 'sync_embedding'
            segment.speaker_identity_status = (
                SpeakerIdentityStatus.user if person_id == USER_SELF_PERSON_ID else SpeakerIdentityStatus.not_user
            )
    for segment, person_id in text_assignments:
        if segment.person_id == person_id:
            segment.speaker_match_source = 'sync_text'
    if prior:
        # Filter after voice, manual and text assignments, including voices visited
        # later in the matching loop. This never changes an identity decision.
        assigned = {s.person_id for s in transcript_segments if s.person_id} | {USER_SELF_PERSON_ID}
        for segment in transcript_segments:
            if segment.is_user or segment.person_id:
                segment.voice_candidates = None
            elif segment.voice_candidates is not None:
                segment.voice_candidates = [c for c in segment.voice_candidates if c['person_id'] not in assigned]
