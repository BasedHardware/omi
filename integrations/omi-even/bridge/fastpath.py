"""Answer a question fast enough that Even AI will actually show it.

Even's custom-agent client has an undocumented timeout, and it is short. Proven
on real hardware: a 0.4s reply renders on the glasses, while 5.6-8.4s replies
arrive at the bridge, return 200 OK, and are never seen.

Omi's `/v2/messages` cannot meet that budget -- its time to *first token* was
6.6-13.9s in measurement, because the agent runs a retrieval loop before writing
anything. So this path skips the agent and reads Omi's stores directly:

    /v1/action-items                   0.17s
    /v1/tools/conversations/search     0.79s
    /v1/tools/memories/search          1.48s

The cost is real and worth stating plainly: these return retrieved facts, not
Omi's composed, reasoned answer. Composing would need an LLM the bridge does not
have a key for. A slightly blunter answer that appears beats a better one that
does not.

The full agent path is still used by the omi Hub app, which streams to the
display and has no deadline to beat.
"""

from __future__ import annotations

import asyncio
import logging
import re

log = logging.getLogger(__name__)

# "Found 5 memories matching 'David Zhang':" -- restates the question, wasting a
# quarter of the screen.
_PREAMBLE_RE = re.compile(r'^Found\s+\d+\s+\w+\s+matching\s+.*?:\s*', re.IGNORECASE | re.DOTALL)

# "(relevance: 0.48, category: interesting, date: 2026-07-27)" -- debugging
# metadata, meaningless on a heads-up display.
_META_RE = re.compile(r'\s*\((?:relevance|category|date)[^)]*\)\s*$', re.IGNORECASE)
_RELEVANCE_RE = re.compile(r'relevance:\s*([0-9.]+)')

# Below this, hits are near-random: the live "David Zhang" query returned a
# downloads-folder path at 0.38 alongside the real colleague fact at 0.48.
_MIN_RELEVANCE = 0.40

# Word groups that decide which store to read. Checked in order, most specific
# first, because "what did I do yesterday" is about conversations even though it
# contains "do".
_ACTION_WORDS = ('action item', 'task', 'to-do', 'todo', 'behind on', 'due', 'my plate', 'commit')
_CONVERSATION_WORDS = (
    'yesterday', 'today', 'last night', 'this morning', 'this week', 'last week',
    'talk', 'said', 'meeting', 'call', 'conversation', 'discuss', 'happened',
)


def _classify(question: str) -> str:
    q = question.lower()
    if any(w in q for w in _ACTION_WORDS):
        return 'actions'
    if any(w in q for w in _CONVERSATION_WORDS):
        return 'conversations'
    return 'memories'


def _clean_bullets(result_text: str, min_relevance: float = _MIN_RELEVANCE) -> list[str]:
    """Turn a tool's result_text into readable lines, best first."""
    body = _PREAMBLE_RE.sub('', result_text or '').strip()
    scored: list[tuple[float, str]] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith('-'):
            continue
        line = line.lstrip('-').strip()
        if not line:
            continue

        match = _RELEVANCE_RE.search(line)
        score = float(match.group(1)) if match else 1.0
        if score < min_relevance:
            continue

        line = _META_RE.sub('', line).strip().rstrip(',;')
        if line:
            scored.append((score, line))

    # Stable sort keeps the tool's own ordering among equal scores.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [text for _, text in scored]


def _format(lines: list[str], empty_message: str, limit: int = 3) -> str:
    if not lines:
        return empty_message
    return '\n'.join(f'- {line}' for line in lines[:limit])


# Lines in a conversation result that are scaffolding rather than content.
_CONV_NOISE_RE = re.compile(
    r'^\s*(Conversation\s*#\d+|Started:|Finished:|\d{1,2}\s+\w+\s+\d{4}\s+at\b)', re.IGNORECASE
)

# The tools report "nothing found" as prose, not as an empty body.
_NO_RESULTS_RE = re.compile(r'^\s*(No\s+(conversations?|memories|results)\s+found|Error:)', re.IGNORECASE)


def _compact_conversations(result_text: str, limit: int = 4) -> str:
    """Reduce a conversation dump to the few lines worth reading on glasses.

    The raw result leads with `Conversation #1`, a timezone-qualified timestamp,
    then `Started:`/`Finished:` repeating it twice more. That is most of a
    380-character screen spent before any content appears.
    """
    body = _PREAMBLE_RE.sub('', result_text or '').strip()
    # The tool phrases "no results" as a sentence rather than returning empty, and
    # echoing it back reads as a broken answer ("- No conversations found matching
    # 'What did I do yesterday?' in the specified date range.").
    if _NO_RESULTS_RE.match(body):
        return ''
    kept: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or _CONV_NOISE_RE.match(line):
            continue
        line = line.lstrip('#').strip()  # "## Screen Check" -> "Screen Check"
        line = line.lstrip('-').strip()
        if line:
            kept.append(line)
        if len(kept) >= limit:
            break
    return '\n'.join(f'- {line}' for line in kept)


_STOPWORDS = frozenset(
    'a an the is are was were do does did i me my you your what when where who whom '
    'why how all about tell know of on in to for and or with can could would should '
    'me mine we us our there here that this those these it its'.split()
)


def _looks_relevant(question: str, text: str) -> bool:
    """Guard so a thin match is not passed off as an answer.

    Conversation search carries no relevance score and always returns
    *something*: "who is the president of the USA" surfaced a conversation about
    wallpapers. One shared word proved too weak a filter -- a long transcript
    mentions almost any single common word eventually -- so this requires most of
    the question's content words, matched on word boundaries rather than as
    substrings.
    """
    terms = {w for w in re.findall(r'[a-z0-9]+', question.lower()) if w not in _STOPWORDS and len(w) > 2}
    if not terms:
        return True  # nothing to check against; do not block on it

    haystack = text.lower()
    hits = sum(1 for term in terms if re.search(rf'\b{re.escape(term)}\b', haystack))
    # With only one or two content words, a single incidental hit is exactly the
    # failure case -- "USA" appears in a conversation about a trip, and the answer
    # to "who is the president of the USA" becomes a wallpaper chat. Demand all of
    # them. Longer questions relax to a majority so a stray word cannot veto a
    # genuine match.
    required = len(terms) if len(terms) <= 2 else (len(terms) + 1) // 2
    return hits >= required


def _day_bounds(days_ago_start: int, days_ago_end: int) -> dict[str, str]:
    """Timezone-aware bounds spanning whole local days.

    The search tool rejects a bare date: it requires
    `YYYY-MM-DDTHH:MM:SS+HH:MM`, and a plain `2026-07-20` comes back as an error
    rather than a filter. That error is indistinguishable from an empty result,
    so the bad format silently produced "nothing recorded" for days that had
    plenty -- a wrong answer, not a missing one.
    """
    from datetime import datetime, time, timedelta

    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).date()
    start_day = today - timedelta(days=days_ago_start)
    end_day = today - timedelta(days=days_ago_end)
    return {
        'start_date': datetime.combine(start_day, time.min, tzinfo=local_tz).isoformat(),
        'end_date': datetime.combine(end_day, time.max.replace(microsecond=0), tzinfo=local_tz).isoformat(),
    }


def _date_window(question: str) -> dict[str, str]:
    """Date bounds for a temporal question, so "yesterday" means yesterday.

    Without this the search is purely semantic and happily returns a conversation
    from three weeks ago -- observed live, "what did I do yesterday" returned
    08 Jul on 27 Jul.
    """
    q = question.lower()
    if 'yesterday' in q:
        return _day_bounds(1, 1)
    if 'today' in q or 'this morning' in q:
        return _day_bounds(0, 0)
    if 'this week' in q:
        return _day_bounds(7, 0)
    if 'last week' in q:
        return _day_bounds(14, 7)
    return {}


async def _search_or_empty(client, tool: str, payload: dict) -> str:
    """Run a retrieval tool, treating any failure as "found nothing".

    These tools flag an empty result the same way they flag a real error, and a
    question with no matches is a normal outcome -- not a reason to spend six
    seconds on the agent path to reach the same conclusion.
    """
    try:
        return await client.tool_search(tool, payload)
    except Exception as exc:  # noqa: BLE001 - empty and broken look alike here
        log.info('%s returned nothing usable: %s', tool, exc)
        return ''


async def fast_answer(client, question: str) -> str:
    """Answer from Omi's stores directly, in roughly two seconds."""
    kind = _classify(question)
    log.info('fastpath: %s', kind)

    if kind == 'actions':
        rows = await client.action_items(limit=25)
        open_items = [r for r in rows if not r.get('completed')]
        # Newest first: an old task the user has ignored for weeks is the least
        # useful thing to put in front of them.
        open_items.sort(key=lambda r: str(r.get('created_at') or ''), reverse=True)
        lines = [str(r.get('description', '')).strip() for r in open_items if r.get('description')]
        return _format(lines, 'Nothing open right now.', limit=4)

    if kind == 'conversations':
        window = _date_window(question)
        payload = {'query': question, 'limit': 3, 'include_transcript': False, **window}
        # The tool reports `is_error` for an empty result as well as a real
        # failure. Treating "nothing that day" as a failure sent the request down
        # the 6s agent path to be told the same thing.
        text = await _search_or_empty(client, 'conversations/search', payload)
        compact = _compact_conversations(text)
        if compact:
            return compact
        if window:
            return 'Nothing recorded for that period.'
        return 'Nothing in your conversations about that.'

    # Default: memories only.
    #
    # There used to be a conversation fallback here for when memory recall was
    # thin, and it actively made answers worse. "Who is the president of the USA"
    # returned a conversation about wallpapers -- and a word-overlap guard could
    # not catch it, because that transcript really does contain both "president"
    # and "USA" somewhere. The deeper issue is that such a question is not a
    # memory question at all: answering it needs world knowledge, which this path
    # has no LLM for. Admitting that beats confidently returning something
    # unrelated.
    memories_text = await _search_or_empty(client, 'memories/search', {'query': question, 'limit': 8})
    lines = _clean_bullets(memories_text)

    if lines:
        return _format(lines, '', limit=3)

    return "Nothing in your memories about that."
