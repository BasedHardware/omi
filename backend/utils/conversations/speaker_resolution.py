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

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from utils.executors import db_executor, llm_executor, run_blocking
from utils.log_sanitizer import sanitize_pii
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


async def _known_people(uid: str) -> Tuple[Dict[str, Optional[str]], List[str], Set[str]]:
    """Existing Person records: a casefolded-name lookup, display names, collisions.

    The display names go to the model so it reuses the user's own spelling
    instead of coining a second Person for the same human.

    Two Person records can share a casefolded name -- "jo" and "Jo" are
    different contacts to the user and one key to this lookup. Binding a claim
    to whichever of them Firestore streamed last would enrol a voiceprint
    against an arbitrary contact, so a colliding name maps to ``None``: known
    enough never to coin a third Person for it, ambiguous enough never to
    resolve. The colliding keys come back separately so the caller can keep
    those claims as suggestions for the user to settle.
    """
    from database import users as users_db

    try:
        people = await run_blocking(db_executor, users_db.get_people, uid) or []
    except Exception as e:
        logger.error('Speaker resolution could not load people: %s', e)
        return {}, [], set()
    known: Dict[str, Optional[str]] = {}
    display_names: List[str] = []
    ambiguous: Set[str] = set()
    for person in people:
        name = person.get('name')
        person_id = person.get('id')
        if not (isinstance(name, str) and name.strip() and isinstance(person_id, str)):
            continue
        key = name.strip().casefold()
        display_names.append(name.strip())
        if key in known and known[key] != person_id:
            known[key] = None
            ambiguous.add(key)
            continue
        if key not in ambiguous:
            known[key] = person_id
    if ambiguous:
        logger.info(
            'Speaker resolution found %d colliding person name(s), leaving them unresolved %s', len(ambiguous), uid
        )
    return known, sorted(set(display_names)), ambiguous


async def _resolve_person_id(uid: str, name: str, known: Dict[str, Optional[str]]) -> Optional[str]:
    """Find or create the Person for a resolved name.

    A name already in ``known`` is never coined a second time, even when it
    maps to ``None`` for a collision: an ambiguous contact resolves to nothing
    rather than to a new duplicate of itself.
    """
    from database import users as users_db

    key = name.casefold()
    if key in known:
        return known[key]
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
        logger.error('Speaker resolution could not create person %s: %s %s', sanitize_pii(name), e, uid)
        return None
    known[key] = person_id
    return person_id


async def _discard_created_people(uid: str, person_ids: Sequence[str], known: Dict[str, Optional[str]]) -> None:
    """Remove Person records this pass coined for a write that never landed.

    A Person created for an assignment is only ever referenced by that
    assignment. If the segment write fails the contact is unreachable from any
    transcript, so it would sit in the user's people list as a name they never
    added and cannot explain.
    """
    from database import users as users_db

    for person_id in person_ids:
        try:
            await run_blocking(db_executor, users_db.delete_person, uid, person_id)
        except Exception as e:
            logger.error('Speaker resolution could not remove orphan person=%s: %s %s', person_id, e, uid)
        for key, value in list(known.items()):
            if value == person_id:
                known.pop(key, None)


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
                sanitize_pii(suggestion.person_name),
                verdict.reason,
            )
            continue
        verified.append(suggestion)
    return verified


def _durable_segment_is_unresolved(segment: Any) -> bool:
    """Whether stored state still leaves this segment for the pass to decide."""
    if not isinstance(segment, dict):
        return False
    return not segment.get('is_user') and not segment.get('person_id')


async def apply_plan(
    uid: str,
    conversation_id: str,
    segments: Sequence[Any],
    assignments: Sequence[ResolvedSpeaker],
    suggestions: Sequence[ResolvedSpeaker],
    known: Dict[str, Optional[str]],
) -> SpeakerResolutionOutcome:
    """Write the verified assignments and enrol voiceprints for them.

    Enrolment is capped per conversation. A transcript that somehow yields a
    long list of confident names is more likely a diarization failure than a
    room of newly identifiable people, and each enrolment writes a voiceprint
    that is expensive to unpick.

    The ``segments`` handed in are a snapshot taken before two LLM round trips,
    so by now the user may have named a speaker by hand. Stored state is
    re-read and only the segments still unresolved *there* are touched, and the
    write goes out as the stored list with those edits applied rather than as
    the snapshot: a user's own decision outranks an inference, and writing the
    whole snapshot back would silently replace it.

    Nothing in memory is mutated until that write lands, so a conversation
    object never carries labels the database does not hold, and a Person coined
    for a write that failed is deleted again rather than left in the user's
    contacts with nothing pointing at it.
    """
    from database import conversations as conversations_db
    from utils.speaker_identification import (
        SPEAKER_ATTRIBUTION_LLM_INFERRED,
        extract_speaker_samples,
        revoke_inferred_speaker_enrolment,
    )

    outcome = SpeakerResolutionOutcome(suggested=list(suggestions))
    if not assignments:
        return outcome

    segment_map = {segment.id: segment for segment in segments if getattr(segment, 'id', None)}

    try:
        stored = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
    except Exception as e:
        logger.error('Speaker resolution could not re-read conversation: %s %s %s', e, uid, conversation_id)
        outcome.suggested.extend(assignments)
        return outcome

    stored_segments = list((stored or {}).get('transcript_segments') or [])
    stored_map = {
        segment['id']: segment for segment in stored_segments if isinstance(segment, dict) and segment.get('id')
    }
    if not stored_map:
        logger.info('Speaker resolution found no stored segments to update %s %s', uid, conversation_id)
        outcome.suggested.extend(assignments)
        return outcome

    created_person_ids: List[str] = []
    pending: List[Tuple[str, ResolvedSpeaker, Tuple[str, ...]]] = []
    enrolments: List[Tuple[str, Tuple[str, ...]]] = []

    for resolved in assignments:
        assigned_ids = tuple(
            segment_id
            for segment_id in resolved.segment_ids
            if segment_id in segment_map and _durable_segment_is_unresolved(stored_map.get(segment_id))
        )
        if not assigned_ids:
            logger.info(
                'Speaker resolution left speaker=%s alone, already decided %s %s',
                resolved.speaker_id,
                uid,
                conversation_id,
            )
            outcome.suggested.append(resolved)
            continue
        was_known = resolved.person_name.casefold() in known
        person_id = await _resolve_person_id(uid, resolved.person_name, known)
        if not person_id:
            outcome.suggested.append(resolved)
            continue
        if not was_known:
            created_person_ids.append(person_id)
        pending.append((person_id, resolved, assigned_ids))

    for person_id, resolved, assigned_ids in pending:
        for segment_id in assigned_ids:
            stored_segment = stored_map[segment_id]
            stored_segment['is_user'] = False
            stored_segment['person_id'] = person_id
        outcome.assigned.append((person_id, resolved.person_name))
        if len(enrolments) < MAX_ENROLLMENTS_PER_CONVERSATION:
            enrolments.append((person_id, assigned_ids))
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
        persisted = await run_blocking(
            db_executor,
            conversations_db.update_conversation_segments,
            uid,
            conversation_id,
            stored_segments,
        )
    except Exception as e:
        logger.error('Speaker resolution could not persist segments: %s %s %s', e, uid, conversation_id)
        persisted = False

    if not persisted:
        logger.error('Speaker resolution segment write did not land, nothing enrolled %s %s', uid, conversation_id)
        await _discard_created_people(uid, created_person_ids, known)
        unwritten = SpeakerResolutionOutcome(suggested=list(outcome.suggested))
        unwritten.suggested.extend(resolved for _, resolved, _ in pending)
        return unwritten

    for person_id, resolved, assigned_ids in pending:
        for segment_id in assigned_ids:
            segment = segment_map[segment_id]
            segment.is_user = False
            segment.person_id = person_id

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
            try:
                revoked = await revoke_inferred_speaker_enrolment(uid, person_id)
            except Exception as revoke_error:
                logger.error(
                    'Speaker resolution could not revoke half-written enrolment person=%s: %s %s',
                    person_id,
                    revoke_error,
                    uid,
                )
                continue
            if revoked:
                logger.info(
                    'Speaker resolution revoked %d inferred sample(s) from a failed enrolment person=%s %s',
                    len(revoked),
                    person_id,
                    uid,
                )

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

    from utils.llm.usage_tracker import Features, track_usage

    known, known_names, ambiguous = await _known_people(uid)

    with track_usage(uid, Features.SPEAKER_RESOLUTION):
        plan = await run_blocking(llm_executor, build_plan, segments, user_name, known_names)
    if plan.is_empty:
        return SpeakerResolutionOutcome()

    try:
        with track_usage(uid, Features.SPEAKER_VERIFICATION):
            verified = await run_blocking(llm_executor, verify_suggestions, segments, plan.suggestions, user_name)
    except Exception as e:
        logger.error('Speaker verification pass failed, keeping suggestions only: %s %s', e, uid)
        verified = []

    verified = [resolved for resolved in verified if resolved.person_name.casefold() not in ambiguous]

    verified_speakers = {resolved.speaker_id for resolved in verified}
    remaining = [resolved for resolved in plan.suggestions if resolved.speaker_id not in verified_speakers]

    return await apply_plan(uid, conversation.id, segments, verified, remaining, known)
