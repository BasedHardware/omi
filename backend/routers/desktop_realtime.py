import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictInt, StrictStr

from database._client import get_customer_firestore_client
from database import llm_usage as llm_usage_db
from utils.executors import db_executor, run_blocking
from utils.llm.realtime_usage import client_reported_cost_usd, client_reported_turn
from utils.other.endpoints import get_current_user_uid
from utils.subscription import enforce_desktop_chat_quota

router = APIRouter()
logger = logging.getLogger(__name__)

_OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
# Leftover AI Studio Live token mint. Vertex Live is not wired here; this is
# not the $1k/day Flash text bill. See backend/docs/vertex-pt-flash.md.
_GEMINI_AUTH_TOKENS_URL = "https://generativelanguage.googleapis.com/v1alpha/auth_tokens"
_OPENAI_REALTIME_MODEL = "gpt-realtime-2"
_GEMINI_LIVE_MODEL = "models/gemini-3.1-flash-live-preview"
_SESSION_START_WINDOW_MIN = 2
_SESSION_MAX_MIN = 30


class MintRequest(BaseModel):
    provider: StrictStr


class UsageReport(BaseModel):
    provider: StrictStr
    model: StrictStr = ""
    # A stable client turn id makes the quota question idempotent (a retried
    # report counts once). Absent on older clients, whose reports keep the
    # historical non-idempotent increment.
    turn_id: StrictStr = ""
    input_text_tokens: StrictInt = 0
    input_audio_tokens: StrictInt = 0
    input_cached_tokens: StrictInt = 0
    output_text_tokens: StrictInt = 0
    output_audio_tokens: StrictInt = 0
    context_plan_id: StrictStr = ""
    stable_cache_identity: StrictStr = ""
    dynamic_context_identity: StrictStr = ""
    context_cache_replaced: bool = False


def _error(
    status_code: int,
    reason: str,
    message: str,
    provider: str | None = None,
    code: str | None = None,
    upstream_status_code: int | None = None,
    retryable: bool = False,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": message,
        "reason": reason,
        "backend_route": "/v2/realtime/session",
        "retryable": retryable,
    }
    if provider is not None:
        body["provider"] = provider
    if code is not None:
        body["code"] = code
    if upstream_status_code is not None:
        body["upstream_status_code"] = upstream_status_code
    return JSONResponse(status_code=status_code, content=body)


def _upstream_error(provider: str, status_code: int, body: str) -> JSONResponse:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {}
    error = parsed.get("error") if isinstance(parsed, dict) else None
    error = error if isinstance(error, dict) else {}
    code_value = error.get("code") or error.get("status") or (parsed.get("code") if isinstance(parsed, dict) else None)
    code = str(code_value) if isinstance(code_value, (str, int, float)) and str(code_value) else None
    message_value = error.get("message") or (parsed.get("message") if isinstance(parsed, dict) else None)
    message = message_value if isinstance(message_value, str) else body[:500]
    lower = f"{code or ''} {message}".lower()
    if status_code == 429 or "quota" in lower:
        reason = "provider_quota_exceeded"
    elif status_code in (401, 403) or any(
        value in lower for value in ("invalid api key", "api key not valid", "authentication", "permission denied")
    ):
        reason = "provider_auth_failed"
    elif status_code >= 500:
        reason = "provider_mint_unavailable"
    else:
        reason = "provider_mint_rejected"
    return _error(status_code, reason, message, provider, code, status_code, status_code == 429 or status_code >= 500)


async def _post_json(
    url: str, provider: str, headers: dict[str, str], body: dict[str, Any], params: dict[str, str] | None = None
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0)) as client:
            response = await client.post(url, headers=headers, json=body, params=params)
    except httpx.HTTPError as error:
        return None, _error(502, "provider_mint_transport_error", str(error), retryable=True)
    if not response.is_success:
        return None, _upstream_error(provider, response.status_code, response.text)
    try:
        data = response.json()
    except json.JSONDecodeError as error:
        return None, _error(502, "provider_mint_transport_error", str(error), retryable=True)
    if not isinstance(data, dict):
        return None, _error(
            502, "provider_mint_transport_error", "provider mint response was not an object", retryable=True
        )
    return data, None


def _record_session(uid: str, token: str, provider: str, model: str, expires_at: str) -> None:
    get_customer_firestore_client().collection("users").document(uid).collection("realtime_sessions").document(
        hashlib.sha256(token.encode()).hexdigest()
    ).set(
        {
            "provider": provider,
            "model": model,
            "status": "minted",
            "minted_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "max_minutes": _SESSION_MAX_MIN,
        }
    )


async def _persist_session(uid: str, token: str, provider: str, model: str, expires_at: str) -> None:
    try:
        await run_blocking(db_executor, _record_session, uid, token, provider, model, expires_at)
    except Exception:
        logger.warning("realtime session-record write failed for uid=%s", uid)


@router.post("/v2/realtime/session")
async def mint_session(request: MintRequest, uid: str = Depends(get_current_user_uid)) -> JSONResponse:
    # The hub only ever mints Omi's own provider token, so a user's BYOK key
    # (Anthropic, for desktop chat) must not exempt them from the cap here.
    await run_blocking(db_executor, enforce_desktop_chat_quota, uid, "desktop", byok_exempt=False)
    if request.provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            return _error(503, "provider_not_configured", "OpenAI realtime is not configured", "OpenAI", retryable=True)
        data, error = await _post_json(
            _OPENAI_CLIENT_SECRETS_URL,
            "openai",
            {"Authorization": f"Bearer {key}"},
            {"session": {"type": "realtime", "model": _OPENAI_REALTIME_MODEL}},
        )
        if error:
            return error
        token = data.get("value") if data else None
        if not isinstance(token, str):
            return _error(
                502, "provider_mint_transport_error", "openai mint: no client secret in response", retryable=True
            )
        expires_at = json.dumps(data["expires_at"], separators=(",", ":")) if data and "expires_at" in data else None
        await _persist_session(uid, token, "openai", _OPENAI_REALTIME_MODEL, expires_at or "")
        return JSONResponse(
            {"provider": "openai", "token": token, **({"expires_at": expires_at} if expires_at is not None else {})}
        )
    if request.provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return _error(503, "provider_not_configured", "Gemini realtime is not configured", "Gemini", retryable=True)
        now = datetime.now(timezone.utc)
        start = (now + timedelta(minutes=_SESSION_START_WINDOW_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
        expires_at = (now + timedelta(minutes=_SESSION_MAX_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data, error = await _post_json(
            _GEMINI_AUTH_TOKENS_URL,
            "gemini",
            {},
            {"uses": 1, "expireTime": expires_at, "newSessionExpireTime": start},
            {"key": key},
        )
        if error:
            return error
        token = data.get("name") if data else None
        if not isinstance(token, str):
            return _error(
                502, "provider_mint_transport_error", "gemini mint: no token name in response", retryable=True
            )
        await _persist_session(uid, token, "gemini", _GEMINI_LIVE_MODEL, expires_at)
        return JSONResponse({"provider": "gemini", "token": token, "expires_at": expires_at})
    return _error(400, "bad_provider", 'provider must be "openai" or "gemini"')


REALTIME_HUB_TURN_QUOTA_SOURCE = 'desktop_realtime_turn'


def _record_usage(
    uid: str,
    report: UsageReport,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    total_tokens: int,
    cost: float,
) -> None:
    client = get_customer_firestore_client()
    if report.turn_id:
        # One question per client turn, exactly once: the same idempotent
        # writer text chat uses, keyed on the client's turn id, with the token
        # cost in the SAME transaction. A retried report finds the event and
        # records nothing; a failed write records nothing of either.
        def telemetry(plan_key: str, day: str) -> dict[str, Any]:
            return llm_usage_db.usage_bucket_update(
                uid,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cached_tokens,
                cache_write_tokens=0,
                total_tokens=total_tokens,
                cost_usd=cost,
                bucket='desktop_chat',
                account='desktop_chat_realtime',
                cost_status='complete',
                quota_questions=0,
                plan_key=plan_key,
                today=day,
            )

        llm_usage_db.record_chat_quota_question(
            uid,
            f'realtime_hub:{report.turn_id}',
            REALTIME_HUB_TURN_QUOTA_SOURCE,
            platform='desktop',
            firestore_client=client,
            usage_update_for=telemetry,
        )
        return
    llm_usage_db.record_llm_usage_bucket(
        uid,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cached_tokens,
        cache_write_tokens=0,
        total_tokens=total_tokens,
        cost_usd=cost,
        bucket='desktop_chat',
        account='desktop_chat_realtime',
        cost_status='complete',
        quota_questions=1,
        firestore_client=client,
    )


def _usage_cost(report: UsageReport) -> float:
    # One rate table for every realtime route: the relay prices the turns it
    # observes on the wire with the same module (utils/llm/realtime_usage.py).
    # The client cannot choose the rate card: mint_session issued one fixed
    # model per provider and only that server-selected model is authoritative.
    turn = client_reported_turn(
        report.provider,
        input_text_tokens=report.input_text_tokens,
        input_audio_tokens=report.input_audio_tokens,
        input_cached_tokens=report.input_cached_tokens,
        output_text_tokens=report.output_text_tokens,
        output_audio_tokens=report.output_audio_tokens,
    )
    issued_model = _OPENAI_REALTIME_MODEL if report.provider == 'openai' else _GEMINI_LIVE_MODEL
    return client_reported_cost_usd(report.provider, issued_model, turn)


@router.post("/v2/realtime/usage", status_code=204)
async def report_usage(report: UsageReport, uid: str = Depends(get_current_user_uid)) -> Response:
    await run_blocking(db_executor, enforce_desktop_chat_quota, uid, "desktop", byok_exempt=False)
    input_tokens = max(report.input_text_tokens, 0) + max(report.input_audio_tokens, 0)
    output_tokens = max(report.output_text_tokens, 0) + max(report.output_audio_tokens, 0)
    cached_tokens = max(report.input_cached_tokens, 0)
    total_tokens = input_tokens + output_tokens + cached_tokens
    if total_tokens <= 0:
        return Response(status_code=204)
    try:
        await run_blocking(
            db_executor,
            _record_usage,
            uid,
            report,
            input_tokens,
            output_tokens,
            cached_tokens,
            total_tokens,
            _usage_cost(report),
        )
    except Exception:
        logger.error("realtime usage record failed for uid=%s", uid)
        return Response(status_code=502)
    return Response(status_code=204)
