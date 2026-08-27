"""Process-local registry of active listen sessions for proactive-message delivery.

Cloud-generated proactive messages (mentor, third-party apps) are produced in
whichever process runs the realtime integrations — the backend when the pusher
is not configured, or the pusher subservice when it is. Either producer
publishes the message to Redis; this registry maps a uid to the live sessions
in this process so the subscriber can forward the event to the right websocket
without any Redis knowledge of client sockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Set

from models.message_event import ProactiveMessageEvent

logger = logging.getLogger(__name__)

_sessions: Dict[str, Set[Any]] = {}
_lock = threading.Lock()

PROACTIVE_MESSAGE_CHANNEL = "proactive_message:listen"


def register(session: Any) -> None:
    with _lock:
        _sessions.setdefault(session.request.uid, set()).add(session)


def unregister(session: Any) -> None:
    with _lock:
        sessions = _sessions.get(session.request.uid)
        if not sessions:
            return
        sessions.discard(session)
        if not sessions:
            _sessions.pop(session.request.uid, None)


def _sessions_for(uid: str) -> List[Any]:
    with _lock:
        return list(_sessions.get(uid, ()))


async def proactive_message_dispatcher(client: Any = None) -> None:
    if client is None:
        # Must be the same Redis the publisher writes to. `publish_proactive_message`
        # uses the shared client in database/redis_db.py (REDIS_DB_HOST / REDIS_DB_PORT /
        # REDIS_DB_PASSWORD); a client built from REDIS_HOST on 6379 with no password
        # subscribes to a different server, so the subscribe succeeds and no message
        # ever arrives.
        from database.redis_db import get_async_redis_client

        client = await get_async_redis_client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(PROACTIVE_MESSAGE_CHANNEL)
        logger.info('Subscribed to proactive-message channel: %s', PROACTIVE_MESSAGE_CHANNEL)
    except Exception as error:
        logger.error('Proactive-message subscribe failed type=%s', type(error).__name__)
        return
    try:
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get('type') != 'message':
                    continue
                payload = json.loads(message['data'])
                uid = payload.get('uid')
                if not uid:
                    continue
                event = ProactiveMessageEvent(
                    app_id=payload.get('app_id') or '',
                    title=payload.get('title') or '',
                    message=payload.get('message') or '',
                    conversation_id=payload.get('conversation_id'),
                )
                for session in _sessions_for(uid):
                    session.send_event(event)
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.error('Proactive-message dispatch failed type=%s', type(error).__name__)
                await asyncio.sleep(1.0)
    finally:
        try:
            await pubsub.unsubscribe(PROACTIVE_MESSAGE_CHANNEL)
            await pubsub.close()
        except Exception:
            pass
