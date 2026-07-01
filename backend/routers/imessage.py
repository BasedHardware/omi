"""iMessage connector routes.

The desktop app reads the local Messages database and pushes normalized threads
here. Unlike the X connector there is no OAuth — access is local to the Mac, so
connecting is a local permission grant (Full Disk Access) plus consent stored here.

  POST /v1/imessage/threads            ingest normalized threads
  GET  /v1/imessage/connection-status  current status
  GET  /v1/imessage/settings           consent + per-contact opt-out
  PUT  /v1/imessage/settings           update consent + opt-out
  POST /v1/imessage/disconnect         forget connection + state
"""

import logging

from fastapi import APIRouter, Depends

from models.imessage import (
    IMessageDraftRequest,
    IMessageDraftResponse,
    IMessageIngestRequest,
    IMessageIngestResponse,
    IMessageSettings,
    IMessageStatus,
)
from utils import imessage_connector
from utils.executors import llm_executor, run_blocking
from utils.llm import reply_draft
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v1/imessage/threads', response_model=IMessageIngestResponse, tags=['imessage'])
async def imessage_ingest(req: IMessageIngestRequest, uid: str = Depends(auth.get_current_user_uid)):
    return await imessage_connector.ingest_threads(uid, req)


@router.get('/v1/imessage/connection-status', response_model=IMessageStatus, tags=['imessage'])
def imessage_connection_status(uid: str = Depends(auth.get_current_user_uid)):
    return imessage_connector.get_status(uid)


@router.get('/v1/imessage/settings', response_model=IMessageSettings, tags=['imessage'])
def imessage_get_settings(uid: str = Depends(auth.get_current_user_uid)):
    return imessage_connector.get_settings(uid)


@router.put('/v1/imessage/settings', response_model=IMessageSettings, tags=['imessage'])
def imessage_update_settings(settings: IMessageSettings, uid: str = Depends(auth.get_current_user_uid)):
    return imessage_connector.update_settings(uid, settings)


@router.post('/v1/imessage/disconnect', tags=['imessage'])
def imessage_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    imessage_connector.disconnect(uid)
    return {'success': True}


@router.post('/v1/imessage/draft-reply', response_model=IMessageDraftResponse, tags=['imessage'])
async def imessage_draft_reply(req: IMessageDraftRequest, uid: str = Depends(auth.get_current_user_uid)):
    thread = [m.dict() for m in req.thread]
    result = await run_blocking(llm_executor, reply_draft.draft_reply, uid, req.person, thread, req.intent)
    return IMessageDraftResponse(draft=result['draft'])
