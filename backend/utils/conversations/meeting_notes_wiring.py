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
from importlib import import_module
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional, Tuple, TYPE_CHECKING

from models.calendar_context import CalendarMeetingContext

if TYPE_CHECKING:
    from utils.conversations.episode_evidence import EvidenceItem
from utils.conversations.meeting_context_gate import should_gather_meeting_context
from utils.conversations.meeting_context_render import (
    MAX_SCREEN_CHARACTERS,
    render_meeting_context_pack,
)
from utils.conversations.screen_text_digest import digest_screen_rows
from utils.conversations.meeting_participants import MeetingRoster, normalize_meeting_participants
from utils.conversations.screen_frame_evidence import (
    NotesFrameImage,
    ScreenFrameEvidence,
    frame_evidence_duration_minutes,
    frame_evidence_started_at,
    load_notes_frame_images,
    load_screen_frame_evidence,
    screen_frame_agent_names,
    screen_frame_names,
    screen_moment_lines,
    with_screen_frame_participants,
)

logger = logging.getLogger(__name__)


def meeting_context_sources() -> Any:
    """The rich retrieval backend is optional; flag-off hot imports must stay cheap."""
    return import_module('utils.conversations.meeting_context_pack')


def _flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def meeting_notes_rich_context_enabled() -> bool:
    return _flag_enabled('MEETING_NOTES_RICH_CONTEXT_ENABLED')


def meeting_notes_episode_evidence_enabled(uid: str | None = None) -> bool:
    return _flag_enabled('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED') and import_module(
        'config.episode_notes'
    ).episode_notes_cohort(uid)


def meeting_notes_screen_text_context_enabled() -> bool:
    return _flag_enabled('MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED')


def meeting_notes_screen_frames_context_enabled() -> bool:
    """Attach up to four approved screenshots as images on the notes call."""
    return _flag_enabled('MEETING_NOTES_SCREEN_FRAMES_CONTEXT_ENABLED')


def _screen_frame_evidence(uid: str, conversation: Any) -> Tuple[ScreenFrameEvidence, ...]:
    # Frame names and summaries are screen text: they ride the screen-text flag.
    # Images need the same docs, so either flag loads them.
    if not (meeting_notes_screen_text_context_enabled() or meeting_notes_screen_frames_context_enabled()):
        return ()
    return load_screen_frame_evidence(uid, getattr(conversation, 'id', None))


def _rich_meeting_roster(
    uid: str,
    conversation: Any,
    calendar_context: Optional[CalendarMeetingContext],
    *,
    include_frame_text: bool = True,
) -> Tuple[Optional[MeetingRoster], List[Dict[str, Any]], bool, Tuple[ScreenFrameEvidence, ...]]:
    """Best-effort normalized roster plus the people-catalog read used for it.

    The roster exists whenever this is meeting-like — resolved meeting context,
    a desktop meeting-role capture, or the multi-party-speech gate — which is
    also the condition under which the background pack may be gathered. Every
    read inside degrades to absent context; nothing here may block note
    generation. Returns ``(roster, people_docs, desktop_meeting_capture,
    frame_evidence)`` so the notes path can reuse the people and frame reads
    and every shared-prefix caller can pass the desktop flag through.

    Names the frame judge read off call tiles join the roster (as
    ``screen_activity`` participants) only where no better source named them.
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
            return None, [], desktop_capture, ()
        evidence = _screen_frame_evidence(uid, conversation)
        if not include_frame_text:
            evidence = tuple(replace(frame, names=(), summary='') for frame in evidence)
        # Names the judge read off approved frames are identity evidence for either
        # flag: with images attached, the roster must carry them too, or the notes
        # validator strips the names the model read from those images.
        if evidence:
            calendar_context = with_screen_frame_participants(
                calendar_context,
                screen_frame_names(evidence) + screen_frame_agent_names(evidence),
                started_at=frame_evidence_started_at(conversation),
                duration_minutes=frame_evidence_duration_minutes(conversation),
            )
        people_docs = meeting_context_sources().load_people_documents(uid)
        owner_name, owner_emails = meeting_context_sources().resolve_owner_identity(uid)
        roster = normalize_meeting_participants(
            calendar_context,
            getattr(conversation, 'source', None),
            owner_name,
            owner_emails,
            people_docs,
        )
        return roster, people_docs, desktop_capture, evidence
    except Exception as exc:  # noqa: BLE001 - rich roster is best effort
        logger.warning('rich meeting roster build failed uid=%s: %s', uid, type(exc).__name__)
        # An EMPTY roster, never None — None would re-enable the unsafe legacy
        # one-name speaker guard while the rich flag is on.
        return MeetingRoster(entries=(), display_title=None, title_is_window_title=False), [], desktop_capture, ()


def _rich_meeting_context_block(
    uid: str,
    conversation: Any,
    roster: MeetingRoster,
    people_docs: List[Dict[str, Any]],
    tz_str: str,
    *,
    include_screen_text: bool,
    screen_moments: Tuple[str, ...] = (),
    evidence_items: Optional[List[EvidenceItem]] = None,
) -> Optional[str]:
    """Render the BACKGROUND CONTEXT block for the notes prompt; None when the
    pack comes back empty. Called only at the notes call site — memory and app
    prompts share the roster but never gather background."""
    try:
        pack = meeting_context_sources().gather_meeting_context_pack(
            uid,
            conversation,
            roster,
            people=people_docs,
            include_screen_text=include_screen_text,
            timezone_name=tz_str,
            screen_moments=screen_moments,
            **({'preserve_screen_rows': True} if evidence_items is not None else {}),
        )
        if evidence_items is not None:
            evidence_items.extend(import_module('utils.conversations.episode_evidence').context_pack_evidence(pack))
            if pack is not None and pack.screen_rows:
                # Long-input fallback needs the same rich background as baseline,
                # reusing already-read rows rather than issuing another query.
                pack = replace(pack, screen_text=digest_screen_rows(pack.screen_rows, MAX_SCREEN_CHARACTERS))
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
    roster, _people_docs, desktop_capture, _evidence = _rich_meeting_roster(uid, conversation, calendar_context)
    return roster, desktop_capture


def rich_notes_inputs(
    uid: str,
    conversation: Any,
    calendar_context: Optional[CalendarMeetingContext],
    tz_str: str,
    *,
    include_background: bool,
    include_screen_text: bool,
    evidence_items: Optional[List[EvidenceItem]] = None,
) -> Tuple[Optional[MeetingRoster], Optional[str], bool, Tuple[NotesFrameImage, ...]]:
    """Roster, optional rendered BACKGROUND CONTEXT block, desktop flag, and frame images for notes."""
    roster, people_docs, desktop_capture, evidence = _rich_meeting_roster(
        uid,
        conversation,
        calendar_context,
        **({'include_frame_text': include_screen_text} if evidence_items is not None else {}),
    )
    if evidence_items is not None:
        evidence_items.extend(
            import_module('utils.conversations.episode_evidence').meeting_evidence(roster, calendar_context, evidence)
        )
    if roster is None or not include_background:
        return roster, None, desktop_capture, ()
    started_at = frame_evidence_started_at(conversation)
    block = _rich_meeting_context_block(
        uid,
        conversation,
        roster,
        people_docs,
        tz_str,
        include_screen_text=include_screen_text,
        screen_moments=screen_moment_lines(evidence, started_at) if include_screen_text else (),
        **({'evidence_items': evidence_items} if evidence_items is not None else {}),
    )
    images: Tuple[NotesFrameImage, ...] = ()
    if meeting_notes_screen_frames_context_enabled():
        try:
            images = load_notes_frame_images(uid, getattr(conversation, 'id', None), evidence, started_at)
        except Exception as exc:  # noqa: BLE001 - frame images are best effort
            logger.warning('rich meeting frame images failed uid=%s: %s', uid, type(exc).__name__)
    return roster, block, desktop_capture, images
