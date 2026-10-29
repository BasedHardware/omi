"""Client read projection with only retained, extant episode members."""

from typing import Any, get_args

from database import conversations
from models.episode import EpisodeCloseReason
from utils.episodes import service


def wire_episode(episode: dict[str, Any] | None) -> dict[str, Any] | None:
    """Additive read fields, without changing the shared lifecycle service's wire helper."""
    if episode is None:
        return None
    wire = service.to_wire(episode)
    assert wire is not None  # Non-null input always has a wire projection.
    # Storage may gain internal boundary reasons before released clients can decode them.
    # Absence is already part of the released wire contract; never widen that enum.
    if wire.get('close_reason') not in get_args(EpisodeCloseReason):
        wire['close_reason'] = None
    return {**wire, 'emoji': episode.get('emoji') or '', 'members': []}


def project_episode(uid: str, episode: dict[str, Any] | None) -> dict[str, Any] | None:
    if episode is None:
        return None
    members: list[dict[str, Any]] = []
    for cid in dict.fromkeys(episode.get('conversation_ids') or []):
        raw = conversations.get_conversation_raw_snapshot(
            uid,
            cid,
            field_paths=[
                'structured',
                'user_title',
                'data_protection_level',
                'relevance_decision',
                'discarded',
                'deleted',
                'sync_merged_into',
                'dream_duplicate_of',
                'started_at',
                'finished_at',
                'created_at',
                'status',
            ],
        )
        if not raw:
            continue
        row = conversations.prepare_conversation_for_read(raw, uid)
        if row is None or not conversations.is_visible_conversation(row) or row.get('sync_merged_into'):
            continue
        structured = row.get('structured') or {}
        members.append(
            {
                'id': cid,
                'title': structured.get('title') or '',
                'emoji': structured.get('emoji') or '',
                'started_at': row.get('started_at') or row.get('created_at') or episode['started_at'],
                'finished_at': row.get('finished_at'),
                'status': row.get('status') or 'completed',
            }
        )
    if not members:
        return None
    ids = {member['id'] for member in members}
    wire = wire_episode(episode)
    assert wire is not None  # Non-null input always has a wire projection.
    wire.update(
        emoji=episode.get('emoji') or '',
        members=members,
        conversation_ids=[member['id'] for member in members],
        moments=[moment for moment in wire['moments'] if moment['conversation_id'] in ids],
        provisional_items=[
            item
            for item in wire['provisional_items']
            if not item.get('conversation_id') or item.get('conversation_id') in ids
        ],
    )
    return wire
