"""
Tools for learning and saving user preferences during conversation.
"""

import contextvars
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

from database._client import get_data_plane_firestore_client
from models.knowledge_ledger_policy import canonicalize_ledger_slot
from models.memory_contracts import deterministic_contract_id
from models.memory_apply import WriterMode
from models.memories import MemoryDB
from models.product_memory import LedgerWriteReason
from utils.log_sanitizer import sanitize_pii
from utils.memory.canonical_memory_adapter import search_canonical_memories
from utils.memory.knowledge_ledger import LedgerProvenance, save_fact
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem, ensure_canonical_apply_control_state
from testing.parity_pack_v0.live_capture import capture_memory_write

logger = logging.getLogger(__name__)

PREFERENCE_DUPLICATE_THRESHOLD = 0.90


def preference_duplicate_message(preference: str, hits: Optional[list]) -> Optional[str]:
    """Return a skip message when hits prove a duplicate preference.

    Scoreless canonical search hits must not suppress unrelated preferences.
    Exact normalized content matches always count; numeric scores only count when
    the search result actually carries a relevance field.
    """
    preferred = " ".join((preference or "").split()).casefold()
    for hit in hits or []:
        raw_score = hit.get("score", hit.get("relevance_score", hit.get("vector_score")))
        content = str(hit.get("content") or "")
        normalized = " ".join(content.split()).casefold()
        if preferred and normalized == preferred:
            return f"Similar preference already exists: {content}"
        if raw_score is None:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if score >= PREFERENCE_DUPLICATE_THRESHOLD:
            return f"Similar preference already exists: {content}"
    return None


# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _get_uid(config: RunnableConfig) -> str:
    """Extract user ID from config or context variable."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg and 'configurable' in cfg:
        raw_configurable = cfg.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable: Dict[str, Any] = cast(Dict[str, Any], raw_configurable)
            uid = configurable.get('user_id')
            if uid:
                return uid
    ctx = _agent_config()
    if ctx and 'configurable' in ctx:
        raw_configurable = ctx.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable = cast(Dict[str, Any], raw_configurable)
            return configurable.get('user_id', '')
    return ''


def _write_provenance(uid: str, preference: str, config: RunnableConfig) -> LedgerProvenance:
    """Build retry-stable provenance without treating an inference as a user assertion."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config) or _agent_config()
    configurable = cfg.get('configurable') if isinstance(cfg, dict) else None
    configurable = configurable if isinstance(configurable, dict) else {}
    source_id = str(configurable.get('chat_session_id') or configurable.get('thread_id') or 'direct-agent-tool').strip()
    normalized_preference = ' '.join(preference.split())
    action_id = (
        "agent-preference:"
        + deterministic_contract_id(
            "agent-preference-write",
            {
                "uid": uid,
                "source_id": source_id,
                "preference": normalized_preference,
            },
        )[:32]
    )
    artifact_ref = {"chat_session_id": source_id} if configurable.get('chat_session_id') else {}
    return LedgerProvenance(
        source_id=source_id,
        source_type="agent_chat",
        source_version="save_user_preference.v1",
        action_id=action_id,
        artifact_ref=artifact_ref,
    )


def _save_compatibility_preference(uid: str, preference: str, *, firestore_client: Any) -> str:
    """Write through the released compatibility seam while its mode is active.

    The ledger is an explicit writer-mode migration target, not a drop-in
    replacement for the default writer.  Keeping this payload free of ledger
    fields is important: ``MemoryService`` classifies it as a compatibility
    write and the canonical adapter enforces that classification against the
    per-user writer control state.
    """
    now = datetime.now(timezone.utc)
    memory_id = str(uuid.uuid4())
    memory_data = {
        "id": memory_id,
        "uid": uid,
        "content": preference,
        "category": "system",
        "manually_added": False,
        "created_at": now,
        "updated_at": now,
        "reviewed": False,
        "visibility": "private",
        "tags": ["agent-learned"],
    }
    memory_data["scoring"] = MemoryDB.calculate_score(MemoryDB.model_validate(memory_data))
    MemoryService(db_client=firestore_client).create_external_memory(
        uid,
        MemoryDB.model_validate(memory_data),
        memory_system=MemorySystem.CANONICAL,
        consumer="agent_preference",
        operation="save_user_preference",
        upsert_vector=False,
        require_canonical_promotion=True,
    )
    capture_memory_write(
        principal_id=uid,
        source="agent_preference_memory_create",
        session_id=memory_id,
        memories=[memory_data],
    )
    return memory_id


@tool
def save_user_preference_tool(
    preference: str,
    slot: str = "",
    config: RunnableConfig = None,
) -> str:  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
    """Save a learned user preference or personal detail for future conversations.

    Call this when you learn something about the user's preferences, habits, or
    personal details that would be useful to remember across conversations. Examples:
    - "Prefers Google Calendar over Outlook"
    - "Default meeting length is 30 minutes"
    - "Works at Acme Corp as a product manager"
    - "Prefers metric units over imperial"

    Do NOT save ephemeral information (today's mood, current task).
    Do NOT save something already known from existing memories.
    Do NOT ask for confirmation — just save it silently when you learn it.

    Args:
        preference: A clear, concise statement of the preference or personal detail.
        slot: Optional canonical registry slot (for example ``home_city`` or
            ``occupation``). Unknown names are stored unslotted and remain
            searchable; do not invent new slot names.
    """
    uid = _get_uid(config)
    if not uid:
        return "Error: Could not determine user ID"

    try:
        firestore_client = get_data_plane_firestore_client()
    except Exception as e:
        logger.error("Failed to resolve preference storage error_type=%s", type(e).__name__)
        return "Error saving preference"

    # The canonical adapter preserves whether a search provider supplied a real
    # relevance score; the universal service currently synthesizes positional
    # scores, which must not suppress an unrelated preference.
    try:
        hits = search_canonical_memories(uid, preference, limit=3, db_client=firestore_client)
        duplicate = preference_duplicate_message(preference, hits)
        if duplicate:
            content = duplicate.rsplit(": ", 1)[-1]
            logger.info("Skipping duplicate preference: %s", sanitize_pii(content))
            return duplicate
    except Exception as e:
        logger.warning("Could not check for duplicate preferences error_type=%s", type(e).__name__)

    try:
        control = ensure_canonical_apply_control_state(uid, db_client=firestore_client)
        writer_mode = WriterMode(control.writer_mode)
        if writer_mode == WriterMode.compatibility:
            _save_compatibility_preference(uid, preference, firestore_client=firestore_client)
        elif writer_mode == WriterMode.ledger:
            provenance = _write_provenance(uid, preference, config)
            resolved_slot = canonicalize_ledger_slot(slot, strict=False) if isinstance(slot, str) else None
            memory_id = save_fact(
                uid,
                preference,
                provenance=provenance,
                write_reason=LedgerWriteReason.agent_reusable_conclusion,
                slot=resolved_slot,
                db_client=firestore_client,
            )
            capture_memory_write(
                principal_id=uid,
                source="agent_preference_ledger_write",
                session_id=provenance.source_id,
                memories=[
                    {
                        "id": memory_id,
                        "content": preference,
                        "ledger_schema_version": "knowledge_ledger.v1",
                        "write_reason": LedgerWriteReason.agent_reusable_conclusion.value,
                    }
                ],
            )
        else:
            raise RuntimeError(f"preference writer is not admitted in {writer_mode.value} mode")
        logger.info("Saved user preference: %s", sanitize_pii(preference))
        return f"Preference saved: {preference}"
    except Exception as e:
        logger.error("Failed to save preference error_type=%s", type(e).__name__)
        return "Error saving preference"
