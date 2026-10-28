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
MEMBER_CONTEXT_FIELD = 'capture_group_member_context'
_OFF_VALUES = frozenset({'0', 'false', 'off', 'no'})
_SHARED_SPEECH_METHODS = frozenset({'overlap_shared_speech_v1', 'shared_speech'})
_SHAREABLE_VISIBILITIES = frozenset({'shared', 'public'})


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


def capture_group_record(conversation: Any) -> Any:
    return (
        conversation.get('capture_group')
        if isinstance(conversation, Mapping)
        else getattr(conversation, 'capture_group', None)
    )


def _value(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def is_shared_speech_group(conversation: Any) -> bool:
    """Fail closed unless every member carries accepted shared-speech evidence."""
    group = capture_group_record(conversation)
    if group is None or _value(group, 'kind') == 'desktop_pendant_call':
        return False
    members = _value(group, 'members') or ()
    if len(members) < 2:
        return False
    for member in members:
        evidence = _value(member, 'evidence')
        if not isinstance(evidence, Mapping) or evidence.get('method') not in _SHARED_SPEECH_METHODS:
            return False
    return True


def shared_speech_group_record(
    uid: str,
    conversation: Any,
    *,
    firestore_client: Any = None,
) -> Optional[Any]:
    """Return current raw group provenance, loading it when the client model omits it."""
    group = capture_group_record(conversation)
    if is_shared_speech_group({'capture_group': group}):
        return group
    conversation_id = conversation.get('id') if isinstance(conversation, Mapping) else getattr(conversation, 'id', None)
    if not isinstance(conversation_id, str) or not conversation_id or group is None:
        return None
    try:
        row = conversations_db.get_conversation_raw_snapshot(
            uid,
            conversation_id,
            field_paths=['capture_group'],
            firestore_client=firestore_client,
        )
    except Exception as exc:  # noqa: BLE001 - provenance failures must fail closed
        logger.warning('capture group provenance read failed: %s', type(exc).__name__)
        return None
    raw_group = (row or {}).get('capture_group')
    return raw_group if is_shared_speech_group({'capture_group': raw_group}) else None


def member_row_is_shareable(row: Optional[Mapping[str, Any]]) -> bool:
    """Only already-shareable captures may contribute identity to a group note."""
    return bool(row) and not row.get('deleted') and row.get('visibility') in _SHAREABLE_VISIBILITIES


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
    group_record: Any = None,
    firestore_client: Any = None,
) -> dict[str, Mapping[str, Any]]:
    """Raw rows of the *other* group members, bounded by the group cap.

    Field-projected snapshots: only the identity-relevant fields are read, so
    member transcripts are never decrypted here.
    """
    group = group_record or shared_speech_group_record(uid, conversation, firestore_client=firestore_client)
    if group is None or not is_shared_speech_group({'capture_group': group}):
        return {}
    own_id = str(
        conversation.get('id') if isinstance(conversation, Mapping) else getattr(conversation, 'id', None) or ''
    )
    rows: dict[str, Mapping[str, Any]] = {}
    for member in group_members({'capture_group': group}):
        if member['id'] == own_id:
            continue
        try:
            row = conversations_db.get_conversation_raw_snapshot(
                uid,
                member['id'],
                field_paths=['external_data', 'visibility', 'deleted', 'screenshot_sharing_enabled'],
                firestore_client=firestore_client,
            )
        except Exception as exc:  # noqa: BLE001 - member identity is best effort
            logger.warning('capture group member row read failed: %s', type(exc).__name__)
            continue
        if row is not None and member_row_is_shareable(row):
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
    group = shared_speech_group_record(uid, conversation, firestore_client=firestore_client)
    if group is None:
        return None
    rows = (
        member_rows
        if member_rows is not None
        else member_context_rows(
            uid,
            conversation,
            group_record=group,
            firestore_client=firestore_client,
        )
    )
    rows = {member_id: row for member_id, row in rows.items() if member_row_is_shareable(row)}
    merged: Optional[CalendarMeetingContext] = None
    for member in group_members({'capture_group': group}):
        context = _context_from_row(rows.get(member['id']))
        merged = merge_meeting_contexts(merged, context)
    return merged


@dataclass(frozen=True)
class PrimaryNotesGap:
    """A new evidence-bearing member can improve the primary's notes."""

    group_id: str
    revision: int
    primary_id: str
    member_context: Optional[CalendarMeetingContext]


def primary_notes_gap(
    primary_row: Mapping[str, Any],
    member_rows: Mapping[str, Mapping[str, Any]],
    *,
    has_new_meeting_evidence: bool = False,
) -> Optional[PrimaryNotesGap]:
    """Return a refresh only for new evidence in an eligible shared-speech group."""
    group = primary_row.get('capture_group') or {}
    if not is_shared_speech_group({'capture_group': group}) or not has_new_meeting_evidence:
        return None
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
        if isinstance(member_id, str) and member_row_is_shareable(member_rows.get(member_id)):
            merged = merge_meeting_contexts(merged, _context_from_row(member_rows.get(member_id)))
    return PrimaryNotesGap(str(group_id), int(group.get('revision') or 0), primary_id, merged)
