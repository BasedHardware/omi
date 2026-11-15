"""Detach only a conversation already authorized for empty-live deletion.

Prepare performs reads only. Apply is called inside the owning deletion
transaction after every session/episode read, so deletion and detach commit
atomically and Firestore's read-before-write rule is preserved.
"""

from typing import Any, Mapping

from config.episode_composition import empty_member_cleanup_enabled

_LISTS = ('conversation_ids', 'recovered_conversation_ids', 'discarded_conversation_ids', 'duplicate_conversation_ids')
_MAPS = ('recorded_members', 'member_activity', 'parallel_content_spans', 'applied', 'applied_segment_ids')


def prepare(transaction: Any, client: Any, uid: str, cid: str, conversation: Mapping[str, Any]) -> list:
    if not empty_member_cleanup_enabled():
        return []
    root = client.collection('users').document(uid)
    link = root.collection('episode_links').document(cid)
    linked = link.get(transaction=transaction).to_dict() or {}
    targets = {
        value
        for value in (linked.get('episode_id'), conversation.get('episode_id'))
        if isinstance(value, str) and value
    }
    if not targets:
        return []
    fence = root.collection('episode_links').document('recorded_timeline')
    fence_row = fence.get(transaction=transaction).to_dict() or {}
    writes = []
    for episode_id in sorted(targets):
        ref = root.collection('episodes').document(episode_id)
        row = ref.get(transaction=transaction).to_dict() or {}
        if cid not in (row.get('conversation_ids') or []):
            continue
        updates: dict[str, Any] = {
            key: [value for value in row.get(key) or [] if value != cid] for key in _LISTS if key in row
        }
        updates.update(
            {key: {k: v for k, v in (row.get(key) or {}).items() if k != cid} for key in _MAPS if key in row}
        )
        updates.update(
            state_version=int(row.get('state_version') or 0) + 1, recorded_partition=None, home_needs_prepare=True
        )
        if row.get('primary_conversation_id') == cid:
            updates['primary_conversation_id'] = next(iter(updates.get('conversation_ids') or []), None)
        writes.append((ref, updates))
    if writes:
        writes.append((fence, {**fence_row, 'version': int(fence_row.get('version') or 0) + 1}))
    # A missing episode must not leave the deleted conversation's reverse link dangling either.
    if linked:
        writes.append((link, None))
    return writes


def apply(transaction: Any, writes: list) -> None:
    for ref, updates in writes:
        if updates is None:
            transaction.delete(ref)
        elif ref.id == 'recorded_timeline':
            transaction.set(ref, updates)
        else:
            transaction.update(ref, updates)


def preserve_registered_audio(conversation: Mapping[str, Any]) -> bool:
    """The episode cleanup repair never authorizes deleting a registered recording."""
    return bool(
        conversation.get('audio_files')
        or conversation.get('server_batch_audio_received') is True
        or conversation.get('server_batch_audio_start') is not None
        or conversation.get('server_batch_audio_end') is not None
    )
