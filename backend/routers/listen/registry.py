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
_shared_capture_conversations: Dict[str, Set[str]] = {}
_lock = threading.Lock()

PROACTIVE_MESSAGE_CHANNEL = "proactive_message:listen"


def _conversation_id_for_session(session: Any) -> str | None:
    current = getattr(getattr(session, 'state', None), 'current_conversation_id', None)
    if current:
        return current
    return getattr(session, '_shared_capture_conversation_id', None)


def register(session: Any) -> None:
    with _lock:
        uid = session.request.uid
        _sessions.setdefault(uid, set()).add(session)
        conversation_id = _conversation_id_for_session(session)
        if conversation_id in _shared_capture_conversations.get(uid, set()):
            session.shared_capture = True


def unregister(session: Any) -> None:
    with _lock:
        uid = session.request.uid
        sessions = _sessions.get(uid)
        if not sessions:
            return
        sessions.discard(session)
        if not sessions:
            _sessions.pop(uid, None)
        marked = _shared_capture_conversations.get(uid)
        if marked:
            active_conversations = {_conversation_id_for_session(active) for active in sessions}
            marked.intersection_update(conversation for conversation in active_conversations if conversation)
            if not marked:
                _shared_capture_conversations.pop(uid, None)


def mark_shared_capture(uid: str, conversation_id: str) -> None:
    """Publish a pairing marker to already-registered sockets in this worker."""
    if not uid or not conversation_id:
        return
    with _lock:
        _shared_capture_conversations.setdefault(uid, set()).add(conversation_id)
        for session in _sessions.get(uid, ()):
            current = getattr(getattr(session, 'state', None), 'current_conversation_id', None)
            source = getattr(getattr(session, 'request', None), 'source', None)
            source = getattr(source, 'value', source)
            if current == conversation_id or (current is None and source in {'omi', 'desktop'}):
                session._shared_capture_conversation_id = conversation_id
                session.shared_capture = True


def is_shared_capture(uid: str, conversation_id: str | None) -> bool:
    if not uid or not conversation_id:
        return False
    with _lock:
        return conversation_id in _shared_capture_conversations.get(uid, set())


def has_shared_capture_peer(uid: str, conversation_id: str | None) -> bool:
    """Return whether another live socket still owns a paired conversation."""
    if not uid or not conversation_id:
        return False
    with _lock:
        if conversation_id not in _shared_capture_conversations.get(uid, set()):
            return False
        return any(_conversation_id_for_session(session) == conversation_id for session in _sessions.get(uid, ()))


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
