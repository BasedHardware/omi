import hashlib
import hmac
import json
import os
from typing import Any

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

import database.action_items as action_items_db
from database import redis_db
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import get_webhook_client
from utils.other.endpoints import get_current_user_uid

router = APIRouter()

DESKTOP_BACKEND_VERSION = "0.1.0"
DESKTOP_BACKEND_SERVICE = "omi-desktop-backend"


def health_response() -> dict[str, str]:
    response = {
        "status": "healthy",
        "service": DESKTOP_BACKEND_SERVICE,
        "version": DESKTOP_BACKEND_VERSION,
    }
    for response_field, environment_name in (
        ("release_tag", "OMI_DESKTOP_RELEASE_TAG"),
        ("release_sha", "OMI_DESKTOP_RELEASE_SHA"),
        ("release_channel", "OMI_DESKTOP_RELEASE_CHANNEL"),
    ):
        value = os.getenv(environment_name)
        if value is not None:
            response[response_field] = value
    return response


def redis_readiness_response(configured: bool, probe: bool | Exception | None) -> tuple[int, dict[str, object]]:
    if not configured:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {
            "status": "not_ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "not_configured", "failure_class": "not_configured"},
        }
    if probe is True:
        return status.HTTP_200_OK, {
            "status": "ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "ready"},
        }
    if probe is False:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {
            "status": "not_ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "unexpected_response", "failure_class": "command_data"},
        }
    failure_class = "transport"
    if isinstance(probe, (redis.exceptions.AuthenticationError, redis.exceptions.AuthorizationError)):
        failure_class = "auth_config"
    elif isinstance(probe, (redis.exceptions.ResponseError, redis.exceptions.DataError)):
        failure_class = "command_data"
    return status.HTTP_503_SERVICE_UNAVAILABLE, {
        "status": "not_ready",
        "service": DESKTOP_BACKEND_SERVICE,
        "redis": {"status": "unavailable", "failure_class": failure_class},
    }


@router.get("/")
@router.get("/health")
def health_check() -> dict[str, str]:
    return health_response()


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    configured = bool(os.getenv("REDIS_DB_HOST"))
    probe: bool | Exception | None = None
    if configured:
        try:
            probe = await run_blocking(critical_executor, redis_db.r.ping)
        except redis.exceptions.RedisError as error:
            probe = error
    status_code, response = redis_readiness_response(configured, probe)
    return JSONResponse(status_code=status_code, content=response)


@router.get("/v1/config/api-keys")
def get_api_keys(_: str = Depends(get_current_user_uid)) -> dict[str, str]:
    return {
        response_field: value
        for response_field, environment_name in (
            ("firebase_api_key", "FIREBASE_API_KEY"),
            ("google_calendar_api_key", "GOOGLE_CALENDAR_API_KEY"),
            ("anthropic_api_key", "DESKTOP_LEGACY_ANTHROPIC_KEY"),
        )
        if (value := os.getenv(environment_name)) is not None
    }


@router.get("/.well-known/apple-developer-domain-association.txt", response_class=PlainTextResponse)
def apple_domain_association() -> str:
    return ""


def _sentry_signature_matches(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _sentry_issue_id(item: dict[str, Any]) -> str | None:
    if item.get("source") != "sentry_feedback":
        return None
    metadata = item.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            return None
    if isinstance(metadata, dict):
        issue_id = metadata.get("sentry_issue_id")
        return issue_id if isinstance(issue_id, str) else None
    return None


async def _sentry_items(uid: str) -> list[dict[str, Any]]:
    return await run_blocking(db_executor, action_items_db.get_action_items, uid, limit=500)


async def _sentry_event_details(issue_id: str) -> tuple[str, str, str, dict[str, Any]]:
    token = os.getenv("SENTRY_AUTH_TOKEN")
    if not token:
        return "", "", "", {}
    try:
        response = await get_webhook_client().get(
            f"https://sentry.io/api/0/issues/{issue_id}/events/latest/", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        event = response.json()
    except Exception:
        return "", "", "", {}
    if not isinstance(event, dict):
        return "", "", "", {}
    contexts = event.get("contexts") or event.get("context") or {}
    feedback = contexts.get("feedback") if isinstance(contexts, dict) else {}
    feedback = feedback if isinstance(feedback, dict) else {}
    message = feedback.get("message") if isinstance(feedback.get("message"), str) else ""
    name = feedback.get("name") if isinstance(feedback.get("name"), str) else ""
    email = feedback.get("contact_email") if isinstance(feedback.get("contact_email"), str) else ""
    if not email and isinstance(event.get("user"), dict):
        email = event["user"].get("email") if isinstance(event["user"].get("email"), str) else ""
    metadata: dict[str, Any] = {}
    if isinstance(event.get("tags"), list):
        metadata["tags"] = event["tags"]
    if isinstance(contexts, dict):
        metadata["contexts"] = contexts
    return message, name, email, metadata


async def _create_sentry_feedback(uid: str, issue: dict[str, Any], existing_ids: set[str], relevance_score: int) -> str:
    issue_id = issue.get("id")
    if not isinstance(issue_id, str) or not issue_id:
        return "ignored"
    if issue_id in existing_ids:
        return "duplicate"
    short_id = issue.get("shortId") if isinstance(issue.get("shortId"), str) else "unknown"
    title = issue.get("title") if isinstance(issue.get("title"), str) else ""
    message, name, email, event_metadata = await _sentry_event_details(issue_id)
    description = f"[Sentry Feedback] {short_id}: {message or title}".rstrip(": ")
    metadata: dict[str, Any] = {
        "sentry_issue_id": issue_id,
        "sentry_short_id": short_id,
        "sentry_url": f"https://mediar-n5.sentry.io/issues/{issue_id}/",
        "tags": ["bug"],
    }
    if name:
        metadata["reporter_name"] = name
    if email:
        metadata["reporter_email"] = email
    metadata.update(event_metadata)
    await run_blocking(
        db_executor,
        action_items_db.create_action_item,
        uid,
        {
            "description": description,
            "source": "sentry_feedback",
            "priority": "high",
            "metadata": metadata,
            "category": "bug",
            "relevance_score": relevance_score,
        },
        f"sentry-feedback:{issue_id}",
    )
    return "created"


@router.post("/v1/webhooks/sentry")
async def sentry_webhook(request: Request) -> dict[str, str]:
    if request.headers.get("sentry-hook-resource") == "installation":
        return {"status": "ok"}
    body = await request.body()
    secret = os.getenv("SENTRY_WEBHOOK_SECRET")
    if secret and not _sentry_signature_matches(secret, body, request.headers.get("sentry-hook-signature")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = await request.json()
        issue = payload["data"]["issue"]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    if not isinstance(payload, dict) or not isinstance(issue, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    if payload.get("action") != "created" or issue.get("issueCategory") != "feedback":
        return {"status": "ignored"}
    uid = os.getenv("SENTRY_ADMIN_UID")
    if not uid:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    items = await _sentry_items(uid)
    existing_ids = {issue_id for item in items if (issue_id := _sentry_issue_id(item))}
    score = max(1, round(max((item.get("relevance_score") or 0 for item in items), default=100) * 0.1))
    return {"status": await _create_sentry_feedback(uid, issue, existing_ids, score)}


def _sentry_poll_skip(reason: str, sentry_status: int | None = None) -> dict[str, object]:
    return {
        "status": "skipped",
        "reason": reason,
        "sentry_status": sentry_status,
        "created": 0,
        "skipped": 0,
        "total_fetched": 0,
    }


@router.post("/v1/webhooks/sentry/poll")
async def sentry_poll() -> dict[str, object]:
    uid = os.getenv("SENTRY_ADMIN_UID")
    token = os.getenv("SENTRY_AUTH_TOKEN")
    if not uid or not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    try:
        response = await get_webhook_client().get(
            "https://sentry.io/api/0/organizations/mediar-n5/issues/?query=issue.category:feedback&limit=25&sort=date",
            headers={"Authorization": f"Bearer {token}"},
        )
    except Exception:
        return _sentry_poll_skip("sentry_unreachable")
    if not response.is_success:
        reason = (
            "sentry_auth_error"
            if response.status_code in {401, 403}
            else "sentry_rate_limited" if response.status_code == 429 else "sentry_upstream_error"
        )
        return _sentry_poll_skip(reason, response.status_code)
    try:
        issues = response.json()
    except ValueError:
        return _sentry_poll_skip("sentry_bad_response")
    if not isinstance(issues, list):
        return _sentry_poll_skip("sentry_bad_response")
    items = await _sentry_items(uid)
    existing_ids = {issue_id for item in items if (issue_id := _sentry_issue_id(item))}
    score = max(1, round(max((item.get("relevance_score") or 0 for item in items), default=100) * 0.1))
    created = 0
    skipped = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        result = await _create_sentry_feedback(uid, issue, existing_ids, score)
        if result == "created":
            created += 1
            issue_id = issue.get("id")
            if isinstance(issue_id, str):
                existing_ids.add(issue_id)
        else:
            skipped += 1
    return {"status": "ok", "created": created, "skipped": skipped, "total_fetched": len(issues)}
