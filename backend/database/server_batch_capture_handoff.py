"""Eligibility and explicit-stop provenance for the server batch capture handoff."""

from config import server_batch
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.v3.policy import NATIVE_MANUAL_STOP


def capture_allowed(capture, current):
    return (
        server_batch.owned(capture)
        and server_batch.owned(current)
        and current.get('external_data') == capture.get('external_data')
        and current.get(server_batch.MARKER) == capture.get(server_batch.MARKER)
        and bool(current.get('private_cloud_sync_enabled'))
        and current.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and not any(current.get(key) for key in ('deleted', 'discarded', 'is_locked', 'uses_custom_stt'))
    )


def manual_stop_patch(current, job, job_id, revision):
    # Persist intent without exposing a manual cut before the full native transcript.
    return (
        {NATIVE_MANUAL_STOP: {'job_id': job_id, 'revision': revision, 'finished_at': current['finished_at']}}
        if (
            current.get('recording') is True
            and job.get('processing_trigger') == ProcessingTrigger.CLIENT_FINALIZE.value
            and current.get('finished_at') is not None
        )
        else {}
    )
