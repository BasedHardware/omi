from __future__ import annotations

import logging
from datetime import datetime, tzinfo
from typing import Any, Dict, List, Optional, Sequence, Set, cast

import database.folders as folders_db
import database.users as users_db
from database.auth import get_user_name
from models.other import Person

from models.client_processing import PROJECTION_FAMILY_FIELDS
from models.conversation import Conversation
from models.note_claims import current_note_claims
from models.transcript_segment import TranscriptSegment, strip_grouping_internal_fields
from utils.conversations.summary_selection import select_primary_summary
from models.conversation_photo import ConversationPhoto
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments
from utils.model_text import (
    DisplayClock,
    ELAPSED_LEGEND,
    UNTRUSTED_LEGEND,
    format_date,
    format_duration,
    format_instant,
    format_span,
    generated,
    untrusted_block,
)

from utils.speakers.display import display_participants, developer_speaker_names

logger = logging.getLogger(__name__)


def _omit_list_note_claims(conv: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(conv.get('structured'), dict) and 'note_claims' in conv['structured']:
        conv['structured'] = dict(conv['structured'])
        conv['structured'].pop('note_claims', None)
    return conv


def resolve_display_tz(tz: Optional[str]) -> Any:
    """Return ``(tzinfo, label)`` for rendering timestamps in a user's local timezone.

    Falls back to ``(UTC, "UTC")`` when the zone is missing or not a valid IANA name.
    Shared by the chat retrieval tools so every user-facing timestamp is shown in the
    user's local time rather than UTC (see issue #4643).
    """
    clock = DisplayClock.from_name(tz)
    return clock.tz, clock.name


def format_local_time(dt: datetime, display_tz: tzinfo, tz_label: str) -> str:
    """Render a stored timestamp as a labelled wall clock in the user's timezone.

    Every timestamp a chat tool hands the model must carry a timezone label. An unlabelled
    UTC wall clock reads as local time to the model, which then states the wrong time of day
    ("tonight" for a mid-afternoon due date) — issues #4643 and #6214.
    """
    return format_instant(dt, DisplayClock(display_tz, tz_label))


def format_local_date(dt: datetime, display_tz: tzinfo) -> str:
    """Render a stored timestamp as a calendar date in the user's timezone.

    Needed because the UTC date rolls over at a different instant than the user's: a memory
    captured at 21:00 in Sao Paulo is stored as the next UTC day, so a raw UTC date is a day
    late for anyone west of Greenwich in the evening (issue #6214).
    """
    return format_date(dt, DisplayClock(display_tz, getattr(display_tz, 'key', 'UTC')))


# ---------------------------------------------------------------------------
# Populate: speaker names, folder names
# ---------------------------------------------------------------------------


def populate_speaker_names(uid: str, conversations: List[Dict[str, Any]], *, preserve_api_values: bool = False) -> None:
    """Add speaker_name to transcript segments based on person_id mappings.

    Mutates conversation dicts in-place. Works with both single conversations
    (pass as [conv]) and lists.
    """
    user_name = get_user_name(uid, use_default=False) or ('User' if preserve_api_values else 'You')

    all_person_ids: Set[str] = set()
    for conv in conversations:
        segments: List[Dict[str, Any]] = cast(List[Dict[str, Any]], conv.get('transcript_segments') or [])
        for seg in segments:
            if seg.get('person_id'):
                all_person_ids.add(str(seg['person_id']))

    people_map: Dict[str, str] = {}
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
        people_map = {str(p['id']): str(p['name']) for p in people_data}

    for conv in conversations:
        # Dense labels are assigned per conversation: the same diarization id in another
        # conversation is a different voice, never the same "Speaker A".
        segments = cast(List[Dict[str, Any]], conv.get('transcript_segments') or [])
        if preserve_api_values:
            for seg, name in zip(segments, developer_speaker_names(segments, names=people_map, owner_name=user_name)):
                seg['speaker_name'] = name
            continue
        display = display_participants(
            segments, names=people_map, owner_name=user_name, resolution=conv.get('speaker_resolution')
        )
        for seg in segments:
            seg['speaker_name'] = display.label(seg)


def populate_folder_names(uid: str, conversations: List[Dict[str, Any]]) -> None:
    """Add folder_name to conversations based on folder_id mappings.

    Mutates conversation dicts in-place. Batch-loads all folder IDs in one query.
    """
    folder_ids: Set[str] = set()
    for conv in conversations:
        if conv.get('folder_id'):
            folder_ids.add(str(conv['folder_id']))

    if not folder_ids:
        for conv in conversations:
            conv['folder_name'] = None
        return

    all_folders = folders_db.get_folders(uid)
    folder_map: Dict[str, str] = {str(f['id']): str(f['name']) for f in all_folders}

    for conv in conversations:
        folder_id = conv.get('folder_id')
        conv['folder_name'] = folder_map.get(str(folder_id)) if folder_id else None


# ---------------------------------------------------------------------------
# Redact: locked-content stripping
# ---------------------------------------------------------------------------


# Untrusted client-authored display siblings of ``structured``. Denylist sinks
# iterate this set: classifying a field here is what strips it from the
# integration payload, rather than only satisfying a test pin. Other denylist
# sinks (persist strip, transcript-edit clear, in-memory drop) still hardcode
# a single name today; the trust-boundary suite requires they actually clear
# every member of this set.
def _strip_match_scores(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Voice calibration evidence stays inside backend persistence and processing."""
    conv.pop('speaker_match_scores', None)
    conv.pop('owner_recognition_diagnostics', None)
    for segment in conv.get('transcript_segments') or []:
        if isinstance(segment, dict):
            segment.pop('speaker_match_scores', None)
            strip_grouping_internal_fields(segment)
    return conv


def redact_conversation_for_list(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Standard list-view redaction: strip detail fields, keep title/overview."""
    _strip_match_scores(conv)
    if not conv.get('is_locked', False):
        return _omit_list_note_claims(conv)
    _omit_list_note_claims(conv)
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    # Search may attach transcript match_snippets before list redaction; never leak evidence for locked rows.
    conv['match_snippets'] = []
    return _omit_list_note_claims(conv)


def redact_conversation_for_integration(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Integration-view redaction: strip private metadata and every projection.

    This sink is a denylist plus a pinned ``Conversation`` field set, not an
    explicit projection-free shape. The integration payload is a full
    ``Conversation.model_dump()`` (via ``conversation_to_dict``) with every
    name in ``PROJECTION_FAMILY_FIELDS`` then removed. Installed third-party
    apps consume this public contract; converting it to an allowlist would
    drop fields they already read. Removal (``pop``), not null assignment:
    setting the key to ``None`` would add a field that was never part of the
    contract. Classifying a sibling on ``Conversation`` into
    ``PROJECTION_FAMILY_FIELDS`` is what strips it here; the trust-boundary
    suite then requires every other denylist sink to clear it too. Locked
    conversations also blank title/overview and drop evidence.
    """
    # Geolocation is private capture metadata and is not part of the public
    # integration contract. Strip it before either locked or unlocked data is
    # serialized into an integration response.
    _strip_match_scores(conv)
    conv.pop('geolocation', None)
    # Server-computed capture badge stays on app views, outside the integration contract.
    conv.pop('capture_coverage', None)
    for field in PROJECTION_FAMILY_FIELDS:
        conv.pop(field, None)
    # Where the live receiver heard each segment is internal placement evidence, not transcript.
    for segment in conv.get('transcript_segments') or []:
        if isinstance(segment, dict):
            segment.pop('audio_capture_start', None)
            segment.pop('audio_capture_end', None)
            segment.pop('audio_source', None)
    if not conv.get('is_locked', False):
        return conv
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['title'] = ''
        conv['structured']['overview'] = ''
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
        if isinstance(conv['structured'].get('note_claims'), list):
            conv['structured']['note_claims'] = current_note_claims(conv['structured'])
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    conv['match_snippets'] = []
    return conv


def redact_conversations_for_list(conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply standard list redaction to a batch of conversations."""
    return [redact_conversation_for_list(c) for c in conversations]


def redact_conversations_for_integration(conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply integration redaction to a batch of conversations."""
    return [redact_conversation_for_integration(c) for c in conversations]


# ---------------------------------------------------------------------------
# Serialize: datetime handling, dict conversion
# ---------------------------------------------------------------------------


def conversations_to_string(
    conversations: Sequence[Conversation],
    use_transcript: bool = False,
    include_timestamps: bool = False,
    people: Optional[List[Person]] = None,
    user_name: Optional[str] = None,
    tz: Optional[str] = None,
    clock: Optional[DisplayClock] = None,
    include_refs: bool = False,
    index_start: int = 1,
    truncation_notes: Optional[Dict[str, str]] = None,
    include_legends: bool = True,
) -> str:
    """Format a sequence of Conversation objects into a human-readable string.

    Callers must pass deserialized Conversation objects (use factory.deserialize_conversation
    for raw dicts). This function does NOT accept dicts.

    When ``tz`` (an IANA timezone name like "America/Sao_Paulo") is provided, timestamps are
    rendered in that timezone and labelled accordingly; otherwise they default to UTC. Pass the
    user's timezone when this text is fed to the chat LLM so it reasons about times correctly.
    """
    result: List[str] = []
    elapsed_timestamps_shown = False
    people_map: Dict[str, Person] = {p.id: p for p in people} if people else {}
    if clock is not None and tz is not None:
        raise ValueError('Pass clock or tz, not both')
    clock = clock or DisplayClock.from_name(tz)
    for i, conversation in enumerate(conversations):
        formatted_date = format_date(conversation.created_at, clock)
        conversation_str = (
            f"Conversation #{i + index_start}\n"
            + (f"ref: conversations/{conversation.id}\n" if include_refs else '')
            + f"{formatted_date} ({str(conversation.structured.category.value).capitalize()})\n"
        )

        # Add started_at and finished_at if available
        conversation_str += f"When: {format_span(conversation.started_at or conversation.created_at, conversation.finished_at, clock)}\n"

        conversation_content: List[str] = []
        title = str(conversation.structured.title or '')
        title = title[:1].upper() + title[1:] if title else ''
        if title:
            conversation_content.append(generated('Title', title))

        overview = str(select_primary_summary(conversation).content or '')
        if overview:
            conversation_content.append(generated('Overview', overview))

        # attendees
        if people_map:
            conv_person_ids = set(conversation.get_person_ids())
            if conv_person_ids:
                attendees_names = [
                    people_map[pid].name + (f' (ref: people/{pid})' if include_refs else '')
                    for pid in sorted(conv_person_ids)
                    if pid in people_map
                ]
                if attendees_names:
                    attendees = ", ".join(attendees_names)
                    conversation_str += f"Attendees: {attendees}\n"

        if conversation.structured.action_items:
            action_items: List[str] = []
            for item in conversation.structured.action_items:
                state = 'done' if item.completed else 'open'
                action_items.append(f'- [{state}] {item.description}')
            conversation_content.append(generated('Action Items', '\n'.join(action_items)))

        if conversation.structured.events:
            events: List[str] = []
            for event in conversation.structured.events:
                events.append(
                    f"- {event.title} ({format_instant(event.start, clock)}, {format_duration(event.duration * 60)})"
                )
            conversation_content.append(generated('Events', '\n'.join(events)))

        if use_transcript:
            safe_segments, owner_note = owner_safe_transcript_segments(conversation.transcript_segments)
            show_timestamps = include_timestamps and TranscriptSegment.can_display_seconds(safe_segments)
            if include_refs:
                transcript = '\n\n'.join(
                    f'#{segment.id} '
                    + TranscriptSegment.segments_as_string(
                        [segment],
                        include_timestamps=show_timestamps,
                        people=people,
                        user_name=user_name,
                        elapsed_timestamps=True,
                    )
                    for segment in safe_segments
                )
            else:
                transcript = TranscriptSegment.segments_as_string(
                    safe_segments,
                    include_timestamps=include_timestamps,
                    people=people,
                    user_name=user_name,
                    elapsed_timestamps=True,
                )
            if show_timestamps and transcript:
                elapsed_timestamps_shown = True
            transcript_block = f"Transcript:\n{owner_note + chr(10) if owner_note else ''}{transcript}"
            if transcript:
                conversation_content.append(transcript_block)
            if truncation_notes and truncation_notes.get(conversation.id):
                conversation_str += truncation_notes[conversation.id] + '\n'
            # photos
            photo_descriptions = ConversationPhoto.photos_as_string(
                conversation.photos,
                include_timestamps=include_timestamps,
                clock=clock,
            )
            if photo_descriptions != 'None':
                conversation_content.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

        if conversation_content:
            conversation_str += untrusted_block('conversation', '\n'.join(conversation_content)) + '\n'

        result.append(conversation_str.strip())

    rendered = "\n\n---------------------\n\n".join(result).strip()
    if include_legends and rendered:
        legends = [UNTRUSTED_LEGEND]
        if elapsed_timestamps_shown:
            legends.insert(0, ELAPSED_LEGEND)
        rendered = '\n'.join(legends) + '\n' + rendered
    return rendered


def serialize_datetimes(obj: Any) -> Any:
    """Recursively convert datetime objects to ISO format strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()  # not-model-facing: client JSON serialization
    elif isinstance(obj, dict):
        obj_dict = cast(Dict[Any, Any], obj)
        return {key: serialize_datetimes(value) for key, value in obj_dict.items()}
    elif isinstance(obj, list):
        obj_list = cast(List[Any], obj)
        return [serialize_datetimes(item) for item in obj_list]
    return obj


def conversation_to_dict(conversation: Conversation) -> Dict[str, Any]:
    """Convert a Conversation to a JSON-safe dict with ISO datetime strings."""
    return _strip_match_scores(serialize_datetimes(conversation.model_dump()))


# Allowlisted citation-card fields. A denylist cannot protect a field added
# after it was written; this set is the only shape that may back RAG cards.
_CITATION_STRUCTURED_FIELDS: tuple[str, ...] = ('title', 'emoji', 'overview', 'category')


def conversation_to_citation_card(conversation: Any) -> Dict[str, Any]:
    """Projection-free citation shape for chat RAG cards.

    Explicit allowlist: never ``model_dump()`` of the Conversation. The
    untrusted client projection is a sibling of ``structured`` and cannot
    appear here. ``structured`` values are the server-authored canonical
    fields, not the projection.
    """
    structured = getattr(conversation, 'structured', None)
    structured_card: Dict[str, Any] = {}
    for field in _CITATION_STRUCTURED_FIELDS:
        if isinstance(structured, dict):
            value: Any = structured.get(field, '')
        elif structured is None:
            value = ''
        else:
            value = getattr(structured, field, '')
        if value is None:
            value = ''
        elif field == 'category':
            enum_value = getattr(value, 'value', None)
            if enum_value is not None:
                value = enum_value
        structured_card[field] = value
    return {
        'id': getattr(conversation, 'id', ''),
        'created_at': getattr(conversation, 'created_at', None),
        'started_at': getattr(conversation, 'started_at', None),
        'finished_at': getattr(conversation, 'finished_at', None),
        'structured': structured_card,
    }
