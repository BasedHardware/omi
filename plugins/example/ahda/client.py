from fastapi import APIRouter, Request, HTTPException, Form, Query, BackgroundTasks, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from db import get_ahda_url, store_ahda, get_ahda_os
import os
import requests
from models import RealtimePluginRequest, EndpointResponse
import time
import asyncio
import logging
from langchain_openai import ChatOpenAI

router = APIRouter()

active_sessions = {}

KEYWORD = "computer"
COMMAND_TIMEOUT = 5  # Seconds to wait after the last word to finalize the command

# Path to the directory containing `index.html`
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

chat = ChatOpenAI(model='gpt-4o', temperature=0)

# Use requests to get raw text from URL
prompt = requests.get("https://raw.githubusercontent.com/ActuallyAdvanced/OMI-AHDA/main/prompt.txt").text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AHDA Utils
def sendToPC(uid, response):
    ahda_url = get_ahda_url(uid)
    if not ahda_url:
        raise ValueError('AHDA URL not configured for this UID')
    payload = {
        'uid': uid,
        'response': response
    }
    try:
        resp = requests.post(ahda_url+"/recieve", json=payload)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error sending webhook: {e}")
        raise
    return {'message': 'Webhook sent successfully'}


@router.post('/ahda/send-webhook', tags=['ahda', 'realtime'])
async def send_ahda_webhook(
    uid: str = Query(...), 
    data: dict = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    segments = data.get("segments")
    if not uid:
        raise HTTPException(status_code=400, detail="UID is required")

    if not segments or not isinstance(segments, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    if uid not in active_sessions:
        logger.info(f"New session started: {uid}")
        active_sessions[uid] = {
            "command": "",
            "last_received_time": time.time(),
            "active": False,
            "timer": None
        }

    async def schedule_finalize_command(uid, delay):
        await asyncio.sleep(delay)
        await finalize_command(uid)

    async def finalize_command(uid):
        final_command = active_sessions[uid]["command"].strip()
        if final_command:
            logger.info(f"Final command for session {uid}: {final_command}")
            await call_chatgpt_to_generate_code(final_command, uid)
        active_sessions[uid]["command"] = ""
        active_sessions[uid]["active"] = False
        active_sessions[uid]["timer"] = None

    # Adjusted to handle segments as dictionaries
    for segment in segments:
        text = segment.get("text", "").strip().lower()
        logger.info(f"Received segment: {text} (session_id: {uid})")

        if KEYWORD in text:
            logger.info("Activation keyword detected!")
            active_sessions[uid]["active"] = True
            active_sessions[uid]["last_received_time"] = time.time()

            if active_sessions[uid]["timer"]:
                pass

            active_sessions[uid]["timer"] = background_tasks.add_task(
                schedule_finalize_command, uid, COMMAND_TIMEOUT
            )
            continue

        if active_sessions[uid]["active"]:
            active_sessions[uid]["command"] += " " + text
            active_sessions[uid]["last_received_time"] = time.time()
            logger.info(f"Aggregating command: {active_sessions[uid]['command'].strip()}")

            if active_sessions[uid]["timer"]:
                pass

            active_sessions[uid]["timer"] = background_tasks.add_task(
                schedule_finalize_command, uid, COMMAND_TIMEOUT
            )

    return {"status": "success"}


async def call_chatgpt_to_generate_code(command, uid):
    try:
        ahda_os = get_ahda_os(uid)
        messages = [
            ("system", prompt.replace("{os_name}",ahda_os)),
            ("human", command),
        ]
        ai_msg = chat.invoke(messages)
        sendToPC(uid, ai_msg)
    except Exception as e:
        logger.error(f"Error calling ChatGPT-4: {e}")
        return {"type": "error", "content": str(e)}

@router.get('/ahda/index', response_class=HTMLResponse, tags=['ahda'])
async def get_ahda_index(request: Request, uid: str = Query(None)):
    if not uid:
        raise HTTPException(status_code=400, detail="UID is required")
    return FileResponse(INDEX_PATH)

@router.post('/ahda/configure', tags=['ahda'])
def configure_ahda(uid: str = Form(...), url: str = Form(...), os: str = Form(...)):
    if not uid or not url:
        raise HTTPException(status_code=400, detail="Both UID, URL AND OS are required")

    store_ahda(uid, url, os)
    return {'message': 'AHDA configured successfully'}
