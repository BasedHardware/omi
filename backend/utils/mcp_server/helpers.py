"""Parsing and projection helpers shared by hosted MCP tool handlers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from utils.conversations.duration import conversation_duration_seconds
from utils.conversations.render import redact_conversation_for_list
from utils.conversations.structured_defaults import project_structured_defaults
from utils.speakers.display import display_participants
from utils.mcp_data import parse_date_only_utc
from utils.mcp_server.errors import ToolExecutionError


def parse_mcp_date(value: Optional[str], field: str) -> Optional[datetime]:
    """Parse a yyyy-mm-dd MCP argument into a UTC-anchored datetime, or None when absent.

    Data stores (Firestore conversation ``created_at``/action-item ``due_at``, the vector
    index, screen-activity timestamps) all operate in UTC. A naive parse would be
    interpreted in the server's local timezone and shift the filter window by the UTC
    offset, so anchor to UTC midnight (matching the integration-router convention).
    """
    if not value:
        return None
    try:
        return parse_date_only_utc(value)
    except ValueError:
        raise ToolExecutionError(f"Invalid {field} format: '{value}'. Expected YYYY-MM-DD.", code=-32602)


_parse_mcp_date = parse_mcp_date


def conversation_participants(conversation: Dict[str, Any], *, include_display: bool = True) -> Dict[str, Any]:
    """Expose stored speaker mappings, without guessing names from prose."""
    segments = conversation.get("transcript_segments")
    if conversation.get("is_locked") or not isinstance(segments, list):
        return {"participants_included": False}
    participants = []
    display = (
        display_participants(
            [s for s in segments if isinstance(s, dict)], resolution=conversation.get('speaker_resolution')
        )
        if include_display
        else None
    )
    seen = set()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        speaker_id = segment.get("speaker_id")
        person_id = segment.get("person_id")
        speaker_id = speaker_id if isinstance(speaker_id, (str, int)) and not isinstance(speaker_id, bool) else None
        person_id = person_id if isinstance(person_id, str) and person_id else None
        key = (display.for_segment(segment).key if display else speaker_id, person_id, segment.get("is_user") is True)
        if speaker_id is None and person_id is None and not key[2]:
            continue
        if key in seen:
            continue
        seen.add(key)
        participants.append(
            {
                "speaker_id": None if display else speaker_id,
                **({"speaker_key": key[0], "speaker_label": display.label(segment)} if display else {}),
                "person_id": key[1],
                "is_user": key[2],
            }
        )
    return {
        "participants_included": True,
        "participants": participants,
        "person_ids": sorted(
            {p["person_id"] for p in participants if isinstance(p["person_id"], str) and p["person_id"]}
        ),
    }


def conversation_card(
    conversation: Dict[str, Any], *, include_display: bool = True, include_participants: bool = True
) -> Dict[str, Any]:
    redact_conversation_for_list(conversation)
    structured_raw = conversation.get("structured")
    structured = structured_raw if isinstance(structured_raw, dict) else {}
    # A v3 row written before its summary carries no category, but the card's response models
    # require it. Only a missing field is filled: an out-of-enum category stays for the caller's
    # own per-record guard to decide, which is what the MCP list/detail routes already do.
    structured = project_structured_defaults({"structured": structured}, fold_invalid_category=False)["structured"]
    return {
        **(
            conversation_participants(conversation, include_display=include_display)
            if include_participants
            else {'participants_included': False}
        ),
        "id": conversation.get("id"),
        "created_at": conversation.get("created_at"),
        "started_at": conversation.get("started_at"),
        "finished_at": conversation.get("finished_at"),
        "language": conversation.get("language"),
        "discarded": bool(conversation.get("discarded", False)),
        **conversation_state_fields(conversation),
        **conversation_call_fields(conversation),
        "structured": {
            key: structured.get(key) for key in ("title", "overview", "category", "emoji") if key in structured
        },
    }


_conversation_card = conversation_card

# Optional card fields: present only on documents that store them (conversations v3),
# so older cards stay the same size; ``fields`` may still name them.
OPTIONAL_CARD_FIELDS = ('kind', 'shown_on_home', 'summary_covers_through')
CONVERSATION_KINDS = ('conversation', 'voice_work', 'media', 'background')


def conversation_state_fields(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """Where a conversation is in its life and what kind of talk it is.

    ``status`` says whether a by-id read is still live (lists hold completed
    conversations only). ``kind`` separates the wearer's own conversations from
    media and other people's background talk; ``shown_on_home`` is the positive
    form of the stored Home-hiding flag. ``duration_seconds`` is the shared
    duration (transcript speech span, or the wall window for a transcript-free
    record such as a photo-only capture) where the transcript is loaded; it is null
    on list cards, which load no transcript, because there the wall window can
    start long before speech.
    """
    status = conversation.get('status')
    status = getattr(status, 'value', status)
    loaded = isinstance(conversation.get('transcript_segments'), list)
    duration = conversation_duration_seconds(conversation) if loaded else None
    fields: Dict[str, Any] = {
        'status': status if isinstance(status, str) else None,
        'duration_seconds': round(duration) if isinstance(duration, (int, float)) else None,
    }
    kind = conversation.get('kind')
    if kind in CONVERSATION_KINDS:
        fields['kind'] = kind
    hidden = conversation.get('home_hidden')
    if isinstance(hidden, bool):
        fields['shown_on_home'] = not hidden
    covers = conversation.get('summary_covers_through')
    if covers is not None:
        fields['summary_covers_through'] = covers
    return fields


def public_transcript_timing(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp public offsets without changing the source's pinned live clock.

    A wholly pre-origin line remains text with a zero-duration, unplaced window;
    it does not supply a playback interval. Search millisecond aliases agree.
    """
    projected = dict(fields)
    for clock_key in ("start", "end", "start_ms", "end_ms"):
        raw_offset = projected.get(clock_key)
        if raw_offset is None or isinstance(raw_offset, bool):
            continue
        try:
            if float(raw_offset) < 0:
                projected[clock_key] = 0
        except (OverflowError, TypeError, ValueError):
            continue
    return projected


def bounded_transcript_segments(
    segments: Any,
    *,
    max_segments: int,
    max_chars: int,
    extra_keys: Tuple[str, ...] = (),
    speaker_display: Any = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    source = [segment for segment in segments if isinstance(segment, dict)] if isinstance(segments, list) else []
    names = {
        str(s['person_id']): str(s['speaker_name']) for s in source if s.get('person_id') and s.get('speaker_name')
    }
    display = speaker_display if speaker_display is not None else display_participants(source, names=names)
    bounded: List[Dict[str, Any]] = []
    used_chars = 0
    truncated = False
    allowed_keys = ("id", "text", "original_text", "speaker_id", "is_user", "person_id", "start", "end") + tuple(
        extra_keys
    )

    for index, segment in enumerate(source):
        if index >= max_segments or used_chars >= max_chars:
            truncated = True
            break
        text = str(segment.get("text") or "")
        remaining_chars = max_chars - used_chars
        if len(text) > remaining_chars:
            if remaining_chars > 3:
                text = text[: remaining_chars - 3].rstrip() + "..."
            else:
                text = text[:remaining_chars]
            truncated = True
        item = {key: segment.get(key) for key in allowed_keys if key in segment}
        if item.get('original_text') is not None:
            # The budget covers every text field the segment returns. Charging only
            # `text` let a corrected segment spend the budget twice.
            original_text = str(item['original_text'])
            remaining_after_text = max_chars - used_chars - len(text)
            if len(original_text) > remaining_after_text:
                original_text = original_text[:remaining_after_text]
                truncated = True
            item['original_text'] = original_text
        item["speaker_id"] = None
        item["speaker_key"] = display.for_segment(segment).key
        item["speaker_label"] = display.label(segment)
        if "speaker_name" in extra_keys and not segment.get("is_user"):
            item["speaker_name"] = display.label(segment)
        item["text"] = text
        bounded.append(public_transcript_timing(item))
        used_chars += len(text) + len(item.get('original_text') or "")
        if truncated:
            break

    if len(bounded) < len(source):
        truncated = True
    return bounded, truncated


_bounded_transcript_segments = bounded_transcript_segments


@dataclass(frozen=True)
class TranscriptPage:
    segments: List[Dict[str, Any]]
    total_segments: int
    next_position: Optional[Dict[str, int]]


def transcript_page(
    segments: Any, *, max_segments: int, max_chars: int, offset: int = 0, char_offset: int = 0
) -> TranscriptPage:
    """Page the already hydrated transcript without losing clipped text.

    Keep whole segments together when possible. A segment larger than a page
    continues at a character position across text then original_text; explicit
    field offsets let clients reassemble those fragments without guessing.
    Speaker identities are resolved against the full transcript on every page.
    """
    source = [s for s in segments if isinstance(s, dict)] if isinstance(segments, list) else []
    if offset > len(source) or (offset == len(source) and char_offset):
        raise ToolExecutionError('Transcript changed. Restart without cursor.', code=-32602)
    names = {
        str(s['person_id']): str(s['speaker_name']) for s in source if s.get('person_id') and s.get('speaker_name')
    }
    display = display_participants(source, names=names)
    bounded: List[Dict[str, Any]] = []
    remaining = max_chars
    while offset < len(source) and len(bounded) < max_segments and remaining > 0:
        segment = source[offset]
        text = str(segment.get('text') or '')
        original = str(segment['original_text']) if segment.get('original_text') is not None else ''
        size = len(text) + len(original)
        if char_offset > size or (char_offset and char_offset == size):
            raise ToolExecutionError('Transcript changed. Restart without cursor.', code=-32602)
        if bounded and size - char_offset > remaining:
            break
        end = min(size, char_offset + remaining)
        fragment = dict(segment)
        fragment['text'] = text[min(char_offset, len(text)) : min(end, len(text))]
        if 'original_text' in fragment:
            fragment['original_text'] = original[max(0, char_offset - len(text)) : max(0, end - len(text))]
        projected, _ = bounded_transcript_segments(
            [fragment], max_segments=1, max_chars=remaining, speaker_display=display
        )
        item = projected[0]
        item['segment_index'] = offset
        if char_offset or end < size:
            item['text_offset'] = min(char_offset, len(text))
            item['original_text_offset'] = max(0, char_offset - len(text))
        bounded.append(item)
        remaining -= end - char_offset
        if end < size:
            char_offset = end
            break
        offset += 1
        char_offset = 0
    return TranscriptPage(
        bounded,
        len(source),
        {'offset': offset, 'char_offset': char_offset} if offset < len(source) else None,
    )


def conversation_call_fields(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """Expose persisted call evidence only; unknown stays null."""
    external = conversation.get('external_data')
    external = external if isinstance(external, dict) else {}
    contexts = [conversation.get(key) or external.get(key) for key in ('calendar_meeting_context', 'calendar_event')]
    contexts = [value for value in contexts if isinstance(value, dict)]
    source = conversation.get('source')
    source = getattr(source, 'value', source)
    source = source if isinstance(source, str) else None
    platform = conversation.get('call_platform')
    platform = platform if isinstance(platform, str) else None
    event_id = conversation.get('calendar_event_id')
    event_id = event_id if isinstance(event_id, str) else None
    is_call = conversation.get('is_call')
    is_call = is_call if isinstance(is_call, bool) else None
    for context in contexts:
        candidate_id = context.get('event_id') or context.get('calendar_event_id') or context.get('id')
        if (
            isinstance(candidate_id, str)
            and candidate_id != 'screen-activity'
            and context.get('calendar_source') != 'screen_activity'
        ):
            event_id = event_id or candidate_id
        candidate_platform = context.get('platform') or context.get('call_platform')
        if isinstance(candidate_platform, str):
            platform = platform or candidate_platform
        url = str(
            context.get('meeting_link')
            or context.get('meeting_url')
            or context.get('join_url')
            or context.get('url')
            or ''
        ).lower()
        for token, name in (('meet.google.', 'google_meet'), ('zoom.us', 'zoom'), ('teams.microsoft.', 'teams')):
            if token in url:
                platform = platform or name
        if context.get('is_call') is True:
            is_call = True
    if source in {'phone_call', 'call', 'desktop_call', 'zoom', 'google_meet', 'teams'}:
        is_call = True
        platform = platform or (
            'phone' if source == 'phone_call' else source if source not in {'call', 'desktop_call'} else None
        )
    if platform:
        normalized = str(platform).casefold().replace('_', ' ')
        if normalized in {'in person', 'in-person', 'physical'}:
            is_call = False if is_call is None else is_call
            platform = None
        else:
            is_call = True
    return {'source': source, 'is_call': is_call, 'call_platform': platform, 'calendar_event_id': event_id}


def select_card_fields(card: Dict[str, Any], fields: Any) -> Dict[str, Any]:
    """Optional lean card projection, with identity retained for reconciliation."""
    if fields is None:
        return card
    if isinstance(fields, str):
        fields = [field.strip() for field in fields.split(',') if field.strip()]
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        raise ToolExecutionError('fields must be an array of card field names or a comma-separated string', code=-32602)
    aliases = {'title', 'overview', 'category', 'emoji'}
    requested = {'structured.' + key if key in aliases else key for key in fields}
    nested = {key.split('.', 1)[1] for key in requested if key.startswith('structured.')}
    unknown = {
        key
        for key in requested
        if key not in card and key not in OPTIONAL_CARD_FIELDS and key not in {'structured.' + name for name in aliases}
    }
    if unknown:
        raise ToolExecutionError('Unknown card fields: ' + ', '.join(sorted(unknown)), code=-32602)
    result = {key: value for key, value in card.items() if key == 'id' or key in requested}
    if nested and 'structured' not in requested:
        result['structured'] = {key: value for key, value in (card.get('structured') or {}).items() if key in nested}
    return result
