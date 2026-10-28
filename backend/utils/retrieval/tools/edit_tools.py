"""Shared user-requested edits; domain services remain the mutation authority."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from database import conversations, users
from database._client import get_data_plane_firestore_client
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from database import chat_edits
from database.chat_edits import envelope
from utils.messaging.undo import record_write
from utils.mcp_server.handlers import other as mcp_people
from utils.retrieval.turn_refs import resolve_edit_ref, tool_error


def _configurable(config: Any) -> Dict[str, Any]:
    # Runtime callers may pass a non-dict despite the RunnableConfig annotation (#23408).
    return (config.get('configurable') if isinstance(config, dict) else None) or {}


def owner(config):
    config = config or {}
    configurable = config.get('configurable') if isinstance(config, dict) else None
    uid = (configurable or {}).get('user_id')
    if not uid:
        raise PermissionError('Authenticated owner required')
    return uid


@tool
def update_conversation(
    conversation_id: Optional[str] = None,
    correction: str = '',
    title: Optional[str] = None,
    overview: Optional[str] = None,
    *,
    config: RunnableConfig,
) -> str:
    """Change a conversation title and/or overview only when the user asks or confirms a proposed correction.

    Omit conversation_id to use the user-attached conversation; otherwise use an
    owned ID attached or returned by search/read in this turn. correction is the user's confirmed
    correction, stored as a durable note used on later reprocessing. Never rewrite
    a transcript or delete a whole conversation. Returns a structured undo receipt.
    """
    uid = owner(config)
    configurable = _configurable(config)
    conversation_id, error = resolve_edit_ref(
        configurable,
        'conversations',
        conversation_id,
        parameter='conversation_id',
        default_to_attachment=True,
    )
    if error:
        return error
    assert conversation_id is not None
    if not correction.strip() or len(correction) > 2000 or (title is None and overview is None):
        return tool_error('invalid_correction', 'Provide a confirmed correction and a title or overview.')
    if title is not None and (not title.strip() or len(title) > 300):
        return tool_error('invalid_title', 'Title must contain 1 to 300 characters.')
    if overview is not None and (not overview.strip() or len(overview) > 20000):
        return tool_error('invalid_overview', 'Overview must contain 1 to 20000 characters.')
    row = conversations.get_conversation(uid, conversation_id)
    if not row or row.get('deleted'):
        return tool_error('conversation_not_found', 'Conversation not found for the authenticated owner.')
    if row.get('is_locked'):
        return tool_error('conversation_locked', 'Conversation is locked and cannot be edited.')
    before = cast(Dict[str, Any], chat_edits.snapshot(uid, 'conversation', conversation_id))
    observed = conversations.prepare_conversation_for_read(cast(Dict[str, Any], chat_edits.decode(before)), uid) or {}
    structured = dict(observed.get('structured') or {})
    notes = list(observed.get('user_corrections') or [])
    corrected_at = datetime.now(timezone.utc).isoformat()  # not-model-facing: persisted edit metadata
    notes.append({'note': correction.strip(), 'at': corrected_at})
    if len(notes) > 100:
        return tool_error('correction_limit_reached', 'Conversation correction note limit reached (100).')
    patch: Dict[str, Any] = {'user_corrections': notes}
    if title is not None:
        structured['title'] = title.strip()
        patch['user_title'] = title.strip()
    if overview is not None:
        structured['overview'] = overview.strip()
        patch['user_overview'] = overview.strip()
    patch['structured'] = structured
    after = conversations.update_conversation_chat(uid, conversation_id, before, patch)
    summary = 'Title → ' + title.strip() if title is not None else 'Overview updated'
    record_write(uid, 'conversation', conversation_id, envelope(before, 'Conversation'), envelope(after, summary))
    return summary


@tool
def rename_person(person_id: str, name: str, *, config: RunnableConfig) -> str:
    """Rename a person only when the user asks or confirms a proposed correction.

    Retrieve the owned person ID first. Reuses the MCP rename implementation,
    retaining the previous name as an alias. Undo restores the prior name and aliases.
    """
    uid = owner(config)
    configurable = _configurable(config)
    resolved_id, error = resolve_edit_ref(configurable, 'people', person_id, parameter='person_id')
    if error:
        return error
    assert resolved_id is not None
    person_id = resolved_id
    clean_name = str(name or '').strip()
    if not clean_name or len(clean_name) > 100:
        return tool_error('invalid_name', 'Person name must contain 1 to 100 characters.')
    if not users.get_person(uid, person_id):
        return 'Error: person not found.'
    before = chat_edits.snapshot(uid, 'person', person_id)
    write_state = {'before': before}
    result = mcp_people.rename_person(
        uid, {'person_id': person_id, 'name': clean_name}, expected_chat_state=write_state
    )
    after = write_state['after']
    summary = 'Name → ' + result['person']['name']
    record_write(uid, 'person', person_id, envelope(before, 'Person'), envelope(after, summary))
    return summary


@tool
def edit_memory(memory_id: str, content: str, *, config: RunnableConfig) -> str:
    """Edit a saved memory only when the user asks or confirms a proposed correction.

    Retrieve the owned memory ID first. Uses the same MemoryService method as MCP,
    preserving canonical correction history. Returns a structured undo receipt.
    """
    uid = owner(config)
    configurable = _configurable(config)
    resolved_id, error = resolve_edit_ref(configurable, 'memories', memory_id, parameter='memory_id')
    if error:
        return error
    assert resolved_id is not None
    memory_id = resolved_id
    if not content.strip() or len(content) > 20000:
        return 'Error: memory content must contain 1 to 20000 characters.'
    db = get_data_plane_firestore_client()
    before = read_canonical_memory_item(uid, memory_id, db_client=db)
    if before is None or before.uid != uid or (before.promotion or {}).get('chat_deleted'):
        return 'Error: memory not found.'
    service = MemoryService(db_client=db)
    updated = service.update_external_memory_content(
        uid, memory_id, content, memory_system=MemorySystem.CANONICAL, consumer='chat', operation='chat_memory_edit'
    )
    target_id = updated.id
    after = read_canonical_memory_item(uid, target_id, db_client=db)
    if after is None:
        raise RuntimeError('Memory edit readback unavailable')
    record_write(uid, 'memory_edit', target_id, before.model_dump(mode='json'), after.model_dump(mode='json'))
    return 'Memory updated: ' + (after.content or '')


@tool
def delete_memory(memory_id: str, *, config: RunnableConfig) -> str:
    """Remove a memory from current knowledge only when the user asks or confirms.

    Retrieve the owned memory ID first. This is reversible removal, preserving
    canonical history; it is not permanent privacy erasure. Use app privacy
    controls for permanent erasure. Returns a structured undo receipt.
    """
    uid = owner(config)
    configurable = _configurable(config)
    resolved_id, error = resolve_edit_ref(configurable, 'memories', memory_id, parameter='memory_id')
    if error:
        return error
    assert resolved_id is not None
    memory_id = resolved_id
    db = get_data_plane_firestore_client()
    before = read_canonical_memory_item(uid, memory_id, db_client=db)
    if before is None or before.uid != uid or (before.promotion or {}).get('chat_deleted'):
        return 'Error: memory not found.'
    after = MemoryService(db_client=db).remove_chat_memory(uid, memory_id)
    record_write(uid, 'memory_deleted', memory_id, before.model_dump(mode='json'), after.model_dump(mode='json'))
    return 'Memory removed from current knowledge (history preserved).'
