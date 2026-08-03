"""Phase-3 person-dossier synthesis: the per-person narrative the People tab renders.

`desktop/macos/docs/people-intelligence-productization.md` classifies `who` / `now` / `overall` /
`facts` / `activities` / `openThreads` as **model-backed**. Nothing in this repo wrote them, so for
every user those sections were permanently empty. This module is the model half of that layer.

Two things make it safe to ship:

**It never sees raw message history.** The evidence it summarizes is memories Omi already extracted
on this account. The device-side path that produced most of them (`PeopleThreadIngest`) redacts
phone numbers, emails and OTP-style codes *before* the transcript ever leaves the machine and caps
the window at the last 40 messages of a thread. This module adds no new data collection and no
second redactor — it reads what is already stored.

**Every emitted field is grounded or absent.** `ground_dossier` is the contract: a model output is
only kept when the model cited an evidence id it was actually given, and every list item has to be
cited individually. A field the model asserted without a citation is dropped, not softened. That is
enforced in code rather than requested in prose, because a prompt rule is advice and a validator is
a guarantee.

Do **not** reuse `extract_memories_prompt` here. Its rules 7 and 8 (`utils/prompts.py:180-186`)
forbid standalone facts about third parties — every fact must be a sentence about the user with the
other person as a modifier. That yields prose that cannot be slotted into a per-person `who`/`now`.
This prompt is modelled on `utils/llm/working_observations.py:131-146`, which already permits a
third-party subject (`about` may be "Sarah", "Mom", "teammate").
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, cast

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from .clients import get_llm
from .usage_tracker import Features, track_usage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounds. Every one of these exists to keep a per-person call affordable when it
# runs across a whole address book — see the cost note in the router.
# ---------------------------------------------------------------------------

#: Below this many evidence items there is nothing to summarize, and the honest output is an
#: empty profile. The router skips these people **without an LLM call**, which is what keeps the
#: cost of a 200-person address book proportional to the handful of people who actually have
#: history rather than to the size of the address book.
MIN_EVIDENCE_ITEMS = 3

#: Most evidence items handed to one call. Ordered strongest-first by the caller, so the cut
#: drops the weakest signal.
MAX_EVIDENCE_ITEMS = 40

#: Per-item character cap. Memory content is already one line; this only bounds pathological rows.
MAX_EVIDENCE_CHARS = 240

#: Per-field output caps. A profile is a glance, not a dossier dump.
MAX_FACTS = 6
MAX_ACTIVITIES = 5
MAX_OPEN_THREADS = 4

#: Hedges are the tell of an ungrounded claim. Rule 5 of the prompt forbids them; this is the
#: mechanical half of that rule, applied to every emitted string.
_HEDGE_PATTERN = re.compile(
    r'\b('
    r'seems?\s+to|seemed\s+to|appears?\s+to|appeared\s+to|likely|probably|possibly|perhaps|'
    r'maybe|might\s+be|may\s+be|could\s+be|presumably|i\s+think|i\s+believe|'
    r'suggests?\s+that|implies?\s+that|apparently'
    r')\b',
    re.IGNORECASE,
)

#: Field names the model is allowed to cite. Anything else in `claims` is ignored.
SCALAR_FIELDS = ('who', 'now', 'overall')
LIST_FIELDS = ('facts', 'activities', 'open_threads')


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """One already-extracted, already-minimized fact about (or referencing) the person.

    `id` is what the model must cite. It is short on purpose — `m0`, `m1`, … — so citing is cheap
    in output tokens and an invented id is easy to reject.
    """

    id: str
    text: str
    #: ISO-8601 day of the underlying memory, or '' when unknown. Recency is what separates `now`
    #: from `overall`, so the model needs it, but only to day precision.
    when: str
    #: 'subject' when the memory is *about* this person, 'mention' when the person is only
    #: referenced by it. The distinction matters: a mention is weaker evidence for `who`.
    role: str

    def render(self) -> str:
        when = f' [{self.when}]' if self.when else ''
        return f'{self.id} ({self.role}){when}: {self.text}'


def _clip(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    cleaned = ' '.join(str(text or '').split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + '…'


def build_evidence(memories: Sequence[Dict[str, Any]], entity_id: str) -> List[EvidenceItem]:
    """Turn raw memory dicts into the bounded evidence list for one person.

    A memory counts as evidence when the person is its subject (`subject_entity_id`) or is
    referenced by it (`object_entity_ids`). Subject memories sort first — they are the stronger
    signal — and the list is capped at `MAX_EVIDENCE_ITEMS`.

    Pure: no IO, no network. This is the function the contract tests drive.
    """
    subject_rows: List[Dict[str, Any]] = []
    mention_rows: List[Dict[str, Any]] = []
    for memory in memories:
        content = _clip(cast(str, memory.get('content') or ''))
        if not content:
            continue
        if memory.get('subject_entity_id') == entity_id:
            subject_rows.append(memory)
        elif entity_id in (memory.get('object_entity_ids') or []):
            mention_rows.append(memory)

    def created_key(memory: Dict[str, Any]) -> str:
        return _iso_day(memory.get('created_at'))

    subject_rows.sort(key=created_key, reverse=True)
    mention_rows.sort(key=created_key, reverse=True)

    out: List[EvidenceItem] = []
    for role, rows in (('subject', subject_rows), ('mention', mention_rows)):
        for memory in rows:
            if len(out) >= MAX_EVIDENCE_ITEMS:
                return out
            out.append(
                EvidenceItem(
                    id=f'm{len(out)}',
                    text=_clip(cast(str, memory.get('content') or '')),
                    when=created_key(memory),
                    role=role,
                )
            )
    return out


def _iso_day(value: Any) -> str:
    """Day-precision ISO string for a Firestore timestamp / datetime / string, or ''."""
    if value is None:
        return ''
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat):
        try:
            return str(isoformat())[:10]
        except Exception:  # pragma: no cover - defensive; a bad timestamp must not break a read
            return ''
    return str(value)[:10]


def evidence_fingerprint(evidence: Sequence[EvidenceItem]) -> str:
    """Stable digest of the evidence a dossier was generated from.

    The cache key. When it is unchanged there is nothing new to say about the person, so the
    stored dossier is returned and no LLM call happens. Text is included (not just ids) so an
    edited or superseded memory invalidates the dossier.
    """
    digest = hashlib.sha256()
    for item in evidence:
        digest.update(item.role.encode('utf-8'))
        digest.update(b'\x1f')
        digest.update(item.text.encode('utf-8'))
        digest.update(b'\x1e')
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Model output shape
# ---------------------------------------------------------------------------


class DossierClaim(BaseModel):
    field: str = Field(
        description="Which output field this claim backs: who, now, overall, facts, activities, or open_threads"
    )
    text: str = Field(description="The exact sentence you put in that field (for a list field, the exact list item)")
    evidence: List[str] = Field(
        description="Evidence ids that state this claim, e.g. ['m0','m4']", default_factory=list
    )


class PersonDossierDraft(BaseModel):
    """Raw model output. Never trusted directly — always passed through `ground_dossier`."""

    who: Optional[str] = Field(
        description="One or two sentences on who this person is to the user. Omit if unsupported.", default=None
    )
    now: Optional[str] = Field(
        description="What is going on with this person recently. Omit if unsupported.", default=None
    )
    overall: Optional[str] = Field(
        description="The arc of the relationship over time. Omit if unsupported.", default=None
    )
    facts: List[str] = Field(description="Durable one-line facts about this person.", default_factory=list)
    activities: List[str] = Field(
        description="Things the user and this person actually do together.", default_factory=list
    )
    open_threads: List[str] = Field(
        description="Specific unresolved requests, promises, questions or decisions.", default_factory=list
    )
    claims: List[DossierClaim] = Field(
        description="One entry per emitted sentence/list item, with the evidence ids backing it.", default_factory=list
    )


@dataclass(frozen=True)
class GroundedDossier:
    """A dossier after the grounding contract has been applied. Safe to persist and render."""

    who: Optional[str]
    now: Optional[str]
    overall: Optional[str]
    facts: List[str]
    activities: List[str]
    open_threads: List[str]
    #: Provenance for what survived: field -> [{"text": ..., "evidence": [...]}]. This is what lets
    #: the UI show why a claim exists, and what a user's correction in `people_overrides.json` is
    #: correcting.
    claims: List[Dict[str, Any]]

    @property
    def is_empty(self) -> bool:
        return not any([self.who, self.now, self.overall, self.facts, self.activities, self.open_threads])

    def as_dict(self) -> Dict[str, Any]:
        return {
            'who': self.who,
            'now': self.now,
            'overall': self.overall,
            'facts': list(self.facts),
            'activities': list(self.activities),
            'open_threads': list(self.open_threads),
            'claims': [dict(claim) for claim in self.claims],
        }


EMPTY_DOSSIER = GroundedDossier(who=None, now=None, overall=None, facts=[], activities=[], open_threads=[], claims=[])


# ---------------------------------------------------------------------------
# The grounding contract
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return ' '.join(str(text or '').split()).strip().lower().rstrip('.')


def _is_hedged(text: str) -> bool:
    return bool(_HEDGE_PATTERN.search(text or ''))


def ground_dossier(draft: PersonDossierDraft, allowed_evidence_ids: Iterable[str]) -> GroundedDossier:
    """Drop everything the model did not actually ground. This is the guarantee, not the prompt.

    A field survives only when the draft carries a claim that

      1. names that field,
      2. cites at least one evidence id that was really in the prompt (an invented id is a
         fabrication tell, so it counts for nothing), and
      3. for a list field, whose `text` matches the list item — every item is cited individually
         rather than the whole list riding on one citation.

    Hedged strings ("seems to", "probably", …) are dropped wherever they appear: rule 5 of the
    prompt says a claim that needs a hedge is a claim without evidence, and this makes that
    mechanical.

    Pure and total — a malformed draft yields an empty dossier, never an exception.
    """
    allowed = {str(item) for item in allowed_evidence_ids if str(item)}

    grounded: Dict[str, List[Dict[str, Any]]] = {}
    for claim in draft.claims or []:
        field = _normalize(getattr(claim, 'field', '') or '').replace(' ', '_')
        if field not in SCALAR_FIELDS and field not in LIST_FIELDS:
            continue
        cited = [item for item in (claim.evidence or []) if item in allowed]
        if not cited:
            continue
        text = ' '.join(str(claim.text or '').split())
        if not text:
            continue
        grounded.setdefault(field, []).append({'field': field, 'text': text, 'evidence': cited})

    kept_claims: List[Dict[str, Any]] = []

    def scalar(field: str, value: Optional[str]) -> Optional[str]:
        text = ' '.join(str(value or '').split())
        if not text or _is_hedged(text):
            return None
        for claim in grounded.get(field, []):
            if _is_hedged(claim['text']):
                continue
            kept_claims.append({'field': field, 'text': text, 'evidence': claim['evidence']})
            return text
        return None

    def listed(field: str, values: Sequence[str], cap: int) -> List[str]:
        by_text = {_normalize(claim['text']): claim for claim in grounded.get(field, [])}
        out: List[str] = []
        seen: set[str] = set()
        for raw in values or []:
            text = ' '.join(str(raw or '').split())
            key = _normalize(text)
            if not text or not key or key in seen or _is_hedged(text):
                continue
            claim = by_text.get(key)
            if claim is None:
                continue
            seen.add(key)
            out.append(text)
            kept_claims.append({'field': field, 'text': text, 'evidence': claim['evidence']})
            if len(out) >= cap:
                break
        return out

    return GroundedDossier(
        who=scalar('who', draft.who),
        now=scalar('now', draft.now),
        overall=scalar('overall', draft.overall),
        facts=listed('facts', draft.facts, MAX_FACTS),
        activities=listed('activities', draft.activities, MAX_ACTIVITIES),
        open_threads=listed('open_threads', draft.open_threads, MAX_OPEN_THREADS),
        claims=kept_claims,
    )


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


def build_dossier_prompt(
    user_name: str, person_name: str, evidence: Sequence[EvidenceItem], format_instructions: str
) -> str:
    """The person-centric prompt.

    Grounding lives in rules 1, 4 and 5: rule 1 makes a citation the price of emitting a field,
    rule 4 puts `open_threads` behind an explicitly unresolved exchange rather than a vibe, and
    rule 5 bans the hedges that ungrounded claims hide behind. `ground_dossier` enforces all three
    afterwards, so a model that ignores them produces an empty profile rather than a confident one.
    """
    listing = '\n'.join(item.render() for item in evidence)
    return f"""You are writing a short profile of ONE person in {user_name}'s life, for {user_name}'s own reference.

The subject is {person_name} — NOT {user_name}. Sentences whose subject is {person_name} are expected and correct here.

You are given numbered EVIDENCE. Each line is a fact Omi already extracted from {user_name}'s own conversations and messages. `(subject)` means the fact is about {person_name}; `(mention)` means {person_name} is only referenced by it. `[date]` is when it was recorded.

Grounding rules — these decide whether your output is used at all:
1. Every field you emit MUST be listed in `claims` with at least one evidence id that states it. A field you cannot cite must be left out (null for a sentence, [] for a list). Anything you emit without a real citation is discarded. An empty profile is a correct answer.
2. Never generalize from evidence about a group, a chat name, or another person into a claim about {person_name}.
3. Never infer a job, employer, school, location, relationship status, health, or family detail that no evidence line states.
4. `open_threads` is the strictest field. Emit an item ONLY when an evidence line shows a specific request, promise, question or decision that was left unresolved — one of you owes the other something, or something was asked and not settled. "They talk often", "they are close", or "they are planning a trip" are NOT open threads. If nothing is unresolved, return [].
5. Do not hedge. No "seems to", "appears to", "likely", "probably", "possibly", "might be". If a claim needs a hedge you do not have the evidence for it — leave it out.
6. Do not restate the evidence lines verbatim as a list. `facts` are durable one-liners; `now` and `overall` are prose.
7. Plain, specific, no advice, no greetings, no second person.

Fields:
- who: one or two sentences on who {person_name} is to {user_name}. Omit unless the evidence names the relationship or the shared context.
- now: what is going on with {person_name} recently. Omit unless the evidence is recent AND specific.
- overall: one or two sentences on how the relationship has gone over time. Omit unless the evidence spans more than one occasion.
- facts: durable one-line facts about {person_name}. At most {MAX_FACTS}.
- activities: things {user_name} and {person_name} actually do together. At most {MAX_ACTIVITIES}.
- open_threads: see rule 4. At most {MAX_OPEN_THREADS}.
- claims: one entry per sentence or list item you emitted — its field, its exact text, and the evidence ids backing it.

EVIDENCE about {person_name}:
{listing}

Return JSON:
{format_instructions}"""


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def generate_person_dossier(
    uid: str, user_name: str, person_name: str, evidence: Sequence[EvidenceItem]
) -> GroundedDossier:
    """One grounded dossier, or `EMPTY_DOSSIER`.

    Returns without calling the model when the evidence is too thin (`MIN_EVIDENCE_ITEMS`) —
    that gate is what keeps a large address book cheap, because most people in one have no
    ingested history at all. Any model/parse failure also degrades to `EMPTY_DOSSIER`: an absent
    narrative is the correct empty state, never an error the People tab has to render.
    """
    if len(evidence) < MIN_EVIDENCE_ITEMS:
        return EMPTY_DOSSIER

    parser = PydanticOutputParser(pydantic_object=PersonDossierDraft)
    prompt = build_dossier_prompt(
        user_name=user_name,
        person_name=person_name,
        evidence=evidence,
        format_instructions=parser.get_format_instructions(),
    )
    try:
        with track_usage(uid, Features.PERSON_DOSSIER):
            response = get_llm('person_dossier').invoke(prompt)
        draft = parser.parse(cast(str, cast(Any, response).content))
    except Exception as error:
        logger.warning('person dossier generation failed: %s', type(error).__name__)
        return EMPTY_DOSSIER

    return ground_dossier(draft, [item.id for item in evidence])
