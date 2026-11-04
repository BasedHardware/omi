"""Attach retained batch audio before its transcript/finalization work starts."""

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from config.episodes import episodes_enabled_for
from config.recorded_time import batch_close_attach_enabled, recorded_episodes_enabled
from config.server_batch import has_audio, owned
from database import conversations
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.episodes import service
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


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
        or not owned(row)
        or row.get('server_batch_audio_closed') is not True
        or not has_audio(row)
        or row.get('private_cloud_sync_enabled') is not True
        or row.get('uses_custom_stt')
        or row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
        or any(row.get(key) for key in ('deleted', 'is_locked', 'deferred', 'sync_merged_into', 'dream_duplicate_of'))
        or is_relevance_discarded(row)
        or any(isinstance(row.get(key), bool) for key in ('server_batch_audio_start', 'server_batch_audio_end'))
    ):
        return 'skipped'
    try:
        started = datetime.fromtimestamp(row['server_batch_audio_start'], timezone.utc)
        finished = datetime.fromtimestamp(row['server_batch_audio_end'], timezone.utc)
        c = collaborators or service.Collaborators(firestore_client=conversations.db)
        service.attach_recorded(uid, conversation_id, row, started, finished, c, pending_transcription=True)
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
