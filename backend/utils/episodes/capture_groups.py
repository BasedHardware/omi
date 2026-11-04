"""Canonical episode membership for confirmed copies of the same captured speech."""

from typing import Any, Mapping, Optional

from database import episodes, conversations


def primary_id(row: Mapping[str, Any]) -> Optional[str]:
    group = row.get('capture_group') or row.get('capture_group_member_context') or {}
    return group.get('primary_id') if isinstance(group, Mapping) else None


def canonical_row(uid, conversation_id, row, *, firestore_client=None):
    primary = primary_id(row)
    if not primary or primary == conversation_id:
        return None
    canonical = conversations.get_conversation(uid, primary, firestore_client=firestore_client)
    return (
        canonical
        if canonical and not any(canonical.get(k) for k in ('discarded', 'deleted', 'sync_merged_into'))
        else None
    )


def join_duplicates(
    uid: str, owner: Mapping[str, Any], cid: str, row: Mapping[str, Any], *, firestore_client: Any = None
) -> None:
    group = row.get('capture_group') or {}
    ids = [m['id'] for m in group.get('members') or [] if isinstance(m, Mapping) and m.get('id') and m['id'] != cid]
    if not ids:
        return
    duplicates = sorted(set(owner.get('duplicate_conversation_ids') or []) | set(ids))
    content_removed = any(m.get('conversation_id') in duplicates for m in owner.get('moments') or [])
    updates: dict[str, Any] = {
        'conversation_ids': list(dict.fromkeys([*(owner.get('conversation_ids') or []), *ids])),
        'duplicate_conversation_ids': duplicates,
    }
    if content_removed:
        updates.update(title='', bullets=[], people=[], open_questions=[], summary_needs_regeneration=True)
    episodes.update_episode(
        uid,
        str(owner['id']),
        expected_version=int(owner.get('state_version') or 0),
        updates=updates,
        link_conversation_ids=ids,
        firestore_client=firestore_client,
    )


def calendar_identity(row: Mapping[str, Any]) -> Optional[str]:
    external = row.get('external_data') if isinstance(row.get('external_data'), Mapping) else {}
    context = external.get('calendar_meeting_context') if isinstance(external, Mapping) else None
    event_id = (context or {}).get('calendar_event_id') if isinstance(context, Mapping) else None
    event_id = event_id or (external or {}).get('calendar_event_id')
    return str(event_id) if event_id else None
