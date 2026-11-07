"""Transactional side effects of one manual speaker assignment.

Extracted from ``database.conversations.assign_conversation_speaker`` so the
label, person evidence, owner-profile retraction and the durable
speaker-learning ledger commit in one transaction without growing that module.
All document reads complete before the first staged write.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from google.api_core.exceptions import Aborted
from google.cloud import firestore

from database.legal_holds import external_write_fence
from database.people_generation import bump_people_generation
from database import speaker_learning_jobs as learning_jobs, recurring_voice_assignments, recurring_voices
from database.notes_identity import identifier_retraction
from utils.observability.recurring_voices import profile_event
from utils.observability.fallback import record_fallback
from utils.owner_voice_evidence import retract_owner_contributions
from utils.person_evidence import person_updates_for_assignment
from utils.speakers import auto_enroll


@dataclass
class AssignmentBookkeeping:
    enabled: bool = True
    involved: bool = False
    recurring_events: tuple = ()


def run_assignment_transaction(client: Any, assign: Any, *, uid: str) -> Any:
    bookkeeping = AssignmentBookkeeping()

    @firestore.transactional
    def apply(transaction):
        bookkeeping.involved = False
        bookkeeping.recurring_events = ()
        with external_write_fence(uid, transaction=transaction, firestore_client=client):
            return assign(transaction, bookkeeping)

    try:
        from database.transcript_pointer import run_preloaded_transactional as run_transactional

        result = run_transactional(client, apply)
        for event in bookkeeping.recurring_events:
            profile_event(event)
        return result
    except (Aborted, ValueError) as error:
        aborted = (isinstance(error, Aborted) and error.__context__ is None) or (
            isinstance(error, ValueError) and isinstance(error.__cause__, Aborted)
        )
        if not bookkeeping.involved or not aborted:
            raise
    bookkeeping.enabled = False
    record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
    from database.transcript_pointer import run_preloaded_transactional as run_transactional

    result = run_transactional(client, apply, attempts=1)
    for event in bookkeeping.recurring_events:
        profile_event(event)
    return result


def persist_assignment_effects(
    transaction: Any,
    user_ref: Any,
    uid: str,
    conversation_id: str,
    before: Sequence[Mapping[str, Any]],
    segments: list,
    receipt: dict,
    resolved: list,
    previous: set,
    *,
    person_id: Optional[str],
    is_user: bool,
    use_for_speech_training: bool,
    evidence_source: str,
    rejection: Optional[dict],
    donor_ids: Sequence[str],
    bookkeeping: AssignmentBookkeeping,
    owner_segment_ids: Optional[list] = None,
) -> tuple[list[str], list[Mapping[str, Any]]]:
    """Return the removed sample paths and the relabeled previous segments."""
    # Read before writes; fence profiles and evidence atomically with the label.
    relabeled = [
        s
        for i, s in enumerate(before)
        if segments[i]['id'] in resolved
        and not (
            (rejection or {}).get('kind') == 'not_me'
            and ((receipt.get('segments') or {}).get(segments[i]['id']) or {}).get('segment_only')
            and s.get('person_id') == segments[i].get('person_id')
            and s.get('is_user') == segments[i].get('is_user')
        )
    ]
    rejected_person_id = (rejection or {}).get('person_id')
    source = user_ref.collection('conversations').document(conversation_id).get(transaction=transaction).to_dict() or {}
    user_doc = user_ref.get(transaction=transaction).to_dict() or {}
    save_other = bool(user_doc.get('save_other_voice_profiles', True))
    people = {
        pid: (pref := user_ref.collection('people').document(pid), pref.get(transaction=transaction).to_dict())
        for pid in previous | {p for p in (person_id, rejected_person_id) if p}
    }
    if any(not people[pid][1] for pid in (person_id, rejected_person_id) if pid):
        raise LookupError('Person not found')
    docs, now = {pid: doc for pid, (_, doc) in people.items()}, datetime.now(timezone.utc)
    evidence = (docs, previous, person_id, relabeled, evidence_source, conversation_id, resolved, now)
    updates, removed = person_updates_for_assignment(
        *evidence,
        receipt,
        segments,
        rejected_person_id=rejected_person_id,
        save_other_voice_profiles=save_other,
        source_conversation_ids=donor_ids,
    )
    if rejection:
        inferred_people = {
            s.get('person_id')
            for s in relabeled
            if s.get('speaker_match_source') == 'notes_inferred' and s.get('person_id')
        }
        for pid in inferred_people:
            if isinstance(pid, str) and docs.get(pid):
                updates.setdefault(pid, {}).update(identifier_retraction(docs[pid], conversation_id))
    owner_update = retract_owner_contributions(user_doc, donor_ids, resolved, now)
    pool_changes = {}
    # Retraction is mandatory even when new enrollment/use is killed off.
    for pid, doc in docs.items():
        change = auto_enroll.retract(
            uid,
            pid,
            (doc or {}).get(auto_enroll.POOL_FIELD),
            [conversation_id, *donor_ids],
            resolved,
        )
        if change:
            updates.setdefault(pid, {}).update(change)
            pool_changes[pid] = change[auto_enroll.POOL_FIELD]
    if pool_changes:
        owner_update.update(auto_enroll.authority_after(user_doc, pool_changes))
    recurring, recurring_events = recurring_voice_assignments.prepare(
        transaction,
        user_ref,
        user_doc,
        conversation_id,
        before,
        segments,
        receipt,
        resolved,
        person_id=person_id,
        person=docs.get(person_id),
        is_user=is_user,
        rejection=rejection,
        train=use_for_speech_training,
    )
    if bookkeeping.enabled:
        bookkeeping.involved = True
        projected_docs = {pid: {**(doc or {}), **updates.get(pid, {})} for pid, doc in docs.items()}
        job_updates = {pid: dict(update) for pid, update in updates.items()}
        try:
            jobs_ref_, payload, events = learning_jobs.prepare_assignment_jobs(
                transaction,
                user_ref,
                conversation_id,
                {
                    'transcript_segments': segments,
                    'manual_speaker_assignments': receipt,
                    'discarded': bool((source or {}).get('discarded')),
                },
                resolved,
                person_id=person_id,
                is_user=is_user,
                use_for_speech_training=use_for_speech_training,
                evidence_source=evidence_source,
                user_doc={**user_doc, **owner_update},
                people=projected_docs,
                updates=job_updates,
                now=now,
                owner_segment_ids=owner_segment_ids,
            )
            if payload is not None:
                transaction.set(jobs_ref_, payload)
        except Exception:
            record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
        else:
            updates = job_updates
            if events:
                receipt[learning_jobs.JOB_EVENTS_KEY] = events
    if recurring is not None and user_doc:
        recurring_voices.write_profiles(transaction, user_ref, user_doc, recurring)
        bookkeeping.recurring_events = tuple(recurring_events)
    if owner_update:
        transaction.update(user_ref, owner_update)
    for pid, update in updates.items():
        transaction.update(people[pid][0], update)
        bump_people_generation(transaction, people[pid][0])
    return removed, relabeled


def owner_confirmation_updates(
    current, owner_confirmation, segment_only, selected_speaker_id, owner_segment_ids, selected_segment_ids, is_user
):
    owner_updates = {}
    if owner_confirmation is not None:
        # Read-only conversation consumers do not depend on prompt models.
        # Load the authorization contract only for the explicit excerpt path.
        from utils.speaker_tag_prompts.owner_confirmation import (
            FIELD as OWNER_CONFIRMATION_FIELD,
            StaleOwnerConfirmation,
            validate_binding as validate_owner_confirmation,
        )

        binding = validate_owner_confirmation(
            current,
            owner_confirmation['prompt_id'],
            owner_confirmation['evidence_id'],
            selected_segment_ids,
            require_played=True,
        )
        if not segment_only or selected_speaker_id != binding['speaker_id'] or owner_segment_ids:
            raise StaleOwnerConfirmation('Owner excerpt cannot authorize whole-voice assignment or learning')
        owner_updates[OWNER_CONFIRMATION_FIELD] = dict(binding, answered='yes' if is_user else 'no')
    return owner_updates


def record_shadow_correction(current, resolved, logger):
    if any(s.get('speaker_grouping_shadow') for s in current.get('transcript_segments') or []):
        try:
            from utils.conversations.speaker_grouping_shadow import record_correction

            record_correction(current, resolved)
        except Exception as error:
            # A committed user correction cannot fail because optional telemetry
            # is unavailable (including its lazy import).
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='other',
                from_mode='speaker_grouping',
                to_mode='incumbent',
                reason='other',
                outcome='recovered',
                log=logger,
            )
            logger.warning(
                'event=speaker_grouping_correction outcome=unavailable exception_type=%s', type(error).__name__
            )


def record_assignment_commit(uid, result, logger):
    """Best-effort observation must never turn a committed label into a failed outcome."""
    from database.people_stats_cache import invalidate_people_stats_cache
    from utils.observability.speaker_identification import record_speaker_review

    current, resolved, _, before = result
    if not resolved:
        return
    observations = (
        lambda: invalidate_people_stats_cache(uid),
        lambda: record_shadow_correction(current, resolved, logger),
        lambda: record_speaker_review(uid, current['id'], before, current['transcript_segments']),
        lambda: learning_jobs.record_speaker_learning_job_events(current.pop(learning_jobs.JOB_EVENTS_KEY, ())),
    )
    for observe in observations:
        try:
            observe()
        except Exception:
            record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
