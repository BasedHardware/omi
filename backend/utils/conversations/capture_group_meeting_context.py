"""Meeting identity carried by a capture group's members (#3244).

The shared-speech capture group confirms that its members recorded one event.
Clients render the primary row only, and the primary is the longest window —
often the pendant, whose own capture carries no meeting identity. When a
desktop meeting member holds ``external_data.calendar_meeting_context``
(participants, title) or approved screen frames, that identity describes the
event the user will read, so the primary's notes must see it.

Two seams consume this module:

- summarization-time context resolution (``_enrich_meeting_context``) merges
  member contexts through the ``member_contexts`` layer of
  ``resolve_meeting_context``;
- ``utils.conversations.capture_group_notes_refresh`` regenerates the primary's
  notes once per group revision when grouping delivered meeting context after
  the primary was already summarized.

Everything here is bounded and best effort: no member read may fail the
conversation being processed, and grouping itself stays metadata-only.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Mapping, Optional

from database import conversations as conversations_db
from models.calendar_context import CalendarMeetingContext
from utils.conversations.meeting_context import merge_meeting_contexts

logger = logging.getLogger(__name__)

KILL_SWITCH_ENV = 'CAPTURE_GROUP_PRIMARY_NOTES_REFRESH_ENABLED'
NOTES_REVISION_FIELD = 'capture_group_notes_revision'
_OFF_VALUES = frozenset({'0', 'false', 'off', 'no'})


def capture_group_primary_notes_enabled() -> bool:
    """On unless explicitly turned off (kill switch; repository norm)."""
    return os.getenv(KILL_SWITCH_ENV, 'true').strip().casefold() not in _OFF_VALUES


def dispatch_primary_notes_refresh(uid: str, conversation: Any) -> None:
    """Offer a just-finalized row to the primary notes refresh, sync/REST path.

    ``utils.conversations.capture_group_notes_refresh`` imports
    ``process_conversation``, so this dispatch loads it lazily exactly like
    ``meeting_notes_wiring``'s ``meeting_context_sources`` seam. Best effort:
    never raises into the caller.
    """
    conversation_id = str(
        conversation.get('id') if isinstance(conversation, Mapping) else getattr(conversation, 'id', None) or ''
    )
    if not conversation_id:
        return
    try:
        import_module('utils.conversations.capture_group_notes_refresh').refresh_primary_notes(uid, conversation_id)
    except Exception:
        logger.warning('event=capture_group_notes_refresh outcome=error exception_type=import_or_dispatch')


def group_members(conversation: Any) -> list[dict[str, Any]]:
    """``[{'id', 'source'}, ...]`` for the conversation's capture-group members."""
    group = (
        conversation.get('capture_group')
        if isinstance(conversation, Mapping)
        else getattr(conversation, 'capture_group', None)
    )
    if group is None:
        return []
    raw = group.get('members') if isinstance(group, Mapping) else getattr(group, 'members', None)
    members: list[dict[str, Any]] = []
    for member in raw or ():
        mid = member.get('id') if isinstance(member, Mapping) else getattr(member, 'id', None)
        source = member.get('source') if isinstance(member, Mapping) else getattr(member, 'source', None)
        if isinstance(mid, str) and mid:
            members.append({'id': mid, 'source': str(source) if source is not None else None})
    return members


def _context_from_row(row: Optional[Mapping[str, Any]]) -> Optional[CalendarMeetingContext]:
    external = (row or {}).get('external_data')
    if not isinstance(external, Mapping):
        return None
    raw = external.get('calendar_meeting_context')
    if not isinstance(raw, Mapping) or not raw:
        return None
    try:
        return CalendarMeetingContext(**raw)
    except Exception:
        return None


def member_context_rows(
    uid: str,
    conversation: Any,
    *,
    firestore_client: Any = None,
) -> dict[str, Mapping[str, Any]]:
    """Raw rows of the *other* group members, bounded by the group cap.

    Field-projected snapshots: only the identity-relevant fields are read, so
    member transcripts are never decrypted here.
    """
    own_id = str(
        conversation.get('id') if isinstance(conversation, Mapping) else getattr(conversation, 'id', None) or ''
    )
    rows: dict[str, Mapping[str, Any]] = {}
    for member in group_members(conversation):
        if member['id'] == own_id:
            continue
        try:
            row = conversations_db.get_conversation_raw_snapshot(
                uid,
                member['id'],
                field_paths=['external_data'],
                firestore_client=firestore_client,
            )
        except Exception as exc:  # noqa: BLE001 - member identity is best effort
            logger.warning('capture group member row read failed: %s', type(exc).__name__)
            continue
        if row is not None:
            rows[member['id']] = row
    return rows


def merged_member_contexts(
    uid: str,
    conversation: Any,
    *,
    member_rows: Optional[Mapping[str, Mapping[str, Any]]] = None,
    firestore_client: Any = None,
) -> Optional[CalendarMeetingContext]:
    """The members' stored meeting contexts merged in record order, or None."""
    if not capture_group_primary_notes_enabled():
        return None
    rows = (
        member_rows
        if member_rows is not None
        else member_context_rows(uid, conversation, firestore_client=firestore_client)
    )
    merged: Optional[CalendarMeetingContext] = None
    for member in group_members(conversation):
        context = _context_from_row(rows.get(member['id']))
        merged = merge_meeting_contexts(merged, context)
    return merged


def _participant_identity(participant: Any) -> Optional[tuple[str, str]]:
    name = (getattr(participant, 'name', None) or '').casefold()
    email = (getattr(participant, 'email', None) or '').casefold()
    identity = (name, email)
    return identity if identity != ('', '') else None


@dataclass(frozen=True)
class PrimaryNotesGap:
    """The primary's notes miss meeting identity that confirmed members carry."""

    group_id: str
    revision: int
    primary_id: str
    member_context: CalendarMeetingContext


def primary_notes_gap(
    primary_row: Mapping[str, Any],
    member_rows: Mapping[str, Mapping[str, Any]],
) -> Optional[PrimaryNotesGap]:
    """Whether the group primary's stored context misses member-held identity.

    Pure: callers pass the current primary row and the members' raw rows. A gap
    exists when the primary has not summarized this group revision, has no
    stored context at all, or when the merged member context names at least
    one participant (by name or email) the
    primary's stored context does not. After one refresh the primary stores the
    merged context and revision receipt, so the same state stops qualifying.
    New membership qualifies even with the same roster, to include new frames.
    """
    group = primary_row.get('capture_group') or {}
    group_id = group.get('id')
    primary_id = primary_row.get('id')
    if not group_id or not isinstance(primary_id, str):
        return None
    others = [m for m in group.get('members') or [] if isinstance(m, Mapping) and m.get('id') != primary_id]
    if not others:
        return None
    merged: Optional[CalendarMeetingContext] = None
    for member in others:
        member_id = member.get('id')
        if isinstance(member_id, str):
            merged = merge_meeting_contexts(merged, _context_from_row(member_rows.get(member_id)))
    if merged is None:
        return None
    receipt = (primary_row.get('external_data') or {}).get(NOTES_REVISION_FIELD)
    if receipt != {'group_id': str(group_id), 'revision': int(group.get('revision') or 0)}:
        return PrimaryNotesGap(str(group_id), int(group.get('revision') or 0), primary_id, merged)
    primary_context = _context_from_row(primary_row)
    if primary_context is None:
        return PrimaryNotesGap(str(group_id), int(group.get('revision') or 0), primary_id, merged)
    known = {identity for identity in map(_participant_identity, primary_context.participants) if identity}
    member_identities = {identity for identity in map(_participant_identity, merged.participants) if identity}
    if member_identities - known:
        return PrimaryNotesGap(str(group_id), int(group.get('revision') or 0), primary_id, merged)
    return None
