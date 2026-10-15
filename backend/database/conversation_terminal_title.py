"""Relevance decisions and deterministic titles for server failure terminals.

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
outside the default list with a shrinking failed-status write when the mandatory decision cannot fit.
"""

from __future__ import annotations

import zlib
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from database import conversations as conversations_db
from database.conversation_terminal_effects import stage_terminal_visibility_refresh
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.conversations.recovery import structured_has_protected_content
from utils.conversations.terminal_relevance import terminal_decision, valid_decision, stamp_terminal_decision
from utils.conversations.terminal_calendar import calendar_retains
from utils.metrics import record_conversation_relevance

# Terminal failure codes after which a user reprocess can still succeed: the
# retry budget ran out on a provider, parser or worker failure. Deliberately
# excludes ``recovery_structure_unavailable`` (the model ran and found nothing
# to summarize, so a retry gives the same answer) and BYOK abandonment.
SUMMARY_RETRYABLE_FAILURE_CODES = frozenset({'processing_failed', 'final_attempt_failed'})

# Headroom kept below FIRESTORE_MAX_DOCUMENT_BYTES for estimation error.
# Generous on purpose: dropping a title near the ceiling costs nothing, while
# an underestimate aborts the terminal write.
TERMINAL_SIZE_HEADROOM_BYTES = 65_536
# Bounded probe for a described photo in the child collection.
PHOTO_DESCRIPTION_PROBE_LIMIT = 64


def transcript_texts(uid: str, conversation: Mapping[str, Any]) -> tuple[list[str], bool]:
    """``(non-blank segment texts, decoded)`` for the transactional snapshot.

    Strict: an encrypted blob must actually decrypt. ``encryption.decrypt``
    returns its input when authentication fails, and a tolerant decode would
    then parse attacker- or corruption-controlled plaintext into a title and a
    Retry offer. Any failure yields ``([], False)``: the caller degrades to the
    time title with no Retry, and never aborts the terminal write.
    """
    raw_segments = conversation.get('transcript_segments')
    if raw_segments is None:
        return [], True
    try:
        segments = conversations_db.decode_transcript_segments_verified(
            uid, raw_segments, bool(conversation.get('transcript_segments_compressed'))
        )
    except (TypeError, ValueError, zlib.error):
        return [], False
    texts: list[str] = []
    for segment in segments:
        if not isinstance(segment, Mapping) or not isinstance(segment.get('text'), str):
            return [], False  # Malformed stored content is not proof of silence.
        text = segment['text']
        if text.strip():
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
    *,
    path: str = 'orphan_terminal',
    transaction: Any = None,
) -> dict[str, Any]:
    """``base_update`` plus the deterministic title when the document can hold it.

    Shared by BYOK abandonment and orphan recovery.
    """
    texts, _decoded = transcript_texts(uid, conversation)
    extras = _title_update(uid, conversation, texts, time_zone_for_uid)
    base_update = with_terminal_relevance(
        uid, conversation, base_update, texts, _decoded, path, conversation_ref, transaction
    )
    return fit_document_limit(conversation, conversation_ref, base_update, extras)


def dead_letter_conversation_updates(
    uid: str,
    conversation: Mapping[str, Any],
    conversation_ref: Any,
    transaction: Any,
    failure_code: str,
    time_zone_for_uid: Callable[[str], str | None] | None,
) -> dict[str, Any]:
    """Close a still-bound row with relevance and an optional deterministic title.

    Content-free audio can be discarded by rule with calendar/photo protection;
    ambiguous content stays kept. A full document that cannot hold a decision
    fails outside the default list instead of publishing an undecided keep.

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
    described_photo = False
    if (
        failure_code in SUMMARY_RETRYABLE_FAILURE_CODES
        and not had_summary
        and (texts or (described_photo := _has_described_photo(conversation, conversation_ref, transaction)))
    ):
        extras['summary_retryable'] = True
    base = with_terminal_relevance(
        uid,
        {**conversation, 'has_photos': True} if described_photo else conversation,
        base,
        texts,
        _decoded,
        'dead_letter',
        conversation_ref,
        transaction,
    )
    return fit_document_limit(conversation, conversation_ref, base, extras)


def with_terminal_relevance(
    uid: str,
    conversation: Mapping[str, Any],
    base: Mapping[str, Any],
    texts: list[str],
    decoded: bool,
    path: str,
    conversation_ref: Any,
    transaction: Any,
) -> dict[str, Any]:
    decision = terminal_decision(
        conversation,
        path=path,
        texts=texts,
        decoded=decoded,
        assess=True,
        calendar_retains=lambda: calendar_retains(uid, conversation),
        photos_retain=lambda: _has_described_photo(
            conversation, conversation_ref, transaction, accept_undescribed=True
        ),
    )
    if not valid_decision(conversation.get('relevance_decision')):
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_relevance',
            from_mode='none',
            to_mode='deterministic',
            reason='other',
            outcome='degraded',
        )
    if decision['verdict'] == 'discard':
        stage_terminal_visibility_refresh(uid, getattr(conversation_ref, 'id', conversation.get('id', '')))
    record_conversation_relevance(
        trigger=decision['trigger'],
        verdict=decision['verdict'],
        decided_by=decision['decided_by'],
        reason=decision['reason'],
    )
    return {**base, 'discarded': decision['verdict'] == 'discard', 'relevance_decision': decision}


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
    # A decision is mandatory. At the actual ceiling, fail outside the default
    # processing/completed list rather than expose an undecided keep or trim content.
    path = getattr(conversation_ref, 'path', None)
    required_size = estimate_firestore_document_bytes(
        {**conversation, **base_update}, path if isinstance(path, str) else None
    )
    if required_size > FIRESTORE_MAX_DOCUMENT_BYTES:
        stage_terminal_visibility_refresh(
            uid_from_conversation_path(path if isinstance(path, str) else '') or '',
            getattr(conversation_ref, 'id', ''),
        )
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_relevance', from_mode='none', to_mode='none', reason='other', outcome='exhausted'
        )
        return {'status': 'failed'}
    combined = {**base_update, **extras}
    if not extras:
        return combined
    after = {**conversation, **combined}
    path = getattr(conversation_ref, 'path', None)
    estimated = estimate_firestore_document_bytes(after, path if isinstance(path, str) else None)
    if estimated + TERMINAL_SIZE_HEADROOM_BYTES > FIRESTORE_MAX_DOCUMENT_BYTES:
        return dict(base_update)
    return combined


def _has_described_photo(
    conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any, *, accept_undescribed: bool = False
) -> bool:
    """Whether the summarizer would receive at least one photo description."""
    inline = conversation.get('photos')
    if isinstance(inline, list) and any(accept_undescribed or _described(photo) for photo in inline):
        return True
    # Photo docs live in the child collection; probe a bounded prefix inside
    # this transaction's snapshot. `has_photos` alone proves no description.
    photos = conversation_ref.collection('photos').limit(PHOTO_DESCRIPTION_PROBE_LIMIT)
    for snapshot in photos.stream(transaction=transaction):
        if accept_undescribed:
            return True
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


def recover_deferred_processing_failure_txn(transaction: Any, conversation_ref: Any) -> bool:
    """Atomically publish a retryable terminal after deferred enrichment fails."""
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if (
        data.get('status') not in {'processing', 'completed'}
        or data.get('discarded')
        or data.get('deferred') is not False
    ):
        return False
    terminal = {**data, 'status': 'completed', 'deferred': True}
    stamp_terminal_decision(terminal, path='deferred_retry')
    transaction.update(conversation_ref, {key: terminal[key] for key in ('status', 'deferred', 'relevance_decision')})
    return True


def uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == 'conversations':
        return parts[1]
    return None
