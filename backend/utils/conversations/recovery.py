"""Pure helpers shared by the self-heal recovery admission fence and verifier.

Stdlib-only: ``database/conversation_finalization_jobs`` evaluates these
inside its outbox transaction, so nothing here may touch Firestore, model
clients, or a clock. Firestore document dicts and ``Structured`` models go
through the same definitions so admission and verification cannot drift.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

RECOVERY_MAX_AUDIO_FILE_IDS = 256

_RICH_STRUCTURED_FIELDS = ('overview', 'sections', 'action_items', 'events')
_PROTECTED_STRUCTURED_TEXT_FIELDS = ('title', 'overview')
_PROTECTED_STRUCTURED_LIST_FIELDS = ('sections', 'action_items', 'events')

TERMINAL_NO_DERIVED_EFFECTS_FIELD = 'terminal_no_derived_effects'


def _field(structured: Any, name: str) -> Any:
    if isinstance(structured, Mapping):
        return structured.get(name)
    return getattr(structured, name, None)


def structured_is_rich(structured: Any) -> bool:
    """Whether the structured payload holds model-enriched content.

    The deterministic minimum keeps every rich field empty, so any non-empty
    one proves enrichment ran. A recovery attempt that would persist only the
    minimum must be refused: completing the job on it would hide the failure.
    """
    for name in _RICH_STRUCTURED_FIELDS:
        value = _field(structured, name)
        if isinstance(value, str):
            if value.strip():
                return True
        elif value:
            return True
    return False


def structured_has_protected_content(structured: Any, user_title: Any = None) -> bool:
    """Whether regenerating the row could overwrite content worth keeping.

    Admission-only predicate: unlike ``structured_is_rich`` (which verifies new
    enrichment actually landed), a real ``title`` — set by the user or by an
    earlier successful pass — and the user-authored ``user_title`` field each
    make the row ineligible even with no overview, so recovery never clobbers
    a useful title for a deterministic-minimum replacement.
    """
    if isinstance(user_title, str):
        if user_title.strip():
            return True
    elif user_title:
        return True
    for name in _PROTECTED_STRUCTURED_TEXT_FIELDS:
        value = _field(structured, name)
        if isinstance(value, str) and value.strip():
            return True
    for name in _PROTECTED_STRUCTURED_LIST_FIELDS:
        if _field(structured, name):
            return True
    return False


def raw_transcript_bytes(conversation: Mapping[str, Any]) -> int:
    """Byte length of the raw encoded transcript field, never its text.

    ``transcript_segments`` may be a compressed/encoded blob or a decoded
    segment list. The byte count is a content fingerprint the follow-up tick
    compares after completion without ever logging transcript text.
    """
    raw = conversation.get('transcript_segments')
    if raw is None:
        return 0
    if isinstance(raw, str):
        return len(raw.encode('utf-8'))
    if isinstance(raw, (bytes, bytearray)):
        return len(raw)
    return len(json.dumps(raw, sort_keys=True, default=str).encode('utf-8'))


def recovery_audio_file_ids(conversation: Mapping[str, Any]) -> list[str] | None:
    """Sorted durable audio-file ids, or ``None`` when the row cannot be tracked.

    The verification fingerprint must describe every stored file: an oversized
    list, a non-mapping entry, or a missing/blank id all refuse rather than
    silently narrowing the set the follow-up tick preserves.
    """
    audio_files = conversation.get('audio_files')
    if not audio_files:
        return []
    if not isinstance(audio_files, (list, tuple)) or len(audio_files) > RECOVERY_MAX_AUDIO_FILE_IDS:
        return None
    if not all(isinstance(entry, Mapping) and entry.get('id') for entry in audio_files):
        return None
    return sorted(str(entry['id']) for entry in audio_files)


class RecoveryStructureUnavailableError(RuntimeError):
    """SERVER_RECOVERY produced only the deterministic minimum.

    Raised before persistence so the row keeps its in-progress content and
    lifecycle status untouched; the durable finalization workflow owns the
    terminal disposition through its existing dead-letter path.
    """
