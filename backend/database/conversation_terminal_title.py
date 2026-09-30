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
"""

from __future__ import annotations

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


def transcript_texts(uid: str, conversation: Mapping[str, Any]) -> list[str]:
    """Non-blank segment texts of the transactional snapshot, or ``[]``.

    Uses the read path's own decode (uid-keyed AES-GCM plus zlib for
    ``enhanced`` rows, zlib for compressed ``standard`` rows). That is local CPU
    work on the snapshot this transaction already holds, so the title always
    describes exactly the transcript that commits, with no compare-and-set
    window. An undecodable blob degrades to the time-based title; it must never
    abort the terminal write that takes the row off ``processing``.
    """
    raw_segments = conversation.get('transcript_segments')
    if not raw_segments:
        return []
    try:
        decoded = conversations_db.prepare_conversation_for_read(
            {
                'transcript_segments': raw_segments,
                'transcript_segments_compressed': conversation.get('transcript_segments_compressed'),
                'data_protection_level': conversation.get('data_protection_level'),
            },
            uid,
        )
    except Exception:
        return []
    segments = (decoded or {}).get('transcript_segments')
    if not isinstance(segments, list):
        return []
    texts: list[str] = []
    for segment in segments:
        text = segment.get('text') if isinstance(segment, Mapping) else None
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return texts


def kept_row_title_update(
    uid: str,
    conversation: Mapping[str, Any],
    time_zone_for_uid: Callable[[str], str | None] | None,
) -> tuple[dict[str, Any], list[str]]:
    """``{'structured': ...}`` giving an untitled row its deterministic title, or ``{}``.

    Shared by every terminal that moves a ``processing`` row into the default
    list (dead-letter, BYOK abandonment, orphan recovery), so none can leave a
    kept row with an empty title. Only the title changes; the rest of the
    stored ``structured`` map survives. A real generated title or a
    ``user_title`` is never touched. Also returns the decoded transcript texts.
    """
    structured = conversation.get('structured')
    fields = dict(structured) if isinstance(structured, Mapping) else {'title': '', 'overview': ''}
    texts = transcript_texts(uid, conversation)
    title = fields.get('title')
    user_title = conversation.get('user_title')
    has_user_title = isinstance(user_title, str) and bool(user_title.strip())
    if not has_user_title and not (isinstance(title, str) and title.strip()):
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
    return ({'structured': fields} if fields != structured else {}), texts


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
    also guarantees every row it leaves in the default list carries something
    useful: an empty generated title is replaced by the model-free
    ``deterministic_minimum_title`` (first transcript sentence, else
    ``"Recording · 3:14 PM"``). A real title or a user title is never touched.

    ``summary_retryable=True`` is written only when a user reprocess
    can succeed: the retry budget ran out on a transient failure, the row has
    transcript text or photos to summarize, and it holds no earlier summary
    that the failure chip would misdescribe.
    """
    had_summary = structured_has_protected_content(conversation.get('structured'), conversation.get('user_title'))
    title_update, texts = kept_row_title_update(uid, conversation, time_zone_for_uid)
    updates: dict[str, Any] = {
        'status': 'completed',
        'discarded': False,
        'finalization_status': 'dead_letter',
        **title_update,
    }
    if (
        failure_code in SUMMARY_RETRYABLE_FAILURE_CODES
        and not had_summary
        and (texts or _has_photos(conversation, conversation_ref, transaction))
    ):
        updates['summary_retryable'] = True
    return updates


def _has_photos(conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any) -> bool:
    if conversation.get('photos') or conversation.get('has_photos'):
        return True
    # Photo-only rows written before `has_photos` keep their photos only in
    # the child collection; read it inside this transaction's snapshot.
    return next(iter(conversation_ref.collection('photos').limit(1).stream(transaction=transaction)), None) is not None
