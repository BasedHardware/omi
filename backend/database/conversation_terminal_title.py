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
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from database import conversations as conversations_db
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.conversations.recovery import structured_has_protected_content

# Terminal failure codes after which a user reprocess can still succeed: the
# retry budget ran out on a provider, parser or worker failure. Deliberately
# excludes ``recovery_structure_unavailable`` (the model ran and found nothing
# to summarize, so a retry gives the same answer) and BYOK abandonment.
SUMMARY_RETRYABLE_FAILURE_CODES = frozenset({'processing_failed', 'final_attempt_failed'})

# Firestore's maximum document size, and the headroom kept for estimation error.
FIRESTORE_MAX_DOCUMENT_BYTES = 1_048_576
TERMINAL_SIZE_HEADROOM_BYTES = 4_096
# Bounded probe for a described photo in the child collection.
PHOTO_DESCRIPTION_PROBE_LIMIT = 64
# Used when a test double exposes no document path.
_FALLBACK_DOCUMENT_NAME_BYTES = 256


def transcript_texts(uid: str, conversation: Mapping[str, Any]) -> tuple[list[str], bool]:
    """``(non-blank segment texts, decoded)`` for the transactional snapshot.

    Strict: an encrypted blob must actually decrypt. ``encryption.decrypt``
    returns its input when authentication fails, and a tolerant decode would
    then parse attacker- or corruption-controlled plaintext into a title and a
    Retry offer. Any failure yields ``([], False)``: the caller degrades to the
    time title with no Retry, and never aborts the terminal write.
    """
    raw_segments = conversation.get('transcript_segments')
    if not raw_segments:
        return [], True
    try:
        segments = conversations_db.decode_transcript_segments_verified(
            uid, raw_segments, bool(conversation.get('transcript_segments_compressed'))
        )
    except (TypeError, ValueError, zlib.error):
        return [], False
    texts: list[str] = []
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
    structured = conversation.get('structured')
    fields = dict(structured) if isinstance(structured, Mapping) else {'title': '', 'overview': ''}
    title = fields.get('title')
    if conversations_db.effective_user_title(conversation.get('user_title')) is None and not (
        isinstance(title, str) and title.strip()
    ):
        started_at = conversation.get('started_at')
        if not isinstance(started_at, datetime):
            started_at = conversation.get('created_at')
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
    had_summary = structured_has_protected_content(
        conversation.get('structured'), conversations_db.effective_user_title(conversation.get('user_title'))
    )
    texts, _decoded = transcript_texts(uid, conversation)
    base: dict[str, Any] = {'status': 'completed', 'discarded': False, 'finalization_status': 'dead_letter'}
    if not isinstance(conversation.get('structured'), Mapping):
        # The API model needs a structured map even to return the row.
        base['structured'] = {'title': '', 'overview': ''}
    extras = _title_update(uid, conversation, texts, time_zone_for_uid)
    if (
        failure_code in SUMMARY_RETRYABLE_FAILURE_CODES
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
    combined = {**base_update, **extras}
    if not extras:
        return combined
    after = {**conversation, **combined}
    path = getattr(conversation_ref, 'path', None)
    estimated = estimate_firestore_document_bytes(after, path if isinstance(path, str) else None)
    if estimated + TERMINAL_SIZE_HEADROOM_BYTES > FIRESTORE_MAX_DOCUMENT_BYTES:
        return dict(base_update)
    return combined


def estimate_firestore_document_bytes(data: Mapping[str, Any], document_path: str | None) -> int:
    """Firestore's documented storage size of one document.

    Document name: each path segment plus one byte, plus 16. Document: the
    fields plus 32. Field: name (UTF-8 plus one) plus value. Strings are UTF-8
    plus one; booleans and null one; numbers and timestamps eight; geo points
    sixteen; bytes their length; arrays and maps the sum of their contents.
    """
    if document_path:
        name_bytes = sum(len(part.encode('utf-8')) + 1 for part in document_path.split('/')) + 16
    else:
        name_bytes = _FALLBACK_DOCUMENT_NAME_BYTES
    return name_bytes + 32 + sum(len(str(key).encode('utf-8')) + 1 + _value_bytes(value) for key, value in data.items())


def _value_bytes(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, (int, float, datetime)):
        return 8
    if isinstance(value, str):
        return len(value.encode('utf-8')) + 1
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, Mapping):
        return sum(len(str(key).encode('utf-8')) + 1 + _value_bytes(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_value_bytes(item) for item in value)
    if hasattr(value, 'latitude') and hasattr(value, 'longitude'):
        return 16
    # Unknown SDK value: over-estimate rather than under-estimate.
    return len(str(value).encode('utf-8')) + 1


def _has_described_photo(conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any) -> bool:
    """Whether the summarizer would receive at least one photo description."""
    inline = conversation.get('photos')
    if isinstance(inline, list) and any(_described(photo) for photo in inline):
        return True
    # Photo docs live in the child collection; probe a bounded prefix inside
    # this transaction's snapshot. `has_photos` alone proves no description.
    photos = conversation_ref.collection('photos').limit(PHOTO_DESCRIPTION_PROBE_LIMIT)
    for snapshot in photos.stream(transaction=transaction):
        to_dict = getattr(snapshot, 'to_dict', None)
        if callable(to_dict) and _described(to_dict()):
            return True
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
    try:
        snapshot = client.collection('users').document(uid).get()
    except Exception:
        return None
    if not getattr(snapshot, 'exists', False):
        return None
    zone = (snapshot.to_dict() or {}).get('time_zone')
    return zone if isinstance(zone, str) and zone else None
