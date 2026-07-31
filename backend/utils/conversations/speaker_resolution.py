"""Post-processing pass that names the speakers a conversation left numbered.

Sits between the LLM route (``utils.llm.speaker_resolution``) and the gate
(``utils.speaker_resolution``), and owns the side effects neither of those may
have: resolving or creating the Person, writing the segment assignments, and
enrolling a voiceprint from the assigned audio.

Enrolment is the irreversible half, so nothing reaches it on one model's word.
The gate produces suggestions only; each is then put to a second, independent
model (``utils.llm.speaker_verification``) that is asked to refute it, and only
the suggestions that survive that attempt are written and enrolled. Everything
else stays a suggestion the user can accept with a tap. Assignments made this
way are tagged ``llm_inferred`` so an embedding that came from an inference
stays distinguishable from one the user confirmed by hand.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.executors import db_executor, llm_executor, run_blocking
from utils.speaker_resolution import ResolutionPlan, ResolvedSpeaker, plan_speaker_resolution

logger = logging.getLogger(__name__)

MAX_ENROLLMENTS_PER_CONVERSATION = 4

MAX_VERIFICATIONS_PER_CONVERSATION = 6

SPEAKER_RESOLUTION_ENABLED = os.getenv('SPEAKER_RESOLUTION_ENABLED', 'false').lower() == 'true'


@dataclass
class SpeakerResolutionOutcome:
    """What the pass did, for logging and for the client to act on."""

    assigned: List[Tuple[str, str]] = field(default_factory=list)
    suggested: List[ResolvedSpeaker] = field(default_factory=list)
    enrolled: List[str] = field(default_factory=list)

    @property
    def changed_segments(self) -> bool:
        return bool(self.assigned)


def _unresolved_speaker_count(segments: Sequence[Any]) -> int:
    speakers = set()
    for segment in segments:
        if getattr(segment, 'is_user', False) or getattr(segment, 'person_id', None):
            continue
        speaker_id = getattr(segment, 'speaker_id', None)
        if isinstance(speaker_id, int) and not isinstance(speaker_id, bool):
            speakers.add(speaker_id)
    return len(speakers)


async def _known_people(uid: str) -> Tuple[Dict[str, str], List[str]]:
    """Existing Person records: a casefolded-name lookup, and the display names.

    The display names go to the model so it reuses the user's own spelling
    instead of coining a second Person for the same human.
    """
    from database import users as users_db

    try:
        people = await run_blocking(db_executor, users_db.get_people, uid) or []
    except Exception as e:
        logger.error('Speaker resolution could not load people: %s', e)
        return {}, []
    known: Dict[str, str] = {}
    display_names: List[str] = []
    for person in people:
        name = person.get('name')
        person_id = person.get('id')
        if isinstance(name, str) and name.strip() and isinstance(person_id, str):
            known[name.strip().casefold()] = person_id
            display_names.append(name.strip())
    return known, sorted(set(display_names))


async def _resolve_person_id(uid: str, name: str, known: Dict[str, str]) -> Optional[str]:
    """Find or create the Person for a resolved name."""
    from database import users as users_db

    existing = known.get(name.casefold())
    if existing:
        return existing
    person_id = str(uuid.uuid4())
    try:
        await run_blocking(
            db_executor,
            users_db.create_person,
            uid,
            {
                'id': person_id,
                'name': name,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc),
            },
        )
    except Exception as e:
        logger.error('Speaker resolution could not create person %r: %s', name, e)
        return None
    known[name.casefold()] = person_id
    return person_id


def build_plan(
    segments: Sequence[Any],
    user_name: Optional[str],
    known_names: Sequence[str],
) -> ResolutionPlan:
    """Run the LLM route and gate its output. Returns an empty plan on failure."""
    from utils.llm.speaker_resolution import resolve_speakers

    claims = resolve_speakers(segments, known_names=known_names, user_name=user_name)
    if not claims:
        return ResolutionPlan()
    return plan_speaker_resolution(claims, segments, user_name=user_name)


def verify_suggestions(
    segments: Sequence[Any],
    suggestions: Sequence[ResolvedSpeaker],
    user_name: Optional[str],
) -> List[ResolvedSpeaker]:
    """Return the suggestions a second model could not refute.

    Runs one refutation call per suggestion, each isolated: a verifier that
    raises refutes only the suggestion it was asked about, and refuting is the
    safe direction, so a broken verifier degrades this pass to suggestion-only
    rather than to unchecked enrolment.

    Bounded per conversation, and spent on the most confident suggestions
    first. Enrolment is already capped; without a matching cap here a
    transcript that diarizes into many speakers would bill an unbounded number
    of calls to reach it. Suggestions past the cap are left unverified, which
    means they stay suggestions.
    """
    from utils.llm.speaker_verification import verify_speaker_identification

    ordered = sorted(suggestions, key=lambda suggestion: suggestion.confidence, reverse=True)
    budgeted = ordered[:MAX_VERIFICATIONS_PER_CONVERSATION]
    if len(ordered) > len(budgeted):
        logger.info(
            'Speaker verification budget reached, leaving %d suggestion(s) unverified',
            len(ordered) - len(budgeted),
        )

    verified: List[ResolvedSpeaker] = []
    for suggestion in budgeted:
        try:
            verdict = verify_speaker_identification(
                segments,
                speaker_id=suggestion.speaker_id,
                person_name=suggestion.person_name,
                evidence_quote=suggestion.evidence_quote,
                user_name=user_name,
            )
        except Exception as e:
            logger.error('Speaker verification raised for speaker=%s: %s', suggestion.speaker_id, e)
            continue
        if verdict.refuted:
            logger.info(
                'Speaker verification refuted speaker=%s name=%s reason=%s',
                suggestion.speaker_id,
                suggestion.person_name,
                verdict.reason,
            )
            continue
        verified.append(suggestion)
    return verified


async def apply_plan(
    uid: str,
    conversation_id: str,
    segments: Sequence[Any],
    assignments: Sequence[ResolvedSpeaker],
    suggestions: Sequence[ResolvedSpeaker],
    known: Dict[str, str],
) -> SpeakerResolutionOutcome:
    """Write the verified assignments and enrol voiceprints for them.

    Enrolment is capped per conversation. A transcript that somehow yields a
    long list of confident names is more likely a diarization failure than a
    room of newly identifiable people, and each enrolment writes a voiceprint
    that is expensive to unpick.
    """
    from database import conversations as conversations_db
    from utils.speaker_identification import SPEAKER_ATTRIBUTION_LLM_INFERRED, extract_speaker_samples

    outcome = SpeakerResolutionOutcome(suggested=list(suggestions))
    if not assignments:
        return outcome

    segment_map = {segment.id: segment for segment in segments if getattr(segment, 'id', None)}
    enrolments: List[Tuple[str, Tuple[str, ...]]] = []

    for resolved in assignments:
        person_id = await _resolve_person_id(uid, resolved.person_name, known)
        if not person_id:
            continue
        assigned_ids = [segment_id for segment_id in resolved.segment_ids if segment_id in segment_map]
        if not assigned_ids:
            continue
        for segment_id in assigned_ids:
            segment = segment_map[segment_id]
            segment.is_user = False
            segment.person_id = person_id
        outcome.assigned.append((person_id, resolved.person_name))
        if len(enrolments) < MAX_ENROLLMENTS_PER_CONVERSATION:
            enrolments.append((person_id, tuple(assigned_ids)))
        logger.info(
            'Speaker resolution assigned speaker=%s person=%s confidence=%.2f %s %s',
            resolved.speaker_id,
            person_id,
            resolved.confidence,
            uid,
            conversation_id,
        )

    if not outcome.assigned:
        return outcome

    try:
        await run_blocking(
            db_executor,
            conversations_db.update_conversation_segments,
            uid,
            conversation_id,
            [segment.dict() for segment in segments],
        )
    except Exception as e:
        logger.error('Speaker resolution could not persist segments: %s %s %s', e, uid, conversation_id)
        return SpeakerResolutionOutcome(suggested=outcome.suggested)

    for person_id, assigned_ids in enrolments:
        try:
            await extract_speaker_samples(
                uid=uid,
                person_id=person_id,
                conversation_id=conversation_id,
                segment_ids=list(assigned_ids),
                attribution=SPEAKER_ATTRIBUTION_LLM_INFERRED,
            )
            outcome.enrolled.append(person_id)
        except Exception as e:
            logger.error('Speaker resolution enrolment failed person=%s: %s %s', person_id, e, uid)

    return outcome


async def resolve_conversation_speakers(uid: str, conversation: Any) -> SpeakerResolutionOutcome:
    """Name the numbered speakers in a finalized conversation.

    Skipped when there is nothing to gain: no unresolved speaker means the
    live path and the user between them already decided everyone.
    """
    segments = list(getattr(conversation, 'transcript_segments', None) or [])
    if not segments or _unresolved_speaker_count(segments) == 0:
        return SpeakerResolutionOutcome()

    try:
        from database.auth import get_user_name

        raw_user_name = await run_blocking(db_executor, get_user_name, uid, False)
        user_name = raw_user_name.strip() if isinstance(raw_user_name, str) else None
    except Exception:
        user_name = None

    known, known_names = await _known_people(uid)

    plan = await run_blocking(llm_executor, build_plan, segments, user_name, known_names)
    if plan.is_empty:
        return SpeakerResolutionOutcome()

    try:
        verified = await run_blocking(llm_executor, verify_suggestions, segments, plan.suggestions, user_name)
    except Exception as e:
        logger.error('Speaker verification pass failed, keeping suggestions only: %s %s', e, uid)
        verified = []

    verified_speakers = {resolved.speaker_id for resolved in verified}
    remaining = [resolved for resolved in plan.suggestions if resolved.speaker_id not in verified_speakers]

    return await apply_plan(uid, conversation.id, segments, verified, remaining, known)


def resolve_conversation_speakers_sync(uid: str, conversation: Any) -> SpeakerResolutionOutcome:
    """Entry point for the post-processing executor, which runs sync callables."""
    if not SPEAKER_RESOLUTION_ENABLED:
        return SpeakerResolutionOutcome()
    try:
        return asyncio.run(resolve_conversation_speakers(uid, conversation))
    except Exception as e:
        logger.error('Speaker resolution failed: %s %s', e, uid)
        return SpeakerResolutionOutcome()
