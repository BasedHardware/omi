"""Resolve and hydrate the conversation context around a thumbs-down.

Two functions, deliberately split, because they run under different trust:

* ``resolve_chat_context`` runs in the nightly report job. It reads only the
  plaintext metadata on a message document — id, sender, created_at,
  chat_session_id — and never touches ``text``. That is enforced at the wire by
  a Firestore field mask (``_METADATA_FIELDS``), not merely by which keys this
  code happens to read: the encrypted body is never sent to the job at all. Its
  output is a pointer list that is safe to persist.

* ``hydrate_context`` runs on one admin request at a time, decrypts the turns
  the pointer names, and returns them to the caller without writing them
  anywhere. This is the only path where negative-feedback conversation text
  exists in plaintext, and it exists only for the life of the response.

Keeping them apart is what lets the daily report be materialized without
creating a second, unencrypted copy of user conversations.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.chat import decrypt_message_payload
from models.feedback import (
    FeedbackContextHydrated,
    FeedbackContextPointer,
    FeedbackContextTurn,
    FeedbackContextTurnText,
    FeedbackTargetKind,
)

logger = logging.getLogger(__name__)

# How far after the thumbs-down we still count a turn as a reaction to it.
# Five minutes is wide enough to catch "let me rephrase that" and the retry it
# produces, and narrow enough that an unrelated question an hour later does not
# get read as fallout from the bad answer.
FOLLOW_UP_WINDOW_SECONDS = 5 * 60

# Preceding turns are capped rather than unbounded: a long-running session can
# hold hundreds of turns, and the setup that produced a bad answer is almost
# always in the last few. `truncated_before` records when we cut.
MAX_PRECEDING_TURNS = 10
MAX_FOLLOW_UP_TURNS = 10

# Hard cap on how much text one hydrate call returns per turn. A pasted
# document can make a single message enormous; the reviewer needs the gist.
MAX_HYDRATED_TEXT_CHARS = 4000

# The only fields the nightly resolver is allowed to pull off a message. Passed
# to Firestore as a projection so the encrypted `text` never crosses the wire
# into the report job — the no-plaintext property of the daily report holds at
# the query, not just in the code that reads the result.
_METADATA_FIELDS = ['id', 'sender', 'created_at', 'chat_session_id']


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for a Firestore snapshot's `to_dict()` (SDK stub gap)."""
    raw: object = doc.to_dict()
    return raw if isinstance(raw, dict) else {}


def _as_utc(value: Any) -> Optional[datetime]:
    """Firestore returns DatetimeWithNanoseconds; normalize to aware UTC."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _messages_ref(uid: str):
    return get_firestore_client().collection('users').document(uid).collection('messages')


def _select_metadata(query: Any) -> Any:
    """Apply the metadata projection, tolerating fakes that lack `select`."""
    select = getattr(query, 'select', None)
    return select(_METADATA_FIELDS) if callable(select) else query


def _find_message(uid: str, message_id: str, *, metadata_only: bool) -> Optional[Tuple[str, Dict[str, Any]]]:
    query = _messages_ref(uid).where(filter=FieldFilter('id', '==', message_id)).limit(1)
    if metadata_only:
        query = _select_metadata(query)
    doc = next(iter(query.stream()), None)
    if doc is None:
        return None
    return doc.id, _typed_doc(doc)


def _turn(raw: Dict[str, Any], rated_at: datetime, position: str) -> Optional[FeedbackContextTurn]:
    created_at = _as_utc(raw.get('created_at'))
    message_id = raw.get('id')
    if created_at is None or not message_id:
        return None
    return FeedbackContextTurn(
        message_id=str(message_id),
        sender=str(raw.get('sender') or 'unknown'),
        created_at=created_at,
        chat_session_id=raw.get('chat_session_id'),
        position=position,
        seconds_from_rated=int((created_at - rated_at).total_seconds()),
    )


def resolve_chat_context(
    uid: str,
    message_id: str,
    *,
    chat_session_id: Optional[str] = None,
    follow_up_window_seconds: int = FOLLOW_UP_WINDOW_SECONDS,
) -> FeedbackContextPointer:
    """Build the pointer window around a rated chat message.

    Before: turns in the same ``chat_session_id`` up to the rated one, newest
    ``MAX_PRECEDING_TURNS`` kept. After: every turn within the follow-up window,
    *regardless of session*, because a user who gives up on a bad answer and
    starts a fresh session is exactly the follow-up worth seeing.

    Reads no message text.
    """
    pointer = FeedbackContextPointer(
        event_id='',
        uid=uid,
        target_kind=FeedbackTargetKind.chat_message,
        target_id=message_id,
        follow_up_window_seconds=follow_up_window_seconds,
    )

    found = _find_message(uid, message_id, metadata_only=True)
    if found is None:
        pointer.resolution_error = 'rated_message_not_found'
        return pointer

    _, rated_raw = found
    rated_at = _as_utc(rated_raw.get('created_at'))
    if rated_at is None:
        pointer.resolution_error = 'rated_message_missing_created_at'
        return pointer

    session_id = chat_session_id or rated_raw.get('chat_session_id')

    turns: List[FeedbackContextTurn] = []

    # --- Before: same session, newest first, then reversed to reading order.
    # Served by the already-declared `messages_by_session_created_at` composite
    # (chat_session_id ASC, created_at DESC) — no new index needed here.
    #
    # With no session id there is no "before" to speak of. Dropping the session
    # filter and keeping the time filter would return the previous ten messages
    # from *any* conversation and label them as the setup for this answer, which
    # is worse than showing nothing: a reviewer would read an unrelated exchange
    # as the question that produced the bad reply.
    if not session_id:
        pointer.resolution_error = 'preceding_turns_session_unknown'
    else:
        try:
            before_docs = list(
                _select_metadata(
                    _messages_ref(uid)
                    .where(filter=FieldFilter('chat_session_id', '==', session_id))
                    .where(filter=FieldFilter('created_at', '<', rated_at))
                    .order_by('created_at', direction='DESCENDING')
                    .limit(MAX_PRECEDING_TURNS + 1)
                ).stream()
            )
            pointer.truncated_before = len(before_docs) > MAX_PRECEDING_TURNS
            for doc in reversed(before_docs[:MAX_PRECEDING_TURNS]):
                turn = _turn(_typed_doc(doc), rated_at, 'before')
                if turn:
                    turns.append(turn)
        except Exception as e:
            logger.error(f'Failed to resolve preceding turns for message {message_id}: {e}')
            pointer.resolution_error = 'preceding_turns_unavailable'

    rated_turn = _turn(rated_raw, rated_at, 'rated')
    if rated_turn:
        turns.append(rated_turn)

    # --- After: any session, within the window. Fetch one past the cap so a
    # burst of retries is reported as truncated rather than quietly clipped.
    try:
        window_end = rated_at + timedelta(seconds=follow_up_window_seconds)
        after_docs = list(
            _select_metadata(
                _messages_ref(uid)
                .where(filter=FieldFilter('created_at', '>', rated_at))
                .where(filter=FieldFilter('created_at', '<=', window_end))
                .order_by('created_at')
                .limit(MAX_FOLLOW_UP_TURNS + 1)
            ).stream()
        )
        pointer.truncated_after = len(after_docs) > MAX_FOLLOW_UP_TURNS
        for doc in after_docs[:MAX_FOLLOW_UP_TURNS]:
            turn = _turn(_typed_doc(doc), rated_at, 'after')
            if turn:
                turns.append(turn)
                pointer.follow_up_count += 1
    except Exception as e:
        logger.error(f'Failed to resolve follow-up turns for message {message_id}: {e}')
        pointer.resolution_error = pointer.resolution_error or 'follow_up_turns_unavailable'

    pointer.turns = turns
    return pointer


def resolve_context(
    uid: str,
    target_kind: FeedbackTargetKind,
    target_id: str,
    *,
    chat_session_id: Optional[str] = None,
) -> FeedbackContextPointer:
    """Dispatch by target kind.

    Only chat messages have a turn-shaped neighbourhood. A rated conversation
    summary or a discarded memory is a single artifact — the report links to it
    by id and the reviewer opens it, rather than us inventing a fake transcript
    around it.
    """
    if target_kind == FeedbackTargetKind.chat_message:
        return resolve_chat_context(uid, target_id, chat_session_id=chat_session_id)
    return FeedbackContextPointer(
        event_id='',
        uid=uid,
        target_kind=target_kind,
        target_id=target_id,
    )


def _readable_text(raw: Dict[str, Any], uid: str) -> Optional[str]:
    """Decrypt one message body, or None if it did not come back readable.

    `utils.encryption.decrypt` returns its *input* when decryption fails — wrong
    key, rotated secret, corrupt blob — and `_decrypt_chat_data` swallows the
    error. So a failed decrypt is indistinguishable from a successful one by
    exception alone: the caller gets base64 ciphertext typed as `str`. Comparing
    against the stored value is what actually detects it, and only for
    `enhanced` rows, where the stored value is known to be ciphertext.
    """
    stored = raw.get('text')
    try:
        decrypted = decrypt_message_payload(raw, uid)
    except Exception as e:
        logger.error(f'Failed to decrypt message for uid hash {hash(uid) & 0xFFFF}: {e}')
        return None

    text = decrypted.get('text')
    if text is None:
        return ''
    if not isinstance(text, str):
        return str(text)
    if raw.get('data_protection_level') == 'enhanced' and isinstance(stored, str) and stored and text == stored:
        # Came back byte-identical to the ciphertext we handed in.
        return None
    return text


def hydrate_context(pointer: FeedbackContextPointer) -> FeedbackContextHydrated:
    """Decrypt the turns a pointer names. Response-scoped; never persisted."""
    hydrated = FeedbackContextHydrated(
        event_id=pointer.event_id,
        target_kind=pointer.target_kind,
        target_id=pointer.target_id,
    )
    if pointer.target_kind != FeedbackTargetKind.chat_message:
        return hydrated

    for turn in pointer.turns:
        found = _find_message(pointer.uid, turn.message_id, metadata_only=False)
        if found is None:
            # Deleted between the report run and this read. Say so rather than
            # showing a gap the reviewer would read as "the user said nothing".
            hydrated.unavailable.append(turn.message_id)
            continue
        _, raw = found
        text = _readable_text(raw, pointer.uid)
        if text is None:
            hydrated.unavailable.append(turn.message_id)
            continue
        if len(text) > MAX_HYDRATED_TEXT_CHARS:
            text = text[:MAX_HYDRATED_TEXT_CHARS] + '… [truncated]'
        hydrated.turns.append(
            FeedbackContextTurnText(
                message_id=turn.message_id,
                sender=turn.sender,
                created_at=turn.created_at,
                position=turn.position,
                seconds_from_rated=turn.seconds_from_rated,
                text=text,
            )
        )
    return hydrated
