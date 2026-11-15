"""Bound metadata repair to one playback open; never build audio in the drain."""

from concurrent.futures import TimeoutError

from fastapi import HTTPException

from utils.executors import playback_metadata_executor, submit_with_context, ExecutorSaturatedError

OPEN_TIMEOUT_SECONDS = 8.0


def _refresh(uid: str, cid: str):
    from database import conversations, record_projection_rebuild as debt
    from utils.batch_pipeline.record_projection_rebuild import rebuild

    version = debt.pending_version(uid, cid)
    # Reuse cold repair's strict discovery, deletion/privacy transaction and CAS.
    # This is metadata only. Existing /urls demand handling builds real artifacts.
    applied = rebuild(uid, cid) if version is not None else None
    if applied is False:
        raise HTTPException(404, 'Conversation not found')
    row = conversations.get_conversation_raw_snapshot(
        uid, cid, field_paths=['audio_files', 'deleted', 'is_locked'], timeout=1
    )
    if row is None or row.get('deleted'):
        raise HTTPException(404, 'Conversation not found')
    if row.get('is_locked'):
        raise HTTPException(402, 'A paid plan is required to access this conversation.')
    # A background refresh may publish and retire debt after the route's first
    # empty read. Always read back metadata, even if its marker is already gone.
    if not row.get('audio_files') and version is not None and applied != 'no_objects':
        raise HTTPException(503, 'Playback metadata is not available yet')
    if applied is True:
        try:
            debt.retire_observed(uid, cid, observed_update_time=version)
        except Exception:
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='sync',
                from_mode='playback_metadata_debt',
                to_mode='durable_repair',
                reason='other',
                outcome='degraded',
            )
    # Incomplete or empty discovery retains debt. Newer marker versions always
    # survive the conditional delete; neither result has producer-token authority.
    return row


def _refresh_safely(uid: str, cid: str):
    try:
        return _refresh(uid, cid)
    except HTTPException:
        raise
    except Exception:
        # The Future's shared callback must not log private SDK payloads.
        raise HTTPException(503, 'Playback metadata repair is unavailable') from None


def refresh_on_open(uid: str, cid: str):
    """Request budget bounds the wait; two workers/zero queue bound late work."""
    try:
        future = submit_with_context(playback_metadata_executor, _refresh_safely, uid, cid)
    except ExecutorSaturatedError as error:
        raise HTTPException(503, 'Playback metadata repair is busy') from error
    try:
        return future.result(timeout=OPEN_TIMEOUT_SECONDS)
    except TimeoutError:
        future.cancel()
        raise
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(503, 'Playback metadata repair is unavailable') from error
