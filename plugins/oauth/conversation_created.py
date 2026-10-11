import requests
import templates as templates
from db import *
from fastapi import HTTPException, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models import Conversation, EndpointResponse

try:
    from .client import get_notion, DEFAULT_TIMEOUT
except (ImportError, ValueError):
    from oauth.client import get_notion, DEFAULT_TIMEOUT

router = APIRouter()
# noinspection PyRedeclaration
templates = Jinja2Templates(directory="templates")


@router.get('/setup-notion-crm', response_class=HTMLResponse, tags=['notion'])
async def setup_notion_crm(request: Request, uid: str):
    """
    Simple setup page Form page for Notion CRM plugin.
    """
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    oauth_url = get_notion().get_oauth_url(uid)
    return templates.TemplateResponse("setup_notion_crm.html", {"request": request, "uid": uid, "oauth_url": oauth_url})


def response_setup_notion_crm_page(request: Request, uid: str, err: str):
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    oauth_url = get_notion().get_oauth_url(uid)
    return templates.TemplateResponse(
        "setup_notion_crm.html",
        {
            "request": request,
            "uid": uid,
            "oauth_url": oauth_url,
            "error_message": err if err != "" else None,
        },
    )


@router.get('/auth/notion/callback', response_class=HTMLResponse, tags=['notion'])
async def callback_auth_notion_crm(request: Request, state: str, code: str):
    """
    Callback from Notion Oauth.
    """

    uid = state

    # Get access token
    oauth_ok = get_notion().get_access_token(code)
    if not isinstance(oauth_ok, dict) or "error" in oauth_ok:
        err = oauth_ok.get("error", {}) if isinstance(oauth_ok, dict) else {}
        print(f"Error: HTTP_{err.get('status')}")
        return response_setup_notion_crm_page(
            request, uid, f"Something went wrong. Please try again! \n (code: 400001)"
        )

    oauth = oauth_ok.get("result")
    if not oauth or not hasattr(oauth, "access_token"):
        return response_setup_notion_crm_page(
            request, uid, f"Something went wrong. Please try again! \n (code: 400001)"
        )

    # Validate access token
    access_token = oauth.access_token
    if oauth.access_token == "":
        return response_setup_notion_crm_page(
            request, uid, f"Something went wrong. Please try again! \n (code: 400002)"
        )

    # Get database to create creds_notion_crm
    databases_ok = get_notion().get_databases_edited_time_desc(access_token)
    if not isinstance(databases_ok, dict) or "error" in databases_ok:
        err = databases_ok.get("error", {}) if isinstance(databases_ok, dict) else {}
        print(f"Error: HTTP_{err.get('status')}")
        return response_setup_notion_crm_page(
            request, uid, f"Something went wrong. Please try again! \n (code: 400003)"
        )

    # Pick top
    databases = databases_ok.get("result", [])
    if not isinstance(databases, list) or len(databases) == 0 or getattr(databases[0], "id", "") == "":
        return response_setup_notion_crm_page(
            request, uid, f"There is no database. Please try again!  \n (code: 400004)"
        )
    database_id = databases[0].id

    # Validate the database
    try:
        ok = validate_database(database_id, access_token)
        if not ok:
            return response_setup_notion_crm_page(
                request, uid, "Something went wrong. Please try again! \n (code: 400005)"
            )
    except HTTPException:
        return response_setup_notion_crm_page(
            request, uid, "Something went wrong. Please try again! \n (code: 400005)"
        )

    # Save
    store_notion_crm_api_key(uid, access_token)
    store_notion_database_id(uid, database_id)
    return templates.TemplateResponse("okpage.html", {"request": request, "uid": uid})


@router.get('/setup/notion-crm', tags=['notion'])
def is_setup_completed(uid: str):
    """
    Check if the user has setup the Notion CRM plugin.
    """
    notion_api_key = get_notion_crm_api_key(uid)
    notion_database_id = get_notion_database_id(uid)
    return {'is_setup_completed': notion_api_key is not None and notion_database_id is not None}


@router.post('/notion-crm', tags=['notion'], response_model=EndpointResponse)
def notion_crm(conversation: Conversation, uid: str):
    """
    The actual plugin that gets triggered when a conversation gets created, and adds the conversation to the Notion CRM.
    """
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not setup properly. Check your plugin settings.'}

    create_notion_row(notion_api_key, get_notion_database_id(uid), conversation)

    return {}


def validate_database(database_id: str, notion_api_key: str):
    # Validate table exists and has correct fields
    database_ok = get_notion().get_database(database_id, notion_api_key)
    if not isinstance(database_ok, dict) or "error" in database_ok:
        err = database_ok.get("error", {}) if isinstance(database_ok, dict) else {}
        raise HTTPException(status_code=400, detail=f"Something went wrong.\n{err}")

    result = database_ok.get("result")
    if not result or not hasattr(result, "properties") or not isinstance(result.properties, list):
        raise HTTPException(status_code=400, detail="Invalid database schema returned from Notion")

    # Use set to optimize exists validating
    property_set = set()
    for field in result.properties:
        if hasattr(field, "name") and field.name:
            property_set.add(field.name)

    # Collect all miss fields
    missing_fields = []
    for field in ["Title", "Speakers", "Category", "Duration (seconds)", "Overview"]:
        if field not in property_set:
            missing_fields.append(field)

    # If any missing, raise error
    if len(missing_fields) > 0:
        value = ", ".join(missing_fields)
        raise HTTPException(status_code=400, detail=f"Fields are missing: {value}")

    return True


def _build_notion_conversation_properties(conversation: Conversation) -> tuple[dict, str]:
    """Safely build Notion page properties and icon emoji from conversation."""
    structured = getattr(conversation, "structured", None)

    # Safe emoji extraction
    emoji = "🧠"
    if structured and getattr(structured, "emoji", None):
        try:
            emoji = structured.emoji.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
            emoji = str(structured.emoji)

    # Safe title
    conv_id = getattr(conversation, "id", None)
    if structured and getattr(structured, "title", None):
        title_text = str(structured.title)
    elif conv_id:
        title_text = f"Conversation {conv_id}"
    else:
        title_text = "Untitled Conversation"

    # Safe speaker count
    speakers_count = 0
    segments = getattr(conversation, "transcript_segments", None)
    if segments and isinstance(segments, list):
        valid_speakers = {
            s.speaker for s in segments if s and getattr(s, "speaker", None) is not None
        }
        speakers_count = len(valid_speakers)

    # Safe category
    category_name = "Other"
    if structured and getattr(structured, "category", None):
        category_name = str(structured.category)

    # Safe duration
    duration_seconds = 0
    started_at = getattr(conversation, "started_at", None)
    finished_at = getattr(conversation, "finished_at", None)
    if started_at is not None and finished_at is not None:
        try:
            delta = (finished_at - started_at).total_seconds()
            duration_seconds = max(0, int(delta))
        except (TypeError, AttributeError):
            duration_seconds = 0

    # Safe overview
    overview_text = ""
    if structured and getattr(structured, "overview", None):
        overview_text = str(structured.overview)

    properties = {
        "Title": {"title": [{"text": {"content": title_text}}]},
        "Speakers": {"number": speakers_count},
        "Category": {"select": {"name": category_name}},
        "Duration (seconds)": {"number": duration_seconds},
        "Overview": {"rich_text": [{"text": {"content": overview_text}}]},
    }
    return properties, emoji


def create_notion_row(
    notion_api_key: str,
    database_id: str,
    conversation: Conversation,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    # Validate table exists and has correct fields
    try:
        ok = validate_database(database_id, notion_api_key)
        if not ok:
            return False
    except HTTPException:
        return False
    except Exception:
        return False

    properties, emoji = _build_notion_conversation_properties(conversation)

    data = {
        "parent": {"database_id": database_id},
        "icon": {"type": "emoji", "emoji": emoji},
        "properties": properties,
    }
    try:
        resp = requests.post(
            'https://api.notion.com/v1/pages',
            json=data,
            headers={
                'Authorization': f'Bearer {notion_api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Notion-Version': '2022-06-28',
            },
            timeout=timeout,
        )
        print('create_notion_row:', resp.status_code)
        # TODO: after, write inside the page the transcript and everything else.
        return 200 <= resp.status_code < 300
    except requests.RequestException:
        return False
