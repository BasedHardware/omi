import base64
import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from database.screen_activity import upsert_screen_activity
from database.vector_db import upsert_screen_activity_vectors
from utils.executors import critical_executor, db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid, get_user
from utils.subscription import is_trial_paywalled

logger = logging.getLogger(__name__)
router = APIRouter()
_SESSION_CACHE_TTL = 3600
_SESSION_CACHE_LIMIT = 50000
_session_cache: dict[str, tuple[str, float]] = {}


class ScreenActivityRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    timestamp: str
    app_name: str = Field(default="", alias="appName")
    window_title: str = Field(default="", alias="windowTitle")
    ocr_text: str = Field(default="", alias="ocrText")
    device_name: str | None = Field(default=None, alias="deviceName")
    client_device_id: str | None = Field(default=None, alias="clientDeviceId")
    embedding: list[float] | None = None

    def storage_id(self) -> str:
        return f"{self.client_device_id}-{self.id}" if self.client_device_id else str(self.id)


class ScreenActivitySyncRequest(BaseModel):
    rows: list[ScreenActivityRow]


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


def _empty_unread_response() -> dict[str, Any]:
    return {"unread_count": 0, "messages": []}


def _cached_session(email: str) -> str | None:
    value = _session_cache.get(email)
    if value and time.monotonic() - value[1] < _SESSION_CACHE_TTL:
        return value[0]
    _session_cache.pop(email, None)
    return None


def _cache_session(email: str, session_id: str) -> None:
    now = time.monotonic()
    _session_cache[email] = (session_id, now)
    expired = [key for key, (_, saved_at) in _session_cache.items() if now - saved_at >= _SESSION_CACHE_TTL]
    for key in expired:
        _session_cache.pop(key, None)
    if len(_session_cache) > _SESSION_CACHE_LIMIT:
        for key, _ in sorted(_session_cache.items(), key=lambda item: item[1][1])[
            : len(_session_cache) - _SESSION_CACHE_LIMIT
        ]:
            _session_cache.pop(key, None)


async def _crisp_get(url: str, headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.get(url, headers=headers)


async def _find_session(email: str, website_id: str, headers: dict[str, str]) -> str | None:
    for page in range(1, 6):
        response = await _crisp_get(f"https://api.crisp.chat/v1/website/{website_id}/conversations/{page}", headers)
        if not response.is_success:
            return None
        data = response.json().get("data") or []
        if not data:
            return None
        for conversation in data:
            candidate = (conversation.get("meta") or {}).get("email")
            if isinstance(candidate, str) and candidate.lower() == email:
                session_id = conversation.get("session_id")
                if isinstance(session_id, str):
                    return session_id
    return None


@router.post("/v1/screen-activity/sync")
async def sync_screen_activity(
    request: ScreenActivitySyncRequest, uid: str = Depends(_authorized_desktop_user)
) -> dict[str, int]:
    if len(request.rows) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 rows per batch")
    if not request.rows:
        return {"synced": 0, "last_id": 0}
    rows = [{**row.model_dump(by_alias=True), "storageId": row.storage_id()} for row in request.rows]
    try:
        written = await run_blocking(db_executor, upsert_screen_activity, uid, rows)
    except Exception as exc:
        logger.exception("Screen activity Firestore write failed for uid=%s", uid)
        raise HTTPException(status_code=500, detail="Firestore write failed") from exc
    embedded_rows = [row for row in rows if row.get("embedding")]
    if embedded_rows:
        try:
            await run_blocking(db_executor, upsert_screen_activity_vectors, uid, embedded_rows)
        except Exception:
            logger.exception("Screen activity vector write failed for uid=%s", uid)
    return {"synced": written, "last_id": max(row.id for row in request.rows)}


@router.get("/v1/crisp/unread")
async def get_crisp_unread(
    since: int = Query(default=0, ge=0), uid: str = Depends(get_current_user_uid)
) -> dict[str, Any]:
    identifier = os.getenv("CRISP_PLUGIN_IDENTIFIER")
    key = os.getenv("CRISP_PLUGIN_KEY")
    website_id = os.getenv("CRISP_WEBSITE_ID")
    if not identifier or not key or not website_id:
        return _empty_unread_response()
    try:
        user = await run_blocking(critical_executor, get_user, uid)
    except Exception:
        logger.exception("Crisp user lookup failed for uid=%s", uid)
        return _empty_unread_response()
    email = getattr(user, "email", None)
    if not isinstance(email, str) or not email:
        return _empty_unread_response()
    email = email.lower()
    auth = base64.b64encode(f"{identifier}:{key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "X-Crisp-Tier": "plugin"}
    try:
        session_id = _cached_session(email)
        if not session_id:
            session_id = await _find_session(email, website_id, headers)
            if session_id:
                _cache_session(email, session_id)
        if not session_id:
            return _empty_unread_response()
        response = await _crisp_get(
            f"https://api.crisp.chat/v1/website/{website_id}/conversation/{session_id}/messages", headers
        )
        if not response.is_success:
            return _empty_unread_response()
        messages = response.json().get("data") or []
        operator_messages = [
            {
                "text": content if isinstance(content, str) else json.dumps(content, separators=(",", ":")),
                "timestamp": timestamp,
                "from": "operator",
            }
            for message in messages
            if message.get("from") == "operator"
            and message.get("type") == "text"
            and isinstance((timestamp := message.get("timestamp")), int)
            and timestamp > since
            and (content := message.get("content")) is not None
        ]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        logger.exception("Crisp unread request failed for uid=%s", uid)
        raise HTTPException(status_code=502, detail="Crisp request failed") from None
    return {"unread_count": len(operator_messages), "messages": operator_messages}
