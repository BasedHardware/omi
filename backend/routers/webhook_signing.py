"""Signing secrets for webhook destinations (#20939).

A secret is returned exactly once, when it is issued. Issuing again rotates it: the new secret
signs immediately and the previous one keeps signing alongside it for 24 hours, so a receiver
can switch without dropping deliveries. Deleting the secret turns signing off; deliveries then
carry no signature headers, exactly as before this feature existed.

Developer webhooks (the URLs in Developer Settings) share one secret per user. Each integration
app has its own, managed by the app owner. Issue, rotate and delete share one per-user rate
limit (``webhook_signing:secret``); reading the status does not count against it.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from database.webhook_signing import (
    WebhookSigningSecrets,
    delete_app_webhook_signing_db,
    delete_user_webhook_signing_db,
    get_app_webhook_signing_db,
    get_user_webhook_signing_db,
    rotate_app_webhook_signing_db,
    rotate_user_webhook_signing_db,
)
from models.webhook_signing import (
    WebhookSigningSecretDeletedResponse,
    WebhookSigningSecretIssuedResponse,
    WebhookSigningSecretStatusResponse,
)
from utils.apps import get_available_app_by_id
from utils.other import endpoints as auth
from utils.webhook_signing import generate_secret

logger = logging.getLogger(__name__)

router = APIRouter()

# Credential mutations are throttled; the status read is not.
_mutating_uid = auth.with_rate_limit(auth.get_current_user_uid, 'webhook_signing:secret')


def _issued(record: WebhookSigningSecrets, response: Response) -> dict[str, Any]:
    # The only response that ever carries the secret; keep it out of every cache on the way.
    response.headers['Cache-Control'] = 'no-store'
    return {
        'secret': record.current,
        'created_at': record.created_at,
        'previous_valid_until': record.previous_valid_until,
    }


def _status(record: WebhookSigningSecrets | None) -> dict[str, Any]:
    if record is None:
        return {'configured': False}
    return {'configured': True, 'created_at': record.created_at, 'previous_valid_until': record.previous_valid_until}


# --- developer webhooks ---------------------------------------------------------------------------


@router.post(
    '/v1/users/developer/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretIssuedResponse
)
def issue_user_webhook_signing_secret(response: Response, uid: str = Depends(_mutating_uid)):
    return _issued(rotate_user_webhook_signing_db(uid, generate_secret()), response)


@router.get(
    '/v1/users/developer/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretStatusResponse
)
def get_user_webhook_signing_secret_status(uid: str = Depends(auth.get_current_user_uid)):
    return _status(get_user_webhook_signing_db(uid))


@router.delete(
    '/v1/users/developer/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretDeletedResponse
)
def delete_user_webhook_signing_secret(uid: str = Depends(_mutating_uid)):
    delete_user_webhook_signing_db(uid)
    return {'status': 'ok'}


# --- integration apps -----------------------------------------------------------------------------


def _owned_app_or_raise(app_id: str, uid: str) -> None:
    # Same ownership rule as the app API-key routes in routers/apps.py.
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.get('uid') != uid:
        raise HTTPException(
            status_code=403, detail='You are not authorized to manage the webhook signing secret for this app'
        )


@router.post('/v1/apps/{app_id}/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretIssuedResponse)
def issue_app_webhook_signing_secret(app_id: str, response: Response, uid: str = Depends(_mutating_uid)):
    _owned_app_or_raise(app_id, uid)
    return _issued(rotate_app_webhook_signing_db(app_id, generate_secret()), response)


@router.get('/v1/apps/{app_id}/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretStatusResponse)
def get_app_webhook_signing_secret_status(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _owned_app_or_raise(app_id, uid)
    return _status(get_app_webhook_signing_db(app_id))


@router.delete(
    '/v1/apps/{app_id}/webhook-signing-secret', tags=['v1'], response_model=WebhookSigningSecretDeletedResponse
)
def delete_app_webhook_signing_secret(app_id: str, uid: str = Depends(_mutating_uid)):
    _owned_app_or_raise(app_id, uid)
    delete_app_webhook_signing_db(app_id)
    return {'status': 'ok'}
