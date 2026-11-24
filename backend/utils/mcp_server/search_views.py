"""How hosted MCP search finds conversations, and says how it found them.

``search_conversations`` asks two indexes for every query: summary vectors
(meaning) and the keyword index over titles and overviews (exact words). Each
result says which of them, and whether its transcript holds the words
(``match_basis``), and the response names every index that could not be asked
(``search_coverage``). A summary hit is never presented as quoted evidence:
only ``match_snippets`` quote the transcript.

``search_transcripts`` finds literal words in saved transcripts without any
index, one bounded page of records per call, and returns the segment index of
each hit so the agent can read around it with ``get_conversation_by_id``
``offset``.
"""

from typing import Any, Dict, Iterable, List, Sequence, Tuple

SUMMARY = 'summary'
KEYWORD = 'keyword'
TRANSCRIPT = 'transcript'
MATCH_BASES = (SUMMARY, KEYWORD, TRANSCRIPT)

TRANSCRIPT_QUERY_MAX_CHARS = 200
TRANSCRIPT_SEARCH_DEFAULT_LIMIT = 10
TRANSCRIPT_SEARCH_MAX_LIMIT = 20
TRANSCRIPT_HITS_PER_CONVERSATION = 5
TRANSCRIPT_HIT_MAX_CHARS = 400
TRANSCRIPT_SCAN_SECONDS = 4.0
TRANSCRIPT_SCAN_DOCUMENTS = 50


def merge_search_ids(vector_ids: Sequence[str], keyword_ids: Sequence[str], limit: int) -> List[str]:
    """Rank ids both indexes found first, then alternate summary-only and keyword-only hits.

    Each index keeps its own order. Alternating means a page full of summary hits
    still leaves room for an exact title or overview match, and the reverse.
    """
    vector = list(dict.fromkeys(str(i) for i in vector_ids if str(i).strip()))
    keyword = list(dict.fromkeys(str(i) for i in keyword_ids if str(i).strip()))
    in_keyword = set(keyword)
    both = [cid for cid in vector if cid in in_keyword]
    in_both = set(both)
    only_vector = [cid for cid in vector if cid not in in_both]
    only_keyword = [cid for cid in keyword if cid not in in_both]
    merged = list(both)
    for index in range(max(len(only_vector), len(only_keyword))):
        merged.extend(group[index] for group in (only_vector, only_keyword) if index < len(group))
    return merged[: max(0, limit)]


def match_basis(cid: str, vector_ids: Iterable[str], keyword_ids: Iterable[str], has_snippets: bool) -> List[str]:
    found = {SUMMARY: cid in set(vector_ids), KEYWORD: cid in set(keyword_ids), TRANSCRIPT: has_snippets}
    return [basis for basis in MATCH_BASES if found[basis]]


def search_coverage(*, vectors_ok: bool, keyword_ok: bool) -> Tuple[str, List[str]]:
    """The indexes that answered, as a stable label plus the names of any that did not."""
    unavailable = [name for name, ok in (('summary_vectors', vectors_ok), ('keyword', keyword_ok)) if not ok]
    if not unavailable:
        return 'summary_vectors_and_keyword', []
    if len(unavailable) == 2:
        return 'none', unavailable
    return ('keyword_only' if not vectors_ok else 'summary_vectors_only'), unavailable


def add_segment_indexes(snippets: List[Dict[str, Any]], segments: Any) -> List[Dict[str, Any]]:
    """Give each snippet the segment index ``get_conversation_by_id`` ``offset`` reads from."""
    rows = [s for s in segments if isinstance(s, dict)] if isinstance(segments, list) else []
    index_of = {str(s['id']): i for i, s in enumerate(rows) if s.get('id') is not None}
    for snippet in snippets:
        sid = snippet.get('segment_id')
        # Legacy segments have no id: fall back to the matcher's position in the same dict list.
        position = snippet.pop('_position', None)
        snippet['segment_index'] = index_of.get(str(sid)) if sid is not None else position
    return snippets


SNIPPET_SEGMENT_INDEX_OUTPUT: Dict[str, Any] = {
    'type': ['integer', 'null'],
    'description': 'Read around this hit with get_conversation_by_id offset (a few segments earlier for context)',
}
MATCH_BASIS_OUTPUT: Dict[str, Any] = {
    'type': 'array',
    'items': {'type': 'string', 'enum': list(MATCH_BASES)},
    'description': 'summary: the summary is about the query (meaning, not quoted words). keyword: the title or '
    'overview has the words. transcript: match_snippets quote the words from the transcript.',
}
UNAVAILABLE_INDEXES_OUTPUT: Dict[str, Any] = {
    'type': 'array',
    'items': {'type': 'string'},
    'description': 'Indexes that could not be searched for this call; results may be missing',
}

SEARCH_TRANSCRIPTS_INPUT: Dict[str, Any] = {
    'type': 'object',
    'properties': {
        'query': {
            'type': 'string',
            'minLength': 1,
            'maxLength': TRANSCRIPT_QUERY_MAX_CHARS,
            'description': 'Literal words or a short phrase, as they would be said (not a question)',
        },
        'conversation_id': {
            'type': 'string',
            'description': 'Search only this whole conversation (no dates or cursor)',
        },
        'start_date': {'type': 'string', 'description': 'created_at on/after midnight in timezone (YYYY-MM-DD)'},
        'end_date': {'type': 'string', 'description': 'created_at through the end of this day (YYYY-MM-DD)'},
        'limit': {
            'type': 'integer',
            'description': 'Maximum conversations with hits to return',
            'default': TRANSCRIPT_SEARCH_DEFAULT_LIMIT,
            'minimum': 1,
            'maximum': TRANSCRIPT_SEARCH_MAX_LIMIT,
        },
        'cursor': {
            'type': 'string',
            'description': 'next_cursor from the previous call with the same query and dates (not with conversation_id)',
        },
    },
    'required': ['query'],
}
_HIT_OUTPUT: Dict[str, Any] = {
    'type': 'object',
    'properties': {
        'segment_index': SNIPPET_SEGMENT_INDEX_OUTPUT,
        'segment_id': {'type': ['string', 'null']},
        'start': {'type': ['number', 'null']},
        'end': {'type': ['number', 'null']},
        'speaker_key': {'type': 'string'},
        'speaker_label': {'type': 'string'},
        'text': {'type': 'string', 'description': 'The matching line, with the speaker'},
    },
}
SEARCH_TRANSCRIPTS_OUTPUT_FIELDS: Dict[str, Any] = {
    'matches': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'conversation': {'type': 'object', 'description': 'id, title and times of the conversation'},
                'hits': {'type': 'array', 'items': _HIT_OUTPUT},
                'more_hits': {'type': 'boolean', 'description': 'The conversation has more hits than listed'},
            },
        },
    },
    'examined': {'type': 'integer', 'description': 'Conversations examined by this call'},
    'complete': {'type': 'boolean', 'description': 'True when the scan reached the end of the window (see unreadable)'},
    'unreadable': {'type': 'integer', 'description': 'Conversations that could not be read; coverage is partial'},
    'next_cursor': {'type': ['string', 'null']},
    'search_coverage': {'type': 'string'},
}
