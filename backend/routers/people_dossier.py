"""Person-dossier read: the model-backed half of the People tab.

`POST /v1/people/dossiers` takes backend `Person` ids and returns, per person, the narrative
fields the profile renders (`who` / `now` / `overall` / `facts` / `activities` / `open_threads`)
plus the provenance behind each one. It is a **read** — it creates nothing, mutates nothing, and
accepts no message content from the caller. The only thing the device sends is person ids and the
fingerprints it already holds.

Why a route instead of on-device: the repository has no on-device language model today (zero
matches for `FoundationModels` / `LanguageModelSession` anywhere under `desktop/`), so "prefer
on-device" in `desktop/macos/docs/people-intelligence-productization.md` currently has nothing to
prefer. The privacy contract is still met, because the evidence summarized here is *already on
this account*: memories Omi extracted from conversations the user already consented to process,
including the thread transcripts `PeopleThreadIngest` uploaded after redacting phone numbers,
emails and OTP codes on-device. This route adds no new collection path.

Cost shape (the reason for every bound in this file):

  * one bounded Firestore memory read per request, shared by every person in the batch — not one
    read per person;
  * people whose evidence is under `MIN_EVIDENCE_ITEMS` are skipped **before** any model call, and
    in a real address book that is the large majority;
  * a caller that already holds a dossier sends its fingerprint and gets `unchanged` back, again
    with no model call, so a steady-state re-sync costs one Firestore read and nothing else.
"""

from __future__ import annotations

import logging
from concurrent.futures import as_completed
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from database import memories as memories_db
from database import users as users_db
from database.auth import get_user_name
from database.entities import person_entity_id
from utils.executors import llm_executor, submit_with_context
from utils.llm.people_dossier import (
    MIN_EVIDENCE_ITEMS,
    EvidenceItem,
    build_evidence,
    evidence_fingerprint,
    generate_person_dossier,
)
from utils.other import endpoints as auth

router = APIRouter()

logger = logging.getLogger(__name__)

#: Most people one request may ask about. This is a sync route, so it holds a FastAPI threadpool
#: worker for its whole duration; twelve is two rounds through `llm_executor`'s six workers, which
#: keeps the worst case comfortably inside the default POST timeout even when every person in the
#: batch has evidence. A larger address book is walked across successive throttled re-syncs.
MAX_PEOPLE_PER_REQUEST = 12

#: Ceiling on the shared memory read. Memories come back scoring-desc, so the cut keeps the
#: highest-value ones. This is the single Firestore cost of a request regardless of batch size.
MEMORY_SCAN_LIMIT = 1200


class PersonDossierRequestItem(BaseModel):
    person_id: str = Field(min_length=1, max_length=128)
    #: The fingerprint the caller already holds for this person. When the evidence still hashes to
    #: it there is nothing new to say, and the person comes back as `unchanged` with no model call.
    known_fingerprint: Optional[str] = Field(default=None, max_length=128)


class PersonDossierRequest(BaseModel):
    people: List[PersonDossierRequestItem] = Field(default_factory=list, max_length=MAX_PEOPLE_PER_REQUEST)


class DossierClaimOut(BaseModel):
    field: str
    text: str
    evidence: List[str] = Field(default_factory=list)


class PersonDossierOut(BaseModel):
    person_id: str
    name: str
    who: Optional[str] = None
    now: Optional[str] = None
    overall: Optional[str] = None
    facts: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    open_threads: List[str] = Field(default_factory=list)
    #: One entry per emitted sentence or list item, with the evidence ids behind it. This is what
    #: lets the profile explain a claim, and what a correction in `people_overrides.json` overrides.
    claims: List[DossierClaimOut] = Field(default_factory=list)
    evidence_count: int = 0
    evidence_fingerprint: str = ''


class SkippedPerson(BaseModel):
    person_id: str
    #: `unknown_person` — no such person on this account.
    #: `insufficient_evidence` — nothing on this account says enough about them to summarize.
    #: `unchanged` — the caller's fingerprint still matches, so its cached dossier is current.
    reason: str


class PersonDossierResponse(BaseModel):
    dossiers: List[PersonDossierOut] = Field(default_factory=list)
    skipped: List[SkippedPerson] = Field(default_factory=list)


@router.post('/v1/people/dossiers', tags=['people'], response_model=PersonDossierResponse)
def get_person_dossiers(
    request: PersonDossierRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'people:dossiers')),
) -> PersonDossierResponse:
    """Narrative + provenance for up to `MAX_PEOPLE_PER_REQUEST` people, in one shared read."""
    requested = _dedupe(request.people)
    if not requested:
        return PersonDossierResponse()

    known_people = {
        str(person.get('id')): str(person.get('name') or '')
        for person in users_db.get_people_by_ids(uid, [item.person_id for item in requested])
        if person.get('id')
    }

    skipped: List[SkippedPerson] = []
    plans: List[Dict[str, Any]] = []
    memories: Optional[List[Dict[str, Any]]] = None

    for item in requested:
        name = known_people.get(item.person_id)
        if not name:
            skipped.append(SkippedPerson(person_id=item.person_id, reason='unknown_person'))
            continue
        if memories is None:
            # Read once, for the whole batch. Deferred to here so a request that resolves no
            # person at all does not touch Firestore.
            memories = memories_db.get_memories(uid, limit=MEMORY_SCAN_LIMIT)
        evidence = build_evidence(memories, person_entity_id(item.person_id))
        fingerprint = evidence_fingerprint(evidence)
        if item.known_fingerprint and item.known_fingerprint == fingerprint:
            skipped.append(SkippedPerson(person_id=item.person_id, reason='unchanged'))
            continue
        if len(evidence) < MIN_EVIDENCE_ITEMS:
            skipped.append(SkippedPerson(person_id=item.person_id, reason='insufficient_evidence'))
            continue
        plans.append({'person_id': item.person_id, 'name': name, 'evidence': evidence, 'fingerprint': fingerprint})

    if not plans:
        return PersonDossierResponse(skipped=skipped)

    user_name = get_user_name(uid) or 'the user'
    dossiers = _generate_all(uid=uid, user_name=user_name, plans=plans)
    # A person whose grounded dossier came back empty is reported as skipped rather than as an
    # all-null card: "we could not tell" and "we looked and there is nothing" read the same to the
    # user, and both must leave the profile in its honest empty state.
    for plan in plans:
        if plan['person_id'] not in {dossier.person_id for dossier in dossiers}:
            skipped.append(SkippedPerson(person_id=plan['person_id'], reason='insufficient_evidence'))
    return PersonDossierResponse(dossiers=dossiers, skipped=skipped)


def _dedupe(items: List[PersonDossierRequestItem]) -> List[PersonDossierRequestItem]:
    seen: set[str] = set()
    out: List[PersonDossierRequestItem] = []
    for item in items:
        person_id = (item.person_id or '').strip()
        if not person_id or person_id in seen:
            continue
        seen.add(person_id)
        out.append(item)
        if len(out) >= MAX_PEOPLE_PER_REQUEST:
            break
    return out


def _generate_all(*, uid: str, user_name: str, plans: List[Dict[str, Any]]) -> List[PersonDossierOut]:
    """Fan the per-person model calls across `llm_executor` and keep only grounded results."""
    futures = {
        submit_with_context(
            llm_executor,
            generate_person_dossier,
            uid,
            user_name,
            plan['name'],
            plan['evidence'],
        ): plan
        for plan in plans
    }
    out: List[PersonDossierOut] = []
    for future in as_completed(futures):
        plan = futures[future]
        try:
            dossier = future.result()
        except Exception as error:  # pragma: no cover - generate_* already degrades internally
            logger.warning('person dossier failed for one person: %s', type(error).__name__)
            continue
        if dossier.is_empty:
            continue
        evidence: List[EvidenceItem] = plan['evidence']
        out.append(
            PersonDossierOut(
                person_id=plan['person_id'],
                name=plan['name'],
                who=dossier.who,
                now=dossier.now,
                overall=dossier.overall,
                facts=dossier.facts,
                activities=dossier.activities,
                open_threads=dossier.open_threads,
                claims=[DossierClaimOut(**claim) for claim in dossier.claims],
                evidence_count=len(evidence),
                evidence_fingerprint=plan['fingerprint'],
            )
        )
    out.sort(key=lambda dossier: dossier.person_id)
    return out
