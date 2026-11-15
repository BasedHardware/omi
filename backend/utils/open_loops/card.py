"""Self-contained Review cards for open loops.

A card must survive without any surrounding UI: the question names who and what
happened in recognizable words, the context line says where it came from
(conversation title + weekday) and why now (due date or "no follow-up since
…"). The deterministic template works without a model; an optional single
cheap-model polish call rewords the same facts behind the same interface and
every failure keeps the template. No relationship, medical or legal inference
is ever made — the templates only restate supplied facts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Optional
from zoneinfo import ZoneInfo

from config.open_loops import card_polish_enabled
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage

logger = logging.getLogger(__name__)

QUESTION_MAX_CHARS = 140
COMBINED_MAX_CHARS = 180
TITLE_MAX_CHARS = 32
WHAT_MAX_CHARS = 90
WHO_MAX_CHARS = 30
# The why-now clause is dropped before the title is squeezed further.
NO_FOLLOW_UP_AFTER_DAYS = 2

ALLOWED_KINDS = ('owed_to_user', 'own_commitment', 'issue_or_blocker')
_FORBIDDEN_JARGON = ('open loop', 'extraction', 'schema', 'action item', 'loop_id', 'task_id')

_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


@dataclass(frozen=True)
class OpenLoopCard:
    question: str
    context_line: str
    source_ref: str
    polished: bool = False

    @property
    def combined_chars(self) -> int:
        return len(self.question) + len(self.context_line)

    def as_payload(self) -> dict[str, Any]:
        return {
            'question': self.question,
            'context_line': self.context_line,
            'source_ref': self.source_ref,
            'polished': self.polished,
        }


def _zone(tz: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz) if tz else ZoneInfo('UTC')
    except Exception:
        return ZoneInfo('UTC')


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _weekday(value: Any, tz: Optional[str]) -> str:
    moment = _as_datetime(value)
    if moment is None:
        day = _as_date(value)
        return _WEEKDAYS[day.weekday()] if day is not None else 'recently'
    return _WEEKDAYS[moment.astimezone(_zone(tz)).weekday()]


def _clip(text: str, limit: int) -> str:
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0] if ' ' in text[:limit] else text[:limit]
    return cut.rstrip(' ,;:') + '…'


def _lead_in(what: str) -> str:
    """Lowercase a verb-led phrase after "Did you/anyone/{who} ".

    An all-caps first word is an acronym, not a sentence verb; keep it.
    """
    first = what.split(' ', 1)[0]
    if len(first) > 1 and first.isupper():
        return what
    return what[0].lower() + what[1:]


def _source_title(loop: Mapping[str, Any]) -> str:
    title = ' '.join((loop.get('title') or '').split())
    if title:
        return _clip(title, TITLE_MAX_CHARS)
    return 'conversation'


def _due_text(loop: Mapping[str, Any], tz: Optional[str], today: date) -> Optional[str]:
    by_when = loop.get('by_when') or loop.get('due')
    if not by_when or not isinstance(by_when, str):
        return None
    due = _as_date(by_when)
    if due is None:
        phrase = _clip(by_when.strip(), 24)
        return f'due {phrase}'
    days = (due - today).days
    if days == 0:
        return 'due today'
    if days < 0:
        return f'was due {_WEEKDAYS[due.weekday()]}'
    if days <= 6:
        return f'due {_WEEKDAYS[due.weekday()]}'
    return f'due {due.strftime("%b %d")}'


def _last_activity(loop: Mapping[str, Any]) -> Any:
    history = loop.get('history')
    if isinstance(history, (list, tuple)) and history:
        last = history[-1]
        if isinstance(last, Mapping):
            return last.get('date')
    return loop.get('started_at')


def _why_now(loop: Mapping[str, Any], tz: Optional[str], today: date) -> str:
    due_text = _due_text(loop, tz, today)
    if due_text:
        return due_text
    last = _as_date(_last_activity(loop))
    if last is not None:
        days = (today - last).days
        if days > 6:
            return f'no follow-up since {last.strftime("%b %d")}'
        if days >= NO_FOLLOW_UP_AFTER_DAYS:
            return f'no follow-up since {_WEEKDAYS[last.weekday()]}'
    return ''


def _what(loop: Mapping[str, Any]) -> str:
    what = loop.get('what')
    if not what:
        task = loop.get('related_task')
        if isinstance(task, Mapping):
            what = task.get('title')
    return _clip(str(what or ''), WHAT_MAX_CHARS).rstrip('.').strip()


def _question(loop: Mapping[str, Any]) -> str:
    """The question body without the trailing question mark."""
    kind = loop.get('kind')
    what = _what(loop)
    if not what:
        what = 'follow up on this'
    who = _clip(str(loop.get('who') or '').strip(), WHO_MAX_CHARS)
    if kind == 'owed_to_user':
        if who and who.casefold() not in ('unknown', 'someone', 'somebody'):
            return f'Did {who} {_lead_in(what)}'
        return f'Did anyone {_lead_in(what)}'
    # own commitments and observed issues are both the owner's move; the
    # extractor phrases issues imperatively ("File the … crash bug").
    return f'Did you {_lead_in(what)}'


def _task_clause(loop: Mapping[str, Any]) -> str:
    """The "(your task from Thu)" tail a strongly task-linked card carries.

    It is what makes the question self-evidently about the tracked task, so a
    Done answer can complete it (see ``store.card_view`` / the service's
    completion gate). Only the strong-link shape (``related_task`` with an
    ``opened_on`` day) carries it; the ask-only fallback task title does not.
    """
    task = loop.get('related_task')
    if not isinstance(task, Mapping) or not task.get('title'):
        return ''
    opened = _as_date(task.get('opened_on'))
    return f' (your task from {_WEEKDAYS[opened.weekday()]})' if opened is not None else ''


def build_card(loop: Mapping[str, Any], *, tz: Optional[str], now: Optional[datetime] = None) -> OpenLoopCard:
    """The deterministic template card; no model, no I/O."""
    weekday = _weekday(loop.get('started_at'), tz)
    title = _source_title(loop)
    zone = _zone(tz)
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()

    body = _question(loop)
    task_tail = _task_clause(loop)
    if task_tail:
        body = body[: QUESTION_MAX_CHARS - 1 - len(task_tail)].rstrip(' ,;:') + task_tail
    question = body[: QUESTION_MAX_CHARS - 1].rstrip(' ,;:') + '?'
    why_now = _why_now(loop, tz, today)
    source = f'{title} ({weekday})'
    context = f"From {weekday}'s {title}"
    if why_now:
        context = f'{context}, {why_now}'

    room = COMBINED_MAX_CHARS - len(question)
    if len(context) > room:
        shorter = f'From {weekday}' + (f', {why_now}' if why_now else '')
        context = shorter if len(shorter) <= room else context[: room - 1].rstrip(' ,;:') + '…'
    started = _as_datetime(loop.get('started_at'))
    source_ref = f'{source}, {started.astimezone(zone).date().isoformat()}' if started is not None else source
    return OpenLoopCard(question=question, context_line=context, source_ref=source_ref)


def _acceptable(card: OpenLoopCard) -> bool:
    question = card.question.strip()
    if not question.endswith('?') or len(question) < 8 or len(question) > QUESTION_MAX_CHARS:
        return False
    if not card.context_line.strip() or card.combined_chars > COMBINED_MAX_CHARS + 20:
        return False
    lowered = f'{question} {card.context_line}'.casefold()
    return not any(token in lowered for token in _FORBIDDEN_JARGON)


POLISH_INSTRUCTIONS = '''You polish one card for a personal AI assistant's daily Review screen. The owner
answers the card with Done / Remind me later / Drop it.

Return ONLY JSON: {"question": "...", "context_line": "..."} — no prose.
- question: one short yes/no question, at most 140 characters.
- context_line: where it came from (conversation title + weekday) and why now; at most one sentence.
- question + context_line together at most 180 characters.
- Stay self-contained: name who and what happened in recognizable everyday words; a reader who saw
  nothing else must understand it.
- Keep every fact from the input; you may only reword. Never add facts, dates, names or urgency.
- Plain words only; never use internal jargon such as "loop", "extraction", "schema" or "action item".
- Never make relationship, medical or legal interpretations, and never speculate about anyone's
  private life.'''


def llm_polisher(uid: str) -> Optional[Callable[[OpenLoopCard, Mapping[str, Any]], Optional[OpenLoopCard]]]:
    """The optional single-call polish, or None while the switch is off.

    The model client is built lazily by ``get_llm`` on the first polish call.
    """
    if not card_polish_enabled():
        return None

    def polish(card: OpenLoopCard, loop: Mapping[str, Any]) -> Optional[OpenLoopCard]:
        model = get_llm('open_loop_card')
        payload = {
            'kind': loop.get('kind'),
            'who': loop.get('who'),
            'what': loop.get('what'),
            'due': loop.get('by_when') or loop.get('due'),
            'conversation_title': loop.get('title'),
            'template_question': card.question,
            'template_context_line': card.context_line,
        }
        # A strongly task-linked card must keep naming the task in its own
        # words — the Done-completion gate checks the final text for it.
        task = loop.get('related_task')
        if isinstance(task, Mapping) and task.get('title'):
            payload['related_task_title'] = task.get('title')
        with track_usage(uid, Features.OPEN_LOOP_CARD):
            response = model.invoke(
                [
                    {'role': 'system', 'content': POLISH_INSTRUCTIONS},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, default=str)},
                ]
            )
        content = str(getattr(response, 'content', response)).strip()
        if content.startswith('```'):
            content = content.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None
        candidate = OpenLoopCard(
            question=str(parsed.get('question', '')).strip(),
            context_line=str(parsed.get('context_line', '')).strip(),
            source_ref=card.source_ref,
            polished=True,
        )
        return candidate if _acceptable(candidate) else None

    return polish


def build_review_card(
    loop: Mapping[str, Any],
    *,
    tz: Optional[str],
    now: Optional[datetime] = None,
    polisher: Optional[Callable[[OpenLoopCard, Mapping[str, Any]], Optional[OpenLoopCard]]] = None,
) -> OpenLoopCard:
    """Template card, optionally reworded by one polish call.

    Any polish failure — exception, malformed JSON, or a candidate that breaks
    the self-contained rules — keeps the deterministic template.
    """
    card = build_card(loop, tz=tz, now=now)
    if polisher is None:
        return card
    try:
        polished = polisher(card, loop)
    except Exception:  # noqa: BLE001 - polish is best-effort by contract
        logger.info('open loop card polish failed; keeping template')
        return card
    if polished is None or not _acceptable(polished):
        return card
    return polished
