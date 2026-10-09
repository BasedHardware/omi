"""Pure production conversation context builder, independent of cache-route clients."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional
from zoneinfo import ZoneInfo

from models.calendar_context import CalendarMeetingContext
from models.conversation_photo import ConversationPhoto
from utils.conversations.meeting_participants import MeetingRoster, is_silent_recorder, bind_speakers_with_roster
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, has_cacheable_prefix
from utils.llm.shaped_agent import route_for_uid

from utils.llm.conversation_notes_prompts import SHARED_CONVERSATION_PREAMBLE


@dataclass(frozen=True)
class ConversationPromptPrefix:
    """Rendered prefix bytes plus the per-conversation routing key.

    Consumers append their own instructions after these messages. Keeping this
    value immutable prevents feature-specific text from leaking before the
    explicit cache breakpoint.
    """

    conversation_id: str
    context: str
    # The IDs come from the source conversation, not from parsing untrusted
    # transcript text.  Consumers use this set to validate model-authored
    # evidence references.
    transcript_segment_ids: frozenset[str] = frozenset()
    has_usable_content: bool = True
    shaped_context: Optional[str] = None

    @property
    def cache_key(self) -> str:
        return f'omi-conv-{self.conversation_id}'

    @property
    def cache_eligible(self) -> bool:
        return has_cacheable_prefix(f'{SHARED_CONVERSATION_PREAMBLE}\n{self.context}')

    def messages(self, *, cache_enabled: bool) -> List[dict[str, Any]]:
        context_block: dict[str, Any] = {'type': 'text', 'text': self.context}
        if cache_enabled and self.cache_eligible:
            context_block['prompt_cache_breakpoint'] = EXPLICIT_CACHE_BREAKPOINT
        return [
            {'role': 'system', 'content': SHARED_CONVERSATION_PREAMBLE},
            {'role': 'system', 'content': [context_block]},
        ]


def _transcript_has_source_content(transcript: str, source_ids: frozenset[str]) -> bool:
    """True when the compact transcript carries text beyond its structural headers.

    A ``[<segment-id> <cluster>]`` opener only counts as a header when the id is
    one of the conversation's own segment ids; the same bracketed shape for an
    unknown id is user text.
    """
    if not source_ids:
        return bool(transcript.strip())
    id_pattern = '|'.join(re.escape(segment_id) for segment_id in source_ids)
    header = re.compile(rf'^\[(?:{id_pattern})(?:\s+\S+)?\]')
    for line in transcript.splitlines():
        remainder = header.sub('', line, count=1) if line.startswith('[') else line
        if remainder.strip():
            return True
    return False


_ROSTER_KIND_LABELS = {'owner': 'owner', 'human': 'human', 'ai_agent': 'ai agent'}


def _speaker_metadata_lines(
    speaker_names: Mapping[int, Optional[str]],
    roster: MeetingRoster,
    desktop_meeting_capture: bool,
) -> List[str]:
    bound_names = {name.casefold() for name in speaker_names.values() if name}
    remote = [entry for entry in roster.entries if entry.kind != 'owner' and not is_silent_recorder(entry)]
    unbound_remote_labels = [
        entry.display_name or entry.email or 'unknown'
        for entry in remote
        if not (entry.display_name and entry.display_name.casefold() in bound_names)
        and not (entry.email and entry.email.casefold() in bound_names)
    ]
    annotate_remote = desktop_meeting_capture and len(remote) > 1 and bool(unbound_remote_labels)
    lines: List[str] = []
    for key, name in speaker_names.items():
        if name:
            lines.append(f'spk {key} {name}')
        elif annotate_remote:
            lines.append(
                f'spk {key} ? (remote audio channel; may contain several people: '
                f'{", ".join(unbound_remote_labels)})'
            )
        else:
            lines.append(f'spk {key} ?')
    return lines


def build_conversation_prompt_prefix(
    *,
    conversation_id: str,
    transcript: str,
    started_at: datetime,
    timezone_name: str,
    language_code: str,
    calendar_context: Optional[CalendarMeetingContext] = None,
    photos: Optional[List[ConversationPhoto]] = None,
    speaker_map: Optional[Mapping[int, Optional[str]]] = None,
    transcript_segment_ids: Optional[Iterable[str]] = None,
    roster: Optional[MeetingRoster] = None,
    desktop_meeting_capture: bool = False,
    uid: Optional[str] = None,
) -> ConversationPromptPrefix:
    """Render the shared context prefix for conversation-wide LLM tasks.

    ``speaker_map`` (from ``conversation_transcript_and_speaker_map``) is rendered
    once as compact ``spk <cluster> <name|?>`` metadata lines, so the transcript
    below it can key turns by cluster instead of carrying ``Speaker N:`` labels the
    model copies into titles (SCA-454).

    ``roster`` (the normalized ``MeetingRoster``) is the rich-meeting-notes path:
    it replaces the calendar participant line with a factual PARTICIPANTS block
    and uses the stricter speaker-binding guard. ``None`` renders the original
    metadata byte-identically. ``desktop_meeting_capture`` marks the remote
    audio channel as mixed, so a bound cluster is demoted to ``?`` when several
    remote participants could share it.
    """
    try:
        user_tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:
        user_tz = timezone.utc
    aware_started_at = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    started_at_local = aware_started_at.astimezone(user_tz).replace(tzinfo=None).isoformat()
    speaker_names: dict[int, Optional[str]] = dict(speaker_map) if speaker_map else {}
    metadata_lines = [
        f'- Captured at: {started_at_local} ({timezone_name or "UTC"})',
    ]
    if roster is not None:
        if roster.display_title:
            metadata_lines.append(f'- Meeting title: {roster.display_title}')
        if calendar_context:
            metadata_lines.extend(
                [
                    f'- Platform: {calendar_context.platform or "Not specified"}',
                    f'- Meeting notes: {calendar_context.notes or "Not specified"}',
                ]
            )
        bind_speakers_with_roster(speaker_names, roster, desktop_meeting_capture)
        if speaker_names:
            metadata_lines.extend(_speaker_metadata_lines(speaker_names, roster, desktop_meeting_capture))
        if roster.entries:
            metadata_lines.append('PARTICIPANTS')
            metadata_lines.extend(
                f'- {entry.display_name or entry.email or "unknown"} | {entry.organization or "-"} '
                f'| {_ROSTER_KIND_LABELS.get(entry.kind, entry.kind)} | via {entry.source}'
                for entry in roster.entries
            )
    elif calendar_context:
        participants = ', '.join(
            filter(
                None,
                [
                    (
                        f'{participant.name} <{participant.email}>'
                        if participant.name and participant.email
                        else participant.name or participant.email
                    )
                    for participant in calendar_context.participants
                ],
            )
        )
        metadata_lines.extend(
            [
                f'- Meeting title: {calendar_context.title}',
                f'- Participants: {participants or "Not specified"}',
                f'- Platform: {calendar_context.platform or "Not specified"}',
                f'- Meeting notes: {calendar_context.notes or "Not specified"}',
            ]
        )

        # One-name rename guard (SCA-454), keyed off the spk map rather than a
        # ``Speaker N:`` dialogue label: when exactly one cluster is unresolved and
        # exactly one calendar participant is not already bound, that participant
        # names the cluster. Anything less certain stays ``?`` — never invented.
        unresolved_keys = [key for key, name in speaker_names.items() if not name]
        bound_names = {name.casefold() for name in speaker_names.values() if name}
        remaining_names = [
            participant.name
            for participant in calendar_context.participants
            if participant.name and participant.name.casefold() not in bound_names
        ]
        if len(unresolved_keys) == 1 and len(remaining_names) == 1:
            speaker_names[unresolved_keys[0]] = remaining_names[0]

    if roster is None and speaker_names:
        metadata_lines.extend(f'spk {key} {name}' if name else f'spk {key} ?' for key, name in speaker_names.items())

    context_parts = ['CONVERSATION METADATA\n' + '\n'.join(metadata_lines), f'FULL TRANSCRIPT\n{transcript.strip()}']
    photo_descriptions = ConversationPhoto.photos_as_string(photos, include_timestamps=True) if photos else ''
    if photo_descriptions and photo_descriptions != 'None':
        context_parts.append(f'CAPTURED PHOTO DESCRIPTIONS\n{photo_descriptions}')

    shaped_context = None
    if uid is not None and route_for_uid(uid) != 'old':
        # Build from the original map, never the roster/calendar-bound copy above.
        # Calendar invitees are expected; screen listings are observed UI data.
        # Neither listing establishes attendance or speaker identity.
        evidence: dict[str, Any] = {
            'started_at': started_at.isoformat(),
            'timezone': timezone_name,
            'language': language_code,
            'speaker_map': dict(speaker_map or {}),
            'expected_calendar': None,
            'observed_screen_listing': None,
            'photo_descriptions': photo_descriptions,
        }
        if calendar_context:
            primary_key = (
                'observed_screen_listing'
                if calendar_context.calendar_source == 'screen_activity'
                else 'expected_calendar'
            )
            sources = calendar_context.participants_by_source()
            for key, participants in (
                ('expected_calendar', sources.expected_calendar),
                ('observed_screen_listing', sources.observed_screen_listing),
            ):
                if participants is None:
                    continue
                # Scalar metadata describes the winning source only. Never copy
                # the legacy participant union into either source's evidence.
                source_context = (
                    calendar_context.model_dump(mode='json', exclude={'participants', 'participant_sources'})
                    if key == primary_key
                    else {}
                )
                source_context['participants'] = [participant.model_dump(mode='json') for participant in participants]
                evidence[key] = source_context
        shaped_context = json.dumps(evidence, ensure_ascii=False) + f'\nFULL TRANSCRIPT\n{transcript.strip()}'

    source_ids = frozenset(segment_id for segment_id in (transcript_segment_ids or ()) if segment_id)
    return ConversationPromptPrefix(
        conversation_id=conversation_id,
        context='\n\n'.join(context_parts),
        transcript_segment_ids=source_ids,
        has_usable_content=_transcript_has_source_content(transcript, source_ids)
        or bool(photo_descriptions and photo_descriptions != 'None'),
        shaped_context=shaped_context,
    )
