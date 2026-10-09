"""Pure production background-pack types and rendering; no retrieval imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

MAX_CONTEXT_PACK_CHARACTERS = 6_000
MAX_PRIOR_MEETINGS_CHARACTERS = 1_600
MAX_PEOPLE_CHARACTERS = 900
MAX_GOALS_CHARACTERS = 400
MAX_MEMORIES_CHARACTERS = 850
MAX_SCREEN_CHARACTERS = 2_500
# Rendered before SCREEN ACTIVITY so the overall cap trims the raw OCR digest,
# not the judge's per-frame summaries.
MAX_SCREEN_MOMENTS_CHARACTERS = 900

BACKGROUND_CONTEXT_HEADING = 'BACKGROUND CONTEXT (not part of this conversation)'


@dataclass(frozen=True)
class PriorMeetingNote:
    title: str
    date_label: str
    gist: str
    open_items: tuple[str, ...] = ()
    source_id: Optional[str] = None
    started_at: Optional[datetime] = None


@dataclass(frozen=True)
class PersonFact:
    name: str
    relationship: Optional[str] = None
    notes: Optional[str] = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeetingContextPack:
    prior_meetings: tuple[PriorMeetingNote, ...] = ()
    people_facts: tuple[PersonFact, ...] = ()
    goals: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()
    screen_text: str = ''
    screen_moments: tuple[str, ...] = ()
    screen_rows: tuple[Mapping[str, Any], ...] = ()

    @property
    def empty(self) -> bool:
        return not (
            self.prior_meetings
            or self.people_facts
            or self.goals
            or self.memories
            or self.screen_text
            or self.screen_moments
            or self.screen_rows
        )


def truncate_context_text(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + '…'


def _render_part(lines: Iterable[str], cap: int) -> str:
    rendered: list[str] = []
    used = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if used + len(line) + 1 > cap:
            # Truncate the item to what remains of the part budget instead of
            # dropping it — one oversized fact must not crowd out the rest.
            remaining = cap - used - 1
            if remaining < 2:
                break
            line = truncate_context_text(line, remaining)
        rendered.append(line)
        used += len(line) + 1
    return '\n'.join(rendered)


def render_meeting_context_pack(pack: Optional[MeetingContextPack]) -> str:
    """Render the pack as the dynamic BACKGROUND CONTEXT block, <= 6000 chars."""
    if pack is None or pack.empty:
        return ''
    parts: list[str] = [BACKGROUND_CONTEXT_HEADING]
    prior_lines = []
    for note in pack.prior_meetings:
        line = f'- [{note.date_label}] {note.title}'
        if note.gist:
            line += f' — {note.gist}'
        prior_lines.append(line)
        for item in note.open_items:
            prior_lines.append(f'  open: {item}')
    prior = _render_part(prior_lines, MAX_PRIOR_MEETINGS_CHARACTERS)
    if prior:
        parts.append(f'PRIOR MEETINGS\n{prior}')
    people_lines = []
    for fact in pack.people_facts:
        line = f'- {fact.name}'
        detail = fact.relationship or ''
        if fact.aliases:
            detail = f'{detail}; aka {", ".join(fact.aliases)}' if detail else f'aka {", ".join(fact.aliases)}'
        if detail:
            line += f' ({detail})'
        if fact.notes:
            line += f' — {fact.notes}'
        people_lines.append(line)
    people = _render_part(people_lines, MAX_PEOPLE_CHARACTERS)
    if people:
        parts.append(f'PEOPLE\n{people}')
    goals = _render_part((f'- {goal}' for goal in pack.goals), MAX_GOALS_CHARACTERS)
    if goals:
        parts.append(f'GOALS\n{goals}')
    memories = _render_part((f'- {memory}' for memory in pack.memories), MAX_MEMORIES_CHARACTERS)
    if memories:
        parts.append(f'MEMORIES\n{memories}')
    moments = _render_part(pack.screen_moments, MAX_SCREEN_MOMENTS_CHARACTERS)
    if moments:
        parts.append(f'SCREEN MOMENTS (approved screenshots from this call)\n{moments}')
    if pack.screen_text:
        parts.append(f'SCREEN ACTIVITY\n{truncate_context_text(pack.screen_text, MAX_SCREEN_CHARACTERS)}')
    rendered = '\n\n'.join(parts)
    if len(rendered) > MAX_CONTEXT_PACK_CHARACTERS:
        rendered = rendered[: MAX_CONTEXT_PACK_CHARACTERS - 1].rstrip() + '…'
    return rendered
