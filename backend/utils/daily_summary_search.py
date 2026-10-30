"""Plain-text search over a user's stored daily summaries (recaps).

No index and no vector search: callers pass a bounded, newest-first window of
summary documents and this module keeps the ones whose readable text contains
every whitespace-separated query term, case-insensitively.
"""

from typing import Any, Dict, Iterable, List, Mapping

# The most recent summaries scanned per search. One summary per day, so this is
# roughly a year of recaps.
DAILY_SUMMARY_SEARCH_WINDOW = 365

# Top-level string fields a person reads on a recap.
_TEXT_FIELDS = ('headline', 'overview')
# List fields whose items are objects carrying readable strings.
_LIST_TEXT_FIELDS: Dict[str, tuple[str, ...]] = {
    'highlights': ('topic', 'summary'),
    'action_items': ('description',),
    'unresolved_questions': ('question',),
    'decisions_made': ('decision',),
    'knowledge_nuggets': ('insight',),
    'memories_learned': ('content',),
    'locations': ('address',),
}


def query_terms(query: str) -> List[str]:
    """Lower-cased, whitespace-separated terms; empty when the query is blank."""
    return [term.casefold() for term in query.split() if term]


def daily_summary_search_text(summary: Mapping[str, Any]) -> str:
    """The recap's human-readable text, lower-cased and newline-joined."""
    parts: List[str] = []
    for field in _TEXT_FIELDS:
        value = summary.get(field)
        if isinstance(value, str) and value:
            parts.append(value)
    for field, keys in _LIST_TEXT_FIELDS.items():
        items = summary.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value:
                    parts.append(value)
    return '\n'.join(parts).casefold()


def filter_daily_summaries(summaries: Iterable[Mapping[str, Any]], query: str, limit: int) -> List[Dict[str, Any]]:
    """Summaries whose text contains every query term, in input order, capped at ``limit``.

    A blank query matches nothing.
    """
    terms = query_terms(query)
    if not terms or limit <= 0:
        return []
    matches: List[Dict[str, Any]] = []
    for summary in summaries:
        text = daily_summary_search_text(summary)
        if all(term in text for term in terms):
            matches.append(dict(summary))
            if len(matches) >= limit:
                break
    return matches
