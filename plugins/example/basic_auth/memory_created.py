import requests
from fastapi import HTTPException, Request, Form, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import templates as templates
from db import *
from models import Memory

router = APIRouter()
# noinspection PyRedeclaration
templates = Jinja2Templates(directory="templates")


@router.get('/setup-notion-crm', response_class=HTMLResponse, tags=['basic_auth'])
async def setup_notion_crm(request: Request, uid: str):
    """
    Simple setup page Form page for Notion CRM plugin.
    """
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    return templates.TemplateResponse("setup_notion_crm.html", {"request": request, "uid": uid})


@router.post('/creds/notion-crm', response_class=HTMLResponse, tags=['basic_auth'])
def creds_notion_crm(request: Request, uid: str = Form(...), api_key: str = Form(...), database_id: str = Form(...)):
    """
    Store the Notion CRM API Key and Database ID in redis "authenticate the user".
    This endpoint gets called from /setup-notion-crm page.
    Parameters
    ----------
    request: Request -> FastAPI Request object
    uid: str -> User ID from the query parameter
    api_key: str -> Notion Integration created API key.
    database_id: str -> Notion Database ID where the data will be stored.

    """
    if not api_key or not database_id:
        raise HTTPException(status_code=400, detail='API Key and Database ID are required')
    print({'uid': uid, 'api_key': api_key, 'database_id': database_id})
    store_notion_crm_api_key(uid, api_key)
    store_notion_database_id(uid, database_id)
    return templates.TemplateResponse("okpage.html", {"request": request, "uid": uid})


@router.get('/setup/notion-crm', tags=['basic_auth'])
def is_setup_completed(uid: str):
    """
    Check if the user has setup the Notion CRM plugin.
    """
    notion_api_key = get_notion_crm_api_key(uid)
    notion_database_id = get_notion_database_id(uid)
    return {'is_setup_completed': notion_api_key is not None and notion_database_id is not None}


@router.post('/notion-crm', tags=['basic_auth', 'memory_created'])
def notion_crm(memory: Memory, uid: str):
    """
    The actual plugin that gets triggered when a memory gets created, and adds the memory to the Notion CRM.
    """
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not setup properly. Check your plugin settings.'}

    create_notion_row(notion_api_key, get_notion_database_id(uid), memory)
    return {}


def create_notion_row(notion_api_key: str, database_id: str, memory: Memory):
    # TODO: validate table exists and has correct fields
    data = {
        "parent": {"database_id": database_id},
        "icon": {
            "type": "emoji",
            "emoji": f"{memory.structured.emoji.encode('latin1').decode('utf-8')}"
        },
        "properties": {
            "Title": {"title": [{"text": {"content": f'{memory.structured.title}'}}]},
            "Category": {"select": {"name": memory.structured.category}},
            "Overview": {"rich_text": [{"text": {"content": memory.structured.overview}}]},
            "Speakers": {'number': len(set(map(lambda x: x.speaker, memory.transcriptSegments)))},
            "Duration (seconds)": {'number': (
                    memory.finishedAt - memory.startedAt).total_seconds() if memory.finishedAt is not None else 0},
        }
    }
    resp = requests.post('https://api.notion.com/v1/pages', json=data, headers={
        'Authorization': f'Bearer {notion_api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Notion-Version': '2022-06-28'
    })
    print(resp.json())
    # TODO: after, write inside the page the transcript and everything else.
    return resp.status_code == 200
