"""Attach retained batch audio before its transcript/finalization work starts."""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from config.batch_timeliness import SLA_SECONDS
from config.episodes import MAX_EPISODE_SECONDS, episodes_enabled_for
from config.recorded_time import (
    batch_admission_attach_enabled,
    batch_close_attach_enabled,
    recorded_episodes_enabled,
)
from config.server_batch import has_audio, owned
from database import conversations
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.episodes import service, late_member
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _admitted_start(row: Mapping[str, Any]) -> datetime | None:
    """The recorded start known at admission: committed audio bounds, else the row clock."""
    value = row.get('server_batch_audio_start')
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return datetime.fromtimestamp(value, timezone.utc)
    for key in ('started_at', 'created_at'):
        candidate = row.get(key)
        if isinstance(candidate, datetime):
            return candidate if candidate.tzinfo is not None else candidate.replace(tzinfo=timezone.utc)
    return None


def _admissible(row: Mapping[str, Any]) -> bool:
    """The privacy and ownership guards shared by admission and audio close."""
    return not (
        not owned(row)
        or row.get('private_cloud_sync_enabled') is not True
        or row.get('uses_custom_stt')
        or row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
        or any(row.get(key) for key in ('deleted', 'is_locked', 'deferred', 'sync_merged_into', 'dream_duplicate_of'))
        or is_relevance_discarded(row)
    )


def attach_admitted_batch_capture(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    *,
    collaborators: service.Collaborators | None = None,
) -> str:
    """Metadata only: give an admitted batch capture its episode before audio close.

    The recorded start is known at admission; the end is not, so the member joins
    with a one-second provisional window and a pending-transcription deadline.
    The audio-close attach then writes the real end through the same fenced
    transaction, so Home never paints the capture as a standalone row for the
    length of the recording. Finalization remains the repair path after a
    transient failure; the capture stays a standalone row until it lands.
    """
    if not episodes_enabled_for(uid) or not recorded_episodes_enabled() or not batch_admission_attach_enabled():
        return 'disabled'
    if not conversation_id or not _admissible(row):
        return 'skipped'
    started = _admitted_start(row)
    if started is None:
        return 'skipped'
    try:
        c = collaborators or service.Collaborators(firestore_client=conversations.db)
        service.attach_recorded(
            uid,
            conversation_id,
            row,
            started,
            started + timedelta(seconds=1),
            c,
            pending_transcription=True,
            admission=True,
            # The capture may still be recording for MAX_EPISODE_SECONDS. The
            # delivery SLA starts at admission, so floor the deadline past the
            # longest possible capture instead of expiring mid-recording.
            deadline_floor=started + timedelta(seconds=MAX_EPISODE_SECONDS + SLA_SECONDS),
        )
        return 'attached'
    except service.AdmissionClosed:
        return 'closed'
    except Exception as error:
        logger.warning('event=episode_batch_admission_attach exception_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='episode_batch_admission',
            to_mode='episode_batch_audio_close',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return 'error'


def _moved_owner(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    started: datetime,
    finished: datetime,
    c: service.Collaborators,
) -> str | None:
    """The episode the real recorded window selects, when it is not the current owner.

    The admission attach decides on the recorded start alone. If the completed
    window now belongs to a different occasion, the close attach re-places the
    member and removes the stale provisional membership in the same transaction.
    A capture that never joined at admission has no owner to move.
    """
    current = row.get('episode_id')
    if not current:
        return None
    try:
        rows = service.episode_timeline.recorded_candidates(uid, started, finished, firestore_client=c.firestore_client)
        selected = service.choose_recorded_episode(rows, started, finished)
    except Exception:
        # An incomplete candidate window is uncertainty, never permission to move.
        return None
    if selected is None or selected.get('id') == current:
        return None
    return str(current)


def attach_closed_batch_capture(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    *,
    collaborators: service.Collaborators | None = None,
) -> str:
    """Metadata only: recorded audio, never arrival time or the live pointer.

    The existing fenced timeline transaction owns membership and idempotency.
    Finalization remains the repair path after a transient attachment failure;
    source rows remain available while they wait. No client-seen or paid work.
    """
    if not episodes_enabled_for(uid) or not recorded_episodes_enabled() or not batch_close_attach_enabled():
        return 'disabled'
    if (
        not conversation_id
        or not _admissible(row)
        or row.get('server_batch_audio_closed') is not True
        or not has_audio(row)
        or any(isinstance(row.get(key), bool) for key in ('server_batch_audio_start', 'server_batch_audio_end'))
    ):
        return 'skipped'
    try:
        started = datetime.fromtimestamp(row['server_batch_audio_start'], timezone.utc)
        finished = datetime.fromtimestamp(row['server_batch_audio_end'], timezone.utc)
        c = collaborators or service.Collaborators(firestore_client=conversations.db)
        moved_from = _moved_owner(uid, conversation_id, row, started, finished, c)
        # Attach first and remove the stale provisional membership in the same
        # transaction. A failed attach leaves the member where it was; a failed
        # detach leaves a duplicate, never an orphaned capture.
        owner = service.attach_recorded(
            uid,
            conversation_id,
            row,
            started,
            finished,
            c,
            pending_transcription=True,
            detach_from=moved_from,
        )
        late_member.joined(uid, conversation_id, row, owner, c)
        return 'attached'
    except Exception as error:
        logger.warning('event=episode_batch_audio_close_attach exception_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='episode_batch_audio_close',
            to_mode='episode_finalize_attach',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return 'error'
