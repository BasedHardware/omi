"""Bounded, opt-in conversation retrieval projection for JIT chat evidence."""

import hashlib
import re
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments
from utils.model_text import (
    DisplayClock,
    ELAPSED_LEGEND,
    UNTRUSTED_LEGEND,
    format_elapsed,
    format_span,
    generated,
    truncation_note,
    untrusted_block,
)
from utils.retrieval.turn_refs import register_record_ref
from utils.retrieval.tools import conversation_jit_gate as _jit_gate

JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY = _jit_gate.JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY
is_jit_conversation_retrieval_enabled = _jit_gate.is_jit_conversation_retrieval_enabled

MAX_JIT_CONVERSATIONS = 20
MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS = 24
MAX_JIT_TRANSCRIPT_SNIPPETS = 3
MAX_JIT_RESULT_CHARS = 24000
# Room kept for what is appended after the blocks: the final truncation note and both legends.
_JIT_TAIL_RESERVE_CHARS = 520
MAX_CHAT_EVIDENCE_REFERENCES = 24
MAX_EVIDENCE_ID_COMPONENT_CHARS = 96
MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS = 500
MAX_JIT_TRANSCRIPT_TEXT_CHARS = 1200
MAX_JIT_ACTION_ITEMS = 5
MAX_JIT_ACTION_ITEM_CHARS = 240
MAX_JIT_CATEGORY_CHARS = 80
MAX_JIT_EMOJI_CHARS = 16
MAX_JIT_TIMESTAMP_CHARS = 64
MAX_JIT_PARTICIPANTS = 12
MAX_JIT_PARTICIPANT_NAME_CHARS = 96
JIT_TRUNCATION_MARKER = "more were omitted, not absent"
_SAFE_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_CALENDAR_BACKED_SOURCES = frozenset(
    {"system_calendar", "macos_calendar", "google", "google_calendar", "outlook_calendar"}
)


def _jit_transcript_options(max_transcript_segments: int) -> Tuple[bool, int]:
    """Map legacy transcript arguments to the bounded JIT hydration contract."""
    if max_transcript_segments == 0:
        return False, 0
    if max_transcript_segments == -1:
        return True, MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS
    return True, max(1, min(int(max_transcript_segments), MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS))


def _validated_conversation_id(conversation_id: Any) -> Optional[str]:
    """Accept only bounded identifiers that remain resolvable and delimiter-safe."""
    normalized = str(conversation_id).strip() if conversation_id is not None else ""
    if (
        not normalized
        or len(normalized) > MAX_EVIDENCE_ID_COMPONENT_CHARS
        or _SAFE_IDENTITY_RE.fullmatch(normalized) is None
    ):
        return None
    return normalized


def _stable_conversation_ref(conversation_id: str) -> str:
    """Return the stable public reference used by JIT cards and evidence."""
    return f"conversation:{conversation_id}"


def _normalized_timestamp(value: Any) -> Optional[str]:
    """Return a bounded ISO timestamp with an explicit offset, or reject it."""
    parsed: Optional[datetime]
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()[:MAX_JIT_TIMESTAMP_CHARS]  # not-model-facing: bounded citation collector metadata


def _bounded_participant_name(value: Any) -> Optional[str]:
    """Return one display-only participant name without leaking addresses or controls."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized or "@" in normalized:
        return None
    return normalized


def _participant_names_from_data(conversation_data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Project bounded names only from attributable calendar records.

    Screen-derived meeting identity is intentionally excluded: OCR can contain
    unrelated calendar tiles and is not authoritative participant evidence.
    """
    candidates: List[Any] = []
    external_data = conversation_data.get("external_data")
    external = external_data if isinstance(external_data, dict) else {}
    calendar_context_raw = external.get("calendar_meeting_context") or conversation_data.get("calendar_meeting_context")
    if (
        isinstance(calendar_context_raw, dict)
        and calendar_context_raw.get("calendar_source") in _CALENDAR_BACKED_SOURCES
    ):
        participants = calendar_context_raw.get("participants")
        if isinstance(participants, (list, tuple)):
            candidates.extend(item.get("name") for item in participants if isinstance(item, dict))

    calendar_event = conversation_data.get("calendar_event")
    if isinstance(calendar_event, dict):
        attendees = calendar_event.get("attendees")
        if isinstance(attendees, (list, tuple)):
            candidates.extend(attendees)

    names: List[str] = []
    truncation_notes: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        name = _bounded_participant_name(candidate)
        if name is None:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        shown_name = name[:MAX_JIT_PARTICIPANT_NAME_CHARS]
        notes = truncation_note(
            shown=len(shown_name),
            total=len(name),
            unit="participant name characters",
            how_to_get_more="Open the conversation calendar details.",
        )
        if notes:
            truncation_notes.append(notes)
        names.append(shown_name)
    if len(names) > MAX_JIT_PARTICIPANTS:
        note = truncation_note(
            shown=MAX_JIT_PARTICIPANTS,
            total=len(names),
            unit="calendar participant names",
            how_to_get_more="Open the conversation calendar details.",
        )
        if note:
            truncation_notes.append(note)
    return names[:MAX_JIT_PARTICIPANTS], truncation_notes


def _bounded_identity_component(value: Any, *, fallback: str) -> str:
    """Encode a subordinate identity without delimiter/control-character collisions."""
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        return fallback
    if len(normalized) <= MAX_EVIDENCE_ID_COMPONENT_CHARS and _SAFE_IDENTITY_RE.fullmatch(normalized):
        return normalized
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    sanitized = re.sub(r"[^A-Za-z0-9._~-]+", "-", normalized).strip("-._~") or "legacy"
    prefix_length = MAX_EVIDENCE_ID_COMPONENT_CHARS - len(digest) - 1
    return f"{sanitized[:prefix_length]}-{digest}"


def _stable_segment_ref(conversation_id: str, segment_id: Any, index: int) -> str:
    """Return a deterministic segment evidence reference, including legacy rows."""
    identity = _bounded_identity_component(segment_id, fallback=f"index-{index}")
    return f"{_stable_conversation_ref(conversation_id)}:segment:{identity}"


def _unique_subordinate_identity(value: Any, *, index: int, seen: set[str]) -> str:
    """Return one bounded identity, disambiguating malformed legacy duplicates."""
    base_identity = _bounded_identity_component(value, fallback=f"index-{index}")
    identity = base_identity
    collision_attempt = 0
    while identity in seen:
        collision_attempt += 1
        identity = _bounded_identity_component(
            f"{base_identity}-duplicate-{index}-{collision_attempt}", fallback=f"index-{index}-{collision_attempt}"
        )
    seen.add(identity)
    return identity


def _summary_card_from_data(conversation_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Project one conversation into bounded, transcript-free JIT card data."""
    conversation_id = _validated_conversation_id(
        conversation_data.get("id") or conversation_data.get("conversation_id")
    )
    created_at = _normalized_timestamp(conversation_data.get("created_at"))
    if conversation_id is None or created_at is None:
        return None
    structured_raw = conversation_data.get("structured") or {}
    structured = structured_raw if isinstance(structured_raw, dict) else {}
    action_items_raw = structured.get("action_items") or []
    action_items = action_items_raw if isinstance(action_items_raw, (list, tuple)) else []
    participants, participant_truncation_notes = _participant_names_from_data(conversation_data)
    return {
        "conversation_ref": _stable_conversation_ref(conversation_id),
        "summary_evidence_ref": f"{_stable_conversation_ref(conversation_id)}:summary",
        "conversation_id": conversation_id,
        "created_at": created_at,
        "started_at": _normalized_timestamp(conversation_data.get("started_at")) or "",
        "finished_at": _normalized_timestamp(conversation_data.get("finished_at")) or "",
        "title": str(structured.get("title") or "").strip(),
        "overview": str(structured.get("overview") or "").strip(),
        "category": str(structured.get("category") or "").strip(),
        "emoji": str(structured.get("emoji") or "").strip()[:MAX_JIT_EMOJI_CHARS],
        "participants": participants,
        "projection_truncation_notes": participant_truncation_notes,
        "action_items": [
            {
                "description": str(item.get("description") or item.get("text") or "").strip(),
                "completed": bool(item.get("completed", False)),
            }
            for item in action_items
            if isinstance(item, dict) and str(item.get("description") or item.get("text") or "").strip()
        ],
    }


def _append_evidence_reference(
    evidence_references: Optional[List[Dict[str, Any]]],
    reference: Dict[str, Any],
) -> bool:
    """Append one bounded, de-duplicated reference to the shared chat envelope."""
    if evidence_references is None:
        return True
    reference_id = reference.get("id")
    if not isinstance(reference_id, str) or not reference_id.strip():
        return False
    if any(item.get("id") == reference_id for item in evidence_references):
        return True
    if len(evidence_references) >= MAX_CHAT_EVIDENCE_REFERENCES:
        return False
    evidence_references.append(reference)
    return True


def _summary_card_evidence_reference(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": card["summary_evidence_ref"],
        "kind": "conversation_summary",
        "state": "available",
        "conversation_id": card["conversation_id"],
        "title": card.get("title") or None,
        "summary": card.get("overview") or None,
    }


def _bounded_transcript_window(
    segments: Sequence[Any],
    *,
    offset: int,
    limit: int,
    conversation_id: str,
) -> List[Dict[str, Any]]:
    """Return a deterministic transcript slice with stable evidence refs."""
    bounded_offset = min(max(0, int(offset)), MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS)
    bounded_limit = max(1, min(int(limit), MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS))
    selected = list(
        islice(
            (segment for segment in segments if isinstance(segment, dict)),
            bounded_offset,
            min(bounded_offset + bounded_limit, MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS),
        )
    )
    window: List[Dict[str, Any]] = []
    seen_segment_ids: set[str] = set()
    for index, segment in enumerate(selected):
        text = str(segment.get("text") or "").strip()[:MAX_JIT_TRANSCRIPT_TEXT_CHARS]
        if not text:
            continue
        absolute_index = bounded_offset + index
        segment_id = _unique_subordinate_identity(segment.get("id"), index=absolute_index, seen=seen_segment_ids)
        window.append(
            {
                "evidence_ref": _stable_segment_ref(conversation_id, segment_id, absolute_index),
                "segment_id": segment_id,
                "start": segment.get("start"),
                "end": segment.get("end"),
                "text": text,
                "speaker_id": segment.get("speaker_id"),
                "is_user": bool(segment.get("is_user", False)),
                "person_id": segment.get("person_id"),
                "speaker_id_scope": segment.get("speaker_id_scope"),
                "text_total_chars": len(str(segment.get("text") or "").strip()),
            }
        )
    return window


def _speaker_label(segment: Optional[Dict[str, Any]], *, user_name: str, people_names: Dict[str, str]) -> str:
    if segment and segment.get("is_user"):
        return user_name
    person_id = segment.get("person_id") if segment else None
    if person_id and str(person_id) in people_names:
        return people_names[str(person_id)]
    speaker_id = segment.get("speaker_id") if segment else None
    return f"Speaker {speaker_id}" if speaker_id is not None else "Unknown speaker"


def _format_summary_card(card: Dict[str, Any], index: int, clock: DisplayClock) -> str:
    """Format one independently admissible summary record."""
    lines = [
        f"Conversation card #{index}",
        f"ref: conversations/{card['conversation_id']}",
        f"conversation_ref: {card['conversation_ref']}",
        f"summary_evidence_ref: {card['summary_evidence_ref']}",
        f"conversation_id: {card['conversation_id']}",
    ]
    if card.get("created_at"):
        lines.append(
            "When: " + format_span(card.get("started_at") or card.get("created_at"), card.get("finished_at"), clock)
        )
    truncation_notes: List[str] = list(card.get("projection_truncation_notes") or [])
    category = str(card.get("category") or "")
    if category:
        shown_category = category[:MAX_JIT_CATEGORY_CHARS]
        lines.append(f"category: {shown_category}")
        note = truncation_note(
            shown=len(shown_category),
            total=len(category),
            unit="category characters",
            how_to_get_more="Open the conversation.",
        )
        if note:
            truncation_notes.append(note)
    if card.get("participants"):
        lines.append("participants: " + " | ".join(card["participants"]))
    generated_lines: List[str] = []
    title = str(card.get("title") or "")
    if title:
        shown_title = title[:160]
        generated_lines.append(generated("Title", shown_title))
        note = truncation_note(
            shown=len(shown_title), total=len(title), unit="title characters", how_to_get_more="Open the conversation."
        )
        if note:
            truncation_notes.append(note)
    overview = str(card.get("overview") or "")
    if overview:
        shown_overview = overview[:600]
        generated_lines.append(generated("Overview", shown_overview))
        note = truncation_note(
            shown=len(shown_overview),
            total=len(overview),
            unit="overview characters",
            how_to_get_more="Open the conversation.",
        )
        if note:
            truncation_notes.append(note)
    action_items = card.get("action_items") or []
    if action_items:
        shown_items = action_items[:MAX_JIT_ACTION_ITEMS]
        action_lines = [
            f"- [{'done' if item['completed'] else 'open'}] {item['description'][:MAX_JIT_ACTION_ITEM_CHARS]}"
            for item in shown_items
        ]
        generated_lines.append(generated("Action Items", "\n".join(action_lines)))
        if len(action_items) > len(shown_items):
            note = truncation_note(
                shown=len(shown_items),
                total=len(action_items),
                unit="action items",
                how_to_get_more="Open the conversation action items.",
            )
            if note:
                truncation_notes.append(note)
        for item in shown_items:
            description = str(item["description"])
            shown_description = description[:MAX_JIT_ACTION_ITEM_CHARS]
            note = truncation_note(
                shown=len(shown_description),
                total=len(description),
                unit="action item characters",
                how_to_get_more="Open the conversation action items.",
            )
            if note:
                truncation_notes.append(note)
    if generated_lines:
        lines.append(untrusted_block("conversation", "\n".join(generated_lines)))
    lines.extend(truncation_notes)
    return "\n".join(lines)


def _can_admit(blocks: Sequence[str], block: str) -> bool:
    """Reserve room for an honest truncation marker while admitting whole records."""
    separator_chars = 2 if blocks else 0
    current_chars = sum(len(item) for item in blocks) + max(0, len(blocks) - 1) * 2
    return current_chars + separator_chars + len(block) + 2 + _JIT_TAIL_RESERVE_CHARS <= MAX_JIT_RESULT_CHARS


def _admit_notes(blocks: List[str], notes: Sequence[str]) -> bool:
    """Append truncation notes inside the result budget; True when one did not fit."""
    for note in notes:
        if not note:
            continue
        if not _can_admit(blocks, note):
            return True
        blocks.append(note)
    return False


def _append_collected_conversation(
    conversations_collected: Optional[List[Dict[str, Any]]], card: Dict[str, Any]
) -> None:
    """Preserve the released numbered-citation collector without heavy source fields."""
    if conversations_collected is None:
        return
    conversation_id = card["conversation_id"]
    conversations_collected.append(
        {
            "id": conversation_id,
            "created_at": card.get("created_at") or None,
            "started_at": card.get("started_at") or None,
            "finished_at": card.get("finished_at") or None,
            "structured": {
                "title": card.get("title") or "",
                "emoji": card.get("emoji") or "",
                "overview": card.get("overview") or "",
                "category": card.get("category") or "",
            },
        }
    )


def format_jit_results(
    conversations_data: Sequence[Dict[str, Any]],
    *,
    query: Optional[str] = None,
    hydrate_transcript_windows: bool = False,
    transcript_window_segments: int = 12,
    transcript_window_offset: int = 0,
    max_transcript_snippets: int = 3,
    evidence_references: Optional[List[Dict[str, Any]]] = None,
    conversations_collected: Optional[List[Dict[str, Any]]] = None,
    coverage_note: Optional[str] = None,
    configurable: Optional[Dict[str, Any]] = None,
    clock: Optional[DisplayClock] = None,
    user_name: str = "User",
    people_names: Optional[Dict[str, str]] = None,
) -> str:
    """Render only whole records whose text and reference can be admitted together."""
    configurable = configurable or {}
    # Callers pass the turn clock; the fallback stays pure (turn zone or labelled UTC, no lookup).
    clock = clock or DisplayClock.from_name(configurable.get("user_timezone"))
    people_names = people_names or {}
    bounded_conversations = list(conversations_data)[:MAX_JIT_CONVERSATIONS]
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any], Optional[int]]] = []
    seen_conversation_ids: set[str] = set()
    collected_conversation_indexes = {
        item.get("id"): index
        for index, item in enumerate(conversations_collected or [], start=1)
        if isinstance(item.get("id"), str)
    }
    rejected_or_duplicate = False
    for data in bounded_conversations:
        card = _summary_card_from_data(data)
        if card is None or card["conversation_id"] in seen_conversation_ids:
            rejected_or_duplicate = True
            continue
        conversation_id = card["conversation_id"]
        seen_conversation_ids.add(conversation_id)
        existing_card_index = collected_conversation_indexes.get(conversation_id)
        if existing_card_index is not None and not hydrate_transcript_windows:
            rejected_or_duplicate = True
            continue
        candidates.append((data, card, existing_card_index))
    blocks: List[str] = [coverage_note] if coverage_note else []
    if not candidates:
        if bounded_conversations:
            note = truncation_note(
                shown=0,
                total=None,
                unit="conversation evidence records",
                how_to_get_more="Request a narrower search or an exact conversation.",
                cut=True,
            )
            blocks.append(note)
        return "\n\n".join(blocks)
    admitted: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    first_card_index = len(conversations_collected) + 1 if conversations_collected is not None else 1
    new_card_count = 0
    truncated = rejected_or_duplicate or len(conversations_data) > len(bounded_conversations)
    shown_evidence_records = 0
    elapsed_timestamps_shown = False
    untrusted_content_shown = False
    for data, card, existing_card_index in candidates:
        if existing_card_index is not None:
            admitted.append((data, card))
            continue
        block = _format_summary_card(card, first_card_index + new_card_count, clock)
        if not _can_admit(blocks, block):
            truncated = True
            break
        if not _append_evidence_reference(evidence_references, _summary_card_evidence_reference(card)):
            truncated = True
            break
        blocks.append(block)
        shown_evidence_records += 1
        untrusted_content_shown = untrusted_content_shown or bool(
            card.get("title") or card.get("overview") or card.get("action_items")
        )
        admitted.append((data, card))
        _append_collected_conversation(conversations_collected, card)
        register_record_ref(configurable, 'conversations', card['conversation_id'])
        new_card_count += 1

    if hydrate_transcript_windows:
        for data, card in admitted:
            conversation_id = card["conversation_id"]
            raw_segments = data.get("transcript_segments") or []
            all_segments = (
                [segment for segment in raw_segments if isinstance(segment, dict)]
                if isinstance(raw_segments, (list, tuple))
                else []
            )
            owner_safe_segments, owner_note = owner_safe_transcript_segments(all_segments)
            segments_by_id = {
                str(segment.get("id")): segment for segment in owner_safe_segments if segment.get("id") is not None
            }
            transcript_truncation_notes: List[str] = []
            if len(all_segments) > MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS:
                transcript_truncation_notes.append(
                    truncation_note(
                        shown=MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS,
                        total=len(all_segments),
                        unit="transcript segments scanned",
                        how_to_get_more="Request a narrower transcript query.",
                    )
                )
            if query:
                bounded_segments = list(islice(owner_safe_segments, MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS))
                max_snippets = max(1, min(int(max_transcript_snippets), MAX_JIT_TRANSCRIPT_SNIPPETS))
                candidate_snippets = build_transcript_match_snippets(
                    bounded_segments,
                    query,
                    context_neighbors=0,
                    max_snippets=max_snippets + 1,
                )
                snippets = candidate_snippets[:max_snippets]
                if len(candidate_snippets) > len(snippets):
                    transcript_truncation_notes.append(
                        truncation_note(
                            shown=len(snippets),
                            total=None,
                            unit="matching transcript snippets",
                            how_to_get_more="Request another transcript window or a narrower query.",
                            cut=True,
                        )
                    )
                seen_segment_ids: set[str] = set()
                for snippet_index, snippet in enumerate(snippets):
                    segment_id = _unique_subordinate_identity(
                        snippet.get("segment_id"), index=snippet_index, seen=seen_segment_ids
                    )
                    evidence_ref = _stable_segment_ref(conversation_id, segment_id, 0)
                    source_segment = segments_by_id.get(str(snippet.get("segment_id")))
                    source_text = str((source_segment or {}).get("text") or snippet.get("text") or "").strip()
                    text = source_text[:MAX_JIT_TRANSCRIPT_TEXT_CHARS]
                    start_seconds = snippet.get("start")
                    end_seconds = snippet.get("end")
                    start_ms = snippet.get("start_ms")
                    end_ms = snippet.get("end_ms")
                    if start_seconds is None and start_ms is not None:
                        start_seconds = float(start_ms) / 1000
                    if end_seconds is None and end_ms is not None:
                        end_seconds = float(end_ms) / 1000
                    if start_seconds is not None or end_seconds is not None:
                        elapsed_timestamps_shown = True
                    excerpt_lines = [
                        f"speaker: {_speaker_label(source_segment, user_name=user_name, people_names=people_names)}"
                    ]
                    if start_seconds is not None or end_seconds is not None:
                        excerpt_lines.append(f"elapsed: {format_elapsed(start_seconds)}–{format_elapsed(end_seconds)}")
                    excerpt_lines.append(f"text: {text}")
                    if owner_note:
                        excerpt_lines.insert(0, owner_note)
                    item_notes: List[str] = []
                    note = truncation_note(
                        shown=len(text),
                        total=len(source_text),
                        unit="transcript characters",
                        how_to_get_more="Request a narrower transcript window.",
                    )
                    if note:
                        item_notes.append(note)
                    block = "\n".join(
                        [
                            f"{card['conversation_ref']} transcript_match",
                            f"evidence_ref: {evidence_ref}",
                            untrusted_block("transcript", "\n".join(excerpt_lines)),
                            *item_notes,
                        ]
                    )
                    reference = {
                        "id": evidence_ref,
                        "kind": "conversation_segment",
                        "state": "available",
                        "conversation_id": conversation_id,
                        "segment_id": segment_id,
                        "start_ms": snippet.get("start_ms"),
                        "end_ms": snippet.get("end_ms"),
                        "summary": text[:600] or None,
                    }
                    if not _can_admit(blocks, block) or not _append_evidence_reference(evidence_references, reference):
                        truncated = True
                        break
                    blocks.append(block)
                    shown_evidence_records += 1
                    untrusted_content_shown = True
            else:
                segments = owner_safe_segments
                window = _bounded_transcript_window(
                    segments,
                    offset=transcript_window_offset,
                    limit=transcript_window_segments,
                    conversation_id=conversation_id,
                )
                if len(segments) > len(window):
                    transcript_truncation_notes.append(
                        truncation_note(
                            shown=len(window),
                            total=len(segments),
                            unit="transcript segments in this window",
                            how_to_get_more="Request a different transcript window.",
                            cut=True,
                        )
                    )
                for segment in window:
                    segment_identity = segment.get("segment_id") or segment["evidence_ref"].rsplit(":", 1)[-1]
                    source_segment = segments_by_id.get(str(segment.get("segment_id")))
                    elapsed_timestamps_shown = (
                        elapsed_timestamps_shown or segment.get("start") is not None or segment.get("end") is not None
                    )
                    excerpt_lines = [
                        f"speaker: {_speaker_label(source_segment, user_name=user_name, people_names=people_names)}"
                    ]
                    if segment.get("start") is not None or segment.get("end") is not None:
                        excerpt_lines.append(
                            f"elapsed: {format_elapsed(segment.get('start'))}–{format_elapsed(segment.get('end'))}"
                        )
                    excerpt_lines.append(f"text: {segment['text']}")
                    if owner_note:
                        excerpt_lines.insert(0, owner_note)
                    item_notes: List[str] = []
                    note = truncation_note(
                        shown=len(segment["text"]),
                        total=segment.get("text_total_chars"),
                        unit="transcript characters",
                        how_to_get_more="Request a narrower transcript window.",
                    )
                    if note:
                        item_notes.append(note)
                    block = "\n".join(
                        [
                            f"{card['conversation_ref']} transcript_window",
                            f"evidence_ref: {segment['evidence_ref']}",
                            f"segment_id: {segment.get('segment_id')}",
                            untrusted_block("transcript", "\n".join(excerpt_lines)),
                            *item_notes,
                        ]
                    )
                    reference = {
                        "id": segment["evidence_ref"],
                        "kind": "conversation_segment",
                        "state": "available",
                        "conversation_id": conversation_id,
                        "segment_id": str(segment_identity),
                        "summary": segment["text"][:600],
                    }
                    if not _can_admit(blocks, block) or not _append_evidence_reference(evidence_references, reference):
                        truncated = True
                        break
                    blocks.append(block)
                    shown_evidence_records += 1
                    untrusted_content_shown = True
                truncated = _admit_notes(blocks, transcript_truncation_notes) or truncated
            if query:
                truncated = _admit_notes(blocks, transcript_truncation_notes) or truncated
    result = "\n\n".join(blocks)
    if truncated:
        note = truncation_note(
            shown=shown_evidence_records,
            total=None,
            unit="conversation evidence records",
            how_to_get_more="Request a narrower search or an exact conversation.",
            cut=True,
        )
        result = f"{result}\n\n{note}" if result else note
    if result and untrusted_content_shown:
        result = f"{UNTRUSTED_LEGEND}\n{result}"
    if result and elapsed_timestamps_shown:
        result = f"{ELAPSED_LEGEND}\n{result}"
    return result


def format_active_jit_conversations(
    conversations_data: Sequence[Dict[str, Any]],
    *,
    configurable: Dict[str, Any],
    query: Optional[str] = None,
    max_transcript_segments: int = 0,
    coverage_note: Optional[str] = None,
    clock: Optional[DisplayClock] = None,
    user_name: str = "User",
    people_names: Optional[Dict[str, str]] = None,
) -> str:
    """Render the opt-in card/evidence contract and populate the shared evidence sink."""
    hydrate, window_segments = _jit_transcript_options(max_transcript_segments)
    evidence_references = configurable.get("evidence_references")
    if not isinstance(evidence_references, list):
        evidence_references = None
    conversations_collected = configurable.get("conversations_collected")
    if not isinstance(conversations_collected, list):
        conversations_collected = None
    return format_jit_results(
        conversations_data,
        query=query,
        hydrate_transcript_windows=hydrate,
        transcript_window_segments=window_segments or MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS,
        max_transcript_snippets=min(window_segments, MAX_JIT_TRANSCRIPT_SNIPPETS) if hydrate else 0,
        evidence_references=evidence_references,
        conversations_collected=conversations_collected,
        coverage_note=coverage_note,
        configurable=configurable,
        clock=clock,
        user_name=user_name,
        people_names=people_names,
    )
