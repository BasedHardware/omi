"""Approved meeting screenshots as evidence for the notes call.

The screen-frame judge already reads every candidate frame; for approved frames
it also records the participant names shown on call tiles and a short factual
summary of what was on screen. This module turns those stored fields (and, when
enabled, the frame pixels themselves) into notes inputs:

- roster names: tile names join the meeting context as ``screen_activity``
  participants when no better source already named them;
- SCREEN MOMENTS: time-offset summaries for the background context pack;
- images: up to four downscaled approved frames attached to the notes call.

Every read is best effort and bounded. Only this environment's frames are used
(`utils/screen_frames/environment.py`): dev and prod share Firestore, not buckets.
Rejected frames were never persisted, so they contribute nothing.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from PIL import Image

from database.screen_frames import get_conversation_screen_frames, own_frames
from database.users import get_meeting_note_screenshots_enabled
from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from utils.conversations.meeting_context import is_ai_agent_tile_name
from utils.conversations.meeting_participants import looks_like_ai_agent_name
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage
from utils.other.storage import configured_screen_frames_bucket, download_screen_frame_bytes

logger = logging.getLogger(__name__)

MAX_NOTES_FRAME_IMAGES = 4
NOTES_FRAME_LONG_EDGE_PX = 1024
NOTES_FRAME_JPEG_QUALITY = 80
FRAME_READ_TIMEOUT_SECONDS = 3.0
FRAME_READ_BUDGET_SECONDS = 6.0
MAX_SCREEN_MOMENTS = 7
MAX_SCREEN_FRAME_NAMES = 8

_NAME_DECORATION = re.compile(r'\s*(?:\(.*?\)|\d{1,2}:\d{2}\s*(?:AM|PM)?|·.*)\s*$', re.IGNORECASE)
_NOT_A_NAME = {'you', 'me', 'guest', 'host', 'presenting', 'participants', 'everyone'}


@dataclass(frozen=True)
class ScreenFrameEvidence:
    frame_id: str
    captured_at: datetime
    role: str
    banner_suitability: float
    names: tuple[str, ...]
    summary: str


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def load_screen_frame_evidence(uid: str, conversation_id: Optional[str]) -> tuple[ScreenFrameEvidence, ...]:
    """This environment's approved frames for the conversation, oldest first.

    Nothing when the account's screenshot setting is off: hidden frames stay out
    of every surface, notes and reprocessing included (contract §9).
    """
    bucket = configured_screen_frames_bucket()
    if not bucket or not conversation_id:
        return ()
    try:
        if not get_meeting_note_screenshots_enabled(uid):
            return ()
        docs = own_frames(get_conversation_screen_frames(uid, conversation_id), bucket)
    except Exception as exc:  # noqa: BLE001 - evidence is best effort
        logger.warning('screen frame evidence read failed uid=%s: %s', uid, type(exc).__name__)
        return ()
    evidence: list[ScreenFrameEvidence] = []
    for doc in docs:
        captured_at = _as_utc(doc.get('captured_at'))
        frame_id = doc.get('id')
        if captured_at is None or not isinstance(frame_id, str) or not frame_id:
            continue
        raw_names = doc.get('visible_participant_names')
        names = tuple(name for name in (raw_names if isinstance(raw_names, list) else []) if isinstance(name, str))
        summary = doc.get('screen_summary')
        evidence.append(
            ScreenFrameEvidence(
                frame_id=frame_id,
                captured_at=captured_at,
                role=str(doc.get('role') or 'strip'),
                banner_suitability=float(doc.get('banner_suitability') or 0.0),
                names=names,
                summary=summary.strip() if isinstance(summary, str) else '',
            )
        )
    evidence.sort(key=lambda item: item.captured_at)
    return tuple(evidence)


def _clean_name(raw: str, *, agents: bool = False) -> Optional[str]:
    """A human tile name, or with ``agents`` an AI-agent tile the roster also classifies as one."""
    name = ' '.join(_NAME_DECORATION.sub('', raw).split()).strip(' •|*·-—')
    tokens = name.split()
    if not 1 <= len(tokens) <= 5 or len(name) > 60 or '@' in name or any(ch.isdigit() for ch in name):
        return None
    if name.casefold() in _NOT_A_NAME or is_ai_agent_tile_name(name) != agents:
        return None
    if agents:
        return name if looks_like_ai_agent_name(name) else None
    return name if len(tokens) <= 4 and any(token[:1].isupper() for token in tokens) else None


def screen_frame_agent_names(evidence: Sequence[ScreenFrameEvidence]) -> list[str]:
    """AI-agent tiles on approved frames. They join the roster as agents (never
    people) so the speaker-binding guard still sees them."""
    return _frame_names(evidence, agents=True)


def screen_frame_names(evidence: Sequence[ScreenFrameEvidence]) -> list[str]:
    """Human tile names the judge read off approved frames, most frequent first."""
    return _frame_names(evidence, agents=False)


def _frame_names(evidence: Sequence[ScreenFrameEvidence], *, agents: bool) -> list[str]:
    counts: dict[str, int] = {}
    spelling: dict[str, str] = {}
    for item in evidence:
        for raw in item.names:
            name = _clean_name(raw, agents=agents)
            if name is None:
                continue
            key = name.casefold()
            counts[key] = counts.get(key, 0) + 1
            spelling.setdefault(key, name)
    ordered = sorted(counts, key=lambda key: -counts[key])
    return [spelling[key] for key in ordered[:MAX_SCREEN_FRAME_NAMES]]


def _email_spells_name(email: str, name_tokens: Sequence[str]) -> bool:
    """Both the first and the last name token appear in the local part ("jordan.rivera").

    A shared first name alone ("john.smith" vs a "John Doe" tile) is a different person.
    """
    if len(name_tokens) < 2:
        return False
    local = _tokens(email.split('@', 1)[0])
    return name_tokens[0] in local and name_tokens[-1] in local


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[\s._\-+'’]+", value.casefold()) if token}


def with_screen_frame_participants(
    context: Optional[CalendarMeetingContext],
    names: Sequence[str],
    *,
    started_at: Optional[datetime],
    duration_minutes: int,
) -> Optional[CalendarMeetingContext]:
    """Add frame-derived names that no better source already supplied.

    A name already on the roster (same name, or same first and last token) is
    skipped. A nameless email participant whose local part matches the name is
    given that name instead of gaining a duplicate. Otherwise the name joins as
    a new participant; with no context at all, a ``screen_activity`` context is
    created for it.
    """
    if not names:
        return context
    participants = list(context.participants) if context is not None else []
    added = False
    for name in names:
        name_tokens = name.casefold().split()
        duplicate = any(
            participant.name
            and (
                participant.name.casefold() == name.casefold()
                or (
                    len(name_tokens) >= 2
                    and participant.name.casefold().split()[:1] == name_tokens[:1]
                    and participant.name.casefold().split()[-1:] == name_tokens[-1:]
                )
            )
            for participant in participants
        )
        if duplicate:
            continue
        email_only = [
            index
            for index, participant in enumerate(participants)
            if not participant.name and participant.email and _email_spells_name(participant.email, name_tokens)
        ]
        if len(email_only) == 1:
            index = email_only[0]
            participants[index] = participants[index].model_copy(update={'name': name})
        else:
            participants.append(MeetingParticipant(name=name))
        added = True
    if not added:
        return context
    if context is not None:
        return context.model_copy(update={'participants': participants})
    if started_at is None:
        return None
    return CalendarMeetingContext(
        calendar_event_id='screen-frames',
        title='Video meeting',
        participants=participants,
        start_time=started_at,
        duration_minutes=max(1, duration_minutes),
        calendar_source='screen_activity',
    )


def _offset_label(captured_at: datetime, started_at: Optional[datetime]) -> str:
    start = _as_utc(started_at)
    if start is None:
        return captured_at.strftime('%H:%M')
    seconds = max(0, int((captured_at - start).total_seconds()))
    return f'+{seconds // 60:02d}:{seconds % 60:02d}'


def screen_moment_lines(evidence: Sequence[ScreenFrameEvidence], started_at: Optional[datetime]) -> tuple[str, ...]:
    """``- [+mm:ss] summary (on screen: names)`` per approved frame with content."""
    lines: list[str] = []
    for item in evidence:
        names = [name for name in (_clean_name(raw) for raw in item.names) if name]
        if not item.summary and not names:
            continue
        line = f'- [{_offset_label(item.captured_at, started_at)}] {item.summary or "Call on screen"}'
        if names:
            line += f' (on screen: {", ".join(names)})'
        lines.append(line)
    return tuple(lines[:MAX_SCREEN_MOMENTS])


def _select_for_images(evidence: Sequence[ScreenFrameEvidence]) -> list[ScreenFrameEvidence]:
    """The banner (the judge's best recall frame) plus evenly spaced others, in capture order."""
    if len(evidence) <= MAX_NOTES_FRAME_IMAGES:
        return list(evidence)
    banner = next((item for item in evidence if item.role == 'banner'), None)
    rest = [item for item in evidence if item is not banner]
    slots = MAX_NOTES_FRAME_IMAGES - (1 if banner else 0)
    step = len(rest) / slots
    chosen = [rest[int(index * step)] for index in range(slots)]
    if banner:
        chosen.append(banner)
    return sorted(chosen, key=lambda item: item.captured_at)


def _downscale_jpeg(raw: bytes) -> bytes:
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert('RGB')
        longest = max(image.size)
        if longest > NOTES_FRAME_LONG_EDGE_PX:
            scale = NOTES_FRAME_LONG_EDGE_PX / float(longest)
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS
            )
        out = io.BytesIO()
        image.save(out, format='JPEG', quality=NOTES_FRAME_JPEG_QUALITY, optimize=True)
        return out.getvalue()


def load_notes_frame_images(
    uid: str,
    conversation_id: Optional[str],
    evidence: Sequence[ScreenFrameEvidence],
    started_at: Optional[datetime],
) -> tuple[NotesFrameImage, ...]:
    """Up to four approved frames as JPEG data URLs, within a total read budget.

    A frame that cannot be read in time is skipped; the notes call proceeds with
    whatever loaded, or with none.
    """
    if not conversation_id or not evidence or not configured_screen_frames_bucket():
        return ()
    deadline = time.monotonic() + FRAME_READ_BUDGET_SECONDS
    images: list[NotesFrameImage] = []
    for item in _select_for_images(evidence):
        remaining = deadline - time.monotonic()
        if remaining <= 0.2:
            logger.warning('screen frame images: read budget exhausted uid=%s loaded=%d', uid, len(images))
            break
        try:
            raw = download_screen_frame_bytes(
                uid, conversation_id, item.frame_id, timeout=min(FRAME_READ_TIMEOUT_SECONDS, remaining)
            )
            jpeg = _downscale_jpeg(raw)
        except Exception as exc:  # noqa: BLE001 - frame images are best effort
            logger.warning('screen frame image read failed uid=%s: %s', uid, type(exc).__name__)
            continue
        images.append(
            NotesFrameImage(
                frame_id=item.frame_id,
                offset_label=_offset_label(item.captured_at, started_at),
                data_url='data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii'),
            )
        )
    return tuple(images)


def frame_evidence_started_at(conversation: Any) -> Optional[datetime]:
    return _as_utc(getattr(conversation, 'started_at', None))


def frame_evidence_duration_minutes(conversation: Any) -> int:
    started = _as_utc(getattr(conversation, 'started_at', None))
    finished = _as_utc(getattr(conversation, 'finished_at', None))
    if started is None or finished is None:
        return 1
    return max(1, int((finished - started).total_seconds() / 60))
