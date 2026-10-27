"""Ephemeral owned-record refs, populated by read tools rather than evidence text.

This is addressability, not write authorization or ownership. Domain services
still verify the authenticated owner on every mutation. Never parse record
content, titles, model arguments or historical messages into this registry.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TurnRefs:
    seen: set[tuple[str, str]] = field(default_factory=set)


def initialize_turn_refs(configurable: Any) -> TurnRefs:
    refs = TurnRefs()
    if not isinstance(configurable, dict):
        return refs
    scope = configurable.get('chat_scope') or {}
    target = scope.get('conversation_id')
    if isinstance(target, str) and target:
        refs.seen.add(('conversations', target))
    configurable['turn_refs'] = refs
    return refs


def register_record_ref(configurable: Any, collection: str, record_id: Any) -> None:
    """Read producers call this only for owned records admitted to model output."""
    if not isinstance(configurable, dict):
        return
    refs = configurable.get('turn_refs')
    if isinstance(refs, TurnRefs) and isinstance(record_id, str) and record_id:
        refs.seen.add((collection, record_id))


def tool_error(code: str, message: str, **details: Any) -> str:
    return json.dumps({'error': {'code': code, 'message': message, **details}})


def resolve_edit_ref(
    configurable: Any,
    collection: str,
    record_id: Optional[str],
    *,
    parameter: str,
    default_to_attachment: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve a default target and enforce attached-chat addressability for any ID tool."""
    if not isinstance(configurable, dict):
        configurable = {}
    scope = configurable.get('chat_scope') or {}
    attached = scope.get('conversation_id')
    target = record_id
    if target is None and default_to_attachment and collection == 'conversations':
        target = attached
    if isinstance(target, str) and target.startswith(collection + '/'):
        target = target[len(collection) + 1 :]
    if not isinstance(target, str) or not target.strip():
        return None, tool_error(
            'missing_record_ref', f'{parameter} is required; attach a record or call search/read first.'
        )
    refs = configurable.get('turn_refs')
    seen = refs.seen if isinstance(refs, TurnRefs) else set()
    is_attachment = collection == 'conversations' and target == attached
    if attached and not is_attachment and (collection, target) not in seen:
        return None, tool_error(
            'unseen_record_ref',
            f"{parameter} not in this chat's attached or retrieved records; call search/read first.",
            parameter=parameter,
            ref=f'{collection}/{target}',
        )
    return target, None
