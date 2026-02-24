"""
agent-proxy — WebSocket proxy that bridges the mobile app to a user's agent VM.

Auth: Firebase ID token in Authorization header (Bearer <token>) during WS upgrade.
Flow: validate token → fetch VM from Firestore → connect to VM WS → bidirectional pump.
"""

import asyncio
import logging
import os

import firebase_admin
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from firebase_admin import auth, credentials, firestore

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


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_agent_vm(uid: str) -> dict | None:
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict().get("agentVm")
    return None


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
                        await vm_ws.send(msg)
                except (WebSocketDisconnect, Exception):
                    pass

            async def vm_to_phone():
                try:
                    async for msg in vm_ws:
                        text = msg if isinstance(msg, str) else msg.decode()
                        await websocket.send_text(text)
                except Exception:
                    pass

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
