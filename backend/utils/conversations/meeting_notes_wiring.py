"""Flag-gated rich meeting-notes inputs shared by the notes, memory, and app prompts.

The notes path gathers the background context pack; the memory and app prompts
share only the normalized roster. Everything here is best effort — every read
degrades to absent context and a failure logs only the exception class, never
payloads that could carry participant data. This module must never import
``process_conversation``; callers bring their conversation and calendar context.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from models.calendar_context import CalendarMeetingContext
from utils.conversations.meeting_context_pack import (
    gather_meeting_context_pack,
    load_people_documents,
    render_meeting_context_pack,
    resolve_owner_identity,
    should_gather_meeting_context,
)
from utils.conversations.meeting_participants import MeetingRoster, normalize_meeting_participants

logger = logging.getLogger(__name__)


def _flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def meeting_notes_rich_context_enabled() -> bool:
    return _flag_enabled('MEETING_NOTES_RICH_CONTEXT_ENABLED')


def meeting_notes_screen_text_context_enabled() -> bool:
    return _flag_enabled('MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED')


def _rich_meeting_roster(
    uid: str,
    conversation: Any,
    calendar_context: Optional[CalendarMeetingContext],
) -> Tuple[Optional[MeetingRoster], List[Dict[str, Any]], bool]:
    """Best-effort normalized roster plus the people-catalog read used for it.

    The roster exists whenever this is meeting-like — resolved meeting context,
    a desktop meeting-role capture, or the multi-party-speech gate — which is
    also the condition under which the background pack may be gathered. Every
    read inside degrades to absent context; nothing here may block note
    generation. Returns ``(roster, people_docs, desktop_meeting_capture)`` so
    the notes path can reuse the people read for the context pack and every
    shared-prefix caller can pass the desktop flag through.
    """
    source_value = getattr(getattr(conversation, 'source', None), 'value', getattr(conversation, 'source', None))
    external_data = getattr(conversation, 'external_data', None) or {}
    desktop_capture = (
        source_value == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
    )
    try:
        gather = should_gather_meeting_context(conversation, calendar_context)
        if calendar_context is None and not desktop_capture and not gather:
            return None, [], desktop_capture
        people_docs = load_people_documents(uid)
        owner_name, owner_emails = resolve_owner_identity(uid)
        roster = normalize_meeting_participants(
            calendar_context,
            getattr(conversation, 'source', None),
            owner_name,
            owner_emails,
            people_docs,
        )
        return roster, people_docs, desktop_capture
    except Exception as exc:  # noqa: BLE001 - rich roster is best effort
        logger.warning('rich meeting roster build failed uid=%s: %s', uid, type(exc).__name__)
        # An EMPTY roster, never None — None would re-enable the unsafe legacy
        # one-name speaker guard while the rich flag is on.
        return MeetingRoster(entries=(), display_title=None, title_is_window_title=False), [], desktop_capture


def _rich_meeting_context_block(
    uid: str,
    conversation: Any,
    roster: MeetingRoster,
    people_docs: List[Dict[str, Any]],
    tz_str: str,
    *,
    include_screen_text: bool,
) -> Optional[str]:
    """Render the BACKGROUND CONTEXT block for the notes prompt; None when the
    pack comes back empty. Called only at the notes call site — memory and app
    prompts share the roster but never gather background."""
    try:
        pack = gather_meeting_context_pack(
            uid,
            conversation,
            roster,
            people=people_docs,
            include_screen_text=include_screen_text,
            timezone_name=tz_str,
        )
        return render_meeting_context_pack(pack) if pack else None
    except Exception as exc:  # noqa: BLE001 - background is best effort
        logger.warning('rich meeting context build failed uid=%s: %s', uid, type(exc).__name__)
        return None


def rich_roster_inputs(
    uid: str,
    conversation: Any,
    calendar_context: Optional[CalendarMeetingContext],
) -> Tuple[Optional[MeetingRoster], bool]:
    """Roster + desktop-capture flag for the memory/app shared prefixes.

    Never gathers the background pack. ``None`` roster means not meeting-like;
    an empty roster means the composition failed and the strict rich path must
    still hold.
    """
    roster, _people_docs, desktop_capture = _rich_meeting_roster(uid, conversation, calendar_context)
    return roster, desktop_capture


def rich_notes_inputs(
    uid: str,
    conversation: Any,
    calendar_context: Optional[CalendarMeetingContext],
    tz_str: str,
    *,
    include_background: bool,
    include_screen_text: bool,
) -> Tuple[Optional[MeetingRoster], Optional[str], bool]:
    """Roster, optional rendered BACKGROUND CONTEXT block, and desktop flag for notes."""
    roster, people_docs, desktop_capture = _rich_meeting_roster(uid, conversation, calendar_context)
    if roster is None or not include_background:
        return roster, None, desktop_capture
    block = _rich_meeting_context_block(
        uid,
        conversation,
        roster,
        people_docs,
        tz_str,
        include_screen_text=include_screen_text,
    )
    return roster, block, desktop_capture
