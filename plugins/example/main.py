import os
from typing import List

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from modal import Image, App, Secret, asgi_app, mount
from multion.client import MultiOn

from db import get_notion_crm_api_key, get_notion_database_id, store_notion_crm_api_key, store_notion_database_id
from llm import retrieve_books_to_buy, news_checker
from models import Memory
from notion_utils import store_memoy_in_db
import templates

app = FastAPI()

modal_app = App(
    name='plugins_examples',
    secrets=[Secret.from_dotenv('.env')],
    mounts=[
        mount.Mount.from_local_dir('templates/', remote_path='templates/'),
    ]
)

multion = MultiOn(api_key=os.getenv('MULTION_API_KEY', '123'))


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


def call_multion(books: List[str]):
    print('Buying books with MultiOn')
    response = multion.browse(
        cmd=f"Add to my cart the following books (in paperback version, or any physical version): {books}",
        url="https://amazon.com",
        local=True,
    )
    return response.message


# *****************************************
# ************ Webhook Example ************
# *****************************************

@app.post("/webhook")
def webhook1(memory: Memory):
    # ONLY WORKS locally ~ multion amazon is not yet available with local=False
    # when that happens this could be a plugin
    if memory.transcript == '':
        return {'message': ''}
    books = retrieve_books_to_buy(memory)
    if books:
        return {'message': call_multion(books)}
    return {'message': ''}


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


@app.post('/creds/notion-crm')
def creds_notion_crm(uid: str = Form(...), api_key: str = Form(...), database_id: str = Form(...)):
    if not api_key or not database_id:
        raise HTTPException(status_code=400, detail='API Key and Database ID are required')
    print({'uid': uid, 'api_key': api_key, 'database_id': database_id})
    store_notion_crm_api_key(uid, api_key)
    store_notion_database_id(uid, database_id)
    return {'status': 'ok'}


@app.post('/notion-crm')
def notion_crm(memory: Memory, uid: str):
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not enabled. Please enable it in the settings.'}

    store_memoy_in_db(notion_api_key, get_notion_database_id(uid), memory)
    return {}


# *******************************************************
# ************ On Transcript Received Plugin ************
# *******************************************************


@app.post('/news-checker')
def news_checker_endpoint(uid: str, data: dict):
    session_id = data['session_id']  # use session id in case your plugin needs the whole conversation context
    segments = data['segments']
    # This is an example, probably not production ready, is interesting anyway.
    # clean_all_transcripts_except(uid, session_id)
    # transcript: list[dict] = append_segment_to_transcript(uid, session_id, new_segments)
    return {'message': news_checker(segments)}
