"""External material, found by the reader's own interests and ranked against them.

Search queries are the learned interest topics, not a static feed list. That is
the whole difference between this and an RSS reader: the topics move when the
reader's work moves, without anyone editing a config file.
"""

import logging
from datetime import date, timedelta

from models.paper import Claim, InterestProfile, NewsLine, Provenance, SourceHealth, SourceRef
from utils.log_sanitizer import sanitize
from utils.retrieval.tools.perplexity_tools import perplexity_web_search_tool

from .arxiv import fetch_papers

logger = logging.getLogger(__name__)

# How many interests drive searches. Beyond the top few the queries stop being
# about what the reader is actually doing this fortnight.
MAX_SEARCH_TOPICS = 4

PAPER_LOOKBACK_DAYS = 4
MAX_PAPER_CANDIDATES = 40


def paper_candidates(profile: InterestProfile, day: date) -> tuple[list, SourceHealth]:
    """arXiv candidates for the reader's top interests."""
    if not profile.is_usable:
        return [], SourceHealth(source='arxiv', ok=True, note='no interest profile to search with')

    queries = [interest.topic for interest in profile.interests[:MAX_SEARCH_TOPICS]]
    since = day - timedelta(days=PAPER_LOOKBACK_DAYS)
    try:
        return fetch_papers(queries, since, limit=MAX_PAPER_CANDIDATES)
    except Exception as e:  # noqa: BLE001 — the section is optional, the edition is not.
        logger.warning('paper: arxiv discovery failed: %s', sanitize(str(e)))
        return [], SourceHealth(source='arxiv', ok=False, note=sanitize(str(e))[:200])


async def web_candidates(profile: InterestProfile) -> tuple[list[NewsLine], SourceHealth]:
    """Recent news and shipped tools for the reader's top interests.

    Perplexity returns prose with citations. We keep it as a claim carrying that
    citation text rather than restating it as fact, because the edition's rule
    is that anything about the outside world names where it came from.
    """
    if not profile.is_usable:
        return [], SourceHealth(source='web', ok=True, note='no interest profile to search with')

    lines: list[NewsLine] = []
    attempted = 0

    for interest in profile.interests[:MAX_SEARCH_TOPICS]:
        attempted += 1
        query = f'latest news and newly shipped tools in the last 3 days about {interest.topic}'
        try:
            # A @tool-decorated BaseTool, not a plain coroutine — calling it
            # directly raises at runtime rather than searching.
            result = await perplexity_web_search_tool.ainvoke({'query': query})
        except Exception as e:  # noqa: BLE001
            logger.warning('paper: web search failed for %r: %s', interest.topic, sanitize(str(e)))
            continue
        text = (result or '').strip()
        if not text or text.lower().startswith('error'):
            continue
        lines.append(
            NewsLine(
                category=interest.topic,
                claim=Claim(
                    text=text,
                    sources=[SourceRef(name='Perplexity web search')],
                    provenance=Provenance.REPORTED,
                ),
            )
        )

    return lines, SourceHealth(
        source='web',
        ok=True,
        fetched=attempted,
        kept=len(lines),
        note='' if lines else 'no usable web results',
    )
