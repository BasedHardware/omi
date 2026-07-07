"""WhatsApp connector routes.

The desktop app reads the local WhatsApp Desktop database (the group-container
``ChatStorage.sqlite``) and pushes normalized threads here. Like iMessage there is
no OAuth — access is local to the Mac (gated by Full Disk Access), so connecting is
a local permission grant plus consent stored here.

  POST /v1/whatsapp/threads            ingest normalized threads
  GET  /v1/whatsapp/connection-status  current status
  GET  /v1/whatsapp/settings           consent + per-sender opt-out
  PUT  /v1/whatsapp/settings           update consent + opt-out
  POST /v1/whatsapp/disconnect         forget connection + state
  POST /v1/whatsapp/draft-reply        draft a reply in the user's voice (never sends)
  POST /v1/whatsapp/contacts/sync      import the macOS address book into People
"""

import logging

from fastapi import APIRouter, Depends

from database import users as users_db
from models.whatsapp import (
    WhatsAppContactsSyncRequest,
    WhatsAppContactsSyncResponse,
    WhatsAppDraftRequest,
    WhatsAppDraftResponse,
    WhatsAppIngestRequest,
    WhatsAppIngestResponse,
    WhatsAppSettings,
    WhatsAppStatus,
)
from utils import whatsapp_connector
from utils.executors import db_executor, run_blocking
from utils.llm import reply_media, reply_scheduling
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v1/whatsapp/threads', response_model=WhatsAppIngestResponse, tags=['whatsapp'])
async def whatsapp_ingest(req: WhatsAppIngestRequest, uid: str = Depends(auth.get_current_user_uid)):
    return await whatsapp_connector.ingest_threads(uid, req)


@router.get('/v1/whatsapp/connection-status', response_model=WhatsAppStatus, tags=['whatsapp'])
def whatsapp_connection_status(uid: str = Depends(auth.get_current_user_uid)):
    return whatsapp_connector.get_status(uid)


@router.get('/v1/whatsapp/settings', response_model=WhatsAppSettings, tags=['whatsapp'])
def whatsapp_get_settings(uid: str = Depends(auth.get_current_user_uid)):
    return whatsapp_connector.get_settings(uid)


@router.put('/v1/whatsapp/settings', response_model=WhatsAppSettings, tags=['whatsapp'])
def whatsapp_update_settings(settings: WhatsAppSettings, uid: str = Depends(auth.get_current_user_uid)):
    return whatsapp_connector.update_settings(uid, settings)


@router.post('/v1/whatsapp/disconnect', tags=['whatsapp'])
def whatsapp_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    whatsapp_connector.disconnect(uid)
    return {'success': True}


@router.post('/v1/whatsapp/draft-reply', response_model=WhatsAppDraftResponse, tags=['whatsapp'])
async def whatsapp_draft_reply(req: WhatsAppDraftRequest, uid: str = Depends(auth.get_current_user_uid)):
    thread = [m.dict() for m in req.thread]
    media_context = await reply_media.build_media_context(uid, thread)
    result, hold = await reply_scheduling.draft_reply_with_scheduling(
        uid, req.person, thread, req.intent, req.is_group, media_context
    )
    return WhatsAppDraftResponse(
        draft=result['draft'],
        ambiguous=result.get('ambiguous', False),
        abstain=result.get('abstain', False),
        needs_input=result.get('needs_input', False),
        needs_input_reason=result.get('needs_input_reason'),
        hold=hold,
    )


@router.post('/v1/whatsapp/contacts/sync', response_model=WhatsAppContactsSyncResponse, tags=['whatsapp'])
async def whatsapp_contacts_sync(req: WhatsAppContactsSyncRequest, uid: str = Depends(auth.get_current_user_uid)):
    contacts = [c.dict() for c in req.contacts]
    count = await run_blocking(db_executor, users_db.import_contacts, uid, contacts)
    return WhatsAppContactsSyncResponse(people_upserted=count)
