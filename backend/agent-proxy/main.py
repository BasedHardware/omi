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
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, cast

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
from google.cloud.firestore import ArrayUnion
from google.cloud.firestore_v1 import Query
from utils.executors import (
    critical_executor,
    db_executor,
    drain_background_tasks,
    run_blocking,
    start_background_task,
)

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 10
GCE_PROJECT = "based-hardware"
VM_KEEPALIVE_INTERVAL = 120  # seconds — ping VM every 2 min during active WS

# Encryption — optional; required for users with enhanced data protection.
ENCRYPTION_SECRET = os.getenv('ENCRYPTION_SECRET', '').encode('utf-8')
_encryption_ok = len(ENCRYPTION_SECRET) >= 32
_firebase_init_lock = threading.RLock()
_firestore_db: Any = None


def _ensure_firebase_initialized() -> None:
    """Initialize the default Firebase app lazily on the caller-owned worker lane."""
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    with _firebase_init_lock:
        try:
            firebase_admin.get_app()
            return
        except ValueError:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if cred_path:
                firebase_admin.initialize_app(credentials.Certificate(cred_path))  # type: ignore[reportUnknownMemberType]
            else:
                firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]


def _get_firestore_db() -> Any:
    """Return the lazy Firestore singleton; construction stays off import paths."""
    global _firestore_db
    if _firestore_db is None:
        with _firebase_init_lock:
            if _firestore_db is None:
                _ensure_firebase_initialized()
                _firestore_db = firestore.client()  # type: ignore[reportUnknownMemberType]
    return _firestore_db


def _verify_id_token(token: str) -> Dict[str, Any]:
    """Verify one Firebase token after ensuring the provider app exists."""
    _ensure_firebase_initialized()
    return cast(Dict[str, Any], auth.verify_id_token(token))  # type: ignore[reportUnknownMemberType]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail startup closed on provider readiness and drain owned persistence on shutdown."""
    await run_blocking(critical_executor, _ensure_firebase_initialized)
    await run_blocking(db_executor, _get_firestore_db)
    try:
        yield
    finally:
        await drain_background_tasks(timeout=10.0)


app = FastAPI(lifespan=lifespan)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _get_user_context(uid: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Get agent VM info and data protection level from the user document."""
    doc = _get_firestore_db().collection('users').document(uid).get()
    if doc.exists:
        data: Dict[str, Any] = _typed_doc(doc)
        agent_vm = cast(Optional[Dict[str, Any]], data.get('agentVm'))
        level = cast(str, data.get('data_protection_level', 'enhanced'))
        return agent_vm, level
    return None, 'enhanced'


def _refresh_vm(uid: str) -> Optional[Dict[str, Any]]:
    """Re-read the VM info from Firestore (called after restart to get new IP)."""
    doc = _get_firestore_db().collection('users').document(uid).get()
    if doc.exists:
        return cast(Optional[Dict[str, Any]], _typed_doc(doc).get('agentVm'))
    return None


# --------------- GCE helpers ---------------


def _get_gce_access_token() -> str:
    """Get a GCE access token via Application Default Credentials."""
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])  # type: ignore[reportUnknownMemberType]
    creds.refresh(google.auth.transport.requests.Request())
    return cast(str, creds.token)


async def _check_gce_status(vm_name: str, zone: str) -> str:
    """Check the actual GCE instance status."""
    token = await run_blocking(critical_executor, _get_gce_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            return "UNKNOWN"
        return resp.json().get("status", "UNKNOWN")


async def _start_vm_and_wait(vm_name: str, zone: str) -> str:
    """Start a stopped/terminated GCE VM and return the new IP."""

    t0 = time.monotonic()
    token = await run_blocking(critical_executor, _get_gce_access_token)
    start_url = (
        f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}/start"
    )

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(start_url, headers={"Authorization": f"Bearer {token}"}, content=b"")
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE start failed: {resp.status_code} {resp.text}")
        t_start = time.monotonic() - t0
        logger.info(f"[vm-start] {vm_name} start API call: {t_start:.1f}s")

        op_name = resp.json().get("name")
        if not op_name:
            raise Exception("Missing operation name in GCE start response")

        op_url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/operations/{op_name}"
        for i in range(24):
            await asyncio.sleep(5)
            token = await run_blocking(critical_executor, _get_gce_access_token)
            status_resp = await client.get(op_url, headers={"Authorization": f"Bearer {token}"})
            status = status_resp.json()
            if status.get("status") == "DONE":
                if "error" in status:
                    raise Exception(f"GCE start operation failed: {status['error']}")
                t_op = time.monotonic() - t0
                logger.info(f"[vm-start] {vm_name} operation done after {i + 1} polls: {t_op:.1f}s")
                break

        # Poll for a valid external IP (may take a few seconds after operation completes)
        instance_url = (
            f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
        )
        ip = None
        for attempt in range(6):
            token = await run_blocking(critical_executor, _get_gce_access_token)
            inst_resp = await client.get(instance_url, headers={"Authorization": f"Bearer {token}"})
            instance = inst_resp.json()
            try:
                candidate = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
                if candidate and candidate != "unknown":
                    ip = candidate
                    t_ip = time.monotonic() - t0
                    logger.info(f"[vm-start] {vm_name} got IP {ip} on attempt {attempt + 1}: {t_ip:.1f}s total")
                    break
            except (KeyError, IndexError):
                pass
            if attempt < 5:
                logger.info(f"[vm-start] {vm_name} no IP yet, retrying ({attempt + 1}/6)...")
                await asyncio.sleep(3)

        if not ip:
            t_fail = time.monotonic() - t0
            logger.error(f"[vm-start] {vm_name} failed to get IP after 6 attempts: {t_fail:.1f}s")
            ip = "unknown"

        return ip


def _update_firestore_vm(uid: str, ip: str | None, status: str) -> None:
    """Update the user's agentVm fields in Firestore."""
    update = {"agentVm.status": status}
    if ip:
        update["agentVm.ip"] = ip
    _get_firestore_db().collection('users').document(uid).update(update)


async def _reset_vm(vm_name: str, zone: str) -> None:
    """Hard-reset a RUNNING VM whose agent process is unresponsive."""
    token = await run_blocking(critical_executor, _get_gce_access_token)
    reset_url = (
        f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}/reset"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(reset_url, headers={"Authorization": f"Bearer {token}"}, content=b"")
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE reset failed: {resp.status_code} {resp.text}")
        logger.info(f"[agent-proxy] VM {vm_name} reset initiated")
        # Wait for the operation to complete
        op_name = resp.json().get("name")
        if op_name:
            op_url = (
                f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/operations/{op_name}"
            )
            for _ in range(12):
                await asyncio.sleep(5)
                t = await run_blocking(critical_executor, _get_gce_access_token)
                status_resp = await client.get(op_url, headers={"Authorization": f"Bearer {t}"})
                if status_resp.json().get("status") == "DONE":
                    break


async def _ensure_vm_running(uid: str, vm: Dict[str, Any], health_failed: bool = False) -> Optional[Dict[str, Any]]:
    """If VM is stopped, restart it and return updated VM info. Returns None on failure."""
    vm_name = cast(str, vm.get("vmName"))
    zone = cast(str, vm.get("zone", "us-central1-a"))
    fs_status = cast(str, vm.get("status", ""))

    if fs_status == "ready":
        # Verify it's actually running
        try:
            gce_status = await _check_gce_status(vm_name, zone)
        except Exception:
            return vm  # Can't check, assume it's fine

        if gce_status == "RUNNING":
            if health_failed:
                # VM is RUNNING but agent process is dead — hard reset
                logger.info(f"[agent-proxy] VM {vm_name} is RUNNING but unhealthy, resetting...")
                await run_blocking(db_executor, _update_firestore_vm, uid, None, "provisioning")
                try:
                    await _reset_vm(vm_name, zone)
                    await run_blocking(db_executor, _update_firestore_vm, uid, vm.get("ip"), "ready")
                    return await run_blocking(db_executor, _refresh_vm, uid)
                except Exception as e:
                    logger.error(f"[agent-proxy] Failed to reset VM {vm_name}: {e}")
                    await run_blocking(db_executor, _update_firestore_vm, uid, None, "error")
                    return None
            return vm
        if gce_status not in ("TERMINATED", "STOPPED"):
            return vm  # STAGING, etc. — let it be

    # VM needs restart
    logger.info(f"[agent-proxy] VM {vm_name} needs restart, starting...")
    await run_blocking(db_executor, _update_firestore_vm, uid, None, "provisioning")

    try:
        ip = await _start_vm_and_wait(vm_name, zone)
        await run_blocking(db_executor, _update_firestore_vm, uid, ip, "ready")
        logger.info(f"[agent-proxy] VM {vm_name} restarted, ip={ip}")
        return await run_blocking(db_executor, _refresh_vm, uid)
    except Exception as e:
        logger.error(f"[agent-proxy] Failed to restart VM {vm_name}: {e}")
        await run_blocking(db_executor, _update_firestore_vm, uid, None, "error")
        return None


async def _wait_for_vm_healthy(vm_ip: str, auth_token: str, timeout: float = 120) -> bool:
    """Poll the VM's /health endpoint until it responds OK."""
    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_running_loop().time() < deadline:
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


def _get_or_create_chat_session(uid: str) -> Dict[str, Any]:
    """Get or create the default (plugin_id=None) chat session."""
    session_ref = (
        _get_firestore_db()
        .collection('users')
        .document(uid)
        .collection('chat_sessions')
        .where('plugin_id', '==', None)
        .limit(1)
    )
    for session in session_ref.stream():
        return _typed_doc(session)

    session_data: Dict[str, Any] = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.now(timezone.utc),
        'plugin_id': None,
        'message_ids': [],
        'file_ids': [],
    }
    (
        _get_firestore_db()
        .collection('users')
        .document(uid)
        .collection('chat_sessions')
        .document(session_data['id'])
        .set(session_data)
    )
    return session_data


# --------------- message persistence ---------------


def _fetch_chat_history(uid: str, chat_session_id: str) -> List[Dict[str, Any]]:
    """Fetch last N messages from the chat session, returned oldest-first."""
    messages_ref = (
        _get_firestore_db()
        .collection('users')
        .document(uid)
        .collection('messages')
        .where('plugin_id', '==', None)
        .where('chat_session_id', '==', chat_session_id)
        .order_by('created_at', direction=Query.DESCENDING)
        .limit(HISTORY_LIMIT)
    )
    messages: List[Dict[str, Any]] = []
    for doc in messages_ref.stream():
        data: Dict[str, Any] = _typed_doc(doc)
        text = data.get('text', '')
        if data.get('data_protection_level') == 'enhanced':
            text = _decrypt_text(cast(str, text), uid)
        messages.append({'sender': data.get('sender', ''), 'text': text})
    return list(reversed(messages))


def _save_message(uid: str, text: str, sender: str, chat_session_id: str, data_protection_level: str) -> None:
    """Save a message to Firestore with encryption and chat session linking."""
    msg_id = str(uuid.uuid4())
    store_text = text
    level = data_protection_level
    if level == 'enhanced':
        if _encryption_ok:
            store_text = _encrypt_text(text, uid)
        else:
            level = 'standard'

    msg_data: Dict[str, Any] = {
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
    user_ref = _get_firestore_db().collection('users').document(uid)
    user_ref.collection('messages').add(msg_data)
    # Link message to chat session
    session_ref = user_ref.collection('chat_sessions').document(chat_session_id)
    session_ref.set({'message_ids': ArrayUnion([msg_id])}, merge=True)


def _build_prompt_with_history(prompt: str, history: List[Dict[str, Any]]) -> str:
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
        logger.warning("[agent-proxy] WS rejected: missing Authorization header")
        await websocket.close(code=4001, reason="Missing Authorization header")
        return

    token = auth_header[7:].strip()
    try:
        decoded_token = await run_blocking(critical_executor, _verify_id_token, token)
        uid = cast(str, decoded_token["uid"])
    except Exception as e:
        logger.warning(f"[agent-proxy] WS rejected: invalid token: {e}")
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Look up the user's agent VM and data protection level
    vm, data_protection_level = await run_blocking(db_executor, _get_user_context, uid)
    if not vm:
        logger.warning(f"[agent-proxy] WS rejected: uid={uid} no VM")
        await websocket.close(code=4002, reason="No agent VM available")
        return

    # Accept WebSocket first so we can send status messages during VM startup
    await websocket.accept()

    vm_ip = vm.get("ip")
    vm_token = vm.get("authToken")

    # Fast path: if Firestore says ready with an IP, try connecting directly (skip GCE check).
    # Only fall back to GCE check + restart if the VM isn't reachable.
    if vm.get("status") == "ready" and vm_ip:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"http://{vm_ip}:8080/health")
                if resp.status_code != 200:
                    raise Exception(f"health returned {resp.status_code}")
        except Exception:
            # VM not reachable — check GCE and restart/reset if needed
            logger.info(f"[agent-proxy] uid={uid} VM {vm_ip} not reachable, checking GCE...")
            await websocket.send_text(json.dumps({"type": "status", "message": "Starting your agent VM..."}))
            vm = await _ensure_vm_running(uid, vm, health_failed=True)
            if not vm or vm.get("status") != "ready" or not vm.get("ip"):
                await websocket.send_text(json.dumps({"type": "error", "message": "Failed to start agent VM"}))
                await websocket.close(code=4002, reason="VM startup failed")
                return
            vm_ip = vm["ip"]
            vm_token = vm["authToken"]
            # Wait for VM to be healthy after restart
            healthy = await _wait_for_vm_healthy(vm_ip, vm_token)
            if not healthy:
                await websocket.send_text(json.dumps({"type": "error", "message": "Agent VM is not responding"}))
                await websocket.close(code=4003, reason="VM not healthy")
                return
    else:
        # No IP or not ready — must restart
        await websocket.send_text(json.dumps({"type": "status", "message": "Starting your agent VM..."}))
        vm = await _ensure_vm_running(uid, vm)
        if not vm or vm.get("status") != "ready" or not vm.get("ip"):
            await websocket.send_text(json.dumps({"type": "error", "message": "Failed to start agent VM"}))
            await websocket.close(code=4002, reason="VM startup failed")
            return
        vm_ip = vm["ip"]
        vm_token = vm["authToken"]
        healthy = await _wait_for_vm_healthy(vm_ip, vm_token)
        if not healthy:
            await websocket.send_text(json.dumps({"type": "error", "message": "Agent VM is not responding"}))
            await websocket.close(code=4003, reason="VM not healthy")
            return

    vm_uri = f"ws://{vm_ip}:8080/ws?token={vm_token}"

    # Get or create the default chat session so messages are linked properly
    chat_session = await run_blocking(db_executor, _get_or_create_chat_session, uid)
    chat_session_id = chat_session['id']

    logger.info(f"[agent-proxy] uid={uid} connecting to vm={vm_ip}")

    try:
        async with websockets.connect(vm_uri, ping_interval=600, ping_timeout=600) as vm_ws:
            logger.info(f"[agent-proxy] uid={uid} connected")

            # Send Firebase token to VM so it can fetch backend tools (calendar, gmail, etc.)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"http://{vm_ip}:8080/auth?token={vm_token}",
                        json={"firebaseToken": token},
                    )
                    logger.info(f"[agent-proxy] uid={uid} sent Firebase token to VM")
            except Exception as e:
                logger.warning(f"[agent-proxy] uid={uid} failed to send Firebase token: {e}")

            first_query_sent = False

            async def _save_ai_response(uid: str, text: str, session_id: str, protection_level: str) -> None:
                """Fire-and-forget AI response save — never blocks event forwarding."""
                try:
                    await run_blocking(db_executor, _save_message, uid, text, 'ai', session_id, protection_level)
                    logger.info(f"[agent-proxy] uid={uid} saved AI response ({len(text)} chars)")
                except Exception as e:
                    logger.warning(f"[agent-proxy] uid={uid} failed to save AI response: {e}")

            async def phone_to_vm():
                nonlocal first_query_sent
                try:
                    async for msg in websocket.iter_text():
                        try:
                            data = json.loads(msg)
                            if data.get('type') == 'query':
                                prompt = data.get('prompt', '')
                                if not first_query_sent:
                                    # First query: fetch history and inject into prompt
                                    history = await run_blocking(db_executor, _fetch_chat_history, uid, chat_session_id)
                                    data['prompt'] = _build_prompt_with_history(prompt, history)
                                    msg = json.dumps(data)
                                    first_query_sent = True
                                    logger.info(
                                        f"[agent-proxy] uid={uid} first query with {len(history)} history messages"
                                    )
                                else:
                                    # Subsequent queries: Claude session already has context
                                    logger.info(f"[agent-proxy] uid={uid} follow-up query (session has context)")
                                # Save user message in background — no need to block VM forwarding
                                start_background_task(
                                    run_blocking(
                                        db_executor,
                                        _save_message,
                                        uid,
                                        prompt,
                                        'human',
                                        chat_session_id,
                                        data_protection_level,
                                    ),
                                    name=f"agent-proxy:{uid}:save-human-message",
                                )
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
                            elif evt_type == 'result':
                                # Use result text as fallback if no deltas were collected
                                if evt_text and not response_text:
                                    response_text = evt_text
                                # Save per-query so each message gets its own history entry
                                if response_text.strip():
                                    _text = response_text.strip()
                                    start_background_task(
                                        _save_ai_response(uid, _text, chat_session_id, data_protection_level),
                                        name=f"agent-proxy:{uid}:save-ai-message",
                                    )
                                response_text = ''
                        except json.JSONDecodeError:
                            pass
                except Exception:
                    pass
                finally:
                    # Save any unsaved partial response (connection dropped mid-query)
                    if response_text.strip():
                        # Use await here since we're in finally — connection is closing anyway
                        await _save_ai_response(uid, response_text.strip(), chat_session_id, data_protection_level)

            async def keepalive_pinger():
                """Periodically ping the VM to prevent idle auto-stop during active WS."""
                async with httpx.AsyncClient(timeout=5) as client:
                    while True:
                        await asyncio.sleep(VM_KEEPALIVE_INTERVAL)
                        try:
                            await client.post(f"http://{vm_ip}:8080/ping?token={vm_token}")
                        except Exception:
                            pass

            t1 = asyncio.create_task(phone_to_vm(), name=f"ws:{uid}:phone_to_vm")
            t2 = asyncio.create_task(vm_to_phone(), name=f"ws:{uid}:vm_to_phone")
            t3 = asyncio.create_task(keepalive_pinger(), name=f"ws:{uid}:keepalive")
            _, pending = await asyncio.wait([t1, t2, t3], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except Exception as e:
        logger.error(f"[agent-proxy] uid={uid} vm_connect failed: {e}")
    finally:
        try:
            await websocket.close(code=1000, reason="Session ended")
        except Exception:
            pass
        logger.info(f"[agent-proxy] uid={uid} disconnected")
