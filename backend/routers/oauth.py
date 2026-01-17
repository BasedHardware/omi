import os
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import firebase_admin.auth
import requests

from database.apps import get_app_by_id_db
from database.redis_db import enable_app, increase_app_installs_count
from utils.apps import is_user_app_enabled, get_is_user_paid_app, is_tester
from models.app import App as AppModel, ActionType

router = APIRouter(
    tags=["oauth"],
)

# Ensure the templates directory exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@router.get("/v1/oauth/authorize", response_class=HTMLResponse)
async def oauth_authorize(
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

    return templates.TemplateResponse(
        "oauth_authenticate.html",
        {
            "request": request,
            "app_id": app_id,
            "app_name": app.name,
            "app_image": app.image,
            "state": state,
            "permissions": permissions,
            "firebase_api_key": os.getenv("FIREBASE_API_KEY"),
            "firebase_auth_domain": os.getenv("FIREBASE_AUTH_DOMAIN"),
            "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID"),
        },
    )


@router.post("/v1/oauth/token")
async def oauth_token(firebase_id_token: str = Form(...), app_id: str = Form(...), state: Optional[str] = Form(None)):
    try:
        decoded_token = firebase_admin.auth.verify_id_token(firebase_id_token)
        uid = decoded_token['uid']
    except firebase_admin.auth.InvalidIdTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase ID token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error verifying Firebase ID token: {e}")

    app_data = get_app_by_id_db(app_id)
    if not app_data:
        raise HTTPException(status_code=404, detail="App not found")

    app = AppModel(**app_data)

    if not app.external_integration or not app.external_integration.app_home_url:
        raise HTTPException(status_code=400, detail="App not configured for OAuth or app home URL not set")

    # Validate if the user has enabled this app, if not, try to enable it automatically
    if not is_user_app_enabled(uid, app_id):
        if app.private is not None:
            if app.private and app.uid != uid and not is_tester(uid):
                raise HTTPException(
                    status_code=403, detail="This app is private and you are not authorized to enable it."
                )

        # Check Setup completes
        if app.works_externally() and app.external_integration.setup_completed_url:
            try:
                res = requests.get(app.external_integration.setup_completed_url + f'?uid={uid}')
                res.raise_for_status()
                if not res.json().get('is_setup_completed', False):
                    raise HTTPException(
                        status_code=400,
                        detail='App setup is not completed. Please complete app setup before authorizing.',
                    )
            except requests.RequestException as e:
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
        if app.is_paid and not get_is_user_paid_app(app.id, uid):
            raise HTTPException(
                status_code=403, detail='This is a paid app. Please purchase the app before authorizing.'
            )

        try:
            enable_app(uid, app_id)
            if (app.private is None or not app.private) and (app.uid is None or app.uid != uid) and not is_tester(uid):
                increase_app_installs_count(app_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Could not automatically enable the app. Please try again or enable it manually.",
            )

    redirect_url = app.external_integration.app_home_url

    return {"uid": uid, "redirect_url": redirect_url, "state": state}
