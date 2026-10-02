"""Speaker-label and People write tools for the hosted MCP server.

``assign_speaker`` drives the same manual-assignment commit the app's
``/v1/conversations/{id}/...assign...`` routes use
(``utils.speaker_assignment_teaching.commit_manual_assignment``), so label
provenance, person label evidence, superseded-sample retirement, and voice
learning stay one implementation. ``create_person`` mirrors the REST
``POST /v1/users/people`` contract: idempotent by name, 2-40 characters.

Write responses carry ids and counts only, never transcript text or speech
samples, so a write grant does not widen what the caller can read.
"""

import asyncio
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import database.users as users_db
from utils.executors import postprocess_executor, submit_with_context
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_memories import parse_mcp_bool
from utils.mcp_server.constants import (
    MCP_CONVERSATION_ID_MAX_BYTES,
    MCP_PERSON_NAME_MAX_CHARS,
    MCP_PERSON_NAME_MIN_CHARS,
    MCP_SPEAKER_ASSIGN_MAX_ID_CHARS,
    MCP_SPEAKER_ASSIGN_MAX_SEGMENT_IDS,
)
from utils.mcp_server.errors import ToolExecutionError
from utils.speaker_assignment_teaching import commit_manual_assignment
from utils.speaker_permissions import named_speaker_prompts_allowed

ASSIGNEE_USER = "user"


def _run_deferred(fn: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
    if inspect.iscoroutinefunction(fn):
        asyncio.run(fn(*args, **kwargs))
    else:
        fn(*args, **kwargs)


class DeferredAssignmentTasks:
    """``BackgroundTasks``-shaped sink for follow-up work an assignment earned.

    Hosted MCP handlers run synchronously on ``db_executor`` with no request
    lifecycle to hang FastAPI background tasks on. The committed assignment's
    follow-ups (retiring superseded sample blobs, voice learning) go to
    ``postprocess_executor`` instead: best-effort and after the commit, as on
    the REST routes, with failures logged by ``submit_with_context``.
    """

    def add_task(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        submit_with_context(postprocess_executor, _run_deferred, fn, args, kwargs)


def _required_text(value: Any, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolExecutionError(f"{field} is required and must be a non-empty string", code=-32602)
    text = value.strip()
    if len(text) > max_chars:
        raise ToolExecutionError(f"{field} is too long (max {max_chars} characters)", code=-32602)
    return text


def _conversation_id(value: Any) -> str:
    conversation_id = _required_text(value, "conversation_id", max_chars=MCP_CONVERSATION_ID_MAX_BYTES)
    if len(conversation_id.encode("utf-8")) > MCP_CONVERSATION_ID_MAX_BYTES:
        raise ToolExecutionError("conversation_id is too long", code=-32602)
    return conversation_id


def _speaker_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolExecutionError("speaker_id must be a non-negative integer", code=-32602)
    return value


def _segment_ids(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ToolExecutionError("segment_ids must be a non-empty array of strings", code=-32602)
    if len(value) > MCP_SPEAKER_ASSIGN_MAX_SEGMENT_IDS:
        raise ToolExecutionError(
            f"segment_ids accepts at most {MCP_SPEAKER_ASSIGN_MAX_SEGMENT_IDS} ids; label a whole speaker with "
            "speaker_id instead",
            code=-32602,
        )
    ids: List[str] = []
    for item in value:
        segment_id = _required_text(item, "segment_ids[]", max_chars=MCP_SPEAKER_ASSIGN_MAX_ID_CHARS)
        if segment_id not in ids:
            ids.append(segment_id)
    return ids


def assign_speaker(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Label a diarized speaker (or specific segments) as the user or a saved person."""
    conversation_id = _conversation_id(arguments.get("conversation_id"))
    speaker_id = _speaker_id(arguments.get("speaker_id"))
    segment_ids = _segment_ids(arguments.get("segment_ids"))
    if speaker_id is None and segment_ids is None:
        raise ToolExecutionError("Provide speaker_id, segment_ids, or both.", code=-32602)
    assignee = _required_text(arguments.get("assignee"), "assignee", max_chars=MCP_SPEAKER_ASSIGN_MAX_ID_CHARS)
    try:
        use_for_speech_training = parse_mcp_bool(
            arguments.get("use_for_speech_training"), "use_for_speech_training", default=False
        )
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)

    is_user = assignee == ASSIGNEE_USER
    person_id = None if is_user else assignee
    # Same entitlement the app's manual assignment routes apply today.
    if person_id is not None and not named_speaker_prompts_allowed(uid):
        raise ToolExecutionError("Naming other people needs a paid plan.", code=-32002)

    try:
        raw, resolved, _removed, _before = commit_manual_assignment(
            uid,
            conversation_id,
            person_id=person_id,
            is_user=is_user,
            segment_ids=segment_ids,
            speaker_id=speaker_id,
            use_for_speech_training=use_for_speech_training,
            background_tasks=DeferredAssignmentTasks(),
        )
    except (KeyError, IndexError):
        # LookupError subclasses that signal a bug, not a missing record: let the
        # transport log the stack and answer ``internal``.
        raise
    except LookupError as error:
        # The commit's own not-found signals: conversation, segment, or person.
        raise ToolExecutionError(str(error), code=-32001) from error
    except PermissionError as error:
        raise ToolExecutionError("A paid plan is required to access this conversation.", code=-32002) from error
    except ValueError as error:
        # Unresolvable segment ids, or segments that do not belong to speaker_id.
        raise ToolExecutionError(str(error), code=-32602) from error

    return {
        "success": True,
        # A merged (sync-bridged) conversation resolves to its survivor.
        "conversation_id": raw.get("id") or conversation_id,
        "assignee": ASSIGNEE_USER if is_user else person_id,
        "updated_segment_count": len(resolved),
        "use_for_speech_training": use_for_speech_training,
    }


def create_person(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Add a person, or return the existing person with exactly that name."""
    name = arguments.get("name")
    if not isinstance(name, str):
        raise ToolExecutionError("name is required and must be a string", code=-32602)
    name = name.strip()
    if not MCP_PERSON_NAME_MIN_CHARS <= len(name) <= MCP_PERSON_NAME_MAX_CHARS:
        raise ToolExecutionError(
            f"name must be {MCP_PERSON_NAME_MIN_CHARS} to {MCP_PERSON_NAME_MAX_CHARS} characters", code=-32602
        )

    existing = users_db.get_person_by_name(uid, name)
    if existing:
        return {
            "success": True,
            "created": False,
            "person": {"id": existing.get("id", ""), "name": existing.get("name", name)},
        }

    now = datetime.now(timezone.utc)
    person = {"id": str(uuid.uuid4()), "name": name, "created_at": now, "updated_at": now}
    users_db.create_person(uid, person)
    return {"success": True, "created": True, "person": {"id": person["id"], "name": name}}
