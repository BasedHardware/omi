import json
import logging
import struct
from typing import Any, Dict, Optional

from fastapi.websockets import WebSocket, WebSocketDisconnect

from database import conversation_finalization_jobs as finalization_jobs_db
from services.conversation_finalization import final_attempt_failed
from utils.byok import set_byok_keys, set_byok_uid
from utils.cloud_tasks import get_listen_finalization_tasks_max_attempts
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.finalizer import (
    ConversationFinalizationDisposition,
    ConversationFinalizationError,
    finalize_persisted_conversation,
)
from utils.executors import db_executor, run_blocking
from utils.observability.journeys import record_capture_finalization_terminal

logger = logging.getLogger('routers.pusher')


async def process_conversation_task(
    uid: str,
    conversation_id: str,
    language: str,
    websocket: WebSocket,
    byok_keys: Optional[Dict[str, str]] = None,
    finalization_job_id: Optional[str] = None,
    dispatch_generation: Optional[int] = None,
) -> None:
    """Process a leased conversation job and send a minimal result to listen.

    `byok_keys` is forwarded from the listen service. When present, LLM and
    STT calls made inside process_conversation route through the user's own
    provider keys instead of Omi's env keys.
    """
    if byok_keys:
        set_byok_keys(byok_keys)
        set_byok_uid(uid)

    async def send_result(result: Dict[str, Any]) -> None:
        """Attempt the optional live acknowledgement after durable work.

        The Firestore finalization transition is authoritative. A listener can
        close after handing opcode 104 to pusher, so a failed result write must
        never turn an already-completed durable job into a worker failure.
        """
        data = bytearray()
        data.extend(struct.pack("I", 201))
        data.extend(bytes(json.dumps(result), "utf-8"))
        try:
            await websocket.send_bytes(bytes(data))
        except (RuntimeError, WebSocketDisconnect):
            logger.info(
                'pusher finalization result undeliverable after source close uid=%s conversation=%s',
                uid,
                conversation_id,
            )

    job_id: Optional[str] = None
    generation: Optional[int] = None
    lease_epoch: Optional[int] = None
    attempt_count: int = 0

    async def record_failure(failure_code: str) -> bool:
        """Release the lease. Returns whether this was the terminal attempt.

        Inline dispatch has no Cloud Tasks worker to exhaust the attempt budget,
        so the claimed attempt count is the only bound on a deterministically
        failing job. Without a terminal state the conversation would stay
        `processing` forever and be re-finalized by every later session.
        """
        if job_id is None or generation is None or lease_epoch is None:
            return False
        terminal = attempt_count >= get_listen_finalization_tasks_max_attempts()
        try:
            if terminal:
                marked_dead_letter = await run_blocking(
                    db_executor,
                    final_attempt_failed,
                    job_id,
                    generation,
                    lease_epoch,
                    attempt_count,
                )
                if not marked_dead_letter:
                    return False
                return True
            await run_blocking(
                db_executor,
                finalization_jobs_db.mark_finalization_retryable,
                job_id,
                generation,
                lease_epoch,
                failure_code,
            )
        except Exception:
            logger.error(
                'pusher finalization recovery update failed uid=%s conversation=%s failure=%s terminal=%s',
                uid,
                conversation_id,
                failure_code,
                terminal,
            )
            return False
        return False

    try:
        if not finalization_job_id or dispatch_generation is None:
            # Every finalization request must be mediated by the Firestore
            # owner.  Accepting the legacy frame would allow a pending pusher
            # session to bypass the durable claim and double-process work.
            await send_result({'conversation_id': conversation_id, 'error': 'durable_job_required'})
            return

        job_id = finalization_job_id
        generation = dispatch_generation

        claim = await run_blocking(
            db_executor,
            finalization_jobs_db.claim_finalization_job,
            job_id,
            generation,
            allow_byok=bool(byok_keys),
            expected_uid=uid,
            expected_conversation_id=conversation_id,
        )
        claim_status = claim['status']
        if claim_status == 'fenced':
            await send_result({'conversation_id': conversation_id, 'fenced': True})
            return
        if claim_status == 'completed':
            await send_result({'conversation_id': conversation_id, 'success': True})
            return
        if claim_status != 'claimed':
            await send_result(
                {
                    'conversation_id': conversation_id,
                    'error': f'job_{claim_status}',
                    # A dead-lettered job is never actionable again; telling the
                    # live session it is terminal stops it from re-requesting.
                    'terminal': claim_status in finalization_jobs_db.TERMINAL_JOB_STATUSES,
                }
            )
            return
        attempt_count = claim['attempt_count']
        lease_epoch = claim['lease_epoch']
        if lease_epoch is None:
            logger.error(
                'pusher finalization claim returned no lease epoch uid=%s conversation=%s', uid, conversation_id
            )
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed'})
            return

        disposition = await finalize_persisted_conversation(
            uid,
            conversation_id,
            language,
            finalization_job_id=job_id,
            dispatch_generation=generation,
            lease_epoch=lease_epoch,
            final_attempt=attempt_count >= get_listen_finalization_tasks_max_attempts(),
        )

        if disposition == ConversationFinalizationDisposition.fenced:
            completed = await run_blocking(
                db_executor,
                lifecycle_service.complete_fenced_finalization,
                job_id,
                generation,
                lease_epoch,
            )
        else:
            completed = await run_blocking(
                db_executor,
                finalization_jobs_db.mark_finalization_completed,
                job_id,
                generation,
                lease_epoch,
            )
        if not completed:
            await send_result({'conversation_id': conversation_id, 'error': 'job_completion_conflict'})
            return
        if disposition == ConversationFinalizationDisposition.fenced:
            record_capture_finalization_terminal('stale', claim.get('created_at'))
            await send_result({'conversation_id': conversation_id, 'fenced': True})
            return
        record_capture_finalization_terminal('success', claim.get('created_at'))
        await send_result({'conversation_id': conversation_id, 'success': True})
    except ConversationFinalizationError:
        terminal = await record_failure('processing_failed')
        logger.error(
            'pusher finalization failed uid=%s conversation=%s failure=processing_failed terminal=%s',
            uid,
            conversation_id,
            terminal,
        )
        try:
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed', 'terminal': terminal})
        except Exception:
            pass
    except Exception:
        terminal = await record_failure('worker_failed')
        logger.error(
            'pusher finalization task failed uid=%s conversation=%s failure=worker_failed terminal=%s',
            uid,
            conversation_id,
            terminal,
        )
        try:
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed', 'terminal': terminal})
        except Exception:
            pass
