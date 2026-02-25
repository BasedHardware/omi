"""
agent-proxy — WebSocket proxy that bridges the mobile app to a user's agent VM.

Auth: Firebase ID token in Authorization header (Bearer <token>) during WS upgrade.
Flow: validate token → fetch VM from Firestore → connect to VM WS → bidirectional pump.
History: fetches last 10 agent messages from Firestore and prepends to prompt.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import firebase_admin
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from firebase_admin import auth, credentials, firestore
from google.cloud.firestore_v1 import Query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase init — uses GOOGLE_APPLICATION_CREDENTIALS or ADC
cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if cred_path:
    firebase_admin.initialize_app(credentials.Certificate(cred_path))
else:
    firebase_admin.initialize_app()

db = firestore.client()

app = FastAPI()

AGENT_PLUGIN_ID = '__agent__'
HISTORY_LIMIT = 10


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_agent_vm(uid: str) -> dict | None:
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict().get("agentVm")
    return None


def _fetch_chat_history(uid: str) -> list:
    """Fetch last N agent messages from Firestore, returned oldest-first."""
    messages_ref = (
        db.collection('users')
        .document(uid)
        .collection('messages')
        .where('plugin_id', '==', AGENT_PLUGIN_ID)
        .order_by('created_at', direction=Query.DESCENDING)
        .limit(HISTORY_LIMIT)
    )
    messages = []
    for doc in messages_ref.stream():
        data = doc.to_dict()
        messages.append(
            {
                'sender': data.get('sender', ''),
                'text': data.get('text', ''),
            }
        )
    return list(reversed(messages))


def _save_message(uid: str, text: str, sender: str):
    """Save a message to Firestore under the agent plugin_id."""
    msg_data = {
        'id': str(uuid.uuid4()),
        'text': text,
        'created_at': datetime.now(timezone.utc),
        'sender': sender,
        'plugin_id': AGENT_PLUGIN_ID,
        'type': 'text',
        'from_external_integration': False,
        'memories_id': [],
        'files_id': [],
    }
    db.collection('users').document(uid).collection('messages').add(msg_data)


def _build_prompt_with_history(prompt: str, history: list) -> str:
    """Prepend conversation history to the current prompt."""
    if not history:
        return prompt

    lines = ["<conversation_history>"]
    for msg in history:
        role = "Human" if msg['sender'] == 'human' else "Assistant"
        lines.append(f"{role}: {msg['text']}")
    lines.append("</conversation_history>")
    lines.append("")
    lines.append(prompt)
    return "\n".join(lines)


@app.websocket("/v1/agent/ws")
async def agent_ws(websocket: WebSocket):
    # Validate Firebase token from Authorization header
    auth_header = websocket.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        await websocket.close(code=4001, reason="Missing Authorization header")
        return

    token = auth_header[7:].strip()
    try:
        uid = auth.verify_id_token(token)["uid"]
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Look up the user's agent VM
    vm = _get_agent_vm(uid)
    if not vm or vm.get("status") != "ready":
        await websocket.close(code=4002, reason="No agent VM available")
        return

    vm_ip = vm["ip"]
    vm_token = vm["authToken"]
    vm_uri = f"ws://{vm_ip}:8080/ws?token={vm_token}"

    await websocket.accept()
    logger.info(f"[agent-proxy] uid={uid} connecting to vm={vm_ip}")

    try:
        async with websockets.connect(vm_uri) as vm_ws:
            logger.info(f"[agent-proxy] uid={uid} connected")

            async def phone_to_vm():
                try:
                    async for msg in websocket.iter_text():
                        try:
                            data = json.loads(msg)
                            if data.get('type') == 'query':
                                prompt = data.get('prompt', '')
                                # Fetch history before saving new message
                                history = await asyncio.to_thread(_fetch_chat_history, uid)
                                data['prompt'] = _build_prompt_with_history(prompt, history)
                                msg = json.dumps(data)
                                # Save user message
                                await asyncio.to_thread(_save_message, uid, prompt, 'human')
                                logger.info(f"[agent-proxy] uid={uid} query with {len(history)} history messages")
                        except (json.JSONDecodeError, Exception) as e:
                            logger.warning(f"[agent-proxy] failed to process message: {e}")
                        await vm_ws.send(msg)
                except (WebSocketDisconnect, Exception):
                    pass

            async def vm_to_phone():
                response_text = ''
                try:
                    async for msg in vm_ws:
                        text = msg if isinstance(msg, str) else msg.decode()
                        await websocket.send_text(text)
                        # Collect response for saving
                        try:
                            event = json.loads(text)
                            evt_type = event.get('type')
                            evt_text = event.get('text', '') or event.get('content', '') or ''
                            if evt_type == 'text_delta':
                                response_text += evt_text
                            elif evt_type == 'result' and evt_text and not response_text:
                                response_text = evt_text
                        except json.JSONDecodeError:
                            pass
                except Exception:
                    pass
                finally:
                    # Save AI response
                    if response_text.strip():
                        try:
                            await asyncio.to_thread(_save_message, uid, response_text.strip(), 'ai')
                            logger.info(f"[agent-proxy] uid={uid} saved AI response ({len(response_text)} chars)")
                        except Exception as e:
                            logger.warning(f"[agent-proxy] failed to save AI response: {e}")

            t1 = asyncio.create_task(phone_to_vm())
            t2 = asyncio.create_task(vm_to_phone())
            _, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except Exception as e:
        logger.error(f"[agent-proxy] uid={uid} vm_connect failed: {e}")
        try:
            await websocket.close(code=4003, reason="VM connection failed")
        except Exception:
            pass
    finally:
        logger.info(f"[agent-proxy] uid={uid} disconnected")
