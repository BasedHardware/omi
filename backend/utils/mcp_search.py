"""Unified search + fetch over the Omi memory bank for the ChatGPT/Claude
connector contract (issue #4862).

OpenAI's ChatGPT connectors and deep-research models consume an MCP server through
a standard pair of read-only tools: ``search(query)`` returns a list of result
stubs (id, title, url, text) and ``fetch(id)`` returns the full document. This
module implements that contract over the two richest text sources Omi has,
memories and conversations, reusing the existing vector search. Claude already
speaks MCP and can call the per-domain tools directly; this unified pair is what
makes the same memory bank directly usable from ChatGPT.

Result ids are namespaced (``memory:<id>`` / ``conversation:<id>``) so ``fetch``
knows which store to read.
"""

from typing import List

import database.conversations as conversations_db
import database.memories as memories_db
import database.vector_db as vector_db

_MEMORY_PREFIX = "memory:"
_CONVERSATION_PREFIX = "conversation:"
_WEB_BASE_URL = "https://h.omi.me"

_DEFAULT_LIMIT = 10
_MAX_LIMIT = 20


class SearchError(Exception):
    """Base error for unified search/fetch."""


class InvalidRequest(SearchError):
    """The query or id argument is missing or not a string."""


class ItemNotFound(SearchError):
    """The fetched item does not exist."""


class ItemLocked(SearchError):
    """The fetched item requires a paid plan."""


def _clamp_limit(value) -> int:
    try:
        parsed = int(value) if value is not None else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        parsed = _DEFAULT_LIMIT
    return max(1, min(parsed, _MAX_LIMIT))


def _snippet(text: str, length: int = 80) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[:length] + "...") if len(text) > length else text


def _memory_url(memory_id: str) -> str:
    return f"{_WEB_BASE_URL}/memories/{memory_id}"


def _conversation_url(conversation_id: str) -> str:
    return f"{_WEB_BASE_URL}/conversations/{conversation_id}"


def _conversation_title(conv: dict) -> str:
    structured = conv.get("structured") or {}
    title = structured.get("title") if isinstance(structured, dict) else None
    return (title or "").strip() or "Conversation"


def _conversation_text(conv: dict) -> str:
    structured = conv.get("structured") or {}
    parts: List[str] = []
    if isinstance(structured, dict) and structured.get("overview"):
        parts.append(str(structured["overview"]).strip())
    segments = conv.get("transcript_segments") or []
    transcript = "\n".join(str(s.get("text", "")).strip() for s in segments if s.get("text"))
    if transcript:
        parts.append(transcript)
    return "\n\n".join(p for p in parts if p).strip() or _conversation_title(conv)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _memory_visible(mem: dict) -> bool:
    """A memory is hidden from the connector when the user rejected it or it has been
    superseded. Shared by ``_search_memories`` and ``fetch`` so the two entry points
    agree (locking is handled separately: skipped in search, a paywall in fetch)."""
    return mem.get("user_review") is not False and mem.get("invalid_at") is None


def _search_memories(uid: str, query: str, limit: int) -> List[dict]:
    fetch_limit = min(limit * 3, 60)
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)
    memory_ids = [str(m.get("memory_id")) for m in matches if m.get("memory_id")]
    if not memory_ids:
        return []
    score_map = {m.get("memory_id"): m.get("score", 0) for m in matches if m.get("memory_id")}
    memories = memories_db.get_memories_by_ids(uid, memory_ids)
    results = []
    for mem in memories:
        # Mirror search_memories: never surface rejected, locked, or superseded facts.
        if not _memory_visible(mem) or mem.get("is_locked", False):
            continue
        mem_id = str(mem.get("id") or "")
        content = mem.get("content", "") or ""
        results.append(
            {
                "id": f"{_MEMORY_PREFIX}{mem_id}",
                "title": _snippet(content) or "Memory",
                "url": _memory_url(mem_id),
                "text": content,
                "_score": score_map.get(mem_id, 0),
            }
        )
    results.sort(key=lambda r: r["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)
    return results[:limit]


def _conversation_preview(conv: dict) -> str:
    """Short preview for a search stub: overview, else transcript, else title.

    Falls back to transcript text so a conversation that has segments but no
    overview still has a non-empty preview, matching what ``fetch`` would return.
    """
    structured = conv.get("structured") or {}
    overview = structured.get("overview") if isinstance(structured, dict) else None
    if overview and str(overview).strip():
        return _snippet(overview, 200)
    segments = conv.get("transcript_segments") or []
    transcript = " ".join(str(s.get("text", "")).strip() for s in segments if s.get("text"))
    if transcript.strip():
        return _snippet(transcript, 200)
    return _conversation_title(conv)


def _search_conversations(uid: str, query: str, limit: int) -> List[dict]:
    # Over-fetch candidates so locked conversations dropped below do not under-fill
    # the returned count, the same way _search_memories does.
    fetch_limit = min(limit * 3, 60)
    conversation_ids = vector_db.query_vectors(query, uid, k=fetch_limit)
    if not conversation_ids:
        return []
    conversations = conversations_db.get_conversations_by_id(uid, conversation_ids)
    results = []
    for conv in conversations:
        # Locked conversations are paywalled; do not surface their content in stubs.
        if conv.get("is_locked", False):
            continue
        conv_id = conv.get("id")
        results.append(
            {
                "id": f"{_CONVERSATION_PREFIX}{conv_id}",
                "title": _conversation_title(conv),
                "url": _conversation_url(conv_id),
                "text": _conversation_preview(conv),
            }
        )
    return results[:limit]


def _interleave(a: List[dict], b: List[dict], limit: int) -> List[dict]:
    """Merge two ranked lists so both sources are represented, capped at limit."""
    out: List[dict] = []
    ia = ib = 0
    while len(out) < limit and (ia < len(a) or ib < len(b)):
        if ia < len(a):
            out.append(a[ia])
            ia += 1
            if len(out) >= limit:
                break
        if ib < len(b):
            out.append(b[ib])
            ib += 1
    return out


def search(uid: str, query: object, limit=None) -> dict:
    """Unified search over memories and conversations.

    Returns the ChatGPT connector shape: ``{"results": [{id, title, url, text}, ...]}``.

    ``query`` arrives straight from the tool arguments, so it may be any JSON
    type; a non-string (or blank) query is an invalid request.
    """
    if not isinstance(query, str) or not query.strip():
        raise InvalidRequest("query is required")
    query = query.strip()
    limit = _clamp_limit(limit)
    memories = _search_memories(uid, query, limit)
    conversations = _search_conversations(uid, query, limit)
    return {"results": _interleave(memories, conversations, limit)}


def fetch(uid: str, item_id: object) -> dict:
    """Fetch a single document by a namespaced id returned from ``search``.

    Returns the ChatGPT connector shape: ``{id, title, text, url, metadata}``.

    ``item_id`` arrives straight from the tool arguments, so it may be any JSON
    type; a non-string (or blank) id is an invalid request, not a 404.
    """
    if not isinstance(item_id, str) or not item_id.strip():
        raise InvalidRequest("id is required")
    item_id = item_id.strip()

    if item_id.startswith(_MEMORY_PREFIX):
        raw_id = item_id[len(_MEMORY_PREFIX) :]
        if not raw_id:
            raise InvalidRequest("memory id is missing in the search id")
        memory = memories_db.get_memory(uid, raw_id)
        # Hide rejected/superseded memories here too, so fetch agrees with search.
        if not memory or not _memory_visible(memory):
            raise ItemNotFound("Memory not found")
        if memory.get("is_locked", False):
            raise ItemLocked("A paid plan is required to access this memory.")
        content = memory.get("content", "") or ""
        return {
            "id": item_id,
            "title": _snippet(content) or "Memory",
            "text": content,
            "url": _memory_url(raw_id),
            "metadata": {
                "type": "memory",
                "category": memory.get("category"),
                "created_at": _iso(memory.get("created_at")),
            },
        }

    if item_id.startswith(_CONVERSATION_PREFIX):
        raw_id = item_id[len(_CONVERSATION_PREFIX) :]
        if not raw_id:
            raise InvalidRequest("conversation id is missing in the search id")
        conv = conversations_db.get_conversation(uid, raw_id)
        if not conv:
            raise ItemNotFound("Conversation not found")
        if conv.get("is_locked", False):
            raise ItemLocked("A paid plan is required to access this conversation.")
        structured = conv.get("structured") or {}
        return {
            "id": item_id,
            "title": _conversation_title(conv),
            "text": _conversation_text(conv),
            "url": _conversation_url(raw_id),
            "metadata": {
                "type": "conversation",
                "category": structured.get("category") if isinstance(structured, dict) else None,
                "created_at": _iso(conv.get("created_at")),
            },
        }

    raise InvalidRequest(f"Unrecognized id: '{item_id}'. Expected a 'memory:' or 'conversation:' id from search.")
