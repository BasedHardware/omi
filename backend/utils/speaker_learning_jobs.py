"""Durable voice-learning retry coordinator for labeled conversations.

Finalization, sync, audio upload and reprocess schedule one fail-open pass
that claims the conversation's persisted learning jobs — committed atomically
with each label — and drives them to a terminal outcome. No task worker, no
queue: one coroutine with a per-pass job bound and a total deadline. The
process-local in-flight set only skips duplicate scheduling; storage is the
authority, so a restart between label and teaching loses nothing.
"""

import asyncio
import logging
from typing import Any, Mapping, Optional

from database import speaker_learning_jobs as learning_jobs_db
from utils.executors import db_executor, run_blocking, start_background_task
from utils.observability.fallback import record_fallback
from utils.speaker_identification import extract_speaker_samples

logger = logging.getLogger(__name__)

VOICE_LEARNING_JOB_MAX_PER_PASS = 5
VOICE_LEARNING_RETRY_DEADLINE_SECONDS = 45
VOICE_LEARNING_RETRY_MAX_IN_FLIGHT = 16

_in_flight_retries: set = set()


async def _finish(uid: str, conversation_id: str, job: Mapping[str, Any], outcome: str) -> None:
    try:
        await run_blocking(
            db_executor,
            learning_jobs_db.finish_job,
            uid,
            conversation_id,
            job['job_id'],
            job['lease_token'],
            outcome,
        )
    except Exception as error:
        logger.warning('speaker_voice_learning finish failed exception_type=%s', type(error).__name__)


async def _execute_job(uid: str, conversation_id: str, job: Mapping[str, Any]) -> str:
    try:
        if job.get('target') == 'owner':
            from utils.speaker_tag_prompts.service import store_owner_voice_sample

            return await store_owner_voice_sample(
                uid,
                conversation_id,
                list(job.get('segment_ids') or []),
                card_generation=job.get('card_generation'),
            )
        return await extract_speaker_samples(
            uid,
            job.get('person_id') or '',
            conversation_id,
            list(job.get('segment_ids') or []),
            **({'sample_rate': job['sample_rate']} if job.get('sample_rate') is not None else {}),
        )
    except asyncio.CancelledError:
        if job.get('job_id') and job.get('lease_token'):
            await _finish(uid, conversation_id, job, 'timeout')
        raise
    except TimeoutError:
        return 'timeout'
    except Exception:
        return 'error'


async def run_speaker_learning_jobs(uid: str, conversation_id: str) -> None:
    """Claim and execute this conversation's durable learning jobs, oldest first."""
    try:
        async with asyncio.timeout(VOICE_LEARNING_RETRY_DEADLINE_SECONDS):
            for _ in range(VOICE_LEARNING_JOB_MAX_PER_PASS):
                job = await run_blocking(db_executor, learning_jobs_db.claim_next_job, uid, conversation_id)
                if not job:
                    break
                outcome = await _execute_job(uid, conversation_id, job)
                await _finish(uid, conversation_id, job, outcome)
    except TimeoutError:
        logger.info('speaker_voice_learning job deadline')
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning('speaker_voice_learning job run failed exception_type=%s', type(error).__name__)


async def _run_authorized_learning(uid: str, conversation_id: str, request: dict) -> str:
    """Persist the request's job, then claim and run exactly that job."""
    try:
        async with asyncio.timeout(VOICE_LEARNING_RETRY_DEADLINE_SECONDS):
            return await _claim_authorized_learning(uid, conversation_id, request)
    except TimeoutError:
        return 'timeout'


async def _claim_authorized_learning(uid: str, conversation_id: str, request: dict) -> str:
    try:
        await run_blocking(
            db_executor,
            learning_jobs_db.ensure_job,
            uid,
            conversation_id,
            person_id=request.get('person_id'),
            segment_ids=request['segment_ids'],
            card_generation=request.get('card_generation'),
            sample_rate=request.get('sample_rate'),
        )
        job = await run_blocking(db_executor, learning_jobs_db.claim_next_job, uid, conversation_id, assignment=request)
    except Exception:
        record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
        return await _execute_job(uid, conversation_id, request)
    if job is None:
        return 'pending'
    execution = dict(job, segment_ids=list(request['segment_ids']))
    outcome = await _execute_job(uid, conversation_id, execution)
    await _finish(uid, conversation_id, job, outcome)
    return outcome


async def run_authorized_person_learning(
    uid: str, person_id: str, conversation_id: str, segment_ids: list, *, sample_rate: Optional[int] = None
) -> str:
    return await _run_authorized_learning(
        uid,
        conversation_id,
        dict(target='person', person_id=person_id, segment_ids=list(segment_ids or []), sample_rate=sample_rate),
    )


async def run_authorized_owner_learning(
    uid: str, conversation_id: str, segment_ids: list, *, card_generation: Optional[int] = None
) -> str:
    return await _run_authorized_learning(
        uid,
        conversation_id,
        dict(
            target='owner',
            person_id=None,
            segment_ids=list(segment_ids or []),
            card_generation=card_generation,
        ),
    )


def schedule_reprocessed_learning(
    uid: str,
    processed_conversation: Any,
    background_tasks: Any,
    *,
    response: Any = None,
    receipt_applied: bool = False,
) -> Any:
    """Schedule durable learning for a successfully reprocessed conversation."""
    # The mobile speaker-label refresh must distinguish this processor from an
    # older backend that accepted reprocess but built its prompt before applying
    # the current manual speaker receipt. A header keeps released JSON decoders
    # compatible and is emitted only after processing returns successfully.
    if response is not None and receipt_applied:
        response.headers['X-Omi-Speaker-Receipt-Summary'] = '1'
    if background_tasks is not None:
        conversation_id = getattr(processed_conversation, 'id', None) or (
            processed_conversation.get('id') if isinstance(processed_conversation, Mapping) else None
        )
        if conversation_id:
            background_tasks.add_task(run_speaker_learning_jobs, uid, conversation_id)
    return processed_conversation


def schedule_person_voice_learning_retry(uid: str, conversation_id: str) -> None:
    """Fail-open scheduling; a scheduling failure must never fail finalization."""
    key = (uid, str(conversation_id))
    if key in _in_flight_retries:
        return
    if len(_in_flight_retries) >= VOICE_LEARNING_RETRY_MAX_IN_FLIGHT:
        logger.info('speaker_voice_learning retry saturated')
        return
    coro = run_speaker_learning_jobs(uid, conversation_id)
    _in_flight_retries.add(key)
    try:
        task = start_background_task(coro, name='speaker-learning-retry')
    except Exception as error:
        coro.close()
        _in_flight_retries.discard(key)
        logger.warning('speaker_voice_learning retry schedule failed exception_type=%s', type(error).__name__)
        return
    try:
        task.add_done_callback(lambda _task: _in_flight_retries.discard(key))
    except (AttributeError, TypeError):
        _in_flight_retries.discard(key)


def schedule_person_voice_learning_retries(uid: str, response: Mapping[str, Any], fenced_key: str) -> None:
    """Schedule bounded retries for each conversation a sync response produced."""
    eligible = (set(response.get('new_memories') or set()) | set(response.get('updated_memories') or set())) - set(
        response.get(fenced_key) or set()
    )
    for conversation_id in sorted(str(cid) for cid in eligible):
        schedule_person_voice_learning_retry(uid, conversation_id)
