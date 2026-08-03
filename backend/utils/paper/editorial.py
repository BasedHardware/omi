"""The one model call in the edition.

Everything else in the paper is computed. This writes the two things that genuinely need
prose: the lede, and the argument against a position the ledger already proved is
one-sided. Both are grounded — the prompt forbids introducing any fact not present in the
day's own record, because a paper that invents a detail about someone's life is finished.
"""

import json
import logging
import re

from models.paper import Counterpoint, Lede
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')

_PROMPT = """You are the editor of a one-page personal newspaper. The reader is its only \
subject. Write in plain, declarative newspaper prose — no second-person coaching, no \
motivational language, no emoji.

HARD RULE: use only facts present in THE RECORD below. Introduce nothing else. No names, \
numbers, places or events that do not appear there. If the record is too thin, return an \
empty string for that field.

THE RECORD (today, {date}):
{record}
{stance_block}
Return only JSON, no fences:
{{
  "headline": "<= 9 words, title case, states what happened. No colon-subtitle format.",
  "body": "2-3 sentences of plain past-tense reportage on that headline.",
  "counterpoint": "{counterpoint_instruction}"
}}"""

_STANCE_TEMPLATE = """
A POSITION THE READER HAS TAKEN {days} SEPARATE DAYS WITHOUT ONCE ARGUING THE OTHER SIDE:
"{position}"
"""

_COUNTERPOINT_ASK = (
    'The strongest good-faith argument AGAINST that position, 2-3 sentences. '
    'Address the reader as "you". Be direct and specific, not balanced. Do not hedge or '
    'restate their view approvingly first.'
)


def _record_for(summary: dict) -> str:
    """Flatten one day's summary into the grounding record the prompt may draw on."""
    lines = []
    if summary.get('headline'):
        lines.append(f"Day headline: {summary['headline']}")
    if summary.get('overview'):
        lines.append(f"Overview: {summary['overview']}")
    for highlight in (summary.get('highlights') or [])[:6]:
        topic = (highlight or {}).get('topic') or ''
        detail = (highlight or {}).get('summary') or ''
        if topic or detail:
            lines.append(f"- {topic}: {detail}".strip())
    for decision in (summary.get('decisions_made') or [])[:5]:
        text = (decision or {}).get('decision')
        if text:
            lines.append(f"- Decided: {text}")
    return '\n'.join(lines)


def _parse(raw: str) -> dict:
    """Best-effort JSON out of a model response. Returns {} rather than raising."""
    cleaned = _FENCE_RE.sub('', raw or '').strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_editorial(
    uid: str,
    summary: dict,
    stance: Counterpoint | None,
) -> tuple[Lede | None, Counterpoint | None]:
    """Write the lede and, when a stance qualifies, the counterpoint argument.

    Falls back to the stored day headline on any model or parse failure — a degraded
    edition still prints something true. The counterpoint is dropped entirely rather than
    filled with a generic argument.
    """
    record = _record_for(summary)
    source_date = str(summary.get('date') or '')
    if not record.strip():
        return None, None

    stance_block = ''
    counterpoint_instruction = 'Return an empty string. There is no position to argue against.'
    if stance is not None:
        stance_block = _STANCE_TEMPLATE.format(days=stance.days_asserted, position=stance.position)
        counterpoint_instruction = _COUNTERPOINT_ASK

    prompt = _PROMPT.format(
        date=source_date,
        record=record,
        stance_block=stance_block,
        counterpoint_instruction=counterpoint_instruction,
    )

    try:
        with track_usage(uid, Features.PAPER):
            response = get_llm('paper', cache_key='omi-paper-edition').invoke(prompt)
        content = getattr(response, 'content', response)
        payload = _parse(content if isinstance(content, str) else str(content))
    except Exception as e:  # noqa: BLE001 — a failed edition must still print.
        logger.warning('paper: editorial generation failed, falling back: %s', sanitize(str(e)))
        payload = {}

    headline = str(payload.get('headline') or '').strip() or str(summary.get('headline') or '').strip()
    lede = None
    if headline:
        lede = Lede(
            headline=headline,
            body=str(payload.get('body') or '').strip() or str(summary.get('overview') or '').strip(),
            source_date=source_date,
        )

    counterpoint = None
    argument = str(payload.get('counterpoint') or '').strip()
    if stance is not None and argument:
        counterpoint = stance.model_copy(update={'argument': argument})

    return lede, counterpoint
