import requests
import templates as templates
from db import *
from fastapi import HTTPException, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models import Memory, EndpointResponse

from .client import get_notion

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
    return templates.TemplateResponse("setup_notion_crm.html", {
        "request": request, "uid": uid,
        "oauth_url": oauth_url,
        "error_message": err if err != "" else None,
    })


@router.get('/auth/notion/callback', response_class=HTMLResponse, tags=['notion'])
async def callback_auth_notion_crm(request: Request, state: str, code: str):
    """
    Callback from Notion Oauth.
    """

    uid = state

    # Get access token
    oauth_ok = get_notion().get_access_token(code)
    if "error" in oauth_ok:
        err = oauth_ok["error"]
        print(err)
        return response_setup_notion_crm_page(request, uid,
                                              f"Something went wrong. Please try again! \n (code: 400001)")

    oauth = oauth_ok["result"]

    # Validate access token
    access_token = oauth.access_token
    if oauth.access_token == "":
        return response_setup_notion_crm_page(request, uid,
                                              f"Something went wrong. Please try again! \n (code: 400002)")

    # Get database to create creds_notion_crm
    databases_ok = get_notion().get_databases_edited_time_desc(access_token)
    if "error" in databases_ok:
        err = databases_ok["error"]
        print(err)
        return response_setup_notion_crm_page(request, uid,
                                              f"Something went wrong. Please try again! \n (code: 400003)")

    # Pick top
    databases = databases_ok["result"]
    if len(databases) == 0 or databases[0].id == "":
        return response_setup_notion_crm_page(request, uid,
                                              f"There is no database. Please try again!  \n (code: 400004)")
    database_id = databases[0].id

    # Validate the database
    ok = validate_database(database_id, access_token)
    if not ok:
        # Follow response from validate function
        return

    # Save
    print({'uid': uid, 'api_key': access_token, 'database_id': database_id})
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
def notion_crm(memory: Memory, uid: str):
    """
    The actual plugin that gets triggered when a memory gets created, and adds the memory to the Notion CRM.
    """
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not setup properly. Check your plugin settings.'}

    create_notion_row(notion_api_key, get_notion_database_id(uid), memory)

    return {}


def validate_database(database_id: str, notion_api_key: str):
    # Validate table exists and has correct fields
    database_ok = get_notion().get_database(database_id, notion_api_key)
    if "error" in database_ok:
        err = database_ok["error"]
        raise HTTPException(status_code=400, detail=f"Something went wrong.\n{err}")

    # Use set to optimize exists validating
    property_set = set()
    for field in database_ok["result"].properties:
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


def create_notion_row(notion_api_key: str, database_id: str, memory: Memory):
    # Validate table exists and has correct fields
    ok = validate_database(database_id, notion_api_key)
    if not ok:
        # Follow response from validate function
        return

    try:
        emoji = memory.structured.emoji.encode('latin1').decode('utf-8')
    except UnicodeEncodeError:
        emoji = memory.structured.emoji

    data = {
        "parent": {"database_id": database_id},
        "icon": {
            "type": "emoji",
            "emoji": f"{emoji}"
        },
        "properties": {
            "Title": {"title": [{"text": {"content": f'{memory.structured.title}'}}]},
            "Speakers": {'number': len(set(map(lambda x: x.speaker, memory.transcript_segments)))},
            "Category": {"select": {"name": memory.structured.category}},
            "Duration (seconds)": {'number': (
                    memory.finished_at - memory.started_at).total_seconds() if memory.finished_at is not None else 0},
            "Overview": {"rich_text": [{"text": {"content": memory.structured.overview}}]},
        }
    }
    resp = requests.post('https://api.notion.com/v1/pages', json=data, headers={
        'Authorization': f'Bearer {notion_api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Notion-Version': '2022-06-28'
    })
    print('create_notion_row:', resp.status_code, resp.json())
    # TODO: after, write inside the page the transcript and everything else.
    return resp.status_code == 200
