import threading
from typing import Any, Dict, List, Optional, Tuple

from cachetools import TTLCache

from database._client import db as firestore_db
from database.auth import get_user_name
from models.memories import Memory, MemoryDB
from models.product_memory import MemoryKind, MemorySubjectScope
from utils.memory.knowledge_ledger import DEFAULT_PROFILE_CHARACTER_BUDGET, LEDGER_SCHEMA_VERSION
from utils.memory.knowledge_ledger_migration import read_ledger_migration_completion
from utils.memory.memory_service import MemoryService
import logging

logger = logging.getLogger(__name__)

# Prompt context is a bounded default-visible intake — never a full account export.
PROMPT_MEMORY_LIMIT = 1000

_PROMPT_DATA_CACHE_MAX_SIZE = 1024
_PROMPT_DATA_CACHE_TTL_SECONDS = 30
_prompt_data_cache: TTLCache[str, Tuple[Optional[str], List[MemoryDB], List[MemoryDB], List[MemoryDB]]] = TTLCache(
    maxsize=_PROMPT_DATA_CACHE_MAX_SIZE, ttl=_PROMPT_DATA_CACHE_TTL_SECONDS
)
_prompt_data_cache_lock = threading.Lock()


def clear_prompt_data_cache(uid: Optional[str] = None) -> None:
    """Drop cached prompt context for one user (or all users when uid is None)."""
    with _prompt_data_cache_lock:
        if uid is None:
            _prompt_data_cache.clear()
        else:
            _prompt_data_cache.pop(uid, None)


def get_prompt_memories(uid: str) -> Tuple[Any, str]:
    user_name, baseline_memories, user_made_memories, generated_memories = get_prompt_data(uid)
    all_memories = baseline_memories + user_made_memories + generated_memories
    ledger_memories = [memory for memory in all_memories if memory.ledger_schema_version == LEDGER_SCHEMA_VERSION]
    if ledger_memories:
        ledger_context = _render_ledger_prompt_context(user_name, ledger_memories)
        legacy_baseline = [row for row in baseline_memories if row.ledger_schema_version != LEDGER_SCHEMA_VERSION]
        legacy_user_made = [row for row in user_made_memories if row.ledger_schema_version != LEDGER_SCHEMA_VERSION]
        legacy_generated = [row for row in generated_memories if row.ledger_schema_version != LEDGER_SCHEMA_VERSION]
        has_legacy_rows = bool(legacy_baseline or legacy_user_made or legacy_generated)
        # A partial migration must never make unreconciled legacy knowledge
        # disappear merely because the first ledger row exists. Only the
        # explicit, fail-closed per-user completion proof plus a zero-legacy
        # snapshot retires this bridge. The second check protects against a
        # stale marker or a legacy writer that was not actually fenced.
        if read_ledger_migration_completion(uid, db_client=firestore_db) is not None and not has_legacy_rows:
            return user_name, ledger_context
        legacy_context = _render_legacy_prompt_context(
            user_name,
            legacy_baseline,
            legacy_user_made,
            legacy_generated,
        )
        return user_name, ledger_context + "\nMigration compatibility context:\n" + legacy_context
    return user_name, _render_legacy_prompt_context(
        user_name,
        baseline_memories,
        user_made_memories,
        generated_memories,
    )


def _render_legacy_prompt_context(
    user_name: Optional[str],
    baseline_memories: List[MemoryDB],
    user_made_memories: List[MemoryDB],
    generated_memories: List[MemoryDB],
) -> str:
    memories_str = ''
    if baseline_memories:
        memories_str += (
            f'you already know the following baseline facts about {user_name} (always in context):'
            f' \n{Memory.get_memories_as_str(baseline_memories)}.\n'
        )
    memories_str += (
        f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    )
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )
    return memories_str + '\n'


def _bounded_lines(lines: List[str], budget: int) -> str:
    rendered: List[str] = []
    used = 0
    for line in lines:
        separator = 1 if rendered else 0
        if used + separator + len(line) > budget:
            continue
        rendered.append(line)
        used += separator + len(line)
    return '\n'.join(rendered)


def _render_ledger_prompt_context(user_name: Optional[str], rows: List[MemoryDB]) -> str:
    """Render only current slotted self-facts and playbook handles."""
    facts = [
        row
        for row in rows
        if row.kind == MemoryKind.fact
        and row.subject_scope == MemorySubjectScope.primary_user
        and row.intent_backed
        and row.user_review is not False
        and row.invalid_at is None
        and row.slot
        and row.content.strip()
    ]
    facts.sort(key=lambda row: (-row.curation_weight, row.slot or '', row.valid_at or row.created_at, row.id))
    profile = _bounded_lines(
        [f"{row.slot}: {row.content.strip()}" for row in facts],
        DEFAULT_PROFILE_CHARACTER_BUDGET,
    )
    playbooks = [
        row
        for row in rows
        if row.kind == MemoryKind.document
        and row.user_review is not False
        and row.invalid_at is None
        and row.content.strip()
    ]
    playbooks.sort(key=lambda row: (-row.curation_weight, row.content, row.id))
    playbook_index = _bounded_lines([f"{row.id}: {row.content.strip()}" for row in playbooks], 800)
    sections = [f"Current profile for {user_name or 'the user'}:\n{profile or '(no current slotted facts)'}"]
    if playbook_index:
        sections.append(
            "Available playbooks (call read_playbook for the body; do not infer it from the title):\n" + playbook_index
        )
    return '\n\n'.join(sections) + '\n'


def safe_create_memory(memory_data: Dict[str, Any]) -> MemoryDB:
    """Safely create a MemoryDB instance handling legacy categories"""
    try:
        return MemoryDB(**memory_data)
    except Exception as e:
        # Handle legacy category conversion if needed
        if 'category' in memory_data and isinstance(memory_data['category'], str):
            # Make a copy to avoid modifying the original data
            fixed_data: Dict[str, Any] = dict(memory_data)
            # Set a default/fallback category if the category is causing issues
            if 'category' in str(e):
                # Use a safe default category
                if memory_data['category'] in [
                    'core',
                    'hobbies',
                    'lifestyle',
                    'interests',
                    'work',
                    'skills',
                    'learnings',
                ]:
                    fixed_data['category'] = 'interesting'
                else:
                    fixed_data['category'] = 'system'
                return MemoryDB(**fixed_data)
        # If we couldn't fix it, re-raise the exception
        raise


def _is_prompt_visible(memory: MemoryDB) -> bool:
    """Rejected, pending-review, locked, and invalidated rows stay out of prompts."""
    if memory.is_locked:
        return False
    if memory.user_review is False:
        return False
    if memory.invalid_at is not None:
        return False
    return True


def get_prompt_data(
    uid: str,
) -> Tuple[Optional[str], List[MemoryDB], List[MemoryDB], List[MemoryDB]]:
    with _prompt_data_cache_lock:
        cached = _prompt_data_cache.get(uid)
    if cached is not None:
        user_name, baseline, user_made, generated = cached
        return user_name, list(baseline), list(user_made), list(generated)

    # Use the default-visible list surface (processed, non-archive) with a hard
    # page cap. Account export is intentionally not used for prompt intake.
    existing_memories = MemoryService(db_client=firestore_db).read(
        uid,
        limit=PROMPT_MEMORY_LIMIT,
        offset=0,
        include_pending_processing=False,
    )

    baseline: List[MemoryDB] = []
    user_made: List[MemoryDB] = []
    generated: List[MemoryDB] = []

    for memory_obj in existing_memories:
        try:
            if not _is_prompt_visible(memory_obj):
                continue
            if memory_obj.is_baseline:
                baseline.append(memory_obj)
            elif memory_obj.manually_added:
                user_made.append(memory_obj)
            else:
                generated.append(memory_obj)
        except Exception as e:
            logger.error(f"Error routing memory into prompt buckets: {e}")

    user_name = get_user_name(uid)
    result = (user_name, baseline, user_made, generated)
    with _prompt_data_cache_lock:
        _prompt_data_cache[uid] = result
    return result
