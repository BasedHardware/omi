from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from modal import Image, App, Secret, asgi_app, mount

import templates
from _mem0 import router as mem0_router
from _multion import router as multion_router
from advanced import openglass as openglass_router
from db import get_notion_crm_api_key, get_notion_database_id, store_notion_crm_api_key, store_notion_database_id, \
    clean_all_transcripts_except, append_segment_to_transcript, remove_transcript
from llm import news_checker
from models import Memory
from notion_utils import store_memoy_in_db

app = FastAPI()

modal_app = App(
    name='plugins_examples',
    secrets=[Secret.from_dotenv('.env')],
    mounts=[mount.Mount.from_local_dir('templates/', remote_path='templates/')]
)


@modal_app.function(
    image=Image.debian_slim().pip_install_from_requirements('requirements.txt'),
    keep_warm=1,  # need 7 for 1rps
    memory=(1024, 2048),
    cpu=4,
    allow_concurrent_inputs=10,
)
@asgi_app()
def plugins_app():
    return app


# **************************************************
# ************ On Memory Created Plugin ************
# **************************************************

# noinspection PyRedeclaration
templates = Jinja2Templates(directory="templates")


@app.get('/setup-notion-crm', response_class=HTMLResponse)
async def setup_notion_crm(request: Request, uid: str):
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    return templates.TemplateResponse("setup_notion_crm.html", {"request": request, "uid": uid})


@app.post('/creds/notion-crm', response_class=HTMLResponse)
def creds_notion_crm(request: Request, uid: str = Form(...), api_key: str = Form(...), database_id: str = Form(...)):
    if not api_key or not database_id:
        raise HTTPException(status_code=400, detail='API Key and Database ID are required')
    print({'uid': uid, 'api_key': api_key, 'database_id': database_id})
    store_notion_crm_api_key(uid, api_key)
    store_notion_database_id(uid, database_id)
    return templates.TemplateResponse("okpage.html", {"request": request, "uid": uid})


@app.get('/setup/notion-crm')
def is_setup_completed(uid: str):
    notion_api_key = get_notion_crm_api_key(uid)
    notion_database_id = get_notion_database_id(uid)
    return {'is_setup_completed': notion_api_key is not None and notion_database_id is not None}


@app.post('/notion-crm')
def notion_crm(memory: Memory, uid: str):
    print(memory.dict())
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not setup properly. Check your plugin settings.'}

    store_memoy_in_db(notion_api_key, get_notion_database_id(uid), memory)
    return {}


# ***********************************************
# ************ EXTERNAL INTEGRATIONS ************
# ***********************************************


app.include_router(multion_router.router)
app.include_router(mem0_router.router)
app.include_router(openglass_router.router)
