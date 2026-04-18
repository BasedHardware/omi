import asyncio
import json
from datetime import datetime
from typing import List

from database.redis_db import (
    get_user_webhook_db,
    user_webhook_status_db,
    disable_user_webhook_db,
    enable_user_webhook_db,
    set_user_webhook_db,
)
from models.conversation import Conversation
from models.users import WebhookType
import database.notifications as notification_db
from utils.conversations.render import populate_speaker_names, populate_folder_names
from utils.conversations.render import conversation_to_dict
from utils.http_client import get_webhook_client, get_webhook_circuit_breaker, get_webhook_semaphore
from utils.notifications import send_notification
import logging

logger = logging.getLogger(__name__)


async def conversation_created_webhook(uid, memory: Conversation):
    if memory.is_locked:
        return

    toggled = user_webhook_status_db(uid, WebhookType.memory_created)

    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.memory_created)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'memory_created_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            payload = conversation_to_dict(memory)
            populate_speaker_names(uid, [payload])
            populate_folder_names(uid, [payload])
            async with get_webhook_semaphore():
                client = get_webhook_client()
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                )
            logger.info(f'memory_created_webhook: {webhook_url} {response.status_code}')
            cb.record_success()
        except Exception as e:
            cb.record_failure()
            logger.error(f"Error sending memory created to developer webhook: {e}")
    else:
        return


async def day_summary_webhook(uid, summary: str):
    toggled = user_webhook_status_db(uid, WebhookType.day_summary)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.day_summary)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'day_summary_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            async with get_webhook_semaphore():
                client = get_webhook_client()
                response = await client.post(
                    webhook_url,
                    json={'summary': summary, 'uid': uid, 'created_at': datetime.now().isoformat()},
                    headers={'Content-Type': 'application/json'},
                )
            logger.info(f'day_summary_webhook: {webhook_url} {response.status_code}')
            cb.record_success()
        except Exception as e:
            cb.record_failure()
            logger.error(f"Error sending day summary to developer webhook: {e}")
    else:
        return


async def realtime_transcript_webhook(uid, segments: List[dict]):
    logger.info(f"realtime_transcript_webhook {uid}")
    toggled = user_webhook_status_db(uid, WebhookType.realtime_transcript)

    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.realtime_transcript)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'realtime_transcript_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            async with get_webhook_semaphore():
                client = get_webhook_client()
                response = await client.post(
                    webhook_url,
                    json={'segments': segments, 'session_id': uid},
                    headers={'Content-Type': 'application/json'},
                )
            logger.info(f'realtime_transcript_webhook: {webhook_url} {response.status_code}')
            cb.record_success()
            if response.status_code == 200:
                response_data = response.json()
                if not response_data:
                    return
                message = response_data.get('message', '')
                if len(message) > 5:
                    send_webhook_notification(uid, message)
        except Exception as e:
            cb.record_failure()
            logger.error(f"Error sending realtime transcript to developer webhook: {e}")
    else:
        return


def get_audio_bytes_webhook_seconds(uid: str):
    toggled = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.audio_bytes)
        if not webhook_url:
            return
        parts = webhook_url.split(',')
        if len(parts) == 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return 5
    else:
        return


async def send_audio_bytes_developer_webhook(uid: str, sample_rate: int, data: bytearray):
    logger.info(f"send_audio_bytes_developer_webhook {uid}")
    # TODO: add a lock, send shorter segments, validate regex.
    toggled = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.audio_bytes)
        if not webhook_url:
            return
        webhook_url = webhook_url.split(',')[0]
        if not webhook_url:
            return
        webhook_url += f'?sample_rate={sample_rate}&uid={uid}'
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'send_audio_bytes_developer_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            async with get_webhook_semaphore():
                client = get_webhook_client()
                response = await client.post(
                    webhook_url, content=bytes(data), headers={'Content-Type': 'application/octet-stream'}
                )
            logger.info(f'send_audio_bytes_developer_webhook: {webhook_url} {response.status_code}')
            cb.record_success()
        except Exception as e:
            cb.record_failure()
            logger.error(f"Error sending audio bytes to developer webhook: {e}")
    else:
        return


def webhook_first_time_setup(uid: str, wType: WebhookType) -> bool:
    res = False
    url = get_user_webhook_db(uid, wType)
    if url == '' or url == ',':
        disable_user_webhook_db(uid, wType)
        res = False
    else:
        enable_user_webhook_db(uid, wType)
        res = True
    return res


def send_webhook_notification(user_id: str, message: str):
    send_notification(user_id, "Webhook" + ' says', message)
