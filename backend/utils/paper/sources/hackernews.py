"""Hacker News — what the reader's field is talking about while they slept.

arXiv says what was *published*; this says what was *discussed*, which is the
other half of "did I miss anything". It needs no credentials, so it is one of
the few external sources that still works on an account with nothing connected.

Deliberately thin, for the same reason arxiv.py is. Titles are carried verbatim
and every line names the HN item it came from, so nothing here can invent a
story: the editorial layer only ever sees things real people actually posted.

One thing learned from the live API and encoded below: Algolia's text search is
typo-tolerant and reads more than the title, so a `query=rust` search returns
stories like "AI Just Created Viruses Not Found in Nature" ("just" is one edit
from "rust"). Printing that under the reader's *rust* interest would be a false
claim about why it is on their page, so a topic hit must also visibly mention
the topic before it is filed under it. The general query still catches the rest.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone

from models.paper import Claim, InterestProfile, NewsLine, Provenance, SourceHealth, SourceRef
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_API = 'https://hn.algolia.com/api/v1/search_by_date'
_TIMEOUT_SECONDS = 20

# A descriptive agent so Algolia can identify (and contact) heavy users.
_USER_AGENT = 'omi-paper/0.1 (+https://omi.me; daily reading brief)'

# Three days is the useful width: a story that peaked four days ago is not news
# to anyone, and a single day misses whatever broke while the reader was busy.
BUZZ_LOOKBACK_DAYS = 3

# Beyond the top few, the queries stop being about what the reader is actually
# working on this fortnight. Mirrors MAX_SEARCH_TOPICS in discovery.py.
MAX_TOPICS = 4

# Point floors, calibrated against live traffic. The general query wants only
# what genuinely landed; a topic query is already narrow, so a high floor there
# returns nothing at all on most days.
_FRONT_PAGE_MIN_POINTS = 50
_TOPIC_MIN_POINTS = 2
_SHOW_HN_MIN_POINTS = 3
_HITS_PER_QUERY = 20

# Categories for the two queries that are not tied to a learned interest.
FRONT_PAGE_CATEGORY = 'front page'
SHOW_HN_CATEGORY = 'show hn'

_ITEM_URL = 'https://news.ycombinator.com/item?id='
_SOURCE = 'Hacker News'

_WORD = re.compile(r'[a-z0-9]+')


def _epoch(day: date) -> int:
    """Midnight UTC on ``day`` as a unix timestamp.

    The window comes from the ``day`` argument and never from the clock, so a
    run for a past date fetches that date's buzz and the whole thing is testable.
    """
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def _mentions(topic: str, haystack: str) -> bool:
    """Does the text visibly contain a word from ``topic``?

    Word-anchored on purpose: substring matching files "trust" under *rust*, and
    a category the reader cannot see justified is exactly the kind of unearned
    claim this edition is built to avoid.
    """
    text = haystack.lower()
    for token in _WORD.findall(topic.lower()):
        if len(token) < 2:
            continue
        if re.search(rf'(?<![a-z0-9]){re.escape(token)}s?(?![a-z0-9])', text):
            return True
    return False


def _publisher(url: str) -> str:
    """The host a story points at, e.g. `404media.co` — derived, never invented."""
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith('www.') else host


def _to_line(hit: dict, category: str) -> NewsLine | None:
    """One Algolia hit to a NewsLine, or None if it is unusable.

    The title is carried through untouched. This module does zero model work, so
    what prints is what was posted.
    """
    object_id = str(hit.get('objectID') or '')
    title = (hit.get('title') or '').strip()
    if not object_id or not title:
        return None

    sources = [SourceRef(name=_SOURCE, url=f'{_ITEM_URL}{object_id}')]
    # Ask HN and Tell HN posts have no external link — `url` comes back null.
    story_url = (hit.get('url') or '').strip()
    if story_url:
        sources.append(SourceRef(name=_publisher(story_url) or 'link', url=story_url))

    return NewsLine(
        category=category,
        claim=Claim(text=title, sources=sources, provenance=Provenance.REPORTED),
    )


def _plan(profile: InterestProfile, window_start: int) -> list[tuple[str, dict]]:
    """The queries to run, most specific first.

    Order matters only for ties: when the same story comes back from several
    queries at the same score, the first attribution sticks, and "the reader
    works on this" is more use to them than "the front page liked it".
    """
    window = f'created_at_i>{window_start}'
    plan: list[tuple[str, dict]] = []

    for interest in profile.interests[:MAX_TOPICS]:
        topic = interest.topic.strip()
        if not topic:
            continue
        plan.append(
            (
                topic,
                {
                    'tags': 'story',
                    'query': topic,
                    'numericFilters': f'points>{_TOPIC_MIN_POINTS},{window}',
                    'hitsPerPage': _HITS_PER_QUERY,
                },
            )
        )

    # Show HN is the single most reliable place a newly shipped tool appears.
    plan.append(
        (
            SHOW_HN_CATEGORY,
            {
                'tags': 'show_hn',
                'numericFilters': f'points>{_SHOW_HN_MIN_POINTS},{window}',
                'hitsPerPage': _HITS_PER_QUERY,
            },
        )
    )
    plan.append(
        (
            FRONT_PAGE_CATEGORY,
            {
                'tags': 'story',
                'numericFilters': f'points>{_FRONT_PAGE_MIN_POINTS},{window}',
                'hitsPerPage': _HITS_PER_QUERY,
            },
        )
    )
    return plan


def _search(params: dict) -> list[dict]:
    request = urllib.request.Request(f'{_API}?{urllib.parse.urlencode(params)}', headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 — fixed host
        payload = json.loads(response.read())
    hits = payload.get('hits')
    return hits if isinstance(hits, list) else []


def fetch_buzz(profile: InterestProfile, day: date, limit: int = 12) -> tuple[list[NewsLine], SourceHealth]:
    """What Hacker News discussed in the three days up to ``day``, best first.

    Runs one query per top interest so the buzz is ranked toward the reader's own
    work, plus Show HN and a high-scoring general query so a big story outside
    their topics still reaches them.

    Never raises. A single failed query is recorded and the rest continue; only
    every query failing is an outage. That distinction is the point: a day where
    nothing cleared the bar and a day where the API was down look identical in
    the output, and the health record is the only thing that tells them apart.
    """
    window_start = _epoch(day - timedelta(days=BUZZ_LOOKBACK_DAYS))
    # Stories filed after the edition's own day are not this edition's news.
    window_end = _epoch(day + timedelta(days=1))

    plan = _plan(profile, window_start)
    # objectID -> (points, created_at_i, line). Highest points wins, because the
    # same story fetched twice can disagree and the later read is the truer one.
    best: dict[str, tuple[int, int, NewsLine]] = {}
    failures = 0
    fetched = 0

    for category, params in plan:
        try:
            hits = _search(params)
        except Exception as e:  # noqa: BLE001 — one bad query must not kill the brief
            # The query is a learned interest topic derived from private
            # conversations, so it does not go to the log either.
            logger.warning('paper: a hacker news query failed: %s', sanitize(str(e)))
            failures += 1
            continue

        is_topic = category not in (FRONT_PAGE_CATEGORY, SHOW_HN_CATEGORY)
        for hit in hits:
            fetched += 1
            created = hit.get('created_at_i')
            if not isinstance(created, int) or not window_start <= created < window_end:
                continue
            if is_topic and not _mentions(category, f'{hit.get("title") or ""} {hit.get("url") or ""}'):
                continue

            line = _to_line(hit, category)
            if line is None:
                continue
            # Bind once so the isinstance check narrows the value actually used.
            raw_points = hit.get('points')
            points: int = raw_points if isinstance(raw_points, int) else 0
            object_id = str(hit['objectID'])
            existing = best.get(object_id)
            if existing is None or points > existing[0]:
                best[object_id] = (points, created, line)

    ranked = sorted(best.values(), key=lambda entry: (entry[0], entry[1]), reverse=True)
    lines = [entry[2] for entry in ranked][:limit]

    every_query_failed = failures == len(plan)
    if every_query_failed:
        note = f'all {len(plan)} queries failed'
    elif failures:
        note = f'{failures}/{len(plan)} queries failed'
    elif not lines:
        note = 'searched fine — nothing cleared the bar'
    else:
        note = ''

    health = SourceHealth(
        source=_SOURCE,
        ok=not every_query_failed,
        fetched=fetched,
        kept=len(lines),
        note=note,
    )
    return lines, health
