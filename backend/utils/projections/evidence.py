"""The evidence a projection is selected from.

A projection is generated from one bounded packet of the user's own recent material, and
this module is the deterministic half of that: it reads nothing and decides nothing about
salience. It gathers, bounds, and tiers.

Three sources, in the order they matter:

- **Conversation `structured.overview` prose** — the corpus that is actually rich. Recurrence
  across days is plainly visible in it, and is read by a model rather than counted off a
  field; the stored recurrence signals in this codebase sit behind a one-uid cohort gate and
  are unreachable.
- **Open action items** with computed age and overdue days — the one deterministic open-loop
  signal, and the fallback that still says something true after a single day of capture.
- **The active goal**, as context for what the person is trying to do.

The tier is the degradation ladder. `EMPTY` is a real outcome and callers must honour it: with
nothing to select from, the correct behaviour is to generate nothing rather than to invent a
subject.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

WINDOW_DAYS = 7

# The window is one prompt, not a map-reduce — a 7-day window of overview prose measures in
# the 7-10k token range. These caps are what keep that true for an unusually dense week.
MAX_CONVERSATIONS = 40
MAX_OVERVIEW_CHARS = 1200
MAX_ACTION_ITEMS = 25

_TRUNCATION_MARK = '…'


class EvidenceTier(str, Enum):
    """Which rung of the degradation ladder a corpus lands on."""

    RICH = 'rich'  # conversation prose is available; recurrence can be read across days
    THIN = 'thin'  # no prose, but open action items still carry true open loops
    EMPTY = 'empty'  # nothing to select from — generate nothing


@dataclass(frozen=True)
class ConversationEvidence:
    id: str
    created_at: Optional[datetime]
    title: str
    overview: str
    category: str


@dataclass(frozen=True)
class ActionItemEvidence:
    id: str
    description: str
    created_at: Optional[datetime]
    due_at: Optional[datetime]
    age_days: Optional[int]
    overdue_days: Optional[int]


@dataclass(frozen=True)
class GoalEvidence:
    title: str
    desired_outcome: str


@dataclass(frozen=True)
class EvidencePacket:
    generated_at: datetime
    window_days: int
    tier: EvidenceTier
    conversations: tuple[ConversationEvidence, ...]
    action_items: tuple[ActionItemEvidence, ...]
    goal: Optional[GoalEvidence]

    def grounding_reference_ids(self) -> tuple[str, ...]:
        """Stable references that can ground a subject, without copying personal prose."""
        references = [f'conversation:{item.id}' for item in self.conversations if item.id]
        references.extend(f'action_item:{item.id}' for item in self.action_items if item.id)
        return tuple(references)

    def reference_ids(self) -> tuple[str, ...]:
        """Every reference the selector may cite, including goal context."""
        references = list(self.grounding_reference_ids())
        if self.goal is not None:
            references.append('goal:active')
        return tuple(references)

    def receipts_for(self, reference_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Compact owner-visible labels for validated references, without source prose."""
        receipts: dict[str, dict[str, Any]] = {}
        for item in self.conversations:
            reference = f'conversation:{item.id}'
            receipts[reference] = {
                'reference': reference,
                'source': 'conversation',
                'label': _truncate(item.title, 160),
                'occurred_at': item.created_at,
            }
        for item in self.action_items:
            reference = f'action_item:{item.id}'
            receipts[reference] = {
                'reference': reference,
                'source': 'action_item',
                'label': _truncate(item.description, 160),
                'occurred_at': item.created_at,
            }
        if self.goal is not None:
            receipts['goal:active'] = {
                'reference': 'goal:active',
                'source': 'goal',
                'label': _truncate(self.goal.title, 160),
                'occurred_at': None,
            }
        return [receipts[reference] for reference in dict.fromkeys(reference_ids) if reference in receipts]

    def signal_summary(self) -> dict[str, Any]:
        """What this packet was built from, in a form that is safe to persist and log.

        Recorded at generation time because it is unrecoverable afterwards. It carries
        identifiers and counts only — never the material itself, which travels no further
        than the prompt.
        """
        return {
            'tier': self.tier.value,
            'window_days': self.window_days,
            'conversation_count': len(self.conversations),
            'conversation_ids': [c.id for c in self.conversations],
            'action_item_count': len(self.action_items),
            'action_item_ids': [item.id for item in self.action_items],
            'has_goal': self.goal is not None,
        }

    def as_prompt_text(self) -> str:
        """Render the packet for the selector prompt."""
        sections: list[str] = []

        if self.conversations:
            lines = ['CONVERSATIONS (oldest first):']
            for conversation in self.conversations:
                lines.append(
                    f'- [conversation:{conversation.id}] '
                    f'[{_format_date(conversation.created_at)}] {conversation.title}'
                )
                lines.append(f'  {conversation.overview}')
            sections.append('\n'.join(lines))

        if self.action_items:
            lines = ['OPEN ACTION ITEMS:']
            for item in self.action_items:
                age = 'age unknown' if item.age_days is None else f'{item.age_days}d old'
                overdue = '' if item.overdue_days is None else f', overdue {item.overdue_days}d'
                lines.append(f'- [action_item:{item.id}] {item.description} ({age}{overdue})')
            sections.append('\n'.join(lines))

        if self.goal is not None:
            lines = [f'ACTIVE GOAL [goal:active]: {self.goal.title}']
            if self.goal.desired_outcome:
                lines.append(f'  desired outcome: {self.goal.desired_outcome}')
            sections.append('\n'.join(lines))

        if not sections:
            return 'No evidence.'
        return '\n\n'.join(sections)


def assemble_packet(
    *,
    conversations: Sequence[Mapping[str, Any]],
    action_items: Sequence[Mapping[str, Any]],
    goal: Optional[Mapping[str, Any]],
    now: Optional[datetime] = None,
    window_days: int = WINDOW_DAYS,
) -> EvidencePacket:
    """Build one evidence packet from already-read documents.

    Pure by design: the caller owns the reads, so the selection inputs can be tested without
    a database and reproduced from a fixture.
    """
    now = now or datetime.now(timezone.utc)

    selected_conversations = _select_conversations(conversations)
    selected_action_items = _select_action_items(action_items, now=now)
    goal_evidence = _goal_evidence(goal)

    if selected_conversations:
        tier = EvidenceTier.RICH
    elif selected_action_items:
        tier = EvidenceTier.THIN
    else:
        # A goal states an intention; it is not an open thread with movement in it, so it
        # cannot by itself be the subject of a projection.
        tier = EvidenceTier.EMPTY

    return EvidencePacket(
        generated_at=now,
        window_days=window_days,
        tier=tier,
        conversations=selected_conversations,
        action_items=selected_action_items,
        goal=goal_evidence,
    )


def _select_conversations(conversations: Iterable[Mapping[str, Any]]) -> tuple[ConversationEvidence, ...]:
    usable: list[ConversationEvidence] = []
    for conversation in conversations:
        if conversation.get('discarded'):
            continue
        structured = conversation.get('structured')
        if not isinstance(structured, Mapping):
            continue
        overview = str(structured.get('overview') or '').strip()
        if not overview:
            continue
        usable.append(
            ConversationEvidence(
                id=str(conversation.get('id') or ''),
                created_at=_as_datetime(conversation.get('created_at')),
                title=str(structured.get('title') or '').strip() or 'Untitled',
                overview=_truncate(overview, MAX_OVERVIEW_CHARS),
                category=str(structured.get('category') or ''),
            )
        )

    # Cap by recency, then present oldest first so recurrence reads as a sequence.
    usable.sort(key=_conversation_sort_key, reverse=True)
    return tuple(reversed(usable[:MAX_CONVERSATIONS]))


def _select_action_items(action_items: Iterable[Mapping[str, Any]], *, now: datetime) -> tuple[ActionItemEvidence, ...]:
    open_items: list[ActionItemEvidence] = []
    for item in action_items:
        if item.get('completed') or item.get('status') == 'completed':
            continue
        description = str(item.get('description') or '').strip()
        if not description:
            continue
        created_at = _as_datetime(item.get('created_at'))
        due_at = _as_datetime(item.get('due_at'))
        open_items.append(
            ActionItemEvidence(
                id=str(item.get('id') or ''),
                description=description,
                created_at=created_at,
                due_at=due_at,
                age_days=_days_between(created_at, now),
                overdue_days=_days_between(due_at, now),
            )
        )

    # Longest-open first: age is the signal, so the cap must not drop the oldest loops.
    open_items.sort(key=lambda item: (item.age_days is None, -(item.age_days or 0)))
    return tuple(open_items[:MAX_ACTION_ITEMS])


def _goal_evidence(goal: Optional[Mapping[str, Any]]) -> Optional[GoalEvidence]:
    if not goal:
        return None
    title = str(goal.get('title') or '').strip()
    if not title:
        return None
    return GoalEvidence(title=title, desired_outcome=str(goal.get('desired_outcome') or '').strip())


def _conversation_sort_key(conversation: ConversationEvidence) -> tuple[int, datetime]:
    created_at = conversation.created_at
    if created_at is None:
        return (0, datetime.min.replace(tzinfo=timezone.utc))
    return (1, created_at)


def _days_between(earlier: Optional[datetime], now: datetime) -> Optional[int]:
    """Whole days from `earlier` to `now`, or None when `earlier` is absent or still ahead."""
    if earlier is None:
        return None
    delta = now - earlier
    if delta.total_seconds() < 0:
        return None
    return delta.days


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    # Firestore timestamps expose `.timestamp()` without being `datetime` instances.
    to_seconds = getattr(value, 'timestamp', None)
    if not callable(to_seconds):
        return None
    try:
        seconds = to_seconds()
    except Exception:
        return None
    if not isinstance(seconds, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATION_MARK)].rstrip() + _TRUNCATION_MARK


def _format_date(value: Optional[datetime]) -> str:
    return value.strftime('%Y-%m-%d') if value else 'date unknown'
