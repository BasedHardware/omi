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

from database import users as users_db
from models.imessage import (
    IMessageContactsSyncRequest,
    IMessageContactsSyncResponse,
    IMessageDraftRequest,
    IMessageDraftResponse,
    IMessageIngestRequest,
    IMessageIngestResponse,
    IMessageSettings,
    IMessageStatus,
)
from utils import imessage_connector
from utils.executors import db_executor, run_blocking
from utils.llm import reply_media, reply_scheduling
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
    # Resolve shared links/images to text (async) before the sync draft step so the
    # drafter understands what a URL is about and what a photo shows.
    media_context = await reply_media.build_media_context(uid, thread)
    # Availability-aware drafting: grounds a scheduling reply in the real calendar and,
    # if the reply accepts a proposed time, creates a tentative hold to confirm/discard.
    result, hold = await reply_scheduling.draft_reply_with_scheduling(
        uid, req.person, thread, req.intent, req.is_group, media_context
    )
    return IMessageDraftResponse(
        draft=result['draft'],
        ambiguous=result.get('ambiguous', False),
        abstain=result.get('abstain', False),
        needs_input=result.get('needs_input', False),
        needs_input_reason=result.get('needs_input_reason'),
        hold=hold,
    )


@router.post('/v1/imessage/contacts/sync', response_model=IMessageContactsSyncResponse, tags=['imessage'])
async def imessage_contacts_sync(req: IMessageContactsSyncRequest, uid: str = Depends(auth.get_current_user_uid)):
    contacts = [c.dict() for c in req.contacts]
    count = await run_blocking(db_executor, users_db.import_contacts, uid, contacts)
    return IMessageContactsSyncResponse(people_upserted=count)
