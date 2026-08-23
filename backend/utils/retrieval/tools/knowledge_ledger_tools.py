"""Progressive-disclosure tools for the intent-backed knowledge ledger.

These tools expose only current, default-visible canonical ledger rows to the
authenticated Omi chat principal.  Search returns compact handles; playbook
bodies are fetched only by an explicit second tool call.  Historical rows and
trigger payloads stay out until their separate policy contracts are ratified.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, Iterable, Optional, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]

from models.memories import MemoryDB
from models.product_memory import (
    MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS,
    MemoryAccessPolicy,
    MemoryItem,
    MemoryKind,
    MemorySubjectScope,
)
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION
from utils.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

MAX_KNOWLEDGE_QUERY_CHARACTERS = 500
MAX_KNOWLEDGE_SEARCH_LIMIT = 20
MAX_KNOWLEDGE_RESULT_CHARACTERS = 12_000
MAX_PLAYBOOK_ID_CHARACTERS = 256
MAX_PLAYBOOK_DESCRIPTION_CHARACTERS = 600
_PLAYBOOK_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")
_LEDGER_KINDS = frozenset({kind.value for kind in MemoryKind})


def _agent_config() -> Optional[Dict[str, Any]]:
    try:
        from utils.retrieval.agentic import agent_config_context

        return cast(Optional[Dict[str, Any]], agent_config_context.get())
    except (ImportError, LookupError):
        return None


def _resolve_uid(config: RunnableConfig | None) -> Optional[str]:
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
    uid = configurable.get("user_id") if isinstance(configurable, dict) else None
    return uid.strip() if isinstance(uid, str) and uid.strip() else None


def _parse_kinds(kinds: Optional[str]) -> frozenset[str]:
    if kinds is None or not kinds.strip():
        return _LEDGER_KINDS
    parsed = frozenset(part.strip().casefold() for part in kinds.split(",") if part.strip())
    if not parsed or not parsed.issubset(_LEDGER_KINDS):
        raise ValueError("kinds must contain only fact, document, or trigger")
    return parsed


def _is_current_ledger_memory(memory: MemoryDB, *, kinds: frozenset[str]) -> bool:
    kind = memory.kind.value if isinstance(memory.kind, MemoryKind) else str(memory.kind or "")
    return (
        memory.ledger_schema_version == LEDGER_SCHEMA_VERSION
        and kind in kinds
        and memory.invalid_at is None
        and memory.user_review is not False
        and not memory.is_locked
    )


def _is_current_ledger_item(item: MemoryItem, *, kinds: frozenset[str]) -> bool:
    promotion = item.promotion or {}
    return (
        item.ledger_schema_version == LEDGER_SCHEMA_VERSION
        and item.kind.value in kinds
        and item.intent_backed
        and item.valid_to is None
        and promotion.get("is_locked") is not True
        and promotion.get("user_review") is not False
    )


def _format_search_results(rows: Iterable[MemoryDB], *, query: str) -> str:
    lines = [f"Current knowledge matching {query!r}:"]
    count = 0
    truncated = False
    for row in rows:
        kind = row.kind.value if isinstance(row.kind, MemoryKind) else str(row.kind or "unknown")
        content = " ".join((row.content or "").split())
        suffix = f" slot={row.slot}" if row.slot else ""
        candidate = f"- [{kind}] {row.id}{suffix}: {content}"
        if len("\n".join(lines + [candidate])) > MAX_KNOWLEDGE_RESULT_CHARACTERS:
            truncated = True
            break
        lines.append(candidate)
        count += 1
    if count == 0:
        return "No current knowledge ledger entries found."
    if truncated:
        lines.append("[Knowledge output is bounded; use a narrower query or kind filter.]")
    return "\n".join(lines)


def search_current_knowledge(
    uid: str,
    query: str,
    *,
    kinds: frozenset[str],
    limit: int,
    db_client: Any,
) -> list[MemoryDB]:
    """Search current ledger handles through the universal canonical read path."""

    matches = MemoryService(db_client=db_client).search(
        uid,
        query,
        limit=limit,
        canonical_item_filter=lambda item: _is_current_ledger_item(item, kinds=kinds),
        result_filter=lambda memory: _is_current_ledger_memory(memory, kinds=kinds),
    )
    return [
        match.memory
        for match in matches
        if match.memory.uid == uid and _is_current_ledger_memory(match.memory, kinds=kinds)
    ][:limit]


def read_current_playbook(uid: str, memory_id: str, *, db_client: Any) -> Optional[MemoryItem]:
    """Read one current chat-visible primary-user playbook, or fail closed."""

    item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
    if item is None or item.uid != uid or item.memory_id != memory_id:
        return None
    visible = filter_canonical_default_visible_items(
        [item],
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
        now=datetime.now(timezone.utc),
    )
    if not visible:
        return None
    promotion = item.promotion or {}
    if (
        item.ledger_schema_version != LEDGER_SCHEMA_VERSION
        or item.kind != MemoryKind.document
        or item.subject_scope != MemorySubjectScope.primary_user
        or not item.intent_backed
        or item.valid_to is not None
        or promotion.get("is_locked") is True
        or promotion.get("user_review") is False
    ):
        return None
    return item


@tool
def search_knowledge(
    query: str,
    kinds: Optional[str] = None,
    limit: int = 8,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
) -> str:
    """Search current facts, playbook handles, and trigger descriptions.

    Use a comma-separated ``kinds`` filter containing ``fact``, ``document``,
    or ``trigger`` when the question targets one ledger kind.  Results contain
    compact current-row handles only.  For a document result, call
    ``read_playbook`` with its memory id to load the body.
    """

    normalized_query = " ".join((query or "").split())
    if not normalized_query or len(normalized_query) > MAX_KNOWLEDGE_QUERY_CHARACTERS:
        return "Error: query must be non-empty and at most 500 characters"
    if limit < 1 or limit > MAX_KNOWLEDGE_SEARCH_LIMIT:
        return f"Error: limit must be between 1 and {MAX_KNOWLEDGE_SEARCH_LIMIT}"
    try:
        parsed_kinds = _parse_kinds(kinds)
    except ValueError as exc:
        return f"Error: {exc}"
    uid = _resolve_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        from database._client import get_firestore_client

        rows = search_current_knowledge(
            uid,
            normalized_query,
            kinds=parsed_kinds,
            limit=limit,
            db_client=get_firestore_client(),
        )
        return _format_search_results(rows, query=normalized_query)
    except Exception as exc:
        logger.error("search_knowledge failed error_type=%s", type(exc).__name__)
        return "Error searching current knowledge"


@tool
def read_playbook(
    memory_id: str,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
) -> str:
    """Load the body of one current playbook returned by ``search_knowledge``.

    The lookup is owner-scoped and admits only active, processed, non-rejected,
    non-locked primary-user ``knowledge_ledger.v1`` documents.  Other ids are
    reported as unavailable without revealing whether a row exists.
    """

    normalized_id = (memory_id or "").strip()
    if (
        not normalized_id
        or len(normalized_id) > MAX_PLAYBOOK_ID_CHARACTERS
        or _PLAYBOOK_ID_PATTERN.fullmatch(normalized_id) is None
    ):
        return "Error: invalid playbook id"
    uid = _resolve_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        from database._client import get_firestore_client

        item = read_current_playbook(uid, normalized_id, db_client=get_firestore_client())
        if item is None:
            return "Playbook unavailable."
        description = " ".join((item.content or "").split())[:MAX_PLAYBOOK_DESCRIPTION_CHARACTERS]
        body = (item.body or "")[:MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS]
        return f"Playbook {item.memory_id}: {description}\n\n{body}".rstrip()
    except Exception as exc:
        logger.error("read_playbook failed error_type=%s", type(exc).__name__)
        return "Playbook unavailable."


__all__ = [
    "read_current_playbook",
    "read_playbook",
    "search_current_knowledge",
    "search_knowledge",
]
