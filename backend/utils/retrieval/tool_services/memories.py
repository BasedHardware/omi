"""
Shared service functions for memory retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, cast

import database.memories as memory_db
import database.notifications as notification_db
import database.vector_db as vector_db
from database._client import db as firestore_db
from database.entities import person_entity_id
from models.memories import MemoryDB
from utils.conversations.render import format_local_date, resolve_display_tz
from utils.memory.atom_keyword_index import merge_memory_search_ids
from utils.memory.legacy_keyword_search import keyword_search_legacy_memory_ids
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.memory.chat_memory_adapter import (
    chat_legacy_read_authorized,
    list_default_chat_memories_decision_text,
    search_memory_default_chat_memories_vector_decision_text,
)
from utils.memory.default_read_rollout import MemoryReadDecision
from utils.retrieval.tool_services.conversations import parse_iso_date
import logging

logger = logging.getLogger(__name__)


def get_memories_text(
    uid: str,
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Fetch user memories/facts and format as LLM-ready text."""
    logger.info(f"get_memories_text - uid: {uid}, limit: {limit}, offset: {offset}")

    # Cap request bounds before either memory or legacy reads.
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_iso_date(start_date, 'start_date')
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"
    if end_date:
        try:
            end_dt = parse_iso_date(end_date, 'end_date')
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        memories = MemoryService(db_client=firestore_db).read(uid, limit=limit, offset=offset, now=now)
        if start_dt or end_dt:
            filtered: List[MemoryDB] = []
            for memory in memories:
                created = memory.created_at
                if start_dt and created and created < start_dt:
                    continue
                if end_dt and created and created > end_dt:
                    continue
                filtered.append(memory)
            memories = filtered
        if not memories:
            return "No memories found."
        return f"User Memories ({len(memories)} total):\n\n{MemoryDB.get_memories_as_str(memories)}".strip()

    default_memories = list_default_chat_memories_decision_text(
        uid=uid,
        limit=limit,
        offset=offset,
        db_client=firestore_db,
        allow_legacy_safe_fallback=True,
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        logger.info("get_memories_text - using memory default chat memory list results")
        return default_memories.text or "No memory default memories found."
    if not chat_legacy_read_authorized(default_memories):
        logger.info(
            "get_memories_text - memory default memory list denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    # Fetch
    memories_data: List[Dict[str, Any]] = []
    try:
        memories_data = memory_db.get_memories(uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt)
    except Exception as e:
        logger.error(f"get_memories_text error: {e}")
        return f"Error retrieving memories: {e}"

    # Filter locked
    if memories_data:
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]

    if not memories_data:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
        return f"No memories found{date_info}."

    # Convert to objects
    memory_objects: List[MemoryDB] = []
    for memory_data in memories_data:
        try:
            memory_objects.append(MemoryDB(**memory_data))
        except Exception as e:
            logger.error(f"Error creating MemoryDB object: {e}")
            continue

    if not memory_objects:
        return "Error: Could not parse memories data"

    result = f"User Memories ({len(memory_objects)} total):\n\n"
    result += MemoryDB.get_memories_as_str(memory_objects)
    return result.strip()


def resolve_subject_entity_id(person_id: Optional[str]) -> Optional[str]:
    """Map a backend ``Person`` uuid to the subject entity id memories are attributed with.

    The uuid is the one from ``users/{uid}/people`` — the same id space as
    ``TranscriptSegment.person_id`` — and :func:`database.entities.person_entity_id` is the
    single place that turns it into the ``person:<uuid>`` string stored on
    ``MemoryDB.subject_entity_id`` and in the Pinecone metadata. No name is resolved here:
    a caller without an id gets no scoping rather than a guess.
    """
    trimmed = (person_id or '').strip()
    return person_entity_id(trimmed) if trimmed else None


def person_memory_ids(uid: str, subject_entity_id: str, *, limit: int) -> List[str]:
    """Ids of the memories attributed to one person, newest first.

    Fail-open like every other retrieval leg: a Firestore error degrades this to
    vector-only results instead of failing the whole search.
    """
    try:
        memories = memory_db.get_memories_by_subject(uid, subject_entity_id, limit=max(limit, 50))
    except Exception as e:
        logger.warning(f"person_memory_ids failed for uid={uid} subject={subject_entity_id}: {e}")
        return []
    ids = [str(memory['id']) for memory in memories if memory.get('id') and not memory.get('is_locked', False)]
    return ids[:limit]


def memory_matches_subject(memory: Any, subject_entity_id: str) -> bool:
    """Whether a hydrated memory is attributed to ``subject_entity_id``.

    Checks the subject spine first and the tag column second — the same id string in two
    places, never a name comparison.
    """
    if getattr(memory, 'subject_entity_id', None) == subject_entity_id:
        return True
    tags: Any = getattr(memory, 'tags', None)
    return isinstance(tags, list) and subject_entity_id in cast(List[Any], tags)


def search_memories_text(
    uid: str,
    query: str,
    limit: int = 5,
    person_id: Optional[str] = None,
) -> str:
    """Hybrid (keyword + vector) memory search, formatted as LLM-ready text.

    Two retrieval legs are merged keyword-first, the shape conversation search settled on
    for the same class of miss (issue #5072):

    * **identity / keyword leg** — with ``person_id`` this reads that person's memories
      out of Firestore by ``subject_entity_id``/``tags``; without one it is the
      selective-term keyword scan in :mod:`utils.memory.legacy_keyword_search`, which
      exists because embedding a bare proper name against a short structural fact is the
      worst case for kNN recall.
    * **vector leg** — unchanged Pinecone kNN, now passing ``subject_entity_id`` into the
      metadata filter :func:`database.vector_db.find_similar_memories` has always
      accepted and no caller ever supplied.

    ``person_id`` is the backend ``Person`` uuid, never a display name or a client-side
    slug. Omitting it leaves the search exactly as wide as it was: the keyword leg returns
    nothing for a query with no selective term, and both legs collapse to today's single
    Pinecone call.
    """
    logger.info(f"search_memories_text - uid: {uid}, query: {query}, limit: {limit}, person_id: {person_id}")

    limit = max(1, min(limit, 20))
    subject_entity_id = resolve_subject_entity_id(person_id)

    # Memory dates go to the chat model; the UTC date rolls over at a different instant than
    # the user's, so a raw UTC date is a day late for them in the evening (issue #6214).
    try:
        display_tz, _ = resolve_display_tz(notification_db.get_user_time_zone(uid))
    except Exception as tz_error:
        logger.warning(f"search_memories_text - timezone lookup failed, formatting dates in UTC: {tz_error}")
        display_tz = timezone.utc

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        if subject_entity_id:
            # Canonical has no subject-scoped read yet, so this narrows the semantic page
            # rather than querying by subject. It can under-return (a fact ranked below
            # `limit` is never seen) but it can never mis-attribute, which is the property
            # that matters on a person profile.
            matches = [match for match in matches if memory_matches_subject(match.memory, subject_entity_id)]
        if not matches:
            return f"No memories found matching '{query}'."
        result = f"Found {len(matches)} memories matching '{query}':\n\n"
        for match in matches:
            memory = match.memory
            date_str = format_local_date(memory.created_at, display_tz) if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {match.score:.2f}, "
                f"category: {memory.category.value}, date: {date_str})\n"
            )
        return result.strip()

    default_memories = search_memory_default_chat_memories_vector_decision_text(
        uid=uid,
        query=query,
        limit=limit,
        db_client=firestore_db,
        allow_legacy_safe_fallback=True,
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        if subject_entity_id:
            # The memory default read has no subject-scoped variant. Returning its
            # unscoped page for a request that named one person would answer a different
            # question, so this cohort gets an explicit "not available" instead.
            logger.info("search_memories_text - person-scoped search unsupported on the memory default read path")
            return "Person-scoped memory search is not available for this account yet."
        logger.info("search_memories_text - using memory default chat vector memory results")
        return default_memories.text or f"No memory vector memories found matching '{query}'."
    if not chat_legacy_read_authorized(default_memories):
        logger.info(
            "search_memories_text - memory default memory vector search denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    try:
        if subject_entity_id:
            keyword_ids = person_memory_ids(uid, subject_entity_id, limit=limit)
        else:
            keyword_ids = keyword_search_legacy_memory_ids(uid, query, limit=limit)

        # A person-scoped request with no query text has nothing to embed; the identity
        # leg already answered it. Every other request keeps the exact call it made before.
        if subject_entity_id and not query.strip():
            matches: List[Dict[str, Any]] = []
        else:
            matches = vector_db.find_similar_memories(
                uid, query, threshold=0.0, limit=limit, subject_entity_id=subject_entity_id
            )

        if not matches and not keyword_ids:
            return f"No memories found matching '{query}'."

        vector_ids = [cast(str, match.get('memory_id')) for match in matches if match.get('memory_id')]
        scores_by_id = {match.get('memory_id'): match.get('score', 0) for match in matches}

        memory_ids = merge_memory_search_ids(keyword_ids, vector_ids)

        if not memory_ids:
            return f"Found matches but no valid memory IDs for query: '{query}'"

        memories_data = memory_db.get_memories_by_ids(uid, memory_ids)

        # Filter locked
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]
        if not memories_data:
            return f"No memories found matching '{query}'."

        # Keyword/identity hits lead — they are the exact-token or by-subject evidence the
        # vector leg missed. The sort is stable and every non-keyword row shares one rank,
        # so a search with no keyword hits renders exactly what it rendered before.
        keyword_rank = {memory_id: rank for rank, memory_id in enumerate(keyword_ids)}
        memories_data = sorted(
            memories_data, key=lambda memory: keyword_rank.get(str(memory.get('id')), len(keyword_rank))
        )

        # Format with scores
        memory_objects: List[Dict[str, Any]] = []
        for memory_data in memories_data:
            try:
                memory_obj = MemoryDB(**memory_data)
                memory_id = memory_data.get('id')
                score = scores_by_id.get(memory_id)
                if score is None:
                    # A keyword/identity hit the vector leg never returned has no cosine
                    # score. Printing 0.00 would tell the model to discount the one row it
                    # most needs, so an exact match is reported at full relevance.
                    score = 1.0 if memory_id in keyword_rank else 0
                memory_objects.append({'memory': memory_obj, 'score': score})
            except Exception as e:
                logger.error(f"Error creating MemoryDB object: {e}")
                continue

        if not memory_objects:
            return f"Found matches but could not retrieve memory details for query: '{query}'"

        result = f"Found {len(memory_objects)} memories matching '{query}':\n\n"
        for item in memory_objects:
            memory = item['memory']
            score = item['score']
            date_str = format_local_date(memory.created_at, display_tz) if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {score:.2f}, category: {memory.category.value}, date: {date_str})\n"
            )

        return result.strip()

    except Exception as e:
        logger.error(f"search_memories_text error: {e}")
        return f"Error searching memories: {e}"
