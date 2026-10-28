"""Bounded notes refreshes when a shared-speech group gains meeting evidence."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Mapping, Optional

from database import capture_group_notes as refresh_state_db
from database import conversations as conversations_db
from database import processing_attention as attention_db
from database.firestore_read_metrics import FirestoreReadSite
from database.screen_frames import get_conversation_screenshot_sharing_enabled
from models.calendar_context import CalendarMeetingContext
from utils.conversations.capture_group_meeting_context import (
    NOTES_REVISION_FIELD,
    capture_group_primary_notes_enabled,
    group_members,
    is_shared_speech_group,
    member_context_rows,
    primary_notes_gap,
)
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.screen_frame_evidence import (
    MAX_GROUP_MEMBER_FRAME_READS,
    load_screen_frame_evidence,
)

logger = logging.getLogger(__name__)

MAX_REFRESHES_PER_GROUP = 3
# The notes prompt includes the primary's frames plus at most these member
# frame sets. Eligibility uses the same bounded member set.
_PRIMARY_META_FIELDS = ['id', 'capture_group', 'external_data', 'deleted', 'discarded', 'status']


def _meta_row(uid: str, conversation_id: str) -> Optional[Mapping[str, Any]]:
    return conversations_db.get_conversation_raw_snapshot(uid, conversation_id, field_paths=list(_PRIMARY_META_FIELDS))


def _eligible_primary_row(row: Any) -> bool:
    return bool(row) and not row.get('deleted') and not row.get('discarded') and row.get('status') == 'completed'


def _meeting_evidence_fingerprints(
    uid: str,
    primary_row: Mapping[str, Any],
    member_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Stable digests for shareable desktop meeting evidence in this group."""
    primary_id = primary_row.get('id')
    desktop_members = [
        member for member in group_members(primary_row) if member['id'] != primary_id and member['source'] == 'desktop'
    ]
    frame_member_ids = {member['id'] for member in desktop_members[:MAX_GROUP_MEMBER_FRAME_READS]}
    result: dict[str, str] = {}
    for member in desktop_members:
        member_id = member['id']
        row = member_rows.get(member_id)
        if not row:
            continue
        external = row.get('external_data') or {}
        if not isinstance(external, Mapping) or external.get('conversation_role') != 'meeting':
            continue
        raw_context = external.get('calendar_meeting_context')
        try:
            context = (
                CalendarMeetingContext(**raw_context).model_dump(mode='json')
                if isinstance(raw_context, Mapping)
                else None
            )
        except Exception:
            context = None
        frames = ()
        if member_id in frame_member_ids and get_conversation_screenshot_sharing_enabled(row):
            frames = load_screen_frame_evidence(uid, member_id)
        frame_payload = [
            {
                'frame_id': frame.frame_id,
                'captured_at': frame.captured_at.isoformat(),
                'role': frame.role,
                'names': list(frame.names),
                'summary': frame.summary,
            }
            for frame in frames
        ]
        if context is None and not frame_payload:
            continue
        encoded = json.dumps(
            {'context': context, 'frames': frame_payload},
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        ).encode('utf-8')
        result[member_id] = hashlib.sha256(encoded).hexdigest()
    return result


def _has_new_evidence(state: Mapping[str, Any], member_fingerprints: Mapping[str, str]) -> bool:
    if int(state.get('refresh_count') or 0) >= MAX_REFRESHES_PER_GROUP:
        return False
    prior = state.get('member_fingerprints') or {}
    seen = set(state.get('seen_evidence_fingerprints') or [])
    return any(
        prior.get(member_id) != fingerprint and fingerprint not in seen
        for member_id, fingerprint in member_fingerprints.items()
    )


def _group_revision_moved(uid: str, conversation_id: str, gap) -> bool:
    try:
        latest = _meta_row(uid, conversation_id)
    except Exception:
        return False
    group = (latest or {}).get('capture_group') or {}
    return bool(
        group.get('id') != gap.group_id
        or group.get('revision') != gap.revision
        or group.get('primary_id') != gap.primary_id
    )


def refresh_primary_notes(uid: str, conversation_id: str) -> bool:
    """Regenerate a primary's notes once for new, shareable meeting evidence.

    The group-state reservation deduplicates evidence fingerprints and caps paid
    attempts. The conversation claim still coordinates against user reprocess
    and ordinary writers, while the final Firestore transaction fences both
    the current group revision and the reservation receipt with the notes write.
    """
    if not capture_group_primary_notes_enabled() or not conversation_id:
        return False
    operation = None
    reservation = None
    persisted = {'owned': False}
    try:
        entry = _meta_row(uid, conversation_id)
        entry_group = (entry or {}).get('capture_group') or {}
        primary_id = entry_group.get('primary_id')
        if not isinstance(primary_id, str) or not primary_id:
            return False
        primary_row: Any = entry if primary_id == conversation_id else _meta_row(uid, primary_id)
        if not _eligible_primary_row(primary_row) or not is_shared_speech_group(primary_row):
            return False
        group = primary_row.get('capture_group') or {}
        group_id = group.get('id')
        revision = group.get('revision')
        if not isinstance(group_id, str) or not isinstance(revision, int):
            return False

        member_rows = member_context_rows(uid, primary_row)
        fingerprints = _meeting_evidence_fingerprints(uid, primary_row, member_rows)
        state = refresh_state_db.get_state(uid, group_id)
        if not _has_new_evidence(state, fingerprints):
            return False
        gap = primary_notes_gap(primary_row, member_rows, has_new_meeting_evidence=True)
        if gap is None:
            return False

        # No revision idempotency key here: processing_attention keys attach to
        # an active attempt. A later group revision must not be pinned to the
        # older attempt that is about to fail its group fence.
        operation, owned = attention_db.claim(uid, primary_id, restart_succeeded=True)
        if not owned or not attention_db.owns_live_claim(uid, operation):
            return False

        reservation = refresh_state_db.claim_refresh(
            uid,
            group_id,
            primary_id,
            revision,
            fingerprints,
            max_refreshes=MAX_REFRESHES_PER_GROUP,
        )
        if reservation is None:
            attention_db.finish(uid, operation, 'failed')
            return False

        full_row = conversations_db.get_conversation(uid, primary_id, read_site=FirestoreReadSite.CAPTURE_GROUP_NOTES)
        if full_row is None or not _eligible_primary_row(full_row):
            refresh_state_db.release_refresh(uid, group_id, reservation['id'])
            attention_db.finish(uid, operation, 'failed')
            return False
        current_group = full_row.get('capture_group') or {}
        if current_group.get('id') != group_id or current_group.get('revision') != revision:
            refresh_state_db.release_refresh(uid, group_id, reservation['id'])
            attention_db.finish(uid, operation, 'failed')
            if _group_revision_moved(uid, conversation_id, gap):
                return refresh_primary_notes(uid, conversation_id)
            return False

        conversation = deserialize_conversation(full_row)
        conversation.external_data = dict(conversation.external_data or {})
        conversation.external_data[NOTES_REVISION_FIELD] = {
            'group_id': group_id,
            'revision': revision,
            'evidence_fingerprints': reservation['evidence_fingerprints'],
        }
        process_conversation(
            uid,
            conversation.language or 'en',
            conversation,
            trigger=ProcessingTrigger.CAPTURE_GROUP,
            persistence_observer=lambda owned: persisted.__setitem__('owned', owned),
            defer_derived_effects=True,
            capture_group_refresh_fence=(group_id, revision, reservation['id']),
        )
        if persisted['owned']:
            attention_db.finish(uid, operation, 'succeeded')
            logger.info(
                'event=capture_group_notes_refresh outcome=refreshed uid=%s conversation_id=%s',
                uid,
                primary_id,
            )
            return True

        refresh_state_db.release_refresh(uid, group_id, reservation['id'])
        attention_db.finish(uid, operation, 'failed')
        if _group_revision_moved(uid, conversation_id, gap):
            return refresh_primary_notes(uid, conversation_id)
        logger.info('event=capture_group_notes_refresh outcome=fenced uid=%s conversation_id=%s', uid, primary_id)
        return False
    except attention_db.ClaimRejected:
        return False
    except Exception as exc:  # noqa: BLE001 - this step may never fail finalization
        logger.warning('event=capture_group_notes_refresh outcome=error exception_type=%s', type(exc).__name__)
        if reservation is not None:
            try:
                refresh_state_db.release_refresh(uid, reservation.get('group_id', ''), reservation['id'])
            except Exception:
                logger.warning('event=capture_group_notes_refresh outcome=state_release_failed')
        if operation is not None:
            try:
                attention_db.finish(uid, operation, 'succeeded' if persisted['owned'] else 'failed')
            except Exception:
                logger.warning('event=capture_group_notes_refresh outcome=release_failed')
        return bool(persisted['owned'])
