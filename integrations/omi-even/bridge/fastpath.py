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

# Defined early: several module-level regexes below interpolate _MONTH_ALT,
# and module code runs top to bottom.
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_MONTH_ALT = '|'.join(_MONTHS)

# "Found 5 memories matching 'David Zhang':" -- restates the question, wasting a
# quarter of the screen.
_PREAMBLE_RE = re.compile(r'^Found\s+\d+\s+\w+\s+matching\s+.*?:\s*', re.IGNORECASE | re.DOTALL)

# "(relevance: 0.48, category: interesting, date: 2026-07-27)" -- debugging
# metadata, meaningless on a heads-up display.
_META_RE = re.compile(r'\s*\((?:relevance|category|date)[^)]*\)\s*$', re.IGNORECASE)
_RELEVANCE_RE = re.compile(r'relevance:\s*([0-9.]+)')

# Relevance is a weak signal here and was originally set far too high. Measured
# against the live account, genuinely useful memories score 0.22-0.48, so a 0.40
# floor was discarding most of the good ones. What actually separates signal from
# noise is the category (below), not the score, so this only rejects the truly
# random tail.
_MIN_RELEVANCE = 0.15

# The dominant failure in memory search: the desktop onboarding file scan writes
# one memory per indexed local file, and those crowd out real ones. Measured hits
# per 10 results -- pickleball 7/10 noise, burgers 9/10, "what I learned in July"
# 10/10, which is why that question answered "nothing".
#
# Filtering on `category: system` was the obvious move and is WRONG: `system` is
# the default bucket for extracted memories
# (`utils/memory_ingestion/adapters/typed_extraction_prompt.py:201`), so rejecting
# it discards real ones too. The backend's own cleanup keys on content instead --
# these patterns follow `backend/utils/memory/legacy_backfill.py:127` and
# `desktop/windows/src/renderer/src/lib/memoryCleanup.ts:20`.
_FILE_NOISE_RE = re.compile(
    r'(\b\d[\d,]*\s+local files indexed\b'
    r'|\bworks on a local project named\b'
    r"|\bthe user'?s? (local )?(documents|downloads|files|projects|repos(itories)?|folders)\b"
    r'|\ba recently modified local file\b'
    r'|^\s*focused on\b'
    r'|^\s*distracted on\b'
    r'|^\s*email from\b'
    r"|^\s*uses(\s+[\w&+()'-]+){1,4}\s*$)",
    re.IGNORECASE,
)

# The double anchor the desktop cleanup uses: a memory that merely mentions a
# project is real, but one that also carries a filesystem path is inventory.
_PATH_HINT_RE = re.compile(r'[~/\\]')
_LOCAL_INDEX_STEM_RE = re.compile(
    r"the user'?s? (local )?(projects?|files?|repos(itories)?|directories|folders|code(bases?)?)\b",
    re.IGNORECASE,
)


def _is_file_inventory(line: str) -> bool:
    """True for a memory that is really an entry from the local-file indexer."""
    if _FILE_NOISE_RE.search(line):
        return True
    return bool(_LOCAL_INDEX_STEM_RE.search(line) and _PATH_HINT_RE.search(line))

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
    # A named day ("on 4 July") is asking what happened, which lives in
    # conversations. Without this it fell through to a semantic memory search
    # with nothing constraining it to the day.
    if _explicit_date(question):
        return 'conversations'
    return 'memories'


# Screen capture files interface chrome into memories. Answering "what did I do
# on 4 July" with "- Show less" is what prompted this: a button label scraped off
# a page, stored as a fact, and returned as an answer.
_UI_CHROME = frozenset(
    {
        'show less', 'show more', 'see more', 'see all', 'read more', 'learn more',
        'click here', 'load more', 'view all', 'sign in', 'log in', 'sign up',
        'accept all', 'got it', 'ok', 'cancel', 'submit', 'continue', 'next',
        'back', 'close', 'done', 'menu', 'search', 'settings', 'home',
    }
)

# Fewer than this many characters cannot carry a fact worth a line of the display.
_MIN_FACT_CHARS = 15


def _is_junk(line: str) -> bool:
    """True for a retrieved line that is interface text rather than a fact."""
    stripped = line.strip().rstrip('.').strip().lower()
    if stripped in _UI_CHROME:
        return True
    if len(stripped) < _MIN_FACT_CHARS:
        return True
    # A "fact" with no verb-like structure and only one or two words is a label.
    return len(stripped.split()) < 3


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

        # Content first: a file-indexing artifact is noise at any relevance, and
        # it is the single biggest source of useless answers.
        if _is_file_inventory(line):
            continue

        match = _RELEVANCE_RE.search(line)
        score = float(match.group(1)) if match else 1.0
        if score < min_relevance:
            continue

        line = _META_RE.sub('', line).strip().rstrip(',;')
        if line and not _is_junk(line):
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


def _target_days(question: str) -> set[str]:
    """The calendar days a question is asking about, as 'DD Mon YYYY' strings.

    Matches the format the search results print ("23 Jul 2026 at 16:08"), so the
    filtering can happen here rather than as a server-side window -- which costs
    13.5s against 3.1s without.
    """
    from datetime import datetime, timedelta

    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).date()

    def fmt(day) -> str:
        return f'{day.day:02d} {day.strftime("%b")} {day.year}'

    q = question.lower()
    if 'yesterday' in q:
        return {fmt(today - timedelta(days=1))}
    if 'today' in q or 'this morning' in q:
        return {fmt(today)}
    if 'this week' in q:
        return {fmt(today - timedelta(days=n)) for n in range(8)}
    if 'last week' in q:
        return {fmt(today - timedelta(days=n)) for n in range(7, 15)}

    window = _explicit_date(question)
    if window:
        stamp = datetime.fromisoformat(window['start_date']).date()
        return {fmt(stamp)}
    return set()


# A bare month name -- "everything I learned for July" -- with no day attached.
_BARE_MONTH_RE = re.compile(rf'\b(?:in|for|during|about|over)\s+({_MONTH_ALT})\w*\b', re.IGNORECASE)


def _explicit_month(question: str) -> tuple[int, int] | None:
    """(year, month) for a month named without a day.

    "Tell me everything I learned for July" carries a clear time reference that
    the day-level parser cannot see, so it fell through to a semantic memory
    search and answered "Nothing in your memories about that."
    """
    from datetime import datetime

    if _explicit_date(question):
        return None  # a full date already handles this

    match = _BARE_MONTH_RE.search(question)
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower()[:3])
    if not month:
        return None

    today = datetime.now().astimezone().date()
    year = today.year if month <= today.month else today.year - 1
    return year, month


# "23 Jul 2026 at 16:08 America/New_York (Technology)" begins each result block.
_CONV_DATE_RE = re.compile(r'^\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b')


def _blocks_matching_days(result_text: str, days: set[str]) -> str:
    """Keep only the result blocks whose date line falls on one of `days`."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in result_text.splitlines():
        if re.match(r'^\s*Conversation\s*#\d+', line, re.IGNORECASE):
            if current:
                blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    kept: list[str] = []
    for block in blocks:
        text = '\n'.join(block)
        stamp = None
        for line in block:
            found = _CONV_DATE_RE.match(line.strip())
            if found:
                stamp = found.group(1)
                break
        if stamp and any(stamp.lstrip('0') == day.lstrip('0') for day in days):
            kept.append(text)
    return '\n'.join(kept)


def _conversation_titles(result_text: str, limit: int = 3) -> list[str]:
    """The one-line summary each conversation block leads with.

    A conversation's title is its most information-dense line -- "A group orders
    fast food and discusses what they got, including burgers, fries, sauces" --
    so it is what belongs next to a memory bullet.
    """
    body = _PREAMBLE_RE.sub('', result_text or '').strip()
    if _NO_RESULTS_RE.match(body):
        return []

    titles: list[str] = []
    expecting = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if re.match(r'^\s*Conversation\s*#\d+', line, re.IGNORECASE):
            expecting = True  # the date line comes next, then the title
            continue
        if not line or _CONV_NOISE_RE.match(line):
            continue
        if expecting:
            candidate = line.lstrip('#-').strip()
            if candidate and not _is_junk(candidate) and candidate not in titles:
                titles.append(candidate)
            expecting = False
        if len(titles) >= limit:
            break
    return titles


def _compact_conversations(result_text: str, limit: int = 4, only_days: set[str] | None = None) -> str:
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
    if only_days:
        body = _blocks_matching_days(body, only_days)
        if not body.strip():
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


# "4 July", "July 4", "4th of July", "on Jul 4th" -- both orders, optional
# ordinal suffix, optional "of".
# `\w*` after each month prefix absorbs the rest of the full name. Without it on
# BOTH branches, "4 July" fails to match while "July 4" succeeds: the alternation
# matches "jul" and then demands a word boundary that the "y" denies.
_EXPLICIT_DATE_RE = re.compile(
    rf'\b(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\w*'
    rf'|({_MONTH_ALT})\w*\s+(\d{{1,2}})(?:st|nd|rd|th)?)\b',
    re.IGNORECASE,
)


def _explicit_date(question: str) -> dict[str, str] | None:
    """Bounds for a named calendar day, e.g. "what did I do on 4 July".

    Without this, a dated question falls through to a semantic memory search --
    "What did I do on 4 July that was not work?" answered "- Show less", a
    fragment of UI chrome, because nothing constrained it to that day.

    A month later than today is read as last year, since people ask about days
    that have happened.
    """
    from datetime import datetime, time, timedelta

    match = _EXPLICIT_DATE_RE.search(question)
    if not match:
        return None

    day_str, month_str = (match.group(1), match.group(2)) if match.group(1) else (match.group(4), match.group(3))
    try:
        day = int(day_str)
    except (TypeError, ValueError):
        return None
    month = _MONTHS.get(month_str.lower()[:3]) if month_str else None
    if not month or not 1 <= day <= 31:
        return None

    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).date()
    year = today.year
    try:
        target = today.replace(year=year, month=month, day=day)
    except ValueError:
        return None  # e.g. 31 February
    if target > today:
        target = target.replace(year=year - 1)

    return {
        'start_date': datetime.combine(target, time.min, tzinfo=local_tz).isoformat(),
        'end_date': datetime.combine(
            target + timedelta(days=1) - timedelta(seconds=1), time.max.replace(microsecond=0), tzinfo=local_tz
        ).replace(hour=23, minute=59, second=59).isoformat(),
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
    explicit = _explicit_date(question)
    return explicit or {}


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


def _is_too_vague(question: str) -> bool:
    """True when there is not enough in the question to search on.

    Speech-to-text produces fragments -- a cough, a half-word, "ping" -- and
    vector search answers every one of them with its nearest neighbour. Asking
    "ping" surfaced an unrelated obscenity from an old transcript. On a display
    worn on your face, returning nothing is strictly better than returning
    whatever happened to be closest.
    """
    terms = {w for w in re.findall(r'[a-z0-9]+', question.lower()) if w not in _STOPWORDS and len(w) > 2}
    if not terms:
        return True
    # A single short token is far more often a mis-transcription than a query.
    return len(terms) == 1 and max(len(t) for t in terms) <= 4


async def gather_facts(client, question: str) -> list[str]:
    """The retrieved lines behind an answer, best first.

    Split out from `fast_answer` so the same material can either be shown as-is
    or handed to a composer -- see `compose.py`, which turns these into prose
    using Omi's own LLM.
    """
    kind = _classify(question)
    if kind == 'actions':
        rows = await client.action_items(limit=25)
        open_items = [r for r in rows if not r.get('completed')]
        open_items.sort(key=lambda r: str(r.get('created_at') or ''), reverse=True)
        return [str(r.get('description', '')).strip() for r in open_items if r.get('description')][:8]

    if kind == 'conversations':
        target = _target_days(question)
        text = await _search_or_empty(
            client, 'conversations/search', {'query': question, 'limit': 8, 'include_transcript': False}
        )
        compact = _compact_conversations(text, limit=8, only_days=target)
        return [line.lstrip('-').strip() for line in compact.splitlines() if line.strip()]

    memories_text, conversations_text = await asyncio.gather(
        _search_or_empty(client, 'memories/search', {'query': question, 'limit': 10}),
        _search_or_empty(
            client, 'conversations/search', {'query': question, 'limit': 4, 'include_transcript': False}
        ),
    )
    facts = _clean_bullets(memories_text)
    if _looks_relevant(question, conversations_text):
        for extra in _conversation_titles(conversations_text):
            if extra not in facts:
                facts.append(extra)
    return facts[:10]


async def fast_answer(client, question: str) -> str:
    """Answer from Omi's stores directly, in roughly two seconds."""
    kind = _classify(question)

    # Only a question with no recognisable intent can be a stray syllable. Asking
    # this before classifying rejected "What did I do on 4 July?", because
    # stopwords and the bare digit leave "july" as the single content word --
    # which looks exactly like a mis-transcription and is not one.
    if kind == 'memories' and _is_too_vague(question):
        log.info('fastpath: question too vague to search on (%.40r)', question)
        return 'Ask me something about your day, your people, or your tasks.'

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
        target = _target_days(question)
        # Deliberately NOT passing start_date/end_date. Measured on the live
        # account, the same query costs 13.5s with a server-side date window and
        # 3.1s without -- and 13.5s is past the timeout this whole path exists to
        # beat. Fetching wider and filtering by date here is the cheaper way to
        # get the same correctness.
        payload = {'query': question, 'limit': 8, 'include_transcript': False}
        text = await _search_or_empty(client, 'conversations/search', payload)
        compact = _compact_conversations(text, only_days=target)
        if compact:
            return compact
        if target:
            return 'Nothing recorded for that day.'
        return 'Nothing in your conversations about that.'

    # Both stores, in parallel, because they hold different things and neither is
    # sufficient alone. Memories carry standing facts ("David is a colleague");
    # conversations carry what actually happened ("a group orders burgers, fries,
    # sauces"). Searching only memories answered "burgers" with a downloads-folder
    # path, while conversations had the real thing. Running them together costs
    # the slower of the two rather than their sum.
    memories_text, conversations_text = await asyncio.gather(
        _search_or_empty(client, 'memories/search', {'query': question, 'limit': 10}),
        _search_or_empty(
            client, 'conversations/search', {'query': question, 'limit': 4, 'include_transcript': False}
        ),
    )

    lines = _clean_bullets(memories_text)

    # Conversations are only merged in when they clearly concern the question.
    # Unguarded, this search always returns its nearest neighbour, which is how
    # "who is the president of the USA" once answered with a chat about
    # wallpapers -- a transcript that genuinely contains both words.
    if _looks_relevant(question, conversations_text):
        for extra in _conversation_titles(conversations_text):
            if extra not in lines:
                lines.append(extra)

    if lines:
        return _format(lines, '', limit=4)

    return 'Nothing in your memories about that.'
