"""Transcript evidence for conversation search (MCP #6621 + in-app find/play).

Conversation indexes (Typesense title/overview, summary vectors) miss phrases that
live only in transcript segments. This module:

1. Merges summary/Typesense hits with transcript-chunk vector hits (when indexed).
2. Builds grep-style transcript snippets from hydrated Firestore segments (with
   start/end for client seek-to-moment).
Chunk indexing is optional (`TRANSCRIPT_CHUNK_INDEXING_ENABLED`); snippet extraction
always runs on returned conversations so clients get evidence even for summary hits.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence

from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Letters/digits in any script (not ASCII-only) so multi-term non-English queries
# can still extract lexical snippets after a semantic transcript hit.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_MAX_SNIPPET_CHARS = 2000


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold()


def _query_terms(query: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(_normalize_text(query)) if len(t) >= 2]


def _segment_matches(text: str, query_norm: str, terms: Sequence[str]) -> bool:
    hay = _normalize_text(text)
    if not hay:
        return False
    if query_norm and query_norm in hay:
        return True
    # Prefer multi-term: require every token when the query has 2+ terms so
    # "budget review" does not match every segment that merely says "review".
    if len(terms) >= 2:
        return all(t in hay for t in terms)
    return bool(terms) and terms[0] in hay


def _seconds_to_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value) * 1000)
    except (TypeError, ValueError):
        return None


def _as_segment_dicts(segments: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in segments:
        if isinstance(s, dict):
            out.append(s)
    return out


def build_transcript_match_snippets(
    segments: Sequence[Any],
    query: str,
    *,
    context_neighbors: int = 1,
    max_snippets: int = 3,
    max_chars: int = _MAX_SNIPPET_CHARS,
) -> List[Dict[str, Any]]:
    """Return grep-style transcript snippets for segments matching ``query``.

    Each snippet includes surrounding neighbor lines (``context_neighbors``),
    segment id when present, and start/end in both seconds and milliseconds.
    """
    query_norm = _normalize_text((query or "").strip())
    terms = _query_terms(query)
    if not query_norm and not terms:
        return []

    segs = _as_segment_dicts(segments)
    if not segs:
        return []

    match_idxs = [i for i, seg in enumerate(segs) if _segment_matches(str(seg.get("text") or ""), query_norm, terms)]
    if not match_idxs:
        return []

    snippets: List[Dict[str, Any]] = []
    used_centers: set[int] = set()
    for center in match_idxs:
        if len(snippets) >= max_snippets:
            break
        if center in used_centers:
            continue
        lo = max(0, center - max(0, context_neighbors))
        hi = min(len(segs), center + max(0, context_neighbors) + 1)
        window = segs[lo:hi]
        used_centers.update(range(lo, hi))

        lines: List[str] = []
        for seg in window:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            speaker = seg.get("speaker_id")
            prefix = f"Speaker {speaker}: " if speaker is not None else ""
            if seg.get("is_user"):
                prefix = "User: "
            lines.append(f"{prefix}{text}")
        if not lines:
            continue

        hit = segs[center]
        start = hit.get("start")
        end = hit.get("end")
        try:
            start_f = float(start) if start is not None else None
        except (TypeError, ValueError):
            start_f = None
        try:
            end_f = float(end) if end is not None else None
        except (TypeError, ValueError):
            end_f = None

        snippet_text = "\n".join(lines)
        max_chars = max(1, min(max_chars, _MAX_SNIPPET_CHARS))
        if len(snippet_text) > max_chars:
            if max_chars > 3:
                snippet_text = snippet_text[: max_chars - 3].rstrip() + "..."
            else:
                snippet_text = snippet_text[:max_chars]
        snippets.append(
            {
                "text": snippet_text,
                "segment_id": hit.get("id"),
                "start": start_f,
                "end": end_f,
                "start_ms": _seconds_to_ms(start_f),
                "end_ms": _seconds_to_ms(end_f),
                "speaker_id": hit.get("speaker_id"),
            }
        )
    return snippets


def merge_summary_and_transcript_ids(
    transcript_conversation_ids: Sequence[str],
    summary_vector_ids: Sequence[str],
    limit: int,
) -> List[str]:
    """Prefer transcript-chunk hits, then summary-vector hits; stable unique, capped."""
    limit = max(0, limit)
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(transcript_conversation_ids) + list(summary_vector_ids):
        cid = str(raw).strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= limit:
            break
    return out


def search_transcript_conversation_ids(
    uid: str,
    query: str,
    *,
    limit: int,
    starts_at: Optional[int] = None,
    ends_at: Optional[int] = None,
    search_transcript_chunks: Callable[..., Any],
) -> List[str]:
    """Fail-open transcript-chunk → conversation ids (empty when index off / errors)."""
    limit = max(1, min(int(limit or 10), 250))
    if not (query or "").strip():
        return []
    transcript_ids: List[str] = []
    try:
        # Over-fetch chunks so multiple hits in one conversation still leave room for others.
        chunk_limit = min(max(limit * 3, limit), 60)
        rows_raw: Any = search_transcript_chunks(uid, query, limit=chunk_limit, starts_at=starts_at, ends_at=ends_at)
        rows: List[Any] = rows_raw if isinstance(rows_raw, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = row.get("conversation_id")
            if cid:
                transcript_ids.append(str(cid))
    except Exception as e:  # noqa: BLE001 - transcript index is optional / best-effort
        logger.warning(
            "conversation search: transcript chunk search failed uid=%s: %s",
            uid,
            sanitize(str(e)),
        )
    return merge_summary_and_transcript_ids(transcript_ids, [], limit)


def resolve_mcp_conversation_search_ids(
    uid: str,
    query: str,
    *,
    limit: int,
    starts_at: Optional[int] = None,
    ends_at: Optional[int] = None,
    query_vectors: Callable[..., List[str]],
    search_transcript_chunks: Callable[..., Any],
    embed_query: Optional[Callable[[str], List[float]]] = None,
) -> List[str]:
    """Combine summary-vector search with transcript-chunk search (fail-open on chunks).

    When ``embed_query`` is provided, the query is embedded once and the vector is
    shared across both Pinecone namespace lookups.
    """
    limit = max(1, min(int(limit or 10), 250))
    shared_vector: Optional[List[float]] = embed_query(query) if embed_query is not None else None
    vector_kw: Dict[str, Any] = {"query_vector": shared_vector} if shared_vector is not None else {}
    summary_ids = query_vectors(query, uid, starts_at=starts_at, ends_at=ends_at, k=limit, **vector_kw) or []
    transcript_ids: List[str] = []
    try:
        chunk_limit = min(max(limit * 3, limit), 60)
        rows_raw: Any = search_transcript_chunks(
            uid, query, limit=chunk_limit, starts_at=starts_at, ends_at=ends_at, **vector_kw
        )
        rows: List[Any] = rows_raw if isinstance(rows_raw, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("conversation_id"):
                transcript_ids.append(str(row["conversation_id"]))
    except Exception as e:  # noqa: BLE001 - transcript index is optional / best-effort
        logger.warning("mcp conversation search: transcript chunk search failed uid=%s: %s", uid, sanitize(str(e)))
    return merge_summary_and_transcript_ids(transcript_ids, summary_ids, limit)


def merge_typesense_page_with_transcript_hits(
    typesense_ids: Sequence[str],
    transcript_ids: Sequence[str],
    *,
    page: int,
    per_page: int,
) -> List[str]:
    """On page 1, prefer spoken-word (transcript) hits, then Typesense title/overview.

    Later pages keep Typesense order only so pagination stays stable without a
    shared cursor across two indexes.
    """
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 10), 250))
    if page > 1:
        return [str(x) for x in typesense_ids if str(x).strip()][:per_page]
    return merge_summary_and_transcript_ids(transcript_ids, typesense_ids, per_page)


def attach_match_snippets_to_conversations(
    conversations: Sequence[Any],
    query: str,
    *,
    max_chars: int = _MAX_SNIPPET_CHARS,
) -> List[Dict[str, Any]]:
    """Copy conversations and attach ``match_snippets`` from transcript_segments."""
    enriched: List[Dict[str, Any]] = []
    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        item = dict(conv)
        segments_raw = item.get("transcript_segments") or []
        segments: List[Any] = segments_raw if isinstance(segments_raw, list) else []
        item["match_snippets"] = build_transcript_match_snippets(segments, query, max_chars=max_chars)
        enriched.append(item)
    return enriched
