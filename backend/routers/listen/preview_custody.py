"""Promote unexpected local-preview audio before committing its original pack."""

import asyncio
import logging

from prometheus_client import Counter

from config.live_stt_preview_custody import preview_batch_custody_enabled
from config.server_batch import capture_language, SUPPORTED as SERVER_BATCH_LANGUAGES
from config.batch_live_preview import capture_snapshot
from database.server_batch_audio import claim_server_batch_lane
from utils.episodes.batch_close import attach_admitted_batch_capture
from utils.executors import db_executor, run_blocking, start_background_task
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

OMI_LISTEN_PREVIEW_BATCH_CUSTODY_TOTAL = Counter(
    'omi_listen_preview_batch_custody_total',
    'Local-preview audio custody promotion attempts by bounded outcome',
    ['outcome'],
)


def _needs_claim(receiver) -> bool:
    host = getattr(receiver, 'host', None)
    conversation_id = getattr(getattr(host, 'state', None), 'current_conversation_id', None)
    return bool(
        getattr(receiver, 'cloud_live_suppressed', False)
        and getattr(receiver, '_cloud_live_deferred_by', None) == 'local_preview'
        and getattr(host, 'local_preview_batch', False)
        and not getattr(host, 'use_custom_stt', False)
        and getattr(host, 'server_batch_only', False) is not True
        and preview_batch_custody_enabled()
        and conversation_id
        and conversation_id not in getattr(receiver, '_preview_batch_claims', ())
    )


async def claim_preview_batch_custody(receiver) -> bool:
    """Once per recording, before the first original pack can commit."""
    if not _needs_claim(receiver):
        return False
    conversation_id = receiver.host.state.current_conversation_id
    attempted = getattr(receiver, '_preview_batch_claims', None)
    if attempted is None:
        attempted = receiver._preview_batch_claims = set()
    attempted.add(conversation_id)
    row = None
    try:
        # Without durable original-audio custody, keep the live transcript.
        language = capture_language(receiver.host)
        if (
            getattr(getattr(receiver, 'raw_archive', None), 'durable', False)
            and getattr(receiver.host, 'private_cloud_sync_enabled', False)
            and not getattr(receiver.host, 'use_custom_stt', False)
            and not getattr(receiver.host, 'server_batch_byok', False)
            and not getattr(receiver.host, 'is_multi_channel', False)
            and getattr(receiver.host, 'pusher_enabled', False)
            and language in SERVER_BATCH_LANGUAGES | {'multi'}
        ):
            row = await run_blocking(
                db_executor,
                claim_server_batch_lane,
                receiver.host.request.uid,
                conversation_id,
                language=language,
            )
    except Exception as error:
        logger.warning('Preview batch custody claim failed type=%s', type(error).__name__)
    if row is None:
        OMI_LISTEN_PREVIEW_BATCH_CUSTODY_TOTAL.labels(outcome='live_fallback').inc()
        record_fallback(
            component='stt_selection',
            from_mode='none',
            to_mode='stream',
            reason='config_incomplete',
            outcome='degraded',
        )
        return False
    receiver.host.batch_record_capture = capture_snapshot(row)
    receiver.host.server_batch_only = True
    # The promotion is this capture's admission: give it its episode now rather
    # than at audio close. Metadata only, fail-open, and never awaited on the
    # audio path that calls this.
    start_background_task(
        run_blocking(
            db_executor,
            attach_admitted_batch_capture,
            receiver.host.request.uid,
            conversation_id,
            # The full claim row carries the recorded clocks; the snapshot is
            # eligibility only and would make the admission attach a no-op.
            dict(row),
        ),
        name='listen_batch_admission_attach',
    )
    OMI_LISTEN_PREVIEW_BATCH_CUSTODY_TOTAL.labels(outcome='promoted').inc()
    return True


async def archive_preview_frame(receiver, *args, **kwargs) -> bool:
    """Join the first-frame handoff even if its receive owner is cancelled.

    Return cancellation to the caller, which synchronously enqueues the decoded
    frame before re-raising it. The local reference is always joined; session
    drain_all must not cancel a half-completed ownership/archive transfer.
    Firestore SDK RPC deadlines/retry limits and archive I/O bounds still apply.
    """
    if not _needs_claim(receiver):
        await receiver.raw_archive.append(*args, **kwargs)
        return False

    async def handoff():
        await claim_preview_batch_custody(receiver)
        await receiver.raw_archive.append(*args, **kwargs)

    # Global tracking logs failures without enrolling this critical transfer in
    # the session supervisor's cancellation set. The receiver owns its join.
    task = start_background_task(handoff(), name='listen_preview_custody_frame')
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True  # A second owner cancellation must not cancel the transfer.
    task.result()
    return cancelled
