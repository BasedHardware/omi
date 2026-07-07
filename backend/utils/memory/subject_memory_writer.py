"""Subject-keyed durable memory writer — the single new persistence point for Phase 1.

`write_subject_memories` persists a batch of extracted facts that are all attributed to one
subject entity (e.g. a specific Person). It MIRRORS the dual-path + conflict-resolution logic
in `utils.conversations.process_conversation` (`_extract_memories_legacy` /
`_extract_memories_canonical`) rather than importing/refactoring it:

- For each new fact, `find_similar_memories(..., subject_entity_id=subject_entity_id)` finds
  candidates, restricted to currently-active memories on the SAME subject, then
  `resolve_memory_conflict` decides add/skip/update/merge/keep_both.
- Persistence is routed exactly like process_conversation: CANONICAL
  (`MemoryService.write`) when `memory_system_request_scope` + `canonical_write_enabled`
  say so, else LEGACY (`save_memories` + `upsert_memory_vector` + invalidate superseded +
  `delete_memory_vector`).

Additive only: it never mutates existing user-keyed extraction and never retracts a whole
conversation's memories (only per-fact supersession, and only in the legacy path — matching
how process_conversation's canonical path defers supersession to the canonical adapter).
"""

import logging
from typing import List, Optional

import database._client as db_client_module
import database.memories as memories_db
from database.vector_db import delete_memory_vector, find_similar_memories, upsert_memory_vector
from models.memories import Memory, MemoryDB, SubjectAttribution, render_memory
from models.product_memory import MemoryTier
from utils.analytics import record_usage
from utils.llm.memories import resolve_memory_conflict
from utils.memory.canonical_activation import canonical_write_enabled
from utils.memory.canonical_memory_adapter import extraction_memory_id
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import memory_system_request_scope

logger = logging.getLogger(__name__)


def _resolve_subject_memories(
    uid: str,
    memories: List[Memory],
    *,
    subject_entity_id: str,
    subject_attribution: SubjectAttribution,
    source_id: str,
    source_type: str,
    source_signal: str,
    artifact_ref: Optional[dict],
    extractor_id: str,
    is_locked: bool,
    language: Optional[str],
    occurred_at=None,
):
    """Run per-fact conflict resolution and build `MemoryDB` objects keyed to the subject.

    Returns (parsed_memories, invalidations) where invalidations is a list of
    (old_memory_id, new_memory_id) pairs that the legacy path must invalidate.
    """
    parsed_memories: List[MemoryDB] = []
    invalidations = []
    seen_norm = set()

    for memory in memories:
        norm = ' '.join((memory.content or '').lower().split())
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)

        # Wider net (low threshold, more candidates) so cross-phrasing contradictions are
        # caught; the LLM decides what's outdated. Restricted to this subject's memories.
        similar_matches = find_similar_memories(
            uid, memory.content, threshold=0.6, limit=8, subject_entity_id=subject_entity_id
        )

        # Only compare against currently-active memories on the SAME subject.
        similar_memories = []
        for match in similar_matches:
            memory_data = memories_db.get_memory(uid, match['memory_id'])
            if memory_data and memory_data.get('invalid_at') is None:
                existing_subject = memory_data.get('subject_entity_id')
                # Strict same-subject isolation: only dedup/supersede within THIS subject's
                # own facts. A candidate with any other subject — including a None
                # (whole-conversation, subject-unknown) memory — must never be superseded by
                # this person-keyed write. find_similar_memories is subject-filtered, but a
                # None-subject vector filter is unfiltered, so this guard is load-bearing.
                if existing_subject != subject_entity_id:
                    continue
                similar_memories.append(
                    {
                        'memory_id': match['memory_id'],
                        'category': match['category'],
                        'score': match['score'],
                        'content': memory_data.get('content', ''),
                    }
                )

        supersede_ids = []
        if similar_memories:
            resolution = resolve_memory_conflict(memory.content, similar_memories, language=language)

            if resolution.action == 'skip':
                continue

            if resolution.action == 'merge':
                if resolution.merged_predicate:
                    memory.predicate = resolution.merged_predicate
                if resolution.merged_arguments:
                    memory.arguments = resolution.merged_arguments
                if resolution.merged_qualifiers:
                    memory.qualifiers = {**memory.qualifiers, **resolution.merged_qualifiers}
                if resolution.merged_content:
                    memory.content = resolution.merged_content
                elif resolution.merged_predicate or resolution.merged_arguments:
                    memory.content = render_memory(memory)

            if resolution.action in ('update', 'merge'):
                for idx in resolution.supersedes or []:
                    if isinstance(idx, int) and 1 <= idx <= len(similar_memories):
                        supersede_ids.append(similar_memories[idx - 1]['memory_id'])

        memory_db_obj = MemoryDB.from_memory(
            memory,
            uid,
            source_id,
            False,
            source_id=source_id,
            source_type=source_type,
            source_signal=source_signal,
            artifact_ref=artifact_ref,
            extractor_id=extractor_id,
            subject_entity_id=subject_entity_id,
            subject_attribution=subject_attribution,
        )
        memory_db_obj.is_locked = is_locked
        # Temporal validity: stamp the fact with WHEN it was actually true — the source
        # conversation's time, not extraction time. A backfill of old messages must record the
        # fact as old (e.g. "training for nationals" from 2 years ago), so retrieval can caveat
        # or down-weight it instead of surfacing a stale fact as current truth.
        if occurred_at is not None:
            memory_db_obj.valid_at = occurred_at
        # Corroboration is durability: a fact that supersedes an existing one has now been
        # seen more than once, so promote it out of the short-term tier it was born into.
        if supersede_ids:
            memory_db_obj.memory_tier = MemoryTier.long_term
        parsed_memories.append(memory_db_obj)

        for old_id in supersede_ids:
            if old_id and old_id != memory_db_obj.id:
                invalidations.append((old_id, memory_db_obj.id))

    return parsed_memories, invalidations


def _write_canonical(uid: str, parsed_memories: List[MemoryDB], *, source_id: str, db_client) -> int:
    memory_service = MemoryService(db_client=db_client)
    for memory_db_obj in parsed_memories:
        memory_db_obj.id = extraction_memory_id(uid=uid, source_id=source_id, content=memory_db_obj.content)
        memory_db_obj.memory_tier = MemoryTier.short_term
        memory_service.write(uid, memory_db_obj.model_dump(mode='json'))
    return len(parsed_memories)


def _write_legacy(uid: str, parsed_memories: List[MemoryDB], invalidations) -> int:
    memories_db.save_memories(uid, [fact.dict() for fact in parsed_memories])

    for memory_db_obj in parsed_memories:
        upsert_memory_vector(
            uid,
            memory_db_obj.id,
            memory_db_obj.content,
            memory_db_obj.category.value,
            subject_entity_id=memory_db_obj.subject_entity_id,
        )

    # Invalidate (not delete) superseded memories: keep them as history but drop them from
    # every retrieval path. Removing the vector also pulls them out of semantic search.
    for old_id, new_id in invalidations:
        try:
            memories_db.invalidate_memory(uid, old_id, superseded_by=new_id)
            delete_memory_vector(uid, old_id)
            logger.info(f'Invalidated superseded subject memory {old_id} -> {new_id}')
        except Exception:
            logger.exception(f'Failed to invalidate superseded subject memory {old_id}')

    return len(parsed_memories)


def write_subject_memories(
    uid: str,
    memories: List[Memory],
    *,
    subject_entity_id: str,
    subject_attribution: SubjectAttribution,
    source_id: str,
    source_type: str = 'conversation',
    source_signal: str = 'transcription',
    artifact_ref: Optional[dict] = None,
    extractor_id: str = 'person_messaging_extractor',
    is_locked: bool = False,
    language: Optional[str] = None,
    occurred_at=None,
) -> int:
    """Persist `memories` attributed to `subject_entity_id`, deduped/superseded against that
    subject's existing active facts. `occurred_at` (the source conversation's time) is stamped
    as each fact's `valid_at` so callers can tell how old the information is. Routes canonical
    vs legacy exactly like process_conversation. Returns the number of memories written."""
    if not memories:
        return 0

    parsed_memories, invalidations = _resolve_subject_memories(
        uid,
        memories,
        occurred_at=occurred_at,
        subject_entity_id=subject_entity_id,
        subject_attribution=subject_attribution,
        source_id=source_id,
        source_type=source_type,
        source_signal=source_signal,
        artifact_ref=artifact_ref,
        extractor_id=extractor_id,
        is_locked=is_locked,
        language=language,
    )

    if not parsed_memories:
        logger.info(f'No subject memories to write for subject={subject_entity_id} source={source_id}')
        return 0

    with memory_system_request_scope(uid) as memory_system:
        db_client = getattr(db_client_module, 'db', None)
        if memory_system == MemorySystem.CANONICAL and canonical_write_enabled(uid, db_client=db_client):
            written = _write_canonical(uid, parsed_memories, source_id=source_id, db_client=db_client)
        else:
            written = _write_legacy(uid, parsed_memories, invalidations)

    # Parity with process_conversation's extraction paths: count person-keyed memory
    # creation in the user's usage stats (the writer previously omitted this). Best-effort:
    # analytics must never break or roll back an already-persisted memory write.
    if written:
        try:
            record_usage(uid, memories_created=written)
        except Exception as e:
            logger.warning(f'subject_memory_writer: usage tracking failed uid={uid}: {e}')
    return written
