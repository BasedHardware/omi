"""Google Play Billing routes: purchase verification, real-time developer notifications, reconcile."""

import base64
import binascii
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import play_billing as play_config
from database.fsr_read_cache import fresh_reader
from models.users import Subscription
from utils import play_billing
from utils.cloud_tasks import verify_configured_cloud_tasks_oidc
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)
router = APIRouter()


class PlayPurchaseRequest(BaseModel):
    purchase_token: str = Field(..., min_length=1, max_length=4096)
    product_id: str = Field(..., min_length=1, max_length=255)


class PlayPurchaseResponse(BaseModel):
    status: Literal['active', 'pending', 'inactive']
    subscription: Optional[Subscription] = None


class PlayBillingErrorResponse(BaseModel):
    code: str
    detail: str


class PlayNotificationResponse(BaseModel):
    status: str


def _error(error: play_billing.PlayBillingError) -> JSONResponse:
    return JSONResponse(status_code=error.http_status, content={'code': error.code, 'detail': error.message})


@router.post(
    '/v1/payments/play/purchases',
    response_model=PlayPurchaseResponse,
    response_model_exclude_none=True,
    responses={400: {'model': PlayBillingErrorResponse}, 409: {'model': PlayBillingErrorResponse}},
)
@fresh_reader
def verify_play_purchase(request: PlayPurchaseRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Verify a Google Play purchase token, bind it to this account and grant Omi Pro once Google says it is paid."""
    try:
        result = play_billing.verify_and_bind(uid, request.purchase_token, request.product_id)
    except play_billing.PlayBillingError as error:
        return _error(error)
    return PlayPurchaseResponse(status=result.status, subscription=result.subscription)


def _decode_push(body: dict) -> dict:
    message = body.get('message')
    data = message.get('data') if isinstance(message, dict) else None
    if not isinstance(data, str):
        raise HTTPException(status_code=400, detail='Missing message data')
    try:
        decoded = json.loads(base64.b64decode(data, validate=True))
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail='Malformed message data') from None
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=400, detail='Malformed message data')
    return decoded


@router.post('/v2/internal/play-billing/rtdn', include_in_schema=False, response_model=PlayNotificationResponse)
def play_rtdn(request: Request, body: dict = Body(...)):
    """Pub/Sub push of a Play real-time developer notification. A non-2xx reply makes Pub/Sub retry."""
    verify_configured_cloud_tasks_oidc(
        request, audience=play_config.rtdn_audience(), invoker_sa=play_config.rtdn_invoker_sa()
    )
    notification = _decode_push(body)
    try:
        outcome = play_billing.handle_developer_notification(notification)
    except play_billing.PlayBillingError as error:
        if error.http_status >= 500:
            raise HTTPException(status_code=503, detail=error.code) from None
        outcome = error.code
    logger.info('play_billing rtdn outcome=%s', outcome)
    return PlayNotificationResponse(status=outcome)


@router.post('/v2/internal/play-billing/reconcile', include_in_schema=False)
def play_reconcile(request: Request):
    """Cloud Scheduler: re-read open Play purchases whose next check has passed."""
    verify_configured_cloud_tasks_oidc(
        request, audience=play_config.reconcile_audience(), invoker_sa=play_config.reconcile_invoker_sa()
    )
    counts = play_billing.reconcile_due()
    logger.info('play_billing reconcile counts=%s', counts)
    return counts
