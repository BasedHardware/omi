from typing import List

import requests

from database.redis_db import get_user_webhook_db
from models.memory import Memory
from models.transcript_segment import TranscriptSegment
from models.users import WebhookType


def memory_created_webhook(uid, memory: Memory):
    webhook_url = get_user_webhook_db(uid, WebhookType.memory_created)
    if not webhook_url:
        return
    webhook_url += f'?uid={uid}'
    response = requests.post(webhook_url, json=memory.dict(), headers={'Content-Type': 'application/json'})
    print('memory_created_webhook:', response.status_code)


async def realtime_transcript_webhook(uid, segments: List[dict]):
    webhook_url = get_user_webhook_db(uid, WebhookType.memory_created)
    if not webhook_url:
        return
    webhook_url += f'?uid={uid}'
    try:
        response = requests.post(
            webhook_url,
            json={'segments': segments, 'session_id': uid},
            headers={'Content-Type': 'application/json'}
        )
        print('realtime_transcript_webhook:', response.status_code)
    except Exception as e:
        print(f"Error sending realtime transcript to developer webhook: {e}")


async def send_audio_bytes_developer_webhook(uid: str, sample_rate: int, data: bytearray):
    # TODO: add a lock, send shorter segments, validate regex.
    webhook_url = get_user_webhook_db(uid, WebhookType.audio_bytes)
    if not webhook_url:
        return
    webhook_url += f'?sample_rate={sample_rate}&uid={uid}'
    try:
        response = requests.post(webhook_url, data=data, headers={'Content-Type': 'application/octet-stream'})
        print('send_audio_bytes_developer_webhook:', response.status_code)
    except Exception as e:
        print(f"Error sending audio bytes to developer webhook: {e}")
