"""
agent-proxy — WebSocket proxy that bridges the mobile app to a user's agent VM.

Auth: Firebase ID token in Authorization header (Bearer <token>) during WS upgrade.
Flow: validate token → fetch VM from Firestore → connect to VM WS → bidirectional pump.
History: fetches last 10 agent messages from Firestore and prepends to prompt.
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import firebase_admin
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
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

HISTORY_LIMIT = 10

# Encryption — optional; required for users with enhanced data protection.
ENCRYPTION_SECRET = os.getenv('ENCRYPTION_SECRET', '').encode('utf-8')
_encryption_ok = len(ENCRYPTION_SECRET) >= 32


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_user_context(uid: str) -> tuple:
    """Get agent VM info and data protection level from the user document."""
    doc = db.collection('users').document(uid).get()
    if doc.exists:
        data = doc.to_dict()
        return data.get('agentVm'), data.get('data_protection_level', 'enhanced')
    return None, 'enhanced'


# --------------- encryption helpers ---------------


def _derive_key(uid: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=uid.encode('utf-8'),
        info=b'user-data-encryption',
    )
    return hkdf.derive(ENCRYPTION_SECRET)


def _encrypt_text(text: str, uid: str) -> str:
    if not text or not _encryption_ok:
        return text
    key = _derive_key(uid)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, text.encode('utf-8'), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')


def _decrypt_text(text: str, uid: str) -> str:
    if not text or not _encryption_ok:
        return text
    try:
        key = _derive_key(uid)
        aesgcm = AESGCM(key)
        payload = base64.b64decode(text.encode('utf-8'))
        return aesgcm.decrypt(payload[:12], payload[12:], None).decode('utf-8')
    except Exception:
        return text


# --------------- chat session helpers ---------------


def _get_or_create_chat_session(uid: str) -> dict:
    """Get or create the default (plugin_id=None) chat session."""
    session_ref = (
        db.collection('users').document(uid).collection('chat_sessions').where('plugin_id', '==', None).limit(1)
    )
    for session in session_ref.stream():
        return session.to_dict()

    session_data = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.now(timezone.utc),
        'plugin_id': None,
        'message_ids': [],
        'file_ids': [],
    }
    db.collection('users').document(uid).collection('chat_sessions').document(session_data['id']).set(session_data)
    return session_data


# --------------- message persistence ---------------


def _fetch_chat_history(uid: str, chat_session_id: str) -> list:
    """Fetch last N messages from the chat session, returned oldest-first."""
    messages_ref = (
        db.collection('users')
        .document(uid)
        .collection('messages')
        .where('plugin_id', '==', None)
        .where('chat_session_id', '==', chat_session_id)
        .order_by('created_at', direction=Query.DESCENDING)
        .limit(HISTORY_LIMIT)
    )
    messages = []
    for doc in messages_ref.stream():
        data = doc.to_dict()
        text = data.get('text', '')
        if data.get('data_protection_level') == 'enhanced':
            text = _decrypt_text(text, uid)
        messages.append({'sender': data.get('sender', ''), 'text': text})
    return list(reversed(messages))


def _save_message(uid: str, text: str, sender: str, chat_session_id: str, data_protection_level: str):
    """Save a message to Firestore with encryption and chat session linking."""
    msg_id = str(uuid.uuid4())
    store_text = text
    level = data_protection_level
    if level == 'enhanced':
        if _encryption_ok:
            store_text = _encrypt_text(text, uid)
        else:
            level = 'standard'

    msg_data = {
        'id': msg_id,
        'text': store_text,
        'created_at': datetime.now(timezone.utc),
        'sender': sender,
        'plugin_id': None,
        'type': 'text',
        'from_external_integration': False,
        'memories_id': [],
        'files_id': [],
        'chat_session_id': chat_session_id,
        'data_protection_level': level,
    }
    user_ref = db.collection('users').document(uid)
    user_ref.collection('messages').add(msg_data)
    # Link message to chat session
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)
    session_ref.update({'message_ids': firestore.ArrayUnion([msg_id])})


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

    # Look up the user's agent VM and data protection level
    vm, data_protection_level = _get_user_context(uid)
    if not vm or vm.get("status") != "ready":
        await websocket.close(code=4002, reason="No agent VM available")
        return

    vm_ip = vm["ip"]
    vm_token = vm["authToken"]
    vm_uri = f"ws://{vm_ip}:8080/ws?token={vm_token}"

    # Get or create the default chat session so messages are linked properly
    chat_session = await asyncio.to_thread(_get_or_create_chat_session, uid)
    chat_session_id = chat_session['id']

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
                                history = await asyncio.to_thread(_fetch_chat_history, uid, chat_session_id)
                                data['prompt'] = _build_prompt_with_history(prompt, history)
                                msg = json.dumps(data)
                                # Save user message
                                await asyncio.to_thread(
                                    _save_message,
                                    uid,
                                    prompt,
                                    'human',
                                    chat_session_id,
                                    data_protection_level,
                                )
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
                            await asyncio.to_thread(
                                _save_message,
                                uid,
                                response_text.strip(),
                                'ai',
                                chat_session_id,
                                data_protection_level,
                            )
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
