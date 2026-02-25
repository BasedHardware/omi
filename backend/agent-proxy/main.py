"""
agent-proxy — WebSocket proxy that bridges the mobile app to a user's agent VM.

Auth: Firebase ID token in Authorization header (Bearer <token>) during WS upgrade.
Flow: validate token → fetch VM from Firestore → if stopped, restart → connect to VM WS → bidirectional pump.
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
import google.auth
import google.auth.transport.requests
import httpx
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
GCE_PROJECT = "based-hardware"
VM_KEEPALIVE_INTERVAL = 120  # seconds — ping VM every 2 min during active WS

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


def _refresh_vm(uid: str) -> dict | None:
    """Re-read the VM info from Firestore (called after restart to get new IP)."""
    doc = db.collection('users').document(uid).get()
    if doc.exists:
        return doc.to_dict().get('agentVm')
    return None


# --------------- GCE helpers ---------------


def _get_gce_access_token() -> str:
    """Get a GCE access token via Application Default Credentials."""
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


async def _check_gce_status(vm_name: str, zone: str) -> str:
    """Check the actual GCE instance status."""
    token = _get_gce_access_token()
    url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            return "UNKNOWN"
        return resp.json().get("status", "UNKNOWN")


async def _start_vm_and_wait(vm_name: str, zone: str) -> str:
    """Start a stopped/terminated GCE VM and return the new IP."""
    token = _get_gce_access_token()
    start_url = (
        f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}/start"
    )

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(start_url, headers={"Authorization": f"Bearer {token}"}, content=b"")
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE start failed: {resp.status_code} {resp.text}")

        op_name = resp.json().get("name")
        if not op_name:
            raise Exception("Missing operation name in GCE start response")

        op_url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/operations/{op_name}"
        for _ in range(24):
            await asyncio.sleep(5)
            token = _get_gce_access_token()
            status_resp = await client.get(op_url, headers={"Authorization": f"Bearer {token}"})
            status = status_resp.json()
            if status.get("status") == "DONE":
                if "error" in status:
                    raise Exception(f"GCE start operation failed: {status['error']}")
                break

        instance_url = (
            f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
        )
        token = _get_gce_access_token()
        inst_resp = await client.get(instance_url, headers={"Authorization": f"Bearer {token}"})
        instance = inst_resp.json()
        try:
            return instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
        except (KeyError, IndexError):
            return "unknown"


def _update_firestore_vm(uid: str, ip: str | None, status: str):
    """Update the user's agentVm fields in Firestore."""
    update = {"agentVm.status": status}
    if ip:
        update["agentVm.ip"] = ip
    db.collection('users').document(uid).update(update)


async def _ensure_vm_running(uid: str, vm: dict) -> dict | None:
    """If VM is stopped, restart it and return updated VM info. Returns None on failure."""
    vm_name = vm.get("vmName")
    zone = vm.get("zone", "us-central1-a")
    fs_status = vm.get("status", "")

    if fs_status == "ready":
        # Verify it's actually running
        try:
            gce_status = await _check_gce_status(vm_name, zone)
        except Exception:
            return vm  # Can't check, assume it's fine

        if gce_status == "RUNNING":
            return vm
        if gce_status not in ("TERMINATED", "STOPPED"):
            return vm  # STAGING, etc. — let it be

    # VM needs restart
    logger.info(f"[agent-proxy] VM {vm_name} needs restart, starting...")
    _update_firestore_vm(uid, None, "provisioning")

    try:
        ip = await _start_vm_and_wait(vm_name, zone)
        _update_firestore_vm(uid, ip, "ready")
        logger.info(f"[agent-proxy] VM {vm_name} restarted, ip={ip}")
        return _refresh_vm(uid)
    except Exception as e:
        logger.error(f"[agent-proxy] Failed to restart VM {vm_name}: {e}")
        _update_firestore_vm(uid, None, "error")
        return None


async def _wait_for_vm_healthy(vm_ip: str, auth_token: str, timeout: float = 120) -> bool:
    """Poll the VM's /health endpoint until it responds OK."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(f"http://{vm_ip}:8080/health")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(3)
    return False


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
    if not vm:
        await websocket.close(code=4002, reason="No agent VM available")
        return

    # Accept WebSocket first so we can send status messages during VM startup
    await websocket.accept()

    # If VM is not ready, try to restart it
    vm_status = vm.get("status", "")
    if vm_status != "ready" or not vm.get("ip"):
        await websocket.send_text(json.dumps({"type": "status", "message": "Starting your agent VM..."}))
        vm = await _ensure_vm_running(uid, vm)
        if not vm or vm.get("status") != "ready" or not vm.get("ip"):
            await websocket.send_text(json.dumps({"type": "error", "message": "Failed to start agent VM"}))
            await websocket.close(code=4002, reason="VM startup failed")
            return
    else:
        # VM says ready — verify GCE status in case it auto-stopped
        vm_name = vm.get("vmName")
        zone = vm.get("zone", "us-central1-a")
        try:
            gce_status = await _check_gce_status(vm_name, zone)
            if gce_status in ("TERMINATED", "STOPPED"):
                await websocket.send_text(json.dumps({"type": "status", "message": "Starting your agent VM..."}))
                vm = await _ensure_vm_running(uid, vm)
                if not vm or vm.get("status") != "ready" or not vm.get("ip"):
                    await websocket.send_text(json.dumps({"type": "error", "message": "Failed to start agent VM"}))
                    await websocket.close(code=4002, reason="VM startup failed")
                    return
        except Exception as e:
            logger.warning(f"[agent-proxy] uid={uid} GCE status check failed, proceeding: {e}")

    vm_ip = vm["ip"]
    vm_token = vm["authToken"]
    vm_uri = f"ws://{vm_ip}:8080/ws?token={vm_token}"

    # Wait for VM to be healthy before connecting WebSocket
    await websocket.send_text(json.dumps({"type": "status", "message": "Connecting to your agent..."}))
    healthy = await _wait_for_vm_healthy(vm_ip, vm_token)
    if not healthy:
        logger.error(f"[agent-proxy] uid={uid} VM {vm_ip} never became healthy")
        await websocket.send_text(json.dumps({"type": "error", "message": "Agent VM is not responding"}))
        await websocket.close(code=4003, reason="VM not healthy")
        return

    # Get or create the default chat session so messages are linked properly
    chat_session = await asyncio.to_thread(_get_or_create_chat_session, uid)
    chat_session_id = chat_session['id']

    logger.info(f"[agent-proxy] uid={uid} connecting to vm={vm_ip}")

    try:
        async with websockets.connect(vm_uri, ping_interval=600, ping_timeout=600) as vm_ws:
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

            async def keepalive_pinger():
                """Periodically ping the VM to prevent idle auto-stop during active WS."""
                async with httpx.AsyncClient(timeout=5) as client:
                    while True:
                        await asyncio.sleep(VM_KEEPALIVE_INTERVAL)
                        try:
                            await client.post(f"http://{vm_ip}:8080/ping?token={vm_token}")
                        except Exception:
                            pass

            t1 = asyncio.create_task(phone_to_vm())
            t2 = asyncio.create_task(vm_to_phone())
            t3 = asyncio.create_task(keepalive_pinger())
            _, pending = await asyncio.wait([t1, t2, t3], return_when=asyncio.FIRST_COMPLETED)
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
