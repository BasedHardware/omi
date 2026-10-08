"""One-turn conversation-note presentation guard."""

from typing import Iterable, Optional

from models.structured import Structured
from utils.llm.meeting_notes_validation import enforce_structured_presentation_contract


def sanitize_conversation_note_presentation(
    structured: Structured, transcript_segment_ids: Optional[Iterable[object]]
) -> Structured:
    """Preserve source membership and visible prose without buying a revision turn."""
    enforce_structured_presentation_contract(structured, transcript_segment_ids, safe_fallback=True)
    return structured
