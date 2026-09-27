"""Explicit support upload and admin-only retrieval of BLE diagnostic bundles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from utils.executors import run_blocking, storage_executor
from utils.other import device_diagnostics_storage
from utils.other import endpoints as auth

router = APIRouter(tags=['device-diagnostics'])
logger = logging.getLogger(__name__)
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
TICKET_PATTERN = re.compile(r'^[0-9A-F]{12}$')
upload_uid = auth.with_rate_limit(auth.get_current_user_uid, 'memories:modify')


class DiagnosticsUpload(BaseModel):
    bundle_base64: str = Field(max_length=5_600_000)


class DiagnosticsReceipt(BaseModel):
    ticket: str


class DiagnosticsBundle(BaseModel):
    bundle: dict[str, Any]


def _admin_key(
    x_admin_key: str = Header(..., alias='X-Admin-Key'),
    x_admin_user: str | None = Header(None, alias='X-Admin-User'),
) -> str:
    expected = os.getenv('ADMIN_KEY', '')
    if not expected or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=403, detail='Invalid admin key')
    key_id = hashlib.sha256(x_admin_key.encode()).hexdigest()[:8]
    return f'admin:{key_id}/{x_admin_user[:64] if x_admin_user else "unattributed"}'


@router.post('/v1/mobile/device-diagnostics', response_model=DiagnosticsReceipt, status_code=201)
async def upload_device_diagnostics(payload: DiagnosticsUpload, uid: str = Depends(upload_uid)) -> DiagnosticsReceipt:
    if len(payload.bundle_base64) > (MAX_BUNDLE_BYTES + 2) // 3 * 4:
        raise HTTPException(status_code=413, detail='Diagnostics bundle is too large')
    try:
        body = base64.b64decode(payload.bundle_base64, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail='Invalid base64 diagnostics bundle') from exc
    if len(body) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail='Diagnostics bundle is too large')
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='Diagnostics bundle must be JSON') from exc
    if not isinstance(parsed, dict) or parsed.get('schema_version') != 2:
        raise HTTPException(status_code=400, detail='Unsupported diagnostics schema')
    ticket = await run_blocking(storage_executor, device_diagnostics_storage.save_bundle, uid, body)
    return DiagnosticsReceipt(ticket=ticket)


@router.get('/v1/admin/device-diagnostics/{ticket}', response_model=DiagnosticsBundle, tags=['admin'])
async def read_device_diagnostics(ticket: str, admin: str = Depends(_admin_key)) -> DiagnosticsBundle:
    if not TICKET_PATTERN.fullmatch(ticket):
        raise HTTPException(status_code=404, detail='Ticket not found')
    bundle = await run_blocking(storage_executor, device_diagnostics_storage.read_bundle, ticket)
    if bundle is None:
        raise HTTPException(status_code=404, detail='Ticket not found')
    logger.info('%s read device diagnostics ticket_hash=%s', admin, hashlib.sha256(ticket.encode()).hexdigest()[:12])
    return DiagnosticsBundle(bundle=bundle)
