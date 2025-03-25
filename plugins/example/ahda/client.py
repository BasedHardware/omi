from fastapi import APIRouter, HTTPException, Query, Body, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
import os
import requests
import asyncio
import logging
from langchain_openai import ChatOpenAI
from db import get_ahda_url, get_ahda_os, store_ahda

router = APIRouter()

active_sessions = {}

KEYWORD = "computer"
COMMAND_TIMEOUT = 8  # Seconds to wait after the last word to finalize the command

# Path to the directory containing `index.html`
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

from models import EndpointResponse

chat = ChatOpenAI(model='gpt-4o', temperature=0)

# Use requests to get raw text from URL
prompt = requests.get("https://raw.githubusercontent.com/ActuallyAdvanced/OMI-AHDA/main/prompt.txt").text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AHDA Utils
def send_to_pc(uid, response):
    ahda_url = get_ahda_url(uid)
    if not ahda_url:
        raise ValueError('AHDA URL not configured for this UID')
    payload = {
        'uid': uid,
        'response': response
    }
    try:
        resp = requests.post(ahda_url + "/receive", json=payload)
        resp.raise_for_status()
        return {'message': 'Webhook sent successfully'}
    except requests.RequestException as e:
        send_debug_to_pc(uid, f"Error sending webhook: {e}")
        logger.error(f"Error sending webhook: {e}")
        return {'message': f'Failed to send webhook: {e}'}

def send_live_transcript_to_pc(uid, response):
    ahda_url = get_ahda_url(uid)
    if not ahda_url:
        raise ValueError('AHDA URL not configured for this UID')
    payload = {
        'uid': uid,
        'response': response
    }
    try:
        resp = requests.post(ahda_url + "/transcript", json=payload)
        resp.raise_for_status()
        return {'message': 'Webhook sent successfully'}
    except requests.RequestException as e:
        logger.error(f"Error sending webhook: {e}")
        return {'message': f'Failed to send webhook: {e}'}

def send_debug_to_pc(uid, response):
    ahda_url = get_ahda_url(uid)
    if not ahda_url:
        raise ValueError('AHDA URL not configured for this UID')
    payload = {
        'uid': uid,
        'response': response
    }
    try:
        resp = requests.post(ahda_url + "/debug", json=payload)
        resp.raise_for_status()
        return {'message': 'Webhook sent successfully'}
    except requests.RequestException as e:
        logger.error(f"Error sending webhook: {e}")
        return {'message': f'Failed to send webhook: {e}'}

@router.post('/ahda/send-webhook', tags=['ahda', 'realtime'], response_model=EndpointResponse)
async def send_ahda_webhook(
    uid: str = Query(...), 
    data: dict = Body(...),
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
            "last_received_time": asyncio.get_event_loop().time(),
            "active": False,
            "timer": None
        }

    async def schedule_finalize_command(uid, delay):
        try:
            await asyncio.sleep(delay)
            if asyncio.get_event_loop().time() - active_sessions[uid]["last_received_time"] >= delay:
                await finalize_command(uid)
        except asyncio.CancelledError:
            logger.info(f"Timer for session {uid} was cancelled")

    async def finalize_command(uid):
        final_command = active_sessions[uid]["command"].strip()
        if final_command:
            send_debug_to_pc(uid, "Finalizing command: " + final_command)
            logger.info(f"Final command for session {uid}: {final_command}")
            await call_chatgpt_to_generate_code(final_command, uid)
        # Reset session
        active_sessions[uid]["command"] = ""
        active_sessions[uid]["active"] = False
        active_sessions[uid]["timer"] = None

    for segment in segments:
        text = segment.get("text", "").strip().lower()
        send_live_transcript_to_pc(uid, text)
        send_debug_to_pc(uid, "Received segment: " + text)
        logger.info(f"Received segment: {text} (session_id: {uid})")

        if not active_sessions[uid]["active"]:
            if KEYWORD in text:
                send_debug_to_pc(uid, "Activation keyword detected!")
                logger.info("Activation keyword detected!")
                active_sessions[uid]["active"] = True
                active_sessions[uid]["command"] = text
                active_sessions[uid]["last_received_time"] = asyncio.get_event_loop().time()

                # Cancel the previous timer if any
                if active_sessions[uid]["timer"]:
                    active_sessions[uid]["timer"].cancel()
                    try:
                        await active_sessions[uid]["timer"]
                    except asyncio.CancelledError:
                        pass

                # Schedule a new timer for finalizing the command
                active_sessions[uid]["timer"] = asyncio.create_task(
                    schedule_finalize_command(uid, COMMAND_TIMEOUT)
                )
            else:
                # Not active and keyword not detected, ignore
                continue
        else:
            # Append to the existing command
            active_sessions[uid]["command"] += " " + text
            active_sessions[uid]["last_received_time"] = asyncio.get_event_loop().time()
            send_debug_to_pc(uid, "Aggregating command: " + active_sessions[uid]["command"].strip())
            logger.info(f"Aggregating command: '{active_sessions[uid]['command'].strip()}'")

            # Cancel the previous timer and set a new one
            if active_sessions[uid]["timer"]:
                active_sessions[uid]["timer"].cancel()
                try:
                    await active_sessions[uid]["timer"]
                except asyncio.CancelledError:
                    pass

            active_sessions[uid]["timer"] = asyncio.create_task(
                schedule_finalize_command(uid, COMMAND_TIMEOUT)
            )

    return {"status": "success"}

async def call_chatgpt_to_generate_code(command, uid):
    try:
        ahda_os = get_ahda_os(uid)
        messages = [
            ("system", prompt.replace("{os_name}", ahda_os)),
            ("human", command),
        ]
        ai_msg = chat.invoke(messages)
        send_debug_to_pc(uid, "ChatGPT-4 response: " + ai_msg.content)
        return send_to_pc(uid, ai_msg.content)
    except Exception as e:
        send_debug_to_pc(uid, f"Error calling ChatGPT-4: {e}")
        logger.error(f"Error calling ChatGPT-4: {e}")
        return {"type": "error", "content": str(e)}

@router.get('/ahda/index', response_class=HTMLResponse, tags=['ahda'])
async def get_ahda_index(request: Request, uid: str = Query(None)):
    if not uid:
        raise HTTPException(status_code=400, detail="UID is required")

    return FileResponse(INDEX_PATH)

@router.get("/ahda/completion", tags=['ahda'])
def is_setup_completed(uid: str):
    ahda_url = get_ahda_url(uid)
    ahda_os = get_ahda_os(uid)

    send_debug_to_pc(uid, f"Checking AHDA setup: {ahda_url}, {ahda_os}")
    return {'is_setup_completed': ahda_url is not None and ahda_os is not None}

@router.post('/ahda/configure', tags=['ahda'])
def configure_ahda(uid: str = Form(...), url: str = Form(...), os: str = Form(...)):
    if not uid or not url:
        raise HTTPException(status_code=400, detail="Both UID, URL AND OS are required")

    store_ahda(uid, url, os)
    return {'message': 'AHDA configured successfully'}
