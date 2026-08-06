"""The model calls in the edition.

Four things genuinely need writing rather than computing: yesterday's story,
the newsletter clustering, the ranking of external material, and the cover
line. Everything else in the paper is arithmetic over stored records.

Two rules bind every prompt here.

**Only the record.** No prompt may introduce a fact absent from the material
handed to it. A paper that invents a detail about someone's life is finished,
and it fails in the one direction the reader cannot check.

**Short, simple, conversational, non-redundant.** Say it once. Plain words. If a
smart friend would not say it out loud, it does not get printed.
"""

import json
import logging
import re

from models.paper import (
    Commitment,
    Cover,
    ForYou,
    NewsletterStory,
    NewsLine,
    PaperItem,
    SourceRef,
    Today,
    Yesterday,
)
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.log_sanitizer import sanitize

from .context import DayContext, record_lines
from .interests import rubric_text

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')

# Length ceilings. The page is finite by construction, so these are enforced on
# output rather than merely requested in the prompt — prompt compliance is not
# a guarantee, and an over-long section silently breaks the one-page contract.
MAX_HEADLINE_WORDS = 9
MAX_STORY_CHARS = 700
MAX_SUMMARY_CHARS = 300
MAX_WHY_CHARS = 400

_STYLE = (
    'Write short, simple, conversational sentences. Say each thing once. Plain words. '
    'No preamble, no motivational language, no emoji, no second-person coaching. '
    'No em dashes, semicolons or ellipses.'
)


def _parse(raw: str) -> dict:
    cleaned = _FENCE_RE.sub('', raw or '').strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def ask_model(uid: str, prompt: str, cache_key: str) -> dict:
    """One model call, returning {} on any failure.

    Callers degrade to stored text rather than raising: a partial edition still
    prints something true.
    """
    try:
        with track_usage(uid, Features.PAPER):
            response = get_llm('paper', cache_key=cache_key).invoke(prompt)
        content = getattr(response, 'content', response)
        return _parse(content if isinstance(content, str) else str(content))
    except Exception as e:  # noqa: BLE001 — a failed section must still leave a paper.
        logger.warning('paper: model call %s failed: %s', cache_key, sanitize(str(e)))
        return {}


def clip(text: object, limit: int) -> str:
    """Trim to a ceiling on a word boundary."""
    value = str(text or '').strip()
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(' ', 1)[0].rstrip(',.;:') + '.'


def clip_words(text: object, limit: int) -> str:
    words = str(text or '').strip().split()
    return ' '.join(words[:limit])


# ---------------------------------------------------------------------------
# Yesterday
# ---------------------------------------------------------------------------

_YESTERDAY_PROMPT = """You are writing the "yesterday" section of one person's daily paper. \
The reader is its only subject.

THE RECORD (everything captured on {day}):
{record}

HARD RULE: use only what is in the record. No names, numbers, places or events that do not \
appear there. If the record is too thin for a field, return an empty string for it.

{style}

Return only JSON, no fences:
{{
  "headline": "<= {max_words} words. What the day was actually about.",
  "story": "3 to 5 sentences on what they did and worked through. Past tense.",
  "decisions": ["<a decision they actually made, quoted close to the record>"],
  "unacted": "<one idea they raised and did not act on, or empty string if none>"
}}"""


def write_yesterday(uid: str, context: DayContext) -> Yesterday | None:
    """Yesterday's story, grounded in the day's own record."""
    lines = record_lines(context)
    if not lines:
        return None

    summary = context.summary or {}
    payload = ask_model(
        uid,
        _YESTERDAY_PROMPT.format(
            day=context.day.isoformat(),
            record='\n'.join(lines),
            style=_STYLE,
            max_words=MAX_HEADLINE_WORDS,
        ),
        'omi-paper-yesterday',
    )

    headline = clip_words(payload.get('headline'), MAX_HEADLINE_WORDS) or str(summary.get('headline') or '').strip()
    story = clip(payload.get('story'), MAX_STORY_CHARS) or str(summary.get('overview') or '').strip()
    if not headline and not story and not context.focus:
        return None

    decisions = [str(d).strip() for d in (payload.get('decisions') or []) if str(d).strip()][:5]
    if not decisions:
        decisions = [
            str((d or {}).get('decision') or '').strip()
            for d in (summary.get('decisions_made') or [])[:5]
            if (d or {}).get('decision')
        ]

    return Yesterday(
        headline=headline,
        story=story,
        focus=context.focus,
        decisions=decisions,
        unacted=clip(payload.get('unacted'), MAX_SUMMARY_CHARS),
        source_date=context.day.isoformat(),
    )


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------

_TODAY_PROMPT = """Write one plain sentence describing the shape of this person's day.

EVENTS TODAY:
{events}

WHAT THEY OWE:
{commitments}

{style}

Use only what is above. If there is nothing scheduled and nothing owed, return an empty \
string for the note.

Return only JSON, no fences:
{{"note": "<one sentence, or empty string>"}}"""


def build_today(uid: str, events: list, commitments: list[Commitment]) -> Today:
    """Today's shape. Deterministic apart from the one framing line."""
    today = Today(events=events, commitments=commitments)
    if today.is_clear:
        return today

    event_lines = '\n'.join(f'- {e.title} at {e.start or "unspecified time"}' for e in events) or '(none)'
    owed_lines = '\n'.join(f'- {c.text}' for c in commitments[:10]) or '(none)'

    payload = ask_model(
        uid,
        _TODAY_PROMPT.format(events=event_lines, commitments=owed_lines, style=_STYLE),
        'omi-paper-today',
    )
    today.note = clip(payload.get('note'), MAX_SUMMARY_CHARS)
    return today


# ---------------------------------------------------------------------------
# Newsletters
# ---------------------------------------------------------------------------

_NEWSLETTER_PROMPT = """Cluster these newsletter messages into distinct stories.

Four newsletters covering one funding round is ONE story, listing all four publications.

MESSAGES:
{messages}

{rubric}

HARD RULE: every story must come from the messages above. Do not add context you know from \
elsewhere. Do not invent numbers. If a message is pure advertising with no information, drop it.

{style}

Return only JSON, no fences:
{{
  "stories": [
    {{
      "summary": "<one sentence. What happened.>",
      "publications": ["<publication names from the messages that covered it>"],
      "why": "<one short clause on why it matters to this reader, or empty string>"
    }}
  ]
}}

Most significant first. At most {limit} stories."""


def cluster_newsletters(uid: str, messages: list[dict], profile, limit: int = 12) -> list[NewsletterStory]:
    """Collapse many newsletters into one line per story."""
    if not messages:
        return []

    rendered = []
    for message in messages[:40]:
        publication = str(message.get('publication') or 'Unknown')
        subject = str(message.get('subject') or '')
        snippet = str(message.get('snippet') or str(message.get('body') or ''))[:400]
        rendered.append(f'[{publication}] {subject}\n{snippet}')

    rubric = rubric_text(profile)
    payload = ask_model(
        uid,
        _NEWSLETTER_PROMPT.format(
            messages='\n\n'.join(rendered),
            rubric=f'THIS READER:\n{rubric}\n' if rubric else '',
            style=_STYLE,
            limit=limit,
        ),
        'omi-paper-newsletters',
    )

    stories: list[NewsletterStory] = []
    for raw in (payload.get('stories') or [])[:limit]:
        if not isinstance(raw, dict):
            continue
        summary = clip(raw.get('summary'), MAX_SUMMARY_CHARS)
        publications = [str(p).strip() for p in (raw.get('publications') or []) if str(p).strip()]
        story = NewsletterStory(
            summary=summary,
            sources=[SourceRef(name=name) for name in publications[:6]],
            why=clip(raw.get('why'), MAX_SUMMARY_CHARS),
        )
        # A story with no publication behind it cannot be checked, so it is not printed.
        if story.is_printable:
            stories.append(story)
    return stories


# ---------------------------------------------------------------------------
# For you
# ---------------------------------------------------------------------------

_RANK_PROMPT = """Rank these papers for one reader and explain each in their terms.

THIS READER:
{rubric}

CANDIDATES:
{candidates}

A paper earns its place by moving something this reader is actually working on, not by \
being interesting in general. If fewer than {limit} clear that bar, return fewer. Never pad.

HARD RULE: use only the candidate text above. Do not add findings, numbers or authors that \
are not there.

{style}

Return only JSON, no fences:
{{
  "picks": [
    {{
      "index": <0-based index into CANDIDATES>,
      "what_it_says": "2 to 3 plain sentences.",
      "why_it_matters": "The specific thing of theirs it moves, and what it changes.",
      "experiment": "One concrete thing they could test in an afternoon."
    }}
  ]
}}"""


def rank_for_you(
    uid: str,
    candidates: list[PaperItem],
    news: list[NewsLine],
    profile,
    limit: int = 3,
) -> ForYou:
    """Pick and explain the external material worth this reader's attention."""
    for_you = ForYou(news=news)
    rubric = rubric_text(profile)
    if not candidates or not rubric:
        return for_you

    rendered = '\n\n'.join(
        f'[{index}] {item.title}\n{item.what_it_says or ""}'.strip() for index, item in enumerate(candidates[:30])
    )
    payload = ask_model(
        uid,
        _RANK_PROMPT.format(rubric=rubric, candidates=rendered, limit=limit, style=_STYLE),
        'omi-paper-rank',
    )

    picked: list[PaperItem] = []
    for raw in (payload.get('picks') or [])[:limit]:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get('index', -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(candidates):
            continue
        base = candidates[index]
        picked.append(
            base.model_copy(
                update={
                    'what_it_says': clip(raw.get('what_it_says'), MAX_WHY_CHARS) or base.what_it_says,
                    'why_it_matters': clip(raw.get('why_it_matters'), MAX_WHY_CHARS),
                    'experiment': clip(raw.get('experiment'), MAX_SUMMARY_CHARS),
                }
            )
        )

    for_you.papers = picked
    return for_you


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------

_COVER_PROMPT = """Write the cover line for today's edition.

WHAT IS IN IT:
{contents}

{style}

Use only what is above. Return only JSON, no fences:
{{
  "thesis": "<the through-line across today's material, one short sentence>",
  "emphasis": "<one word from that sentence to set in accent>",
  "standfirst": "<one sentence under it, or empty string>"
}}"""


def write_cover(uid: str, contents: list[str]) -> Cover:
    if not contents:
        return Cover()
    payload = ask_model(
        uid,
        _COVER_PROMPT.format(contents='\n'.join(f'- {line}' for line in contents[:20]), style=_STYLE),
        'omi-paper-cover',
    )
    return Cover(
        thesis=clip(payload.get('thesis'), MAX_SUMMARY_CHARS),
        emphasis=clip_words(payload.get('emphasis'), 2),
        standfirst=clip(payload.get('standfirst'), MAX_SUMMARY_CHARS),
    )
