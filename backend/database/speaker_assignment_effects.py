"""Transactional side effects of one manual speaker assignment.

Extracted from ``database.conversations.assign_conversation_speaker`` so the
label, person evidence, owner-profile retraction and the durable
speaker-learning ledger commit in one transaction without growing that module.
All document reads complete before the first staged write.
"""

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from database import speaker_learning_jobs as learning_jobs
from utils.observability.fallback import record_fallback
from utils.owner_voice_evidence import retract_owner_contributions
from utils.person_evidence import person_updates_for_assignment


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
    owner_segment_ids: Optional[list] = None,
) -> tuple[list[str], list[Mapping[str, Any]]]:
    """Return the removed sample paths and the relabeled previous segments."""
    # Read before writes; fence profiles and evidence atomically with the label.
    relabeled = [s for i, s in enumerate(before) if segments[i]['id'] in resolved]
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
        *evidence, receipt, segments, rejected_person_id=rejected_person_id, save_other_voice_profiles=save_other
    )
    owner_update = retract_owner_contributions(user_doc, donor_ids, resolved, now)
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
    except Exception:
        jobs_ref_ = None
        payload = None
        events = []
        record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
    else:
        updates = job_updates
    if events:
        receipt[learning_jobs.JOB_EVENTS_KEY] = events
    if owner_update:
        transaction.update(user_ref, owner_update)
    for pid, update in updates.items():
        transaction.update(people[pid][0], update)
    if payload is not None:
        transaction.set(jobs_ref_, payload)
    return removed, relabeled
