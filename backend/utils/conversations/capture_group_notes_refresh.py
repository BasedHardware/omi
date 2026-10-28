"""One notes refresh for a capture-group primary when meeting context arrives late.

Live multi-surface captures finalize in any order, and a group forms only once
both rows are completed — so the primary (the longest window, often the pendant)
is usually summarized before the group exists. When a confirmed same-event
member then carries ``calendar_meeting_context`` the primary's stored context
lacks, the row clients render would keep ambient-quality notes while the
meeting identity sits on hidden members (owner meeting 2026-10-28).

``refresh_primary_notes`` closes that gap exactly once per group revision: the
shared processing claim (``database.processing_attention``) with an
idempotency key pinned to ``(group id, revision)`` fences concurrent writers,
and after one successful refresh the primary stores a revision receipt with
the notes, so the same group state never qualifies again. A new desktop half
qualifies even if its roster matches, because it can carry new screen evidence.
Membership, transcripts, discard state and audio are untouched; only notes regenerate
(``ProcessingTrigger.CAPTURE_GROUP``: no created-side effects, relevance keep).
A refresh that fails marks its attempt failed and is not retried for the same
revision — the next membership change or a user reprocess picks it up.

The entry read is field-projected, so the common no-group finalization pays one
cheap snapshot; the full conversation document is read only once a gap is
proven.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from database import conversations as conversations_db
from database import processing_attention as attention_db
from database.firestore_read_metrics import FirestoreReadSite
from utils.conversations.capture_group_meeting_context import (
    capture_group_primary_notes_enabled,
    NOTES_REVISION_FIELD,
    member_context_rows,
    primary_notes_gap,
)
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation
from utils.conversations.processing_trigger import ProcessingTrigger

logger = logging.getLogger(__name__)

# Exactly the fields the eligibility and gap decisions read; the full document
# is loaded only when a refresh is proven necessary.
_PRIMARY_META_FIELDS = ['id', 'capture_group', 'external_data', 'deleted', 'discarded', 'status']


def _meta_row(uid: str, conversation_id: str) -> Optional[Mapping[str, Any]]:
    return conversations_db.get_conversation_raw_snapshot(uid, conversation_id, field_paths=list(_PRIMARY_META_FIELDS))


def _eligible_primary_row(row: Any) -> bool:
    return bool(row) and not row.get('deleted') and not row.get('discarded') and row.get('status') == 'completed'


def refresh_primary_notes(uid: str, conversation_id: str) -> bool:
    """Regenerate the primary's notes if its group holds meeting context it lacks.

    Best effort by contract: never raises into the caller's finalization.
    Returns whether a refresh ran.
    """
    if not capture_group_primary_notes_enabled() or not conversation_id:
        return False
    operation = None
    owned = False
    try:
        entry = _meta_row(uid, conversation_id)
        group = (entry or {}).get('capture_group') or {}
        primary_id = group.get('primary_id')
        if not isinstance(primary_id, str) or not primary_id:
            return False
        primary_row: Any = entry if primary_id == conversation_id else _meta_row(uid, primary_id)
        if not _eligible_primary_row(primary_row):
            return False
        gap = primary_notes_gap(primary_row, member_context_rows(uid, primary_row))
        if gap is None:
            return False
        operation, owned = attention_db.claim(
            uid,
            primary_id,
            idempotency_key=f'capture-group-notes:{gap.group_id}:{gap.revision}',
            restart_succeeded=True,
        )
        if not owned or not attention_db.owns_live_claim(uid, operation):
            return False
        full_row = conversations_db.get_conversation(uid, primary_id, read_site=FirestoreReadSite.CAPTURE_GROUP_NOTES)
    except attention_db.ClaimRejected:
        return False
    except Exception as exc:  # noqa: BLE001 - the refresh may never fail finalization
        logger.warning('event=capture_group_notes_refresh outcome=error exception_type=%s', type(exc).__name__)
        if operation is not None and owned:
            try:
                attention_db.finish(uid, operation, 'failed')
            except Exception:
                logger.warning('event=capture_group_notes_refresh outcome=release_failed')
        return False

    persisted = {'owned': False}
    try:
        if full_row is None or not _eligible_primary_row(full_row):
            attention_db.finish(uid, operation, 'failed')
            return False
        # Recheck the group after claiming: a member may have joined while
        # the first metadata snapshot was being read. Do not stamp newer
        # membership as summarized by an older attempt.
        current_group = full_row.get('capture_group') or {}
        if current_group.get('id') != gap.group_id or current_group.get('revision') != gap.revision:
            attention_db.finish(uid, operation, 'failed')
            return False
        conversation = deserialize_conversation(full_row)
        conversation.external_data = dict(conversation.external_data or {})
        conversation.external_data[NOTES_REVISION_FIELD] = {'group_id': gap.group_id, 'revision': gap.revision}
        process_conversation(
            uid,
            conversation.language or 'en',
            conversation,
            trigger=ProcessingTrigger.CAPTURE_GROUP,
            persistence_observer=lambda owned: persisted.__setitem__('owned', owned),
            defer_derived_effects=True,
        )
        attention_db.finish(uid, operation, 'succeeded' if persisted['owned'] else 'failed')
        logger.info(
            'event=capture_group_notes_refresh outcome=%s uid=%s conversation_id=%s',
            'refreshed' if persisted['owned'] else 'fenced',
            uid,
            primary_id,
        )
        return bool(persisted['owned'])
    except Exception as exc:  # noqa: BLE001 - the refresh may never fail finalization
        logger.warning('event=capture_group_notes_refresh outcome=failed exception_type=%s', type(exc).__name__)
        try:
            attention_db.finish(uid, operation, 'failed')
        except Exception:
            logger.warning(
                'event=capture_group_notes_refresh outcome=release_failed exception_type=%s', type(exc).__name__
            )
        return False
