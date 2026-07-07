"""Telegram connector routes.

The desktop app runs an on-device MTProto client (bootstrapped from the local
Telegram Desktop session) that reads the user's messages and pushes normalized
threads here. Like iMessage there is no OAuth — the session is local to the user's
Mac, so connecting is the consent signal.

  POST /v1/telegram/threads            ingest normalized threads
  GET  /v1/telegram/connection-status  current status
  GET  /v1/telegram/settings           consent + per-sender opt-out
  PUT  /v1/telegram/settings           update consent + opt-out
  POST /v1/telegram/disconnect         forget connection + state
  POST /v1/telegram/draft-reply        draft a reply in the user's voice (never sends)
"""

import logging

from fastapi import APIRouter, Depends

from models.telegram import (
    TelegramDraftRequest,
    TelegramDraftResponse,
    TelegramIngestRequest,
    TelegramIngestResponse,
    TelegramSettings,
    TelegramStatus,
)
from utils import telegram_connector
from utils.llm import reply_media, reply_scheduling
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v1/telegram/threads', response_model=TelegramIngestResponse, tags=['telegram'])
async def telegram_ingest(req: TelegramIngestRequest, uid: str = Depends(auth.get_current_user_uid)):
    return await telegram_connector.ingest_threads(uid, req)


@router.get('/v1/telegram/connection-status', response_model=TelegramStatus, tags=['telegram'])
def telegram_connection_status(uid: str = Depends(auth.get_current_user_uid)):
    return telegram_connector.get_status(uid)


@router.get('/v1/telegram/settings', response_model=TelegramSettings, tags=['telegram'])
def telegram_get_settings(uid: str = Depends(auth.get_current_user_uid)):
    return telegram_connector.get_settings(uid)


@router.put('/v1/telegram/settings', response_model=TelegramSettings, tags=['telegram'])
def telegram_update_settings(settings: TelegramSettings, uid: str = Depends(auth.get_current_user_uid)):
    return telegram_connector.update_settings(uid, settings)


@router.post('/v1/telegram/disconnect', tags=['telegram'])
def telegram_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    telegram_connector.disconnect(uid)
    return {'success': True}


@router.post('/v1/telegram/draft-reply', response_model=TelegramDraftResponse, tags=['telegram'])
async def telegram_draft_reply(req: TelegramDraftRequest, uid: str = Depends(auth.get_current_user_uid)):
    thread = [m.dict() for m in req.thread]
    media_context = await reply_media.build_media_context(uid, thread)
    result, hold = await reply_scheduling.draft_reply_with_scheduling(
        uid, req.person, thread, req.intent, req.is_group, media_context
    )
    return TelegramDraftResponse(
        draft=result['draft'],
        ambiguous=result.get('ambiguous', False),
        abstain=result.get('abstain', False),
        needs_input=result.get('needs_input', False),
        needs_input_reason=result.get('needs_input_reason'),
        hold=hold,
    )
