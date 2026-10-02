"""Bounded voice-learning retry coordinator for finalized conversations.

Finalization (and sync) schedule one fail-open retry pass that re-resolves the
current receipt-named people from the freshly-read conversation and retries
teaching only for those still missing a usable voiceprint. No task worker, no
queue — one coroutine with a people bound and a total deadline.
"""

import asyncio
import logging
from typing import Any, List, Mapping

from database import conversations as conversations_db
from database import users as users_db
from models.other import VoiceReadiness, voice_readiness
from utils.executors import db_executor, run_blocking, start_background_task
from utils.person_evidence import receipt_person_ids
from utils.speaker_identification import extract_speaker_samples
from utils.speaker_learning_policy import authorized_teaching_segments

logger = logging.getLogger(__name__)

VOICE_LEARNING_RETRY_MAX_PEOPLE = 5
VOICE_LEARNING_RETRY_DEADLINE_SECONDS = 45
VOICE_LEARNING_RETRY_MAX_IN_FLIGHT = 16

_in_flight_retries: set = set()


async def retry_people_without_voiceprint(uid: str, conversation_id: str) -> None:
    """Retry voice-learning for receipt-named people lacking a usable voiceprint."""
    try:
        async with asyncio.timeout(VOICE_LEARNING_RETRY_DEADLINE_SECONDS):
            conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
            if (
                not conversation
                or conversation.get('discarded')
                or conversation.get('is_locked')
                or conversation.get('deleted')
            ):
                return
            eligible: List[tuple] = []
            for person_id in receipt_person_ids(conversation.get('manual_speaker_assignments')):
                if len(eligible) >= VOICE_LEARNING_RETRY_MAX_PEOPLE:
                    break
                person = await run_blocking(db_executor, users_db.get_person, uid, person_id)
                if not person or voice_readiness(person) == VoiceReadiness.ready:
                    continue
                segment_ids: List[str] = [
                    segment['id']
                    for segment in authorized_teaching_segments(conversation, person_id)
                    if isinstance(segment.get('id'), str)
                ]
                if segment_ids:
                    eligible.append((person_id, segment_ids))
            for person_id, segment_ids in eligible:
                await extract_speaker_samples(uid, person_id, conversation_id, segment_ids)
    except TimeoutError:
        logger.info('speaker_voice_learning retry deadline conversation=%s', conversation_id)
    except Exception as error:
        logger.warning(
            'speaker_voice_learning retry failed conversation=%s exception_type=%s',
            conversation_id,
            type(error).__name__,
        )


def schedule_person_voice_learning_retry(uid: str, conversation_id: str) -> None:
    """Fail-open scheduling; a scheduling failure must never fail finalization."""
    key = (uid, str(conversation_id))
    if key in _in_flight_retries:
        return
    if len(_in_flight_retries) >= VOICE_LEARNING_RETRY_MAX_IN_FLIGHT:
        logger.info('speaker_voice_learning retry saturated conversation=%s', conversation_id)
        return
    coro = retry_people_without_voiceprint(uid, conversation_id)
    _in_flight_retries.add(key)
    try:
        task = start_background_task(coro, name='speaker-learning-retry')
    except Exception as error:
        coro.close()
        _in_flight_retries.discard(key)
        logger.warning(
            'speaker_voice_learning retry schedule failed conversation=%s exception_type=%s',
            conversation_id,
            type(error).__name__,
        )
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
