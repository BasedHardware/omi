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

from utils.llm.notes_agent_prompt import length_ceiling, length_floor
from utils.llm.shaped_agent import Problem

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


def check_notes(submission: Mapping[str, Any], *, transcript_words: int) -> NotesCheck:
    """Problems the model should fix itself on its first submission."""
    check = NotesCheck()
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
