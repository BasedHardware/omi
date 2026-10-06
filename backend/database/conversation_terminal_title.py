"""Deterministic titles for rows a server terminal moves into the default list.

Every terminal that closes a ``processing`` conversation as kept and visible
(finalization dead-letter, BYOK abandonment, crash-orphan recovery) must leave
it titled, so no client ever renders a bare "Untitled Conversation" for a row
the server chose to show. The title is only ever the model-free
``deterministic_minimum_title``: the first transcript sentence, else
``"Recording · 3:14 PM"``. The dead-letter alone may also mark a row
``summary_retryable``, and only when a user reprocess can still succeed.

These helpers run inside those Firestore transactions. Transcript decode is
local CPU work (uid-keyed AES-GCM plus zlib) on the snapshot the transaction
already holds, so the title always describes the transcript that commits. The
one IO, the user's time zone for a transcript-free row, is a plain
non-transactional read that cannot fail the terminal write.

A terminal must always be able to commit. The title and retry marker only ever
grow the document, so they are added only when the estimated post-write size
stays under Firestore's 1 MiB ceiling; a row at the ceiling still terminalizes
with the pre-existing status-only write.
"""

from __future__ import annotations

import zlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from database import conversations as conversations_db
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.conversations.recovery import structured_has_protected_content

# Terminal failure codes after which a user reprocess can still succeed: the
# retry budget ran out on a provider, parser or worker failure. Includes both
# dead-letter production codes ('final_attempt_failed', 'processing_failed').
# Deliberately excludes ``recovery_structure_unavailable`` (the model ran and
# found nothing to summarize; retry would produce the same result) and BYOK
# abandonment.
SUMMARY_RETRYABLE_FAILURE_CODES: frozenset[str] = frozenset(
    {
        'final_attempt_failed',
        'processing_failed',
    }
)

# Headroom kept below FIRESTORE_MAX_DOCUMENT_BYTES for estimation error.
# Generous on purpose: dropping a title near the ceiling costs nothing, while
# an underestimate aborts the terminal write.
TERMINAL_SIZE_HEADROOM_BYTES: int = 65_536
# Bounded probe for a described photo in the child collection.
PHOTO_DESCRIPTION_PROBE_LIMIT: int = 64
MAX_ID_LENGTH: int = 128


def _clean_id(raw_id: Any, field_name: str = 'id') -> str:
    """Validate and clean identifier strings (uid, conversation_id, etc.)."""
    if not isinstance(raw_id, str):
        raise ValueError(f"{field_name} must be a string, got {type(raw_id).__name__}")
    cleaned = raw_id.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if len(cleaned) > MAX_ID_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length of {MAX_ID_LENGTH} characters")
    if '\0' in cleaned or '..' in cleaned or '/' in cleaned or '\\' in cleaned:
        raise ValueError(f"{field_name} contains invalid path traversal or control characters")
    return cleaned


def transcript_texts(uid: str, conversation: Mapping[str, Any]) -> tuple[list[str], bool]:
    """Plain-text sentences from ``transcript_segments``; ``([], True)`` on empty.

    Strict security rationale: an encrypted blob must actually decrypt.
    ``encryption.decrypt`` returns its input when authentication fails, and a
    tolerant decode would then parse attacker- or corruption-controlled plaintext
    into a title and a Retry offer. Any failure yields ``([], False)``: the caller
    degrades to the deterministic time title with no Retry, and never aborts the
    terminal write.
    """
    if not isinstance(uid, str) or not uid.strip():
        return [], False
    try:
        clean_uid = _clean_id(uid, 'uid')
    except ValueError:
        return [], False

    if not isinstance(conversation, Mapping):
        return [], False

    raw_segments = conversation.get('transcript_segments')
    if not raw_segments:
        return [], True
    try:
        segments = conversations_db.decode_transcript_segments_verified(
            clean_uid, raw_segments, bool(conversation.get('transcript_segments_compressed'))
        )
    except (TypeError, ValueError, zlib.error):
        return [], False
    texts: list[str] = []
    if isinstance(segments, (list, tuple)):
        for segment in segments:
            text: Any = segment.get('text') if isinstance(segment, Mapping) else None
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts, True


def _title_update(
    uid: str,
    conversation: Mapping[str, Any],
    texts: list[str],
    time_zone_for_uid: Callable[[str], str | None] | None,
) -> dict[str, Any]:
    """``{'structured': ...}`` giving an untitled row its deterministic title, or ``{}``.

    Only the title changes; the rest of the stored ``structured`` map
    survives. A real generated title or a non-blank ``user_title`` is never
    touched (a blank ``user_title`` is no override; see
    ``conversations_db.effective_user_title``).
    """
    if not isinstance(conversation, Mapping):
        return {}
    structured = conversation.get('structured')
    fields = dict(structured) if isinstance(structured, Mapping) else {'title': '', 'overview': ''}
    title = fields.get('title')
    user_title = conversation.get('user_title')
    if conversations_db.effective_user_title(user_title) is None and not (isinstance(title, str) and title.strip()):
        started_at = conversation.get('started_at')
        if not isinstance(started_at, datetime):
            started_at = conversation.get('created_at')
        if isinstance(started_at, datetime) and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        fields['title'] = deterministic_minimum_title(
            SimpleNamespace(
                transcript_segments=[SimpleNamespace(text=text) for text in texts],
                started_at=started_at if isinstance(started_at, datetime) else None,
            ),
            # Called only when the transcript is empty (photo-only rows).
            tz_name_provider=(lambda: time_zone_for_uid(uid)) if time_zone_for_uid is not None else None,
        )
    return {'structured': fields} if fields != structured else {}


def kept_row_terminal_update(
    uid: str,
    conversation: Mapping[str, Any],
    conversation_ref: Any,
    base_update: Mapping[str, Any],
    time_zone_for_uid: Callable[[str], str | None] | None,
) -> dict[str, Any]:
    """``base_update`` plus the deterministic title when the document can hold it.

    Shared by BYOK abandonment and orphan recovery.
    """
    texts, _decoded = transcript_texts(uid, conversation)
    extras = _title_update(uid, conversation, texts, time_zone_for_uid)
    return fit_document_limit(conversation, conversation_ref, base_update, extras)


def dead_letter_conversation_updates(
    uid: str,
    conversation: Mapping[str, Any],
    conversation_ref: Any,
    transaction: Any,
    failure_code: str,
    time_zone_for_uid: Callable[[str], str | None] | None,
) -> dict[str, Any]:
    """Close a still-bound ``processing`` row as a visible, titled conversation.

    Matches BYOK abandonment and orphan recovery (``completed``, kept), and
    also gives an untitled row its deterministic title.

    ``summary_retryable=True`` is written only when a user reprocess can
    succeed: the retry budget ran out on a transient failure, the summarizer
    has usable input (decoded transcript text, or a photo with a description;
    it reads descriptions, never pixels), and the row holds no earlier summary
    that the failure chip would misdescribe.
    """
    if not isinstance(conversation, Mapping):
        conversation = {}
    user_title = conversation.get('user_title')
    had_summary = structured_has_protected_content(
        conversation.get('structured'), conversations_db.effective_user_title(user_title)
    )
    texts, _decoded = transcript_texts(uid, conversation)
    base: dict[str, Any] = {'status': 'completed', 'discarded': False, 'finalization_status': 'dead_letter'}
    if not isinstance(conversation.get('structured'), Mapping):
        # The API model needs a structured map even to return the row.
        base['structured'] = {'title': '', 'overview': ''}
    extras = _title_update(uid, conversation, texts, time_zone_for_uid)
    clean_failure_code = failure_code.strip() if isinstance(failure_code, str) else ''
    if (
        clean_failure_code in SUMMARY_RETRYABLE_FAILURE_CODES
        and not had_summary
        and (texts or _has_described_photo(conversation, conversation_ref, transaction))
    ):
        extras['summary_retryable'] = True
    return fit_document_limit(conversation, conversation_ref, base, extras)


def fit_document_limit(
    conversation: Mapping[str, Any],
    conversation_ref: Any,
    base_update: Mapping[str, Any],
    extras: Mapping[str, Any],
) -> dict[str, Any]:
    """``base_update`` with ``extras`` merged in, unless that could exceed 1 MiB.

    ``base_update`` is the terminal's own status write, which the caller has
    always committed. ``extras`` (title, retry marker) are optional growth: an
    oversized update aborts the whole transaction and would strand the row on
    ``processing``, so they are dropped rather than risk that.
    """
    safe_base = dict(base_update) if isinstance(base_update, Mapping) else {}
    safe_extras = dict(extras) if isinstance(extras, Mapping) else {}
    combined = {**safe_base, **safe_extras}
    if not safe_extras:
        return combined
    safe_conv = dict(conversation) if isinstance(conversation, Mapping) else {}
    after = {**safe_conv, **combined}
    path = getattr(conversation_ref, 'path', None)
    estimated = estimate_firestore_document_bytes(after, path if isinstance(path, str) else None)
    if estimated + TERMINAL_SIZE_HEADROOM_BYTES > FIRESTORE_MAX_DOCUMENT_BYTES:
        return safe_base
    return combined


def _has_described_photo(conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any) -> bool:
    """Whether the summarizer would receive at least one photo description."""
    if not isinstance(conversation, Mapping) or conversation_ref is None:
        return False
    inline = conversation.get('photos')
    if isinstance(inline, list) and any(_described(photo) for photo in inline):
        return True
    # Photo docs live in the child collection; probe a bounded prefix inside
    # this transaction's snapshot. `has_photos` alone proves no description.
    try:
        photos = conversation_ref.collection('photos').limit(PHOTO_DESCRIPTION_PROBE_LIMIT)
        for snapshot in photos.stream(transaction=transaction):
            to_dict = getattr(snapshot, 'to_dict', None)
            if callable(to_dict) and _described(to_dict()):
                return True
    except Exception:
        return False
    return False


def _described(photo: Any) -> bool:
    description = photo.get('description') if isinstance(photo, Mapping) else None
    return isinstance(description, str) and bool(description.strip())


def user_time_zone(client: Any, uid: str) -> str | None:
    """The user's IANA zone for the photo-only fallback title; ``None`` on any miss.

    A plain read, not a transactional one: the zone only renders the
    ``"Recording · 3:14 PM"`` label, so it must neither join the transaction's
    read set nor be able to fail the terminal write.
    """
    if client is None or not hasattr(client, 'collection'):
        return None
    try:
        clean_uid = _clean_id(uid, 'uid')
        snapshot = client.collection('users').document(clean_uid).get()
    except Exception:
        return None
    if not getattr(snapshot, 'exists', False):
        return None
    to_dict = getattr(snapshot, 'to_dict', None)
    zone = (to_dict() or {}).get('time_zone') if callable(to_dict) else None
    return zone if isinstance(zone, str) and zone else None


__all__ = [
    'SUMMARY_RETRYABLE_FAILURE_CODES',
    'FIRESTORE_MAX_DOCUMENT_BYTES',
    'TERMINAL_SIZE_HEADROOM_BYTES',
    'PHOTO_DESCRIPTION_PROBE_LIMIT',
    'MAX_ID_LENGTH',
    '_clean_id',
    'transcript_texts',
    'kept_row_terminal_update',
    'dead_letter_conversation_updates',
    'fit_document_limit',
    'estimate_firestore_document_bytes',
    'user_time_zone',
]
