"""Stateless chat generation (v2).

``POST /v2/messages`` (``routers/chat.py``) owns the user's chat state: it persists
the human turn, attributes a chat quota question to it, runs goal extraction, and
persists the generated answer. Automated drafting surfaces (the AI clone) only need
the generated text, so routing them through that endpoint writes machine turns into
the human's canonical chat history.

This module exposes the same generation path with persistence and session identity
removed. It lives beside ``routers/chat.py`` rather than inside it so the persisting
and non-persisting surfaces cannot drift into sharing state by accident.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from models.app import App
from models.chat import GenerateReplyRequest, GenerateReplyResponse, Message, MessageSender, MessageType
from utils.apps import get_available_app_by_id
from utils.executors import db_executor, run_blocking
from utils.llm.usage_tracker import Features, reset_usage_context, set_usage_context
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.retrieval.graph import execute_chat_stream
from utils.subscription import enforce_chat_quota

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post('/v2/chat/generate-reply', tags=['chat'], response_model=GenerateReplyResponse)
async def generate_reply(
    data: GenerateReplyRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:send_message")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Stateless owner-authenticated reply generation.

    Same generation path as ``POST /v2/messages`` (``execute_chat_stream``) with the
    persistence and session identity removed: no human or AI message is written to the
    owner's chat history, no chat session is acquired or mutated, and no chat quota
    question is attributed to the conversation. Automated drafting surfaces (the AI
    clone) must use this instead of ``/v2/messages`` so machine-generated turns never
    contaminate the human's chat.

    Error contract is explicit: streamed ``error: `` frames and the canned answer the
    stream stages alongside ``callback_data['error']`` are never returned as reply
    text. A failed generation is an HTTP 502 with ``{'error': <reason>}``.
    """
    await run_blocking(db_executor, enforce_chat_quota, uid, platform=x_app_platform)

    app_id = data.app_id if data.app_id not in ['null', ''] else None
    app_record = await run_blocking(db_executor, get_available_app_by_id, app_id, uid) if app_id else None
    if app_id and not app_record:
        raise HTTPException(status_code=404, detail={'error': 'app_not_found'})
    app = App(**app_record) if app_record else None
    resolved_app_id = app.id if app else None

    created_at = datetime.now(timezone.utc)
    messages = [
        Message(
            id=str(uuid.uuid4()),
            text=turn.text,
            created_at=created_at,
            sender=turn.sender,
            type=MessageType.text,
            app_id=resolved_app_id,
        )
        for turn in data.history
    ]
    messages.append(
        Message(
            id=str(uuid.uuid4()),
            text=data.text,
            created_at=created_at,
            sender=MessageSender.human,
            type=MessageType.text,
            app_id=resolved_app_id,
        )
    )

    callback_data: dict[str, Any] = {}
    usage_token = set_usage_context(uid, Features.CHAT)
    try:
        try:
            async for _chunk in execute_chat_stream(
                uid,
                messages,
                app,
                cited=False,
                callback_data=callback_data,
                chat_session=None,
                platform=x_app_platform,
            ):
                continue
        except Exception as exc:
            logger.error('stateless reply generation raised uid=%s error_type=%s', uid, type(exc).__name__)
            callback_data['error'] = 'stream_failure'
    finally:
        reset_usage_context(usage_token)

    error = callback_data.get('error')
    answer = callback_data.get('answer')
    if error or not answer:
        logger.error('stateless reply generation failed uid=%s reason=%s', uid, error or 'no_answer')
        record_fallback(
            component='other',
            from_mode='llm_answer',
            to_mode='none',
            reason='other',
            outcome='exhausted',
        )
        raise HTTPException(status_code=502, detail={'error': error or 'no_answer'})

    return GenerateReplyResponse(text=re.sub(r'\[\d+\]', '', answer), app_id=resolved_app_id)
