"""Bounded, opt-in conversation retrieval projection for JIT chat evidence."""

import hashlib
import os
import re
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.conversations.mcp_transcript_search import build_transcript_match_snippets

MAX_JIT_CONVERSATIONS = 20
MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS = 24
MAX_JIT_TRANSCRIPT_SNIPPETS = 3
MAX_JIT_RESULT_CHARS = 24000
MAX_CHAT_EVIDENCE_REFERENCES = 24
MAX_EVIDENCE_ID_COMPONENT_CHARS = 96
MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS = 500
MAX_JIT_TRANSCRIPT_TEXT_CHARS = 1200
MAX_JIT_ACTION_ITEMS = 5
MAX_JIT_ACTION_ITEM_CHARS = 240
MAX_JIT_CATEGORY_CHARS = 80
MAX_JIT_EMOJI_CHARS = 16
MAX_JIT_TIMESTAMP_CHARS = 64
JIT_TRUNCATION_MARKER = "[Bounded JIT result omitted additional evidence records.]"
JIT_CONVERSATION_RETRIEVAL_ENV = "JIT_CONVERSATION_RETRIEVAL_ENABLED"
JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY = "jit_conversation_retrieval_enabled"
_SAFE_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")


def _is_enabled_value(value: Any) -> bool:
    """Accept only explicit boolean gate values and fail closed otherwise."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_jit_conversation_retrieval_enabled(configurable: Optional[Dict[str, Any]]) -> bool:
    """Return whether the additive JIT conversation contract is explicitly enabled.

    A per-request config value wins over the environment feature flag, including an
    explicit false. Keeping the default false preserves released tool behavior until
    a caller or rollout configuration opts in.
    """
    if isinstance(configurable, dict) and JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY in configurable:
        return _is_enabled_value(configurable[JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY])
    return _is_enabled_value(os.getenv(JIT_CONVERSATION_RETRIEVAL_ENV, "false"))


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
    return parsed.isoformat()[:MAX_JIT_TIMESTAMP_CHARS]


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
    return {
        "conversation_ref": _stable_conversation_ref(conversation_id),
        "summary_evidence_ref": f"{_stable_conversation_ref(conversation_id)}:summary",
        "conversation_id": conversation_id,
        "created_at": created_at,
        "started_at": _normalized_timestamp(conversation_data.get("started_at")) or "",
        "finished_at": _normalized_timestamp(conversation_data.get("finished_at")) or "",
        "title": str(structured.get("title") or "").strip()[:160],
        "overview": str(structured.get("overview") or "").strip()[:600],
        "category": str(structured.get("category") or "").strip()[:MAX_JIT_CATEGORY_CHARS],
        "emoji": str(structured.get("emoji") or "").strip()[:MAX_JIT_EMOJI_CHARS],
        "action_items": [
            str(item.get("description") or item.get("text") or "").strip()[:MAX_JIT_ACTION_ITEM_CHARS]
            for item in action_items[:MAX_JIT_ACTION_ITEMS]
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
            }
        )
    return window


def _format_summary_card(card: Dict[str, Any], index: int) -> str:
    """Format one independently admissible summary record."""
    lines = [
        f"Conversation card #{index}",
        f"conversation_ref: {card['conversation_ref']}",
        f"summary_evidence_ref: {card['summary_evidence_ref']}",
        f"conversation_id: {card['conversation_id']}",
    ]
    for field in ("created_at", "started_at", "finished_at", "category"):
        value = card.get(field)
        if value:
            lines.append(f"{field}: {value}")
    if card.get("title"):
        lines.append(f"title: {card['title']}")
    if card.get("overview"):
        lines.append(f"overview: {card['overview']}")
    if card.get("action_items"):
        lines.append("action_items: " + " | ".join(card["action_items"]))
    return "\n".join(lines)


def _can_admit(blocks: Sequence[str], block: str) -> bool:
    """Reserve room for an honest truncation marker while admitting whole records."""
    separator_chars = 2 if blocks else 0
    current_chars = sum(len(item) for item in blocks) + max(0, len(blocks) - 1) * 2
    return current_chars + separator_chars + len(block) + 2 + len(JIT_TRUNCATION_MARKER) <= MAX_JIT_RESULT_CHARS


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
) -> str:
    """Render only whole records whose text and reference can be admitted together."""
    bounded_conversations = list(conversations_data)[:MAX_JIT_CONVERSATIONS]
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    seen_conversation_ids: set[str] = set()
    rejected_or_duplicate = False
    for data in bounded_conversations:
        card = _summary_card_from_data(data)
        if card is None or card["conversation_id"] in seen_conversation_ids:
            rejected_or_duplicate = True
            continue
        seen_conversation_ids.add(card["conversation_id"])
        candidates.append((data, card))
    if not candidates:
        return JIT_TRUNCATION_MARKER if bounded_conversations else ""
    blocks: List[str] = []
    admitted: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    truncated = rejected_or_duplicate or len(conversations_data) > len(bounded_conversations)
    for data, card in candidates:
        block = _format_summary_card(card, len(admitted) + 1)
        if not _can_admit(blocks, block):
            truncated = True
            break
        if not _append_evidence_reference(evidence_references, _summary_card_evidence_reference(card)):
            truncated = True
            break
        blocks.append(block)
        admitted.append((data, card))
        _append_collected_conversation(conversations_collected, card)

    if hydrate_transcript_windows:
        for data, card in admitted:
            conversation_id = card["conversation_id"]
            if query:
                segments_raw = data.get("transcript_segments") or []
                segments = segments_raw if isinstance(segments_raw, (list, tuple)) else []
                bounded_segments = list(islice(segments, MAX_JIT_TRANSCRIPT_SCAN_SEGMENTS))
                snippets = build_transcript_match_snippets(
                    bounded_segments,
                    query,
                    context_neighbors=0,
                    max_snippets=max(1, min(int(max_transcript_snippets), MAX_JIT_TRANSCRIPT_SNIPPETS)),
                )
                seen_segment_ids: set[str] = set()
                for snippet_index, snippet in enumerate(snippets):
                    segment_id = _unique_subordinate_identity(
                        snippet.get("segment_id"), index=snippet_index, seen=seen_segment_ids
                    )
                    evidence_ref = _stable_segment_ref(conversation_id, segment_id, 0)
                    text = str(snippet.get("text") or "").strip()[:MAX_JIT_TRANSCRIPT_TEXT_CHARS]
                    block = "\n".join(
                        [
                            f"{card['conversation_ref']} transcript_match",
                            f"evidence_ref: {evidence_ref}",
                            f"start_ms: {snippet.get('start_ms')}",
                            f"end_ms: {snippet.get('end_ms')}",
                            f"text: {text}",
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
            else:
                segments_raw = data.get("transcript_segments") or []
                segments = segments_raw if isinstance(segments_raw, (list, tuple)) else []
                window = _bounded_transcript_window(
                    segments,
                    offset=transcript_window_offset,
                    limit=transcript_window_segments,
                    conversation_id=conversation_id,
                )
                for segment in window:
                    segment_identity = segment.get("segment_id") or segment["evidence_ref"].rsplit(":", 1)[-1]
                    block = "\n".join(
                        [
                            f"{card['conversation_ref']} transcript_window",
                            f"evidence_ref: {segment['evidence_ref']}",
                            f"segment_id: {segment.get('segment_id')}",
                            f"start: {segment.get('start')}",
                            f"end: {segment.get('end')}",
                            f"text: {segment['text']}",
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
    result = "\n\n".join(blocks)
    if truncated:
        result = f"{result}\n\n{JIT_TRUNCATION_MARKER}" if result else JIT_TRUNCATION_MARKER
    return result


def format_active_jit_conversations(
    conversations_data: Sequence[Dict[str, Any]],
    *,
    configurable: Dict[str, Any],
    query: Optional[str] = None,
    max_transcript_segments: int = 0,
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
    )
