"""Keyword retrieval leg for legacy-cohort memory search (proper-name recall).

Pure vector search loses the exact-token case. Embedding a bare proper name
("Sophia") against a short structural fact ("Sophia — in your "AV Founders" group")
is the worst case for kNN recall: there is almost no shared semantic surface for the
embedding to latch onto, so the fact the user literally asked for never enters top-k.
Conversation search hit the same class of miss and fixed it by adding a keyword leg
merged ahead of the vector ids (issue #5072— see
:func:`utils.conversations.search.keyword_search_conversation_ids` and
:func:`utils.conversations.search.merge_conversation_search_ids`). This module is that
same shape for memories: **ids only, fail-open to ``[]``, merged keyword-first by the
caller**.

The *source* differs because it has to. Only the ``conversations`` collection and the
canonical ``canonical_memory_atoms`` collection are in Typesense; legacy memories — the
default cohort, and the one every account starts on — are indexed nowhere but Firestore.
So this leg reads a bounded window of the same collection ``GET /v3/memories`` already
reads and matches whole words in process.

It stays a **recall addition rather than a ranking change**: a memory is only promoted
when it matches a *selective* term — one occurring in at most ``SELECTIVE_DF_RATIO`` of
the scanned window. Names, acronyms and rare nouns are selective; "what", "about" and
"work" are not. A query with no selective term returns ``[]`` and search behaves exactly
as it did before this leg existed, which is what keeps the unfiltered legacy contract
intact.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

import database.memories as memory_db
from utils.retrieval.hybrid import bm25_scores

logger = logging.getLogger(__name__)

SCAN_LIMIT_ENV = "MEMORY_KEYWORD_SCAN_LIMIT"
# One bounded read per keyword search. `get_memories_text` already reads up to 5000
# memories in a single chat tool call, so a scan of this size is within the cost this
# path already carries; the env override exists so the bound can be tuned without a deploy.
DEFAULT_SCAN_LIMIT = 1000
MAX_SCAN_LIMIT = 5000
# Two-character tokens are almost never the selective term in a "who is X" query and
# they inflate the candidate set, so they are dropped before matching.
MIN_TERM_LENGTH = 3
# A term occurring in more than this share of the scanned window is a common word, not a
# name. Matching one is not evidence, so it never promotes a memory above the vector leg.
SELECTIVE_DF_RATIO = 0.2

_TERM_RE = re.compile(r"[a-z0-9]+")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _terms(text: str) -> List[str]:
    """Lowercase alphanumeric whole-word tokens of at least ``MIN_TERM_LENGTH`` chars."""
    return [term for term in _TERM_RE.findall((text or "").lower()) if len(term) >= MIN_TERM_LENGTH]


def default_scan_limit() -> int:
    """How many memories one keyword search may read, from env with a hard ceiling."""
    try:
        value = int(os.getenv(SCAN_LIMIT_ENV, "") or DEFAULT_SCAN_LIMIT)
    except (TypeError, ValueError):
        return DEFAULT_SCAN_LIMIT
    return max(1, min(value, MAX_SCAN_LIMIT))


def _document_text(memory: Dict[str, Any]) -> str:
    """Searchable text for one memory: its content plus its tags.

    Tags are included because they carry the durable person provenance
    (``person:<person_id>``) and the writer cohort marker, so a query naming a tag value
    finds the fact even when the content phrasing differs.
    """
    tags = memory.get('tags')
    tag_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
    content = memory.get('content') or ''
    return f"{content} {tag_text}".strip()


def _created_at(memory: Dict[str, Any]) -> datetime:
    created_at = memory.get('created_at')
    if not isinstance(created_at, datetime):
        return _EPOCH
    return created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)


class _Candidate:
    __slots__ = ("memory_id", "text", "terms", "created_at")

    def __init__(self, memory_id: str, text: str, terms: Set[str], created_at: datetime):
        self.memory_id = memory_id
        self.text = text
        self.terms = terms
        self.created_at = created_at


def selective_terms(query_terms: List[str], candidates_terms: List[Set[str]]) -> Set[str]:
    """Query terms rare enough in the scanned window to count as evidence of a match.

    Pure so the selectivity rule — the thing that keeps this leg from reordering ordinary
    searches — is assertable without Firestore.
    """
    if not candidates_terms:
        return set()
    ceiling = max(1, int(len(candidates_terms) * SELECTIVE_DF_RATIO))
    selected: Set[str] = set()
    for term in query_terms:
        frequency = sum(1 for terms in candidates_terms if term in terms)
        if 0 < frequency <= ceiling:
            selected.add(term)
    return selected


def keyword_search_legacy_memory_ids(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    scan_limit: int | None = None,
    firestore_client: Any = None,
) -> List[str]:
    """Legacy-cohort keyword search returning only memory ids, for hybrid retrieval.

    Fail-open: any read or matching error returns ``[]`` so the caller falls back to
    vector-only results, exactly like the conversation leg.
    """
    query_terms = list(dict.fromkeys(_terms(query)))
    if not query_terms:
        return []

    capped_limit = max(1, min(limit, 50))
    window = max(1, scan_limit if scan_limit is not None else default_scan_limit())

    try:
        memories = memory_db.get_memories(uid, limit=window, offset=0, firestore_client=firestore_client)

        candidates: List[_Candidate] = []
        for memory in memories:
            if memory.get('is_locked', False):
                continue
            memory_id = memory.get('id')
            if not memory_id:
                continue
            text = _document_text(memory)
            terms = set(_terms(text))
            if not terms:
                continue
            candidates.append(_Candidate(str(memory_id), text, terms, _created_at(memory)))

        selected = selective_terms(query_terms, [candidate.terms for candidate in candidates])
        if not selected:
            return []

        matched = [candidate for candidate in candidates if candidate.terms & selected]
        if not matched:
            return []

        scores = bm25_scores(query, [candidate.text for candidate in matched])
        ranked: List[Tuple[float, datetime, str]] = [
            (scores[index], candidate.created_at, candidate.memory_id) for index, candidate in enumerate(matched)
        ]
        ranked.sort(reverse=True)
        return [memory_id for _score, _created, memory_id in ranked[:capped_limit]]
    except Exception as exc:
        logger.warning(
            "keyword_search_legacy_memory_ids failed for uid=%s, falling back to vector-only: %s",
            uid,
            exc,
        )
        return []
