"""Deterministic checks and repairs for a ``submit_notes`` payload. Pure: no I/O.

Each problem carries its failure class (``format`` or ``content``; the agent adds
``evidence``). The harness :class:`~utils.llm.shaped_agent.SendBackBudget` returns a
submission once per class; after that it is repaired here instead, so a format slip
never costs the owner their notes. Near-miss keys (``body`` for ``body_markdown``) are
normalized by the harness from the schema's declared aliases before these checks run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from models.structured import Structured
from config.refactor_modes import serving_for, shadow_or_serve
from utils.llm.meeting_notes_presentation import enforce_static_conversation_note_presentation
from utils.llm.notes_refactor_metrics import shadow, result
from utils.observability.fallback import record_fallback
from utils.llm.notes_lengths import length_ceiling, length_floor
from utils.llm.shaped_agent import Problem
from utils.llm.notes_identity import NotesIdentity, notes_identity, repair_identity

# Words that make a heading a task list rather than discussion.
_ACTION_HEADING = re.compile(
    r'^\W*(action[\s-]*items?|next[\s-]*steps?|to[\s-]*dos?|todos?|follow[\s-]*ups?|tasks?|'
    r'open\s+items|takeaways\s+and\s+actions|commitments)\W*$',
    re.IGNORECASE,
)
_TOP_BULLET = re.compile(r'^[-*+] \S', re.MULTILINE)
_NESTED_BULLET = re.compile(r'^(?: {2,}|\t+)[-*+] \S', re.MULTILINE)
_WORD = re.compile(r"[\w'’-]+")
# A meeting this long is expected to nest its details.
NESTING_MIN_WORDS = 1500
LENGTH_TOLERANCE = 1.25
DUPLICATE_TASK_OVERLAP = 0.8


FORMAT = 'format'
CONTENT = 'content'


@dataclass
class NotesCheck:
    findings: list[Problem] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        return [finding.message for finding in self.findings]

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, kind: str, message: str) -> None:
        self.findings.append(Problem(kind, message))


def body_words(sections: Iterable[Mapping[str, Any]]) -> int:
    return sum(len(_WORD.findall(str(section.get('body_markdown') or ''))) for section in sections)


def nested_bullet_count(body: str) -> int:
    return len(_NESTED_BULLET.findall(body or ''))


def is_action_heading(heading: str) -> bool:
    return bool(_ACTION_HEADING.match((heading or '').strip()))


_ROLE_PREFIX = re.compile(r'^(?:the|a|an|other|another|one|some|unknown|unnamed)\b', re.IGNORECASE)


def is_named(name: str) -> bool:
    """A participant entry must carry a name, not a role description ("Other attendee", "David's partner")."""
    text = name.strip()
    if not text or _ROLE_PREFIX.match(text) or "'s " in text or '’s ' in text:
        return False
    return any(word[:1].isupper() for word in text.split())


def _tokens(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text or '') if len(word) > 2}


def duplicates_open_task(description: str, open_tasks: Sequence[Any]) -> bool:
    wanted = _tokens(description)
    if not wanted:
        return False
    for task in open_tasks:
        text = task.get('description') if isinstance(task, Mapping) else task
        other = _tokens(str(text or ''))
        if other and len(wanted & other) / max(len(wanted), len(other)) >= DUPLICATE_TASK_OVERLAP:
            return True
    return False


TITLE_MAX_CHARS = 70
TITLE_MAX_WORDS = 10


def check_notes(
    submission: Mapping[str, Any],
    *,
    transcript_words: int,
    contract_v2: bool = False,
    identity: NotesIdentity | None = None,
) -> NotesCheck:
    """Problems the model should fix itself on its first submission."""
    check = NotesCheck()
    if identity is not None and repair_identity(submission, identity)[1]:
        check.add(
            'evidence',
            'Unsupported speaker identity: People names and lookup results are spelling data. '
            'Use a resolved voice binding, conversation calendar/tile roster or user correction; '
            'otherwise say a speaker, hedge names as heard and lead the title with the topic.',
        )
    if contract_v2:
        title = str(submission.get('title') or '').strip()
        if not title or len(title) > TITLE_MAX_CHARS or len(title.split()) > TITLE_MAX_WORDS:
            check.add(FORMAT, 'Use a nonempty specific title of at most 70 characters and 10 words.')
        if any(not is_named(str(person.get('name') or '')) for person in submission.get('participants') or []):
            check.add(CONTENT, 'Participants must be evidenced names, never unresolved speaker labels or roles.')
    sections = [section for section in submission.get('sections') or [] if isinstance(section, Mapping)]
    if not sections:
        check.add(FORMAT, 'No sections: write the notes as sections with bullet-list bodies.')
        return check
    action_sections = [str(s.get('heading')) for s in sections if is_action_heading(str(s.get('heading') or ''))]
    if action_sections:
        check.add(
            FORMAT,
            'Remove the section(s) ' + ', '.join(repr(name) for name in action_sections) + '; commitments belong '
            'only in action_items.',
        )
    prose = [str(s.get('heading')) for s in sections if not _TOP_BULLET.search(str(s.get('body_markdown') or ''))]
    if prose:
        check.add(
            FORMAT, 'Write these section bodies as "- " bullet lists, not prose: ' + ', '.join(map(repr, prose)) + '.'
        )
    if transcript_words >= NESTING_MIN_WORDS and not any(
        nested_bullet_count(str(s.get('body_markdown') or '')) for s in sections
    ):
        check.add(FORMAT, 'Nest the details: put supporting details under their point as indented "  - " sub-bullets.')
    ceiling = length_ceiling(transcript_words)
    words = body_words(sections)
    if words > ceiling * LENGTH_TOLERANCE:
        check.add(
            CONTENT,
            f'The section bodies have {words} words; the ceiling is {ceiling}. Cut minor details and repetition.',
        )
    floor = length_floor(transcript_words)
    if words < floor:
        check.add(
            CONTENT,
            f'The section bodies have {words} words; this meeting needs at least {floor}. Cover every substantive '
            'thread with its points and details.',
        )
    return check


def repair_notes(
    submission: Mapping[str, Any], *, open_tasks: Sequence[Any], owner_names: Sequence[str] = ()
) -> tuple[dict[str, Any], list[str]]:
    """Static repairs applied to every accepted submission. Returns ``(payload, repairs)``."""
    repaired = dict(submission)
    repairs: list[str] = []
    owners = {name.strip().casefold() for name in owner_names if name.strip()}
    people = [person for person in repaired.get('participants') or [] if isinstance(person, Mapping)]
    others = [
        person
        for person in people
        if str(person.get('name') or '').strip().casefold() not in owners and is_named(str(person.get('name') or ''))
    ]
    if len(others) != len(people):
        repairs.append('participant_dropped')
        repaired['participants'] = others
    sections = [section for section in repaired.get('sections') or [] if isinstance(section, Mapping)]
    kept = [section for section in sections if not is_action_heading(str(section.get('heading') or ''))]
    if len(kept) != len(sections) and kept:
        repairs.append('action_section_dropped')
        repaired['sections'] = kept
    items = [item for item in repaired.get('action_items') or [] if isinstance(item, Mapping)]
    fresh = []
    for item in items:
        # Notes only propose new tasks: reconciliation belongs to Dream.
        if item.get('candidate_action') in ('update', 'complete') or item.get('target_task_id'):
            repairs.append('task_reconciliation_dropped')
            continue
        if duplicates_open_task(str(item.get('description') or ''), open_tasks):
            repairs.append('duplicate_open_task_dropped')
            continue
        seen = {str(other.get('description') or '').casefold() for other in fresh}
        if str(item.get('description') or '').casefold() in seen:
            repairs.append('duplicate_action_item_dropped')
            continue
        fresh.append(item)
    if len(fresh) != len(items) or 'action_items' in repaired:
        repaired['action_items'] = fresh
    return repaired, sorted(set(repairs))


def repair_contract(
    submission: Mapping[str, Any],
    *,
    transcript_words: int,
    open_tasks: Sequence[Any] = (),
    owner_names: Sequence[str] = (),
    transcript_segment_ids: Iterable[str] = (),
    identity: NotesIdentity | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Same bounded, model-free repairs for every v2 arm. Never invent missing coverage.

    A floor violation is observable and eligible for the agent's content send-back.
    Static repair preserves a grounded short note rather than padding it with fiction.
    """
    repaired, repairs = repair_notes(submission, open_tasks=open_tasks, owner_names=owner_names)
    if identity is not None:
        repaired, identity_repairs = repair_identity(repaired, identity)
        repairs.extend(identity_repairs)
    title = ' '.join(str(repaired.get('title') or '').split()[:TITLE_MAX_WORDS])
    if len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS].rsplit(' ', 1)[0] or title[:TITLE_MAX_CHARS]
    if title != repaired.get('title'):
        repairs.append('title_bounded')
    repaired['title'] = title
    owners = {name.strip() for name in owner_names if name.strip()}
    for owner in sorted(owners, key=len, reverse=True):
        title = re.sub(r'(?<!\w)' + re.escape(owner) + r"(?:['’]s)?(?!\w)", '', title, flags=re.IGNORECASE)
    title = re.sub(r'^\W*(?:and\s+)?|\s+and\W*$', '', title, flags=re.IGNORECASE).strip(' :,-')
    if title != repaired.get('title'):
        repairs.append('owner_removed_from_title')
    repaired['title'] = title
    allowed = set(transcript_segment_ids)
    sections = []
    remaining = length_ceiling(transcript_words)
    for section in repaired.get('sections') or []:
        section = dict(section)
        body = str(section.get('body_markdown') or '').strip()
        lines = []
        for line in body.splitlines():
            if not line.strip():
                continue
            if not re.match(r'^\s*[-*+]\s', line):
                line = '- ' + line.strip()
                repairs.append('body_bulleted')
            count = len(_WORD.findall(line))
            if count > remaining:
                repairs.append('length_bounded')
                if remaining <= 0:
                    continue
                # Retain a grounded prefix, never drop an entire substantive
                # section merely because the model made one oversized bullet.
                tokens = list(_WORD.finditer(line))
                line = line[: tokens[remaining - 1].end()].rstrip() + '…'
                count = remaining
            # Never retain an orphaned nested detail as its own claim.
            if not lines and line.startswith((' ', '\t')):
                line = line.lstrip()
            lines.append(line)
            remaining -= count
        if not lines:
            continue
        section['body_markdown'] = '\n'.join(lines)
        original = section.get('source_segment_ids') or []
        section['source_segment_ids'] = list(dict.fromkeys(ref for ref in original if ref in allowed))
        if section['source_segment_ids'] != original:
            repairs.append('citations_filtered')
        sections.append(section)
    repaired['sections'] = sections
    for field_name in ('action_items', 'events'):
        repaired[field_name] = [dict(item) for item in repaired.get(field_name) or []]
        for item in repaired[field_name]:
            refs = item.get('source_segment_ids') or []
            item['source_segment_ids'] = list(dict.fromkeys(ref for ref in refs if ref in allowed))
    return repaired, sorted(set(repairs))


def enforce_output_contract(
    structured: Any,
    *,
    transcript_words: int,
    transcript_segment_ids: Iterable[str],
    owner_names: Sequence[str] = (),
    open_tasks: Sequence[Any] = (),
    title_people: Sequence[str] = (),
    identity: NotesIdentity | None = None,
) -> NotesCheck:
    """Validate and repair the parsed artifact including visible Markdown citations."""

    payload = structured.model_dump(mode='json')
    check = check_notes(payload, transcript_words=transcript_words, contract_v2=True, identity=identity)
    payload, check.repairs = repair_contract(
        payload,
        transcript_words=transcript_words,
        open_tasks=open_tasks,
        owner_names=owner_names,
        transcript_segment_ids=transcript_segment_ids,
        identity=identity,
    )
    repaired = Structured.model_validate(payload)
    for field_name in (
        'title',
        'overview',
        'sections',
        'participants',
        'action_items',
        'events',
        'insights',
        'note_claims',
    ):
        if getattr(structured, field_name) != getattr(repaired, field_name):
            setattr(structured, field_name, getattr(repaired, field_name))
    enforce_static_conversation_note_presentation(structured, transcript_segment_ids, title_people=title_people)
    # Title people repair can lengthen the title: the shared bounds apply last.
    bounded, _ = repair_contract({'title': structured.title}, transcript_words=transcript_words)
    structured.title = bounded['title']
    if identity is not None:
        _finish_identity(structured, None, {'notes_identity': identity})
    return check


OUTPUT_RULES = '''OUTPUT CONTRACT
- Return a specific title of at most 70 characters and 10 words. Never put the account owner's name in it.
- Lead with a non-owner counterpart's name only when confident speaker evidence identifies them; otherwise lead
  with the topic. Likely identities are hedged in the body, never stated as certain in the title.
- Return exactly one emoji that represents the conversation.
- Title, overview, section bodies, participants, tasks and events use the packet's output_language.
- Use the packet's LENGTH range; density is guidance, never permission to pad unsupported facts.
- Every section body is a bullet list. Nest supporting details. Commitments belong only in action_items.
- Participants contain evidenced non-owner names only; omit unresolved people instead of inventing a name.
- A People spelling or search_people hit cannot bind a voice: require a resolved speaker binding, a calendar
  attendee or tile/roster name in this conversation, or the user's correction. Transcript-only names stay hedged.
- Copy only authoritative transcript IDs into source_segment_ids, never into visible text or links.
- Speaker bands and the no-guess rule override any naming leads in calendar, contact, screen or background data.'''


def finish_notes_contract(
    structured: Any, *, prefix: Any, uid: str | None, words: int, rich_mode: bool, inputs: Mapping[str, Any]
) -> Any:
    """Shadow validates a copy; serving mutates only the cohort's artifact. Zero model calls."""

    serve = serving_for('NOTES_PACKET_V2_MODE', uid)
    if shadow_or_serve('NOTES_PACKET_V2_MODE'):
        try:
            target = structured.model_copy(deep=True)
            check = enforce_output_contract(
                target,
                transcript_words=words,
                transcript_segment_ids=prefix.transcript_segment_ids,
                owner_names=tuple(name for name in (prefix.account_owner_name, *prefix.owner_names) if name),
                open_tasks=inputs.get('existing_action_items') or (),
            )
            shadow(
                'output_contract',
                'disagree' if check.findings or check.repairs else 'agree',
                repairs=len(check.repairs),
            )
            if serve:
                result(
                    'output_contract',
                    'repaired' if check.repairs else 'accepted_with_problems' if check.findings else 'passed',
                )
                return _finish_identity(target, prefix, inputs)
        except Exception:
            shadow('output_contract', 'error')
            if serve:
                record_fallback(
                    component='conversation_notes',
                    from_mode='notes_output_contract',
                    to_mode='legacy_presentation',
                    reason='local_heal',
                    outcome='degraded',
                )
    # refactor: superseded by notes_output_contract when NOTES_PACKET_V2_MODE=serve
    enforce_static_conversation_note_presentation(
        structured,
        prefix.transcript_segment_ids,
        title_people=() if rich_mode else prefix.title_people,
    )
    return _finish_identity(structured, prefix, inputs)


def _finish_identity(structured: Any, prefix: Any, inputs: Mapping[str, Any]) -> Any:
    identity = inputs.get('notes_identity') or notes_identity(prefix, inputs)
    payload, repairs = repair_identity(structured.model_dump(mode='json'), identity)
    if repairs:
        repaired = Structured.model_validate(payload)
        for field_name in (
            'title',
            'overview',
            'sections',
            'participants',
            'action_items',
            'events',
            'insights',
            'note_claims',
        ):
            if getattr(structured, field_name) != getattr(repaired, field_name):
                setattr(structured, field_name, getattr(repaired, field_name))
        record_identity_repair()
    return structured


def record_identity_repair() -> None:
    result('speaker_identity', 'repaired')
    record_fallback(
        component='conversation_notes',
        from_mode='unsupported_identity',
        to_mode='supported_labels',
        reason='local_heal',
        outcome='degraded',
    )
