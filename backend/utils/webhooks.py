import asyncio
import json
from datetime import datetime
from typing import List

import requests
import websockets

from database.redis_db import get_user_webhook_db, user_webhook_status_db, disable_user_webhook_db, \
    enable_user_webhook_db, set_user_webhook_db
from models.memory import Memory
from models.users import WebhookType
import database.notifications as notification_db
from utils.notifications import send_notification


def memory_created_webhook(uid, memory: Memory):
    toggled = user_webhook_status_db(uid, WebhookType.memory_created)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.memory_created)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        try:
            response = requests.post(
                webhook_url,
                json=memory.as_dict_cleaned_dates(),
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            print('memory_created_webhook:', webhook_url, response.status_code)
        except Exception as e:
            print(f"Error sending memory created to developer webhook: {e}")
    else:
        return


def day_summary_webhook(uid, summary: str):
    toggled = user_webhook_status_db(uid, WebhookType.day_summary)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.day_summary)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        try:
            response = requests.post(
                webhook_url,
                json={
                    'summary': summary,
                    'uid': uid,
                    'created_at': datetime.now().isoformat()
                },
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            print('day_summary_webhook:', webhook_url, response.status_code)
        except Exception as e:
            print(f"Error sending day summary to developer webhook: {e}")
    else:
        return


async def realtime_transcript_webhook(uid, segments: List[dict]):
    toggled = user_webhook_status_db(uid, WebhookType.realtime_transcript)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.realtime_transcript)
        if not webhook_url:
            return
        webhook_url += f'?uid={uid}'
        try:
            response = requests.post(
                webhook_url,
                json={'segments': segments, 'session_id': uid},
                headers={'Content-Type': 'application/json'},
                timeout=15,
            )
            print('realtime_transcript_webhook:', webhook_url, response.status_code)
            if response.status_code == 200:
                response_data = response.json()
                if not response_data:
                    return
                message = response_data.get('message', '')
                if len(message) > 5:
                    token = notification_db.get_token_only(uid)
                    send_webhook_notification(token, message)
        except Exception as e:
            print(f"Error sending realtime transcript to developer webhook: {e}")
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
    # TODO: add a lock, send shorter segments, validate regex.
    toggled = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.audio_bytes)
        webhook_url = webhook_url.split(',')[0]
        if not webhook_url:
            return
        webhook_url += f'?sample_rate={sample_rate}&uid={uid}'
        try:
            response = requests.post(webhook_url, data=data, headers={'Content-Type': 'application/octet-stream'}, timeout=15)
            print('send_audio_bytes_developer_webhook:', webhook_url, response.status_code)
        except Exception as e:
            print(f"Error sending audio bytes to developer webhook: {e}")
    else:
        return


# continue?
async def connect_user_webhook_ws(sample_rate: int, language: str, preseconds: int = 0):
    uri = ''

    try:
        socket = await websockets.connect(uri, extra_headers={})
        await socket.send(json.dumps({}))

        async def on_message():
            try:
                async for message in socket:
                    response = json.loads(message)
            except websockets.exceptions.ConnectionClosedOK:
                print("Speechmatics connection closed normally.")
            except Exception as e:
                print(f"Error receiving from Speechmatics: {e}")
            finally:
                if not socket.closed:
                    await socket.close()
                    print("Speechmatics WebSocket closed in on_message.")

        asyncio.create_task(on_message())
        return socket
    except Exception as e:
        print(f"Exception in process_audio_speechmatics: {e}")
        raise


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

def send_webhook_notification(token: str, message: str):
    send_notification(token, "Webhook" + ' says', message)
