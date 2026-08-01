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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from utils.executors import db_executor, llm_executor, run_blocking
from utils.log_sanitizer import sanitize, sanitize_pii
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


async def _known_people(uid: str) -> Tuple[Dict[str, Optional[str]], List[str], Set[str], Dict[str, str]]:
    """Existing Person records: a name lookup, display names, collisions, a roster.

    The display names go to the model so it reuses the user's own spelling
    instead of coining a second Person for the same human.

    Two Person records can share a casefolded name -- "jo" and "Jo" are
    different contacts to the user and one key to this lookup. Binding a claim
    to whichever of them Firestore streamed last would enrol a voiceprint
    against an arbitrary contact, so a colliding name maps to ``None``: known
    enough never to coin a third Person for it, ambiguous enough never to
    resolve. The colliding keys come back separately so the caller can keep
    those claims as suggestions for the user to settle.

    The fourth return is the reverse direction, ``person_id`` to display name.
    A finalized ``TranscriptSegment`` carries only ``person_id``, so this is the
    only way either model can be shown that a speaker is already someone.
    """
    from database import users as users_db

    try:
        people = await run_blocking(db_executor, users_db.get_people, uid) or []
    except Exception as e:
        logger.error('Speaker resolution could not load people: %s', sanitize(e))
        return {}, [], set(), {}
    known: Dict[str, Optional[str]] = {}
    display_names: List[str] = []
    ambiguous: Set[str] = set()
    names_by_id: Dict[str, str] = {}
    for person in people:
        name = person.get('name')
        person_id = person.get('id')
        if not (isinstance(name, str) and name.strip() and isinstance(person_id, str)):
            continue
        key = name.strip().casefold()
        display_names.append(name.strip())
        names_by_id[person_id] = name.strip()
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
    return known, sorted(set(display_names)), ambiguous, names_by_id


async def _resolve_person_id(uid: str, name: str, known: Dict[str, Optional[str]]) -> Tuple[Optional[str], bool]:
    """Find or create the Person for a resolved name, and say which it was.

    A name already in ``known`` is never coined a second time, even when it
    maps to ``None`` for a collision: an ambiguous contact resolves to nothing
    rather than to a new duplicate of itself.

    Creation goes through ``get_or_create_person_by_name`` rather than reading
    the roster and coining a uuid, because two conversations for one user can
    finish at once: both would miss the same unseen name, both would coin, and
    the user would end up with two records for one human and a voiceprint on
    each. That helper makes the name select the document, so the second caller
    contends for it instead of duplicating it.

    Returns:
        ``(person_id, created)``, where ``created`` is that helper's own answer
        rather than a guess from whether the name was in ``known``. Of the two
        passes contending for one new name, only one really creates the record;
        the other reuses it, and a pass that mistook reuse for creation would
        delete the other's Person out from under an assignment it had already
        written and enrolled when its own write failed.
    """
    from database import users as users_db

    key = name.casefold()
    if key in known:
        return known[key], False
    try:
        person, created = await run_blocking(db_executor, users_db.get_or_create_person_by_name, uid, name)
    except Exception as e:
        logger.error('Speaker resolution could not create person %s: %s %s', sanitize_pii(name), sanitize(e), uid)
        return None, False
    person_id = person.get('id')
    if not isinstance(person_id, str) or not person_id:
        return None, False
    known[key] = person_id
    return person_id, bool(created)


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
            logger.error('Speaker resolution could not remove orphan person=%s: %s %s', person_id, sanitize(e), uid)
        for key, value in list(known.items()):
            if value == person_id:
                known.pop(key, None)


def build_plan(
    segments: Sequence[Any],
    user_name: Optional[str],
    known_names: Sequence[str],
    person_names: Optional[Dict[str, str]] = None,
) -> ResolutionPlan:
    """Run the LLM route and gate its output. Returns an empty plan on failure."""
    from utils.llm.speaker_resolution import resolve_speakers

    claims = resolve_speakers(segments, known_names=known_names, user_name=user_name, person_names=person_names)
    if not claims:
        return ResolutionPlan()
    return plan_speaker_resolution(claims, segments, user_name=user_name)


async def verify_suggestions(
    segments: Sequence[Any],
    suggestions: Sequence[ResolvedSpeaker],
    user_name: Optional[str],
    person_names: Optional[Dict[str, str]] = None,
) -> List[ResolvedSpeaker]:
    """Return the suggestions a second model could not refute.

    Runs one refutation call per suggestion, each isolated: a verifier that
    raises refutes only the suggestion it was asked about, and refuting is the
    safe direction, so a broken verifier degrades this pass to suggestion-only
    rather than to unchecked enrolment.

    Orchestration stays async and borrows an ``llm_executor`` thread per call
    rather than once for the loop. The pool has six workers and the budget below
    is six requests, so a single offload around the whole loop lets one
    conversation hold a sixth of the pool for six serial round trips while every
    other LLM feature queues behind it.

    Bounded per conversation, and spent on the most confident suggestions
    first. Enrolment is already capped; without a matching cap here a
    transcript that diarizes into many speakers would bill an unbounded number
    of calls to reach it. Suggestions past the cap are left unverified, which
    means they stay suggestions.
    """
    from utils.llm.speaker_verification import record_verification_exhausted, verify_speaker_identification

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
            verdict = await run_blocking(
                llm_executor,
                verify_speaker_identification,
                segments,
                speaker_id=suggestion.speaker_id,
                person_name=suggestion.person_name,
                evidence_quote=suggestion.evidence_quote,
                user_name=user_name,
                person_names=person_names,
            )
        except Exception as e:
            logger.error('Speaker verification raised for speaker=%s: %s', suggestion.speaker_id, sanitize(e))
            record_verification_exhausted('other')
            continue
        if verdict.refuted:
            logger.info(
                'Speaker verification refuted speaker=%s name=%s',
                suggestion.speaker_id,
                sanitize_pii(suggestion.person_name),
            )
            continue
        verified.append(suggestion)
    return verified


def _decided_speaker_ids(stored_segments: Sequence[Any]) -> Set[int]:
    """Speaker indices durable state has already settled, wholly or in part.

    A speaker counts as decided the moment one of its segments carries a
    ``person_id`` or belongs to the account owner. Deciding this per segment
    instead would let a speaker the user named halfway through keep its
    remaining segments for an inference, and the stored conversation would then
    bind one voice to two people at once.
    """
    decided: Set[int] = set()
    for segment in stored_segments:
        if not isinstance(segment, dict):
            continue
        speaker_id = segment.get('speaker_id')
        if not isinstance(speaker_id, int) or isinstance(speaker_id, bool):
            continue
        if segment.get('is_user') or segment.get('person_id'):
            decided.add(speaker_id)
    return decided


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
    so by now the user may have named a speaker by hand. Eligibility is settled
    against durable state instead, and settled *inside* the write transaction:
    ``assign_conversation_segment_people`` re-reads the conversation, refuses
    any speaker one of whose segments is already resolved, and commits the rest,
    all under one Firestore transaction. Checking beforehand and writing a
    precomputed array afterwards leaves a window in which the user's own
    assignment lands between the two and is overwritten by the stale array.

    The read before that is only an optimisation: it skips speakers that were
    plainly decided already, so the pass does not coin a Person it is about to
    delete again. The transaction remains the authority on what may be written.

    Nothing in memory is mutated until that write lands, so a conversation
    object never carries labels the database does not hold, and a Person this
    pass really created for a write that failed is deleted again rather than
    left in the user's contacts with nothing pointing at it.
    """
    from database import conversations as conversations_db
    from utils.speaker_identification import (
        SPEAKER_ATTRIBUTION_LLM_INFERRED,
        SpeakerEnrolmentOutcome,
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
        logger.error('Speaker resolution could not re-read conversation: %s %s %s', sanitize(e), uid, conversation_id)
        outcome.suggested.extend(assignments)
        return outcome

    stored_segments = list((stored or {}).get('transcript_segments') or [])
    if not stored_segments:
        logger.info('Speaker resolution found no stored segments to update %s %s', uid, conversation_id)
        outcome.suggested.extend(assignments)
        return outcome

    decided = _decided_speaker_ids(stored_segments)
    created_person_ids: List[str] = []
    pending: List[Tuple[str, ResolvedSpeaker]] = []

    for resolved in assignments:
        if resolved.speaker_id in decided:
            logger.info(
                'Speaker resolution left speaker=%s alone, already decided %s %s',
                resolved.speaker_id,
                uid,
                conversation_id,
            )
            outcome.suggested.append(resolved)
            continue
        person_id, created = await _resolve_person_id(uid, resolved.person_name, known)
        if not person_id:
            outcome.suggested.append(resolved)
            continue
        if created:
            created_person_ids.append(person_id)
        pending.append((person_id, resolved))

    if not pending:
        return outcome

    try:
        applied = await run_blocking(
            db_executor,
            conversations_db.assign_conversation_segment_people,
            uid,
            conversation_id,
            [(resolved.speaker_id, person_id) for person_id, resolved in pending],
        )
    except Exception as e:
        logger.error('Speaker resolution could not persist segments: %s %s %s', sanitize(e), uid, conversation_id)
        applied = {}

    enrolments: List[Tuple[str, Tuple[str, ...]]] = []
    for person_id, resolved in pending:
        assigned_ids = tuple(applied.get(resolved.speaker_id) or ())
        if not assigned_ids:
            outcome.suggested.append(resolved)
            continue
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
        for segment_id in assigned_ids:
            segment = segment_map.get(segment_id)
            if segment is None:
                continue
            segment.is_user = False
            segment.person_id = person_id

    written_person_ids = {person_id for person_id, _ in outcome.assigned}
    orphaned = [person_id for person_id in created_person_ids if person_id not in written_person_ids]
    if orphaned:
        logger.error(
            'Speaker resolution coined %d person(s) for a binding that did not land %s %s',
            len(orphaned),
            uid,
            conversation_id,
        )
        await _discard_created_people(uid, orphaned, known)

    for person_id, assigned_ids in enrolments:
        try:
            enrolment = await extract_speaker_samples(
                uid=uid,
                person_id=person_id,
                conversation_id=conversation_id,
                segment_ids=list(assigned_ids),
                attribution=SPEAKER_ATTRIBUTION_LLM_INFERRED,
            )
        except Exception as e:
            logger.error('Speaker resolution enrolment failed person=%s: %s %s', person_id, sanitize(e), uid)
            try:
                revoked = await revoke_inferred_speaker_enrolment(uid, person_id)
            except Exception as revoke_error:
                logger.error(
                    'Speaker resolution could not revoke half-written enrolment person=%s: %s %s',
                    person_id,
                    sanitize(revoke_error),
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
            continue
        if enrolment is SpeakerEnrolmentOutcome.ENROLLED:
            outcome.enrolled.append(person_id)
            continue
        logger.info('Speaker resolution enrolled no sample for person=%s %s %s', person_id, uid, conversation_id)

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

    known, known_names, ambiguous, names_by_id = await _known_people(uid)

    with track_usage(uid, Features.SPEAKER_RESOLUTION):
        plan = await run_blocking(llm_executor, build_plan, segments, user_name, known_names, names_by_id)
    if plan.is_empty:
        return SpeakerResolutionOutcome()

    try:
        with track_usage(uid, Features.SPEAKER_VERIFICATION):
            verified = await verify_suggestions(segments, plan.suggestions, user_name, names_by_id)
    except Exception as e:
        logger.error('Speaker verification pass failed, keeping suggestions only: %s %s', sanitize(e), uid)
        verified = []

    verified = [resolved for resolved in verified if resolved.person_name.casefold() not in ambiguous]

    verified_speakers = {resolved.speaker_id for resolved in verified}
    remaining = [resolved for resolved in plan.suggestions if resolved.speaker_id not in verified_speakers]

    return await apply_plan(uid, conversation.id, segments, verified, remaining, known)
