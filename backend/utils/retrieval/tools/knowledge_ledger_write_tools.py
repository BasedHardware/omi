"""JIT-gated write verbs for the intent-backed knowledge ledger.

These tools are the only production callers of ``write_playbook``,
``create_trigger``, and ``close_fact`` in ``utils.memory.knowledge_ledger``.
Each one enforces a narrow, explicit-intent contract before delegating to the
canonical ledger authority: a playbook only after a recurring workflow has
actually been reconstructed, a trigger only from articulated standing intent
using deterministic selectors, and a fact close only for an owner-scoped
current fact. Errors from bad input or a rejected mutation are returned as
plain strings; nothing here lets a malformed tool call raise into the agent
loop.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Mapping, Optional, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

from database._client import get_data_plane_firestore_client
from models.knowledge_ledger_policy import PLAYBOOK_HANDLE_CHARACTER_LIMIT
from models.memory_contracts import deterministic_contract_id
from models.product_memory import MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS, MemoryKind, MemorySubjectScope
from utils.log_sanitizer import sanitize_pii
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from utils.memory.jit_trigger_contract import (
    DEFAULT_TRIGGER_RUNTIME_POLICY,
    MAX_TRIGGER_ACTION_PROMPT_CHARS,
    compile_trigger_condition,
)
from utils.memory.knowledge_ledger import (
    LEDGER_SCHEMA_VERSION,
    LedgerProvenance,
    close_fact as close_ledger_fact,
    create_trigger,
    write_playbook,
)

logger = logging.getLogger(__name__)

MAX_SAVE_PLAYBOOK_DESCRIPTION_CHARACTERS = PLAYBOOK_HANDLE_CHARACTER_LIMIT
MAX_SAVE_PLAYBOOK_BODY_CHARACTERS = MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS
MAX_TRIGGER_DESCRIPTION_CHARACTERS = MAX_TRIGGER_ACTION_PROMPT_CHARS
MAX_CLOSE_FACT_REASON_CHARACTERS = 500
MAX_MEMORY_ID_CHARACTERS = 256
_MEMORY_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")

# Only deterministic local selectors are admitted. ``embedding`` is a known
# schema field but is intentionally not in this set: TriggerEmbeddingPolicy is
# disabled pending scorer attestation, so an embedding selector is rejected
# below with an explicit error rather than silently accepted and then never
# matching anything.
_ALLOWED_TRIGGER_CONDITION_FIELDS = frozenset(
    {"match_mode", "entity_aliases", "keywords", "regex", "apps", "windows", "time", "calendar"}
)

# The paid-work snapshot (utils.memory.jit_trigger_snapshot) only admits a
# trigger whose ``arguments.wakeup_budget_per_day`` matches this exact policy
# value; anything else makes the row invisible to the desktop watchlist.
_TRIGGER_ARGUMENTS = {"wakeup_budget_per_day": DEFAULT_TRIGGER_RUNTIME_POLICY.planned_notifications_per_trigger_per_day}


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
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


def _write_provenance(
    uid: str, *, source_version: str, action_payload: Dict[str, Any], config: RunnableConfig
) -> LedgerProvenance:
    """Build retry-stable provenance for one agent-authored ledger write verb."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config) or _agent_config()
    configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
    configurable = configurable if isinstance(configurable, dict) else {}
    source_id = str(configurable.get("chat_session_id") or configurable.get("thread_id") or "direct-agent-tool").strip()
    action_id = (
        "agent-"
        + source_version
        + ":"
        + deterministic_contract_id(
            "agent-ledger-write",
            {"uid": uid, "source_id": source_id, "source_version": source_version, **action_payload},
        )[:32]
    )
    artifact_ref = {"chat_session_id": source_id} if configurable.get("chat_session_id") else {}
    return LedgerProvenance(
        source_id=source_id,
        source_type="agent_chat",
        source_version=source_version,
        action_id=action_id,
        artifact_ref=artifact_ref,
    )


def _reject_disallowed_trigger_condition_fields(condition: Mapping[str, Any]) -> Optional[str]:
    """Fail closed on any selector this contract does not admit yet.

    Embedding selectors get a dedicated, explicit message: they are a known
    field on the schema, disabled pending scorer attestation, and must never
    be silently dropped or accepted as a no-op selector.
    """
    if "embedding" in condition:
        return (
            "embedding-based trigger selectors are not available (the embedding scorer "
            "attestation is not enabled); use entity/alias, keyword/regex, app/window, time, or "
            "calendar selectors instead"
        )
    if "action" in condition:
        return "condition must not set 'action'; describe what to do in the description argument"
    extra = sorted(set(condition) - _ALLOWED_TRIGGER_CONDITION_FIELDS)
    if extra:
        return f"unsupported trigger condition field(s): {', '.join(extra)}"
    return None


def build_paid_trigger_condition(description: str, condition: Mapping[str, Any]) -> Dict[str, Any]:
    """Compile one deterministic, paid-work-authoritative trigger condition.

    Raises ``ValueError`` (including from pydantic validation) for a
    malformed or disallowed selector. The returned dict is the exact
    canonical JSON shape stored as ``MemoryItem.trigger_condition`` and read
    back by ``utils.memory.jit_trigger_snapshot.read_authoritative_trigger_snapshot``.
    """
    rejection = _reject_disallowed_trigger_condition_fields(condition)
    if rejection is not None:
        raise ValueError(rejection)
    full_condition = {**condition, "action": {"type": "agent_prompt", "prompt": description}}
    compiled = compile_trigger_condition(full_condition)
    return compiled.as_condition()


@tool
def save_playbook(description: str, body: str, config: RunnableConfig = None) -> str:  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
    """Save a reusable step-by-step playbook for a recurring, involved workflow.

    Call this only after you have actually reconstructed a multi-step
    workflow the user repeats — a release checklist, a weekly report routine,
    an onboarding sequence — and it is worth recalling verbatim next time.

    Do NOT call this for a one-off task, a simple fact or preference (use
    ``save_user_preference_tool`` instead), or a workflow you have not
    actually walked through end to end.

    Args:
        description: A short, single-line handle for this playbook (at most
            360 characters). This is what ``search_knowledge`` shows when
            browsing playbooks, so keep it scannable, e.g. "Cut a release
            candidate".
        body: The full step-by-step playbook content (at most 24,000
            characters).
    """
    uid = _resolve_uid(config)
    if not uid:
        return "Error: Could not determine user ID"

    normalized_description = " ".join((description or "").split())
    normalized_body = (body or "").strip()
    if not normalized_description:
        return "Error: description must not be blank"
    if len(normalized_description) > MAX_SAVE_PLAYBOOK_DESCRIPTION_CHARACTERS:
        return f"Error: description must be at most {MAX_SAVE_PLAYBOOK_DESCRIPTION_CHARACTERS} characters"
    if not normalized_body:
        return "Error: body must not be blank"
    if len(normalized_body) > MAX_SAVE_PLAYBOOK_BODY_CHARACTERS:
        return f"Error: body must be at most {MAX_SAVE_PLAYBOOK_BODY_CHARACTERS} characters"

    try:
        firestore_client = get_data_plane_firestore_client()
    except Exception as exc:
        logger.error("Failed to resolve playbook storage error_type=%s", type(exc).__name__)
        return "Error saving playbook"

    try:
        provenance = _write_provenance(
            uid,
            source_version="save_playbook.v1",
            action_payload={"description": normalized_description, "body": normalized_body},
            config=config,
        )
        memory_id = write_playbook(
            uid,
            normalized_description,
            normalized_body,
            provenance=provenance,
            db_client=firestore_client,
        )
        logger.info("Saved playbook: %s", sanitize_pii(normalized_description))
        return f"Playbook saved ({memory_id}): {normalized_description}"
    except ValueError as exc:
        logger.info("Rejected playbook write error_type=%s", type(exc).__name__)
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("Failed to save playbook error_type=%s", type(exc).__name__)
        return "Error saving playbook"


@tool
def create_standing_trigger(
    description: str,
    condition: Dict[str, Any],
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """Create a standing watch that notifies the user when a condition recurs.

    Call this ONLY when the user has explicitly articulated a standing
    intent in this conversation — e.g. "watch for emails from Jane and tell
    me" or "let me know whenever the deploy channel mentions an incident".
    Never call it from a pattern you merely noticed in passive behavior; an
    inferred habit is not standing intent (ratified 12/13).

    ``condition`` must use only deterministic selectors: ``entity_aliases``
    (a map of entity name to a list of aliases), ``keywords``, ``regex``,
    ``apps``, ``windows``, ``time`` (``weekdays``/``start``/``end``/
    ``timezone``), and ``calendar`` (``event_keywords``/``event_types``).
    ``match_mode`` may be ``"all"`` (default, every selector must match) or
    ``"any"``. Embedding/semantic selectors are not supported and are
    rejected.

    Args:
        description: What to tell the user when this trigger fires, in your
            own words (at most 2000 characters), e.g. "Tell the user Jane
            emailed about the contract."
        condition: The deterministic selector payload described above.
    """
    uid = _resolve_uid(config)
    if not uid:
        return "Error: Could not determine user ID"

    normalized_description = " ".join((description or "").split())
    if not normalized_description:
        return "Error: description must not be blank"
    if len(normalized_description) > MAX_TRIGGER_DESCRIPTION_CHARACTERS:
        return f"Error: description must be at most {MAX_TRIGGER_DESCRIPTION_CHARACTERS} characters"

    try:
        compiled_condition = build_paid_trigger_condition(normalized_description, condition)
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        firestore_client = get_data_plane_firestore_client()
    except Exception as exc:
        logger.error("Failed to resolve trigger storage error_type=%s", type(exc).__name__)
        return "Error creating standing trigger"

    try:
        provenance = _write_provenance(
            uid,
            source_version="create_standing_trigger.v1",
            action_payload={"description": normalized_description, "condition": compiled_condition},
            config=config,
        )
        memory_id = create_trigger(
            uid,
            normalized_description,
            compiled_condition,
            provenance=provenance,
            arguments=dict(_TRIGGER_ARGUMENTS),
            db_client=firestore_client,
        )
        logger.info("Created standing trigger: %s", sanitize_pii(normalized_description))
        return f"Standing trigger created ({memory_id}): {normalized_description}"
    except ValueError as exc:
        logger.info("Rejected trigger write error_type=%s", type(exc).__name__)
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("Failed to create standing trigger error_type=%s", type(exc).__name__)
        return "Error creating standing trigger"


@tool("close_fact")
def close_fact_tool(memory_id: str, reason: str, config: RunnableConfig = None) -> str:  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
    """Close a current fact that is no longer true, with no replacement fact.

    Call this for "that's no longer true" when nothing should replace the
    closed fact. If something does replace it, that is an update, not a
    close — save the new fact instead (the ledger will supersede the old
    one). The closed row stays in history for audit; it stops appearing as
    current knowledge.

    Args:
        memory_id: The current ledger fact's memory id, e.g. from
            ``search_knowledge``.
        reason: A short explanation of why the fact no longer holds (kept in
            logs for audit context, at most 500 characters).
    """
    uid = _resolve_uid(config)
    if not uid:
        return "Error: Could not determine user ID"

    normalized_memory_id = (memory_id or "").strip()
    normalized_reason = " ".join((reason or "").split())
    if (
        not normalized_memory_id
        or len(normalized_memory_id) > MAX_MEMORY_ID_CHARACTERS
        or _MEMORY_ID_PATTERN.fullmatch(normalized_memory_id) is None
    ):
        return "Error: invalid memory id"
    if not normalized_reason:
        return "Error: reason must not be blank"
    if len(normalized_reason) > MAX_CLOSE_FACT_REASON_CHARACTERS:
        return f"Error: reason must be at most {MAX_CLOSE_FACT_REASON_CHARACTERS} characters"

    try:
        firestore_client = get_data_plane_firestore_client()
    except Exception as exc:
        logger.error("Failed to resolve fact storage error_type=%s", type(exc).__name__)
        return "Fact could not be closed"

    try:
        # ``read_canonical_memory_item`` only ever returns an active row, so a
        # foreign-owned id and an already-closed id (its status moves to
        # superseded the moment it closes) both land here as a not-found —
        # the same safe, non-raising outcome ``read_playbook`` uses for its
        # equivalent cases.
        item = read_canonical_memory_item(uid, normalized_memory_id, db_client=firestore_client)
        if (
            item is None
            or item.uid != uid
            or item.ledger_schema_version != LEDGER_SCHEMA_VERSION
            or item.kind != MemoryKind.fact
            or item.subject_scope != MemorySubjectScope.primary_user
        ):
            return "Fact unavailable."
        close_ledger_fact(uid, normalized_memory_id, db_client=firestore_client)
        logger.info("Closed fact reason=%s", sanitize_pii(normalized_reason))
        return f"Fact closed ({normalized_memory_id})."
    except ValueError as exc:
        # A race against a concurrent close/mutation surfaces here even though
        # the read above found an active row a moment earlier.
        logger.info("Fact close rejected error_type=%s", type(exc).__name__)
        return "Fact is already closed or unavailable."
    except Exception as exc:
        logger.error("Failed to close fact error_type=%s", type(exc).__name__)
        return "Fact could not be closed"


__all__ = [
    "build_paid_trigger_condition",
    "close_fact_tool",
    "create_standing_trigger",
    "save_playbook",
]
