import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi.responses import JSONResponse

from database import conversation_audio as conversation_audio_db
from database import conversations as conversations_db
from database.sync_jobs import release_job_run_lock, try_acquire_job_run_lock
from utils.cloud_tasks import get_sync_tasks_max_attempts
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.other.conversation_playback_storage import (
    get_conversation_playback_signed_url,
    mark_conversation_playback_unavailable,
    upload_conversation_playback_artifact,
)
from utils.other.storage import compute_audio_files_fingerprint
from utils.sync import playback as sync_playback
from utils.sync.conversation_artifact_protocol import (
    FinalizationIdentity,
    conversation_finalization_identity,
    conversation_playback_artifact_generation_id,
)

logger = logging.getLogger(__name__)


def _parse_payload(payload: dict[str, Any]) -> tuple[str, str, str, Optional[str], Optional[FinalizationIdentity]]:
    uid = payload['uid']
    conversation_id = payload['conversation_id']
    fingerprint = payload['fingerprint']
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError('missing conversation owner')
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError('missing fingerprint')
    artifact_generation_id = payload.get('artifact_generation_id')
    raw_identity = payload.get('expected_finalization_identity')
    identity = None
    if raw_identity is not None:
        if not isinstance(raw_identity, list) or len(raw_identity) != 3:
            raise ValueError('invalid finalization identity')
        incarnation_id, job_id, revision = raw_identity
        if not isinstance(incarnation_id, str) or not incarnation_id:
            raise ValueError('invalid finalization incarnation')
        if job_id is not None and not isinstance(job_id, str):
            raise ValueError('invalid finalization job')
        if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool)):
            raise ValueError('invalid finalization revision')
        identity = incarnation_id, job_id, revision
    if artifact_generation_id is not None and artifact_generation_id != conversation_playback_artifact_generation_id(
        fingerprint,
        identity,
    ):
        raise ValueError('invalid artifact generation')
    return uid, conversation_id, fingerprint, artifact_generation_id, identity


def _source_is_current(
    conversation: Optional[dict[str, Any]],
    audio_files: list[dict[str, Any]],
    expected_identity: Optional[FinalizationIdentity],
) -> bool:
    return bool(
        conversation
        and conversation.get('audio_files') == audio_files
        and (expected_identity is None or conversation_finalization_identity(conversation) == expected_identity)
    )


async def run_conversation_merge_job(payload: dict[str, Any], task_retry_count: int) -> JSONResponse:
    """Build one source-fenced conversation playback artifact."""
    try:
        uid, conversation_id, payload_fingerprint, artifact_generation_id, expected_identity = _parse_payload(payload)
    except Exception:
        logger.error('audio_merge handler: invalid v2 payload, dropping task')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    lock_key = f'audio:{conversation_id}:conversation'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation or not conversation.get('audio_files'):
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'no_audio_files'})
        audio_files = conversation['audio_files']
        if not _source_is_current(conversation, audio_files, expected_identity):
            return JSONResponse(status_code=200, content={'status': 'superseded'})
        fingerprint = compute_audio_files_fingerprint(audio_files)
        if payload_fingerprint != fingerprint:
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        stamp = conversation.get('conversation_audio') or {}
        if (
            stamp.get('audio_files_fingerprint') == fingerprint
            and stamp.get('artifact_generation_id') == artifact_generation_id
        ):
            existing = await run_blocking(
                storage_executor,
                get_conversation_playback_signed_url,
                uid,
                conversation_id,
                artifact_generation_id,
            )
            if existing:
                return JSONResponse(status_code=200, content={'status': 'exists'})

        started_at = conversation.get('started_at') or conversation.get('created_at')
        try:
            if not isinstance(started_at, datetime):
                raise ValueError('invalid conversation start timestamp')
            mp3_data, spans = await run_blocking(
                sync_executor,
                sync_playback.build_conversation_playback_artifact,
                uid,
                conversation_id,
                audio_files,
                started_at.timestamp(),
            )
        except FileNotFoundError:
            logger.warning('audio_merge: conversation chunks missing conv=%s, dropping', conversation_id)
            await run_blocking(
                storage_executor,
                mark_conversation_playback_unavailable,
                uid,
                conversation_id,
                fingerprint,
                'chunks_missing',
                artifact_generation_id,
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception:
            if task_retry_count >= get_sync_tasks_max_attempts() - 1:
                logger.error('audio_merge_failed_final conversation artifact conv=%s', conversation_id)
                await run_blocking(
                    storage_executor,
                    mark_conversation_playback_unavailable,
                    uid,
                    conversation_id,
                    fingerprint,
                    'merge_failed',
                    artifact_generation_id,
                )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                'audio_merge: conversation attempt %s failed conv=%s, will retry',
                task_retry_count + 1,
                conversation_id,
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        latest = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not _source_is_current(latest, audio_files, expected_identity):
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        await run_blocking(
            storage_executor,
            upload_conversation_playback_artifact,
            uid,
            conversation_id,
            mp3_data,
            artifact_generation_id,
        )
        mp3_size = len(mp3_data)
        del mp3_data

        conversation_audio = {
            'audio_files_fingerprint': fingerprint,
            'artifact_generation_id': artifact_generation_id,
            'duration': round(spans[-1]['wall_offset'] + spans[-1]['len'], 3),
            'captured_duration': round(sum(span['len'] for span in spans), 3),
            'spans': spans,
            'content_type': 'audio/mpeg',
            'built_at': datetime.now(timezone.utc),
        }
        committed = await run_blocking(
            db_executor,
            conversation_audio_db.commit_conversation_audio_if_source_current,
            uid,
            conversation_id,
            conversation_audio,
            expected_audio_files=audio_files,
            expected_finalization_identity=expected_identity,
        )
        if not committed:
            return JSONResponse(status_code=200, content={'status': 'superseded'})
        logger.info(
            'audio_merge: built conversation artifact conv=%s size=%s spans=%s',
            conversation_id,
            mp3_size,
            len(spans),
        )
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)
