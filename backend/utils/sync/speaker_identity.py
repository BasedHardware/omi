"""Speaker identity for sync and the pusher's transcription shadow pass.

Keep this module independent of the sync pipeline's local VAD dependency.
"""

from __future__ import annotations

import logging
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from database import users as users_db
from database.auth import get_user_name
from models.transcript_segment import TranscriptSegment
from utils.observability.speaker_identification import SYNC_SPEAKER_DECISIONS
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.speaker_match import mean_embedding, select_speaker_match
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
    cache: Dict[str, dict] = {}

    # Load user's own speaker embedding
    embedding_list = users_db.get_user_speaker_embedding(uid)
    if embedding_list:
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        cache[USER_SELF_PERSON_ID] = {'embedding': user_embedding, 'name': get_user_name(uid)}

    # Load all people with speaker embeddings
    people = users_db.get_people(uid)
    for person in people or []:
        emb = usable_person_voiceprint(person)
        if emb and person.get('id'):
            cache[person['id']] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': person.get('name') or 'Unknown',
            }

    return cache


def identify_speakers_for_segments(
    transcript_segments: List['TranscriptSegment'],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    uid: str,
    language: Optional[str] = None,
    *,
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

    # Group all available evidence by diarized speaker.
    speaker_segments: Dict[int, List[TranscriptSegment]] = {}
    for seg in transcript_segments:
        sid = seg.speaker_id if seg.speaker_id is not None else 0
        speaker_segments.setdefault(sid, []).append(seg)

    # Voice embedding matching (only when audio and cached embeddings are available)
    # Track matched person_ids so each person is only assigned to one speaker
    # (diarization tells us speakers are distinct — no person can be two speakers).
    matched_person_ids: set = set()

    if audio_bytes and person_embeddings_cache and speaker_embedding_configured():
        # Preserve existing longest-segment priority for one-person/one-speaker dedup.
        # Pooling changes evidence, not the order in which identities are reserved.
        # Note: matched_person_ids assumes diarization is correct (one person = one speaker).
        # If diarization fragments one person across speaker IDs, only the best match wins.
        sorted_speakers = sorted(
            speaker_segments.items(),
            key=lambda kv: max(s.end - s.start for s in kv[1]),
            reverse=True,
        )

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
            decision = select_speaker_match(distances)
            accepted = decision.person_id is not None and decision.person_id not in matched_person_ids
            outcome = 'accepted' if accepted else 'duplicate_person' if decision.accepted else 'no_match'
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
                len(embeddings),
                evidence_seconds,
                evidence.available_seconds if evidence is not None else 0.0,
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
        if speaker_id in speaker_to_person_map:
            continue
        for seg in segments:
            detected_name = detect_speaker_from_text(seg.text, language=language)
            if detected_name:
                person = users_db.get_person_by_name(uid, detected_name)
                if person and person.get('id'):
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
