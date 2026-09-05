import hmac
import logging
import os
import secrets
from typing import Optional
from fastapi import APIRouter, Cookie, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import firebase_admin.auth
import httpx

from database.apps import get_app_by_id_db
from utils.executors import critical_executor, db_executor, run_blocking
from utils.other.endpoints import enforce_account_deletion_http_access
from utils.http_client import safe_request_target, get_auth_client, UnsafeWebhookURLError
from database.redis_db import enable_app, increase_app_installs_count
from utils.apps import is_user_app_enabled, get_is_user_paid_app, is_tester
from utils.jit_qa_admission import JITQAAdmissionError, enforce_jit_qa_uid
from models.app import App as AppModel, ActionType

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["oauth"],
)


class OAuthTokenResponse(BaseModel):
    """OAuth token-exchange response for app integrations."""

    uid: str = Field(description='Authenticated user UID.')
    redirect_url: str = Field(description='URL to redirect the user back to the app.')
    state: Optional[str] = Field(
        default=None, description='Opaque state value passed through from the authorize request.'
    )


# Ensure the templates directory exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Double-submit CSRF protection for the authorize -> token exchange: /authorize
# hands the browser the same random value two ways (an HttpOnly SameSite=Strict
# cookie it never has to read, and a value embedded directly in the page it
# loaded), and /token requires both to match. A cross-site page cannot forge
# this — it has no way to read or set the cookie for our origin, and
# SameSite=Strict keeps the cookie from being attached to a cross-site request
# in the first place. This closes the "state accepted but never validated
# server-side" gap without depending on the third-party app's own `state`
# handling, which Omi's server has no way to verify.
OAUTH_CSRF_COOKIE_NAME = 'omi_oauth_csrf'


@router.get("/v1/oauth/authorize", response_class=HTMLResponse)
def oauth_authorize(
    request: Request,
    app_id: str,
    state: Optional[str] = None,
):
    app_data = get_app_by_id_db(app_id)
    if not app_data:
        raise HTTPException(status_code=404, detail="App not found")

    app = AppModel(**app_data)

    if not app.external_integration:
        raise HTTPException(status_code=400, detail="App does not support external integration")

    if not app.external_integration.app_home_url:
        raise HTTPException(status_code=400, detail="App home URL not configured for this app.")

    # Prepare permission strings
    permissions = []
    if app.capabilities:
        if "chat" in app.capabilities:
            permissions.append({"icon": "💬", "text": "Engage in chat conversations with Omi."})
        if "memories" in app.capabilities:
            permissions.append({"icon": "📝", "text": "Access and manage your conversations."})

        if "external_integration" in app.capabilities and app.external_integration:
            if app.external_integration.triggers_on == 'audio_bytes':
                permissions.append({"icon": "🎤", "text": "Process audio data in real-time."})
            elif app.external_integration.triggers_on == 'memory_creation':
                permissions.append({"icon": "🔔", "text": "Trigger actions when new conversations are created."})
            elif app.external_integration.triggers_on == 'transcript_processed':
                permissions.append({"icon": "🎧", "text": "Trigger actions when live transcripts are processed."})

            if app.external_integration.actions:
                for action_item in app.external_integration.actions:
                    action_type_value = action_item.action.value
                    if action_type_value == ActionType.CREATE_MEMORY.value:
                        permissions.append({"icon": "✍️", "text": "Create new conversations on your behalf."})
                    elif action_type_value == ActionType.CREATE_FACTS.value:
                        permissions.append({"icon": "➕", "text": "Create new memories for you."})
                    elif action_type_value == ActionType.READ_CONVERSATIONS.value:
                        permissions.append({"icon": "📖", "text": "Access and read your conversation history."})
                    elif action_type_value == ActionType.READ_MEMORIES.value:
                        permissions.append({"icon": "🔍", "text": "Access and read your stored memories."})
                    elif action_type_value == ActionType.READ_TASKS.value:
                        permissions.append({"icon": "📋", "text": "Access and read your stored tasks."})
        if (
            "proactive_notification" in app.capabilities
            and app.proactive_notification
            and app.proactive_notification.scopes
        ):
            if "user_name" in app.proactive_notification.scopes:
                permissions.append({"icon": "📛", "text": "Access your user name for notifications."})
            if "user_facts" in app.proactive_notification.scopes:
                permissions.append({"icon": "💡", "text": "Access your facts for notifications."})
            if "user_context" in app.proactive_notification.scopes:
                permissions.append({"icon": "📜", "text": "Access your conversation context for notifications."})
            if "user_chat" in app.proactive_notification.scopes:
                permissions.append({"icon": "🗣️", "text": "Access your chat history for notifications."})

    if not permissions:
        permissions.append({"icon": "✅", "text": "Access your basic Omi profile information."})

    # Remove duplicate permissions (based on text)
    unique_permissions = []
    seen_texts = set()
    for perm in permissions:
        if perm["text"] not in seen_texts:
            unique_permissions.append(perm)
            seen_texts.add(perm["text"])
    permissions = unique_permissions

    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request,
        "oauth_authenticate.html",
        {
            "app_id": app_id,
            "app_name": app.name,
            "app_image": app.image,
            "state": state,
            "csrf_token": csrf_token,
            "permissions": permissions,
            "firebase_api_key": os.getenv("FIREBASE_API_KEY"),
            "firebase_auth_domain": os.getenv("FIREBASE_AUTH_DOMAIN"),
            "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID"),
        },
    )
    response.set_cookie(
        OAUTH_CSRF_COOKIE_NAME,
        csrf_token,
        max_age=600,
        httponly=True,
        secure=True,
        samesite='strict',
    )
    return response


def _setup_completed_from_payload(payload: object) -> bool:
    """Read `is_setup_completed` from a third-party setup_completed_url body.

    Mirrors `routers.apps._setup_completed_from_response`: the body is
    developer-controlled, so a JSON scalar or array is as likely as the documented
    object. Anything that is not an object carrying a truthy `is_setup_completed`
    means setup is not completed. A non-JSON body still raises ValueError out of
    `res.json()` and is answered with the 503 below.
    """
    return isinstance(payload, dict) and bool(payload.get('is_setup_completed', False))


@router.post("/v1/oauth/token", response_model=OAuthTokenResponse)
async def oauth_token(
    firebase_id_token: str = Form(...),
    app_id: str = Form(...),
    state: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    oauth_csrf_cookie: Optional[str] = Cookie(default=None, alias=OAUTH_CSRF_COOKIE_NAME),
):
    if not oauth_csrf_cookie or not hmac.compare_digest(csrf_token, oauth_csrf_cookie):
        raise HTTPException(
            status_code=403,
            detail='This authorization request is invalid or expired. Please restart the connection from the app.',
        )
    try:
        decoded_token = await run_blocking(
            critical_executor,
            firebase_admin.auth.verify_id_token,
            firebase_id_token,
        )
        uid = decoded_token['uid']
    except firebase_admin.auth.InvalidIdTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase ID token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error verifying Firebase ID token: {e}")

    try:
        enforce_jit_qa_uid(uid)
    except JITQAAdmissionError as error:
        raise HTTPException(status_code=403, detail="account is not admitted to the isolated JIT QA plane") from error
    await run_blocking(db_executor, enforce_account_deletion_http_access, uid)

    app_data = await run_blocking(db_executor, get_app_by_id_db, app_id)
    if not app_data:
        raise HTTPException(status_code=404, detail="App not found")

    app = AppModel(**app_data)

    if not app.external_integration or not app.external_integration.app_home_url:
        raise HTTPException(status_code=400, detail="App not configured for OAuth or app home URL not set")

    # Validate if the user has enabled this app, if not, try to enable it automatically
    if not await run_blocking(db_executor, is_user_app_enabled, uid, app_id):
        if app.private is not None:
            if app.private and app.uid != uid and not await run_blocking(db_executor, is_tester, uid):
                raise HTTPException(
                    status_code=403, detail="This app is private and you are not authorized to enable it."
                )

        # Check Setup completes
        if app.works_externally() and app.external_integration.setup_completed_url:
            try:
                pinned_url, pin_kwargs = await run_blocking(
                    db_executor, safe_request_target, app.external_integration.setup_completed_url
                )
                client = get_auth_client()
                res = await client.get(
                    pinned_url + f'?uid={uid}',
                    headers=pin_kwargs['headers'],
                    extensions=pin_kwargs['extensions'],
                    follow_redirects=False,
                )
                res.raise_for_status()
                if not _setup_completed_from_payload(res.json()):
                    raise HTTPException(
                        status_code=400,
                        detail='App setup is not completed. Please complete app setup before authorizing.',
                    )
            except UnsafeWebhookURLError as e:
                logger.warning(f'Rejected setup_completed_url for app {app_id}: {e}')
                raise HTTPException(
                    status_code=400,
                    detail='This app is misconfigured (setup URL is not a public address). Please contact the app developer.',
                )
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                raise HTTPException(
                    status_code=503,
                    detail=f'Failed to verify app setup completion. Please try again later or contact support.',
                )
            except ValueError:
                raise HTTPException(
                    status_code=503,
                    detail='Could not verify app setup due to an invalid response from the app. Please contact app developer or support.',
                )

        # Check payment status
        if app.is_paid and not await run_blocking(db_executor, get_is_user_paid_app, app.id, uid):
            raise HTTPException(
                status_code=403, detail='This is a paid app. Please purchase the app before authorizing.'
            )

        try:
            await run_blocking(db_executor, enable_app, uid, app_id)
            if (
                (app.private is None or not app.private)
                and (app.uid is None or app.uid != uid)
                and not await run_blocking(db_executor, is_tester, uid)
            ):
                await run_blocking(db_executor, increase_app_installs_count, app_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Could not automatically enable the app. Please try again or enable it manually.",
            )

    redirect_url = app.external_integration.app_home_url

    return {"uid": uid, "redirect_url": redirect_url, "state": state}
