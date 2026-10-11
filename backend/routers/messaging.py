"""Authenticated app-side linking; provider webhooks are supplied by adapters."""

from fastapi import APIRouter, Depends, HTTPException, Request
from database.messaging import MessagingStore
from utils.messaging.gateway import Gateway
from models.messaging import (
    ChannelLinkRequest,
    ChannelLinkProof,
    ChannelLinksResponse,
    ChannelVisibilityRequest,
    ChannelLinkReceipt,
)
from config.messaging import public_link_fields
from utils.messaging.access import require_access
from utils.other.endpoints import get_current_user_uid, with_rate_limit

router = APIRouter()


def _admit(uid):
    try:
        require_access(uid)
    except PermissionError:
        raise HTTPException(status_code=403, detail='Messaging channels unavailable') from None


@router.post('/v1/messaging/link-proofs', response_model=ChannelLinkProof, tags=['messaging'])
def mint_link_proof(
    body: ChannelLinkRequest, uid: str = Depends(with_rate_limit(get_current_user_uid, 'chat:send_message'))
):
    _admit(uid)
    proof = MessagingStore().mint(uid, body.channel, body.provider, body.kind)
    deep_link, address = public_link_fields(body.channel, proof['proof'])
    return {**proof, 'deep_link': deep_link, 'address': address}


@router.get('/v1/messaging/links', response_model=ChannelLinksResponse, tags=['messaging'])
def list_links(uid: str = Depends(get_current_user_uid)):
    # Revocation remains available after entitlement loss or a kill switch.
    return {'links': MessagingStore().links(uid)}


@router.delete('/v1/messaging/links/{link_id}', response_model=ChannelLinkReceipt, tags=['messaging'])
def unlink(link_id: str, uid: str = Depends(get_current_user_uid)):
    if len(link_id) != 64 or any(c not in '0123456789abcdef' for c in link_id):
        raise HTTPException(status_code=404, detail='Link not found')
    try:
        MessagingStore().unlink(uid, link_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail='Link not found') from None
    return {'status': 'unlinked'}


@router.patch('/v1/messaging/links/{link_id}', response_model=ChannelLinkReceipt, tags=['messaging'])
def set_visibility(link_id: str, body: ChannelVisibilityRequest, uid: str = Depends(get_current_user_uid)):
    if len(link_id) != 64 or any(c not in '0123456789abcdef' for c in link_id):
        raise HTTPException(status_code=404, detail='Link not found')
    try:
        MessagingStore().set_settings(uid, link_id, body.model_dump(exclude_none=True))
    except PermissionError:
        raise HTTPException(status_code=404, detail='Link not found') from None
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid link settings') from None
    return {'status': 'updated'}


# Stage B registers constructed gateways during application setup. This bounded
# registry contains provider objects, never per-user/session state.
_gateways = {}


def register_adapter(adapter_id, adapter, *, wake=None):
    if adapter_id in _gateways or len(_gateways) >= 16:
        raise ValueError('Duplicate adapter or adapter capacity reached')
    gateway = Gateway(adapter, wake=wake)
    if wake is None:

        async def dispatch(paths):
            for path in paths:
                await gateway.process(path)

        gateway.wake = dispatch
    _gateways[adapter_id] = gateway
    return gateway


@router.post('/v1/messaging/webhooks/{adapter_id}', status_code=202, tags=['messaging'])
async def receive_webhook(adapter_id: str, request: Request):
    gateway = _gateways.get(adapter_id)
    if gateway is None:
        raise HTTPException(status_code=404, detail='Adapter unavailable')
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status_code=413, detail='Webhook too large')
    try:
        await gateway.webhook(body, request.headers)
    except PermissionError:
        raise HTTPException(status_code=401, detail='Invalid webhook signature') from None
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid webhook') from None
    return {'status': 'accepted'}
