"""
agent-proxy — WebSocket proxy that bridges the mobile app to a user's agent VM.

Auth: Firebase ID token in Authorization header (Bearer <token>) during WS upgrade.
Flow: validate token → fetch VM from Firestore → request reconciliation when unavailable → connect to VM WS → bidirectional pump.
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
from zoneinfo import ZoneInfo

import firebase_admin
import httpx
import websockets
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from firebase_admin import auth, credentials, firestore
from google.cloud.firestore import ArrayUnion, transactional
from google.cloud.firestore_v1 import Query
from utils.executors import (
    critical_executor,
    db_executor,
    drain_background_tasks,
    run_blocking,
    start_background_task,
)
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from services.agent_vm_lifecycle import (
    SESSION_LEASE_TTL_SECONDS,
    claim_session_lease,
    demoted_updating_vm,
    heartbeat_session_lease,
    reconcile_requested,
    release_session_lease,
    request_vm_start,
)

logger = logging.getLogger(__name__)

from resilience import circuit_open, classify_error  # noqa: E402

HISTORY_LIMIT = 10
# Legacy placeholder that earlier builds persisted as agentVm.ip when the GCE
# IP poll timed out. Never written any more; still read so already-poisoned
# records heal on the next connect instead of resetting a healthy VM forever.
UNRESOLVED_VM_IP = "unknown"
VM_KEEPALIVE_INTERVAL = 120  # seconds — ping VM every 2 min during active WS
# Each inbound request is fenced immediately; this is only the bounded idle
# relay backstop that closes a socket after deletion is admitted.
ACCOUNT_DELETION_IDLE_RECHECK_INTERVAL = 30  # seconds
# Wait this long for the VM's session_state hello before deciding whether to seed
# history on the first query. The VM sends it synchronously on connect, so this is a
# tiny grace window; on timeout we seed history (a fresh amnesiac session is the worse
# failure than a one-time duplicate).
VM_HELLO_TIMEOUT = 3.0  # seconds
AGENT_VM_SESSION_LEASES_ENABLED = os.getenv("AGENT_VM_SESSION_LEASES_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}


def _utc_now() -> datetime:
    """Return the proxy's server clock for per-query model context."""
    return datetime.now(timezone.utc)


def current_time_prompt(prompt: str, time_zone: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """Prefix a mobile agent query with the proxy's authoritative current time.

    The mobile Claude-agent path bypasses the normal chat backend, so it must
    receive the same live clock context explicitly. The timezone comes from the
    mobile OS when available; invalid or missing values fail closed to UTC.
    """
    zone_name = (time_zone or "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(zone_name)
    except (KeyError, ValueError):
        logger.warning("[agent-proxy] invalid client timezone; falling back to UTC")
        zone_name = "UTC"
        zone = timezone.utc

    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_time = current.astimezone(zone).replace(microsecond=0)
    return f"# Current Time\n{local_time.isoformat()} ({zone_name})\n\n{prompt}"


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


def _get_account_deletion_status(uid: str) -> Optional[str]:
    """Read the uncached deletion authority for the proxy's independent auth boundary."""
    doc = _get_firestore_db().collection('account_deletions').document(uid).get()
    status = (doc.to_dict() or {}).get('wipe_status') if doc.exists else None
    return normalize_account_deletion_status(marker_exists=doc.exists, raw_status=status)


class AccountDeletionAccessBlocked(RuntimeError):
    """Raised when a durable deletion marker denies owner-scoped work."""


def _require_account_deletion_access(uid: str) -> None:
    status = _get_account_deletion_status(uid)
    if account_deletion_blocks_access(status):
        raise AccountDeletionAccessBlocked(status or 'unknown')


async def _require_account_deletion_access_async(uid: str) -> None:
    await run_blocking(db_executor, _require_account_deletion_access, uid)


def _is_usable_vm_ip(ip: Any) -> bool:
    """True when `ip` is an address the proxy can actually dial.

    `UNRESOLVED_VM_IP` is truthy, so a stored placeholder satisfies every
    `if ip:` reader on the connect path while resolving to nothing.
    """
    return isinstance(ip, str) and bool(ip) and ip != UNRESOLVED_VM_IP


def _vm_unavailable_event(uid: str) -> Dict[str, Any]:
    """Honest user-plane copy: circuit-open gets the cooldown message instead of
    an infinite provisioning spinner."""
    try:
        doc = _get_firestore_db().collection('users').document(uid).get()
        vm = (doc.to_dict() or {}).get('agentVm', {}) if doc.exists else {}
        if circuit_open(vm, time.time()):
            return {
                "type": "error",
                "code": "agent_unavailable",
                "message": "Your agent is having trouble starting. We're looking into it — try again in about 30 minutes.",
            }
    except Exception:
        logger.warning("[agent-proxy] could not read breaker state for copy", exc_info=True)
    return {"type": "error", "code": "unavailable", "message": "Failed to start your agent. Please try again."}


async def _ensure_vm_running(uid: str, vm: Dict[str, Any], health_failed: bool = False) -> Optional[Dict[str, Any]]:
    """Ask the reconciler to restore an unavailable VM without mutating GCE here."""
    vm_name = cast(str, vm.get("vmName"))
    vm_auth_token = cast(str, vm.get("authToken", ""))

    if circuit_open(vm, time.time()):
        # 3 consecutive restart failures within the cooldown: stop hammering
        # GCE and give the user an honest error instead of an infinite spinner.
        logger.error(
            f"[agent-proxy] restart circuit OPEN for uid={uid} vm={vm_name} "
            f"failures={vm.get('restartFailures')} last={vm.get('lastRestartFailureAt')}"
        )
        return None

    requested = await run_blocking(db_executor, request_vm_start, uid, vm_name, vm_auth_token)
    if not requested:
        return None
    logger.info(
        "[agent-proxy] queued reconciler repair for uid=%s vm=%s health_failed=%s",
        uid,
        vm_name,
        health_failed,
    )
    return demoted_updating_vm(vm)


async def _wait_for_vm_healthy(vm_ip: str, auth_token: str, timeout: float = 120) -> bool:
    """Poll the VM's /health endpoint until it responds OK."""
    deadline = asyncio.get_running_loop().time() + timeout
    headers = {"Authorization": f"Bearer {auth_token}"}
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                resp = await client.get(f"http://{vm_ip}:8080/health", headers=headers)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(3)
    return False


async def _send_startup_event(websocket: WebSocket, uid: str, payload: Dict[str, Any]) -> bool:
    """Push a VM-startup status/error event to the client. False means the client is gone.

    VM startup outlives the client's keepalive window (the health wait alone is 120s), so by
    the time these events go out uvicorn may already have dropped the phone with a 1011 ping
    timeout. A vanished client is the terminal, expected end of this connection — not an ASGI
    error — and must not escape agent_ws, which is the only ownership the relay loop below
    already has and this startup path did not.
    """
    try:
        await websocket.send_text(json.dumps(payload))
        return True
    except Exception as e:
        logger.info(f"[agent-proxy] uid={uid} client gone during VM startup: {type(e).__name__}")
        return False


async def _close_client(websocket: WebSocket, uid: str, code: int, reason: str) -> None:
    """Close the client socket, tolerating a client that already went away."""
    # Record typed terminal closes so the outer session cleanup does not append a
    # misleading normal-close frame after a startup or drain failure.
    setattr(websocket, "_agent_proxy_typed_close_sent", True)
    try:
        await websocket.close(code=code, reason=reason)
    except Exception as e:
        logger.debug(f"[agent-proxy] uid={uid} close({code}) on gone client: {type(e).__name__}")


async def _admit_account_access_or_close(websocket: WebSocket, uid: str) -> bool:
    """Revalidate the durable deletion fence and close with a typed event."""
    try:
        await _require_account_deletion_access_async(uid)
        return True
    except AccountDeletionAccessBlocked:
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "account_deletion_in_progress",
                "retryable": False,
                "message": "Account deletion is in progress.",
            },
        )
        await _close_client(websocket, uid, 4005, "Account deletion in progress")
        return False
    except Exception:
        logger.error("[agent-proxy] deletion fence unavailable for uid=%s", uid, exc_info=True)
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "account_deletion_state_unavailable",
                "retryable": True,
                "message": "Account status is temporarily unavailable. Please try again.",
            },
        )
        await _close_client(websocket, uid, 1013, "Account state unavailable")
        return False


async def _ensure_vm_running_or_close(
    websocket: WebSocket, uid: str, vm: Dict[str, Any], health_failed: bool = False
) -> tuple[Optional[Dict[str, Any]], bool]:
    """Run VM repair while preserving the typed account-deletion socket close."""
    try:
        return await _ensure_vm_running(uid, vm, health_failed=health_failed), False
    except AccountDeletionAccessBlocked:
        await _admit_account_access_or_close(websocket, uid)
        return None, True


async def _prepare_vm_for_session(
    websocket: WebSocket,
    uid: str,
    vm: Dict[str, Any],
    lease_lost: asyncio.Event,
) -> Optional[Tuple[Dict[str, Any], str, str]]:
    """Resolve and verify the VM after transactional session admission."""
    vm_ip = vm.get("ip")
    vm_token = vm.get("authToken")

    if vm.get("status") == "ready" and _is_usable_vm_ip(vm_ip):
        try:
            headers = {"Authorization": f"Bearer {vm_token}"} if vm_token else {}
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"http://{vm_ip}:8080/health", headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"health returned {resp.status_code}")
        except Exception:
            logger.info(f"[agent-proxy] uid={uid} VM {vm_ip} not reachable, checking GCE...")
            await _send_startup_event(websocket, uid, {"type": "status", "message": "Starting your agent VM..."})
            candidate_vm, deletion_blocked = await _ensure_vm_running_or_close(websocket, uid, vm, health_failed=True)
            if deletion_blocked or lease_lost.is_set():
                return None
            if candidate_vm is not None and candidate_vm.get("status") == "updating":
                await _send_startup_event(
                    websocket,
                    uid,
                    {
                        "type": "error",
                        "code": "agent_vm_draining",
                        "state": "updating",
                        "retryable": True,
                        "message": "Your agent is being updated. Please retry shortly.",
                    },
                )
                await _close_client(websocket, uid, 1013, "Agent VM is updating")
                return None
            if (
                candidate_vm is None
                or candidate_vm.get("status") != "ready"
                or not _is_usable_vm_ip(candidate_vm.get("ip"))
            ):
                await _send_startup_event(websocket, uid, await run_blocking(db_executor, _vm_unavailable_event, uid))
                await _close_client(websocket, uid, 4002, "VM startup failed")
                return None
            vm = candidate_vm
            vm_ip = vm["ip"]
            vm_token = vm["authToken"]
            if not await _wait_for_vm_healthy(vm_ip, vm_token):
                await _send_startup_event(
                    websocket,
                    uid,
                    {
                        "type": "error",
                        "code": "agent_vm_not_ready",
                        "state": "provisioning",
                        "retryable": True,
                        "message": "Your agent is still starting. Please try again shortly.",
                    },
                )
                await _close_client(websocket, uid, 4003, "VM not healthy")
                return None
    else:
        await _send_startup_event(websocket, uid, {"type": "status", "message": "Starting your agent VM..."})
        candidate_vm, deletion_blocked = await _ensure_vm_running_or_close(websocket, uid, vm)
        if deletion_blocked or lease_lost.is_set():
            return None
        if candidate_vm is not None and candidate_vm.get("status") == "updating":
            await _send_startup_event(
                websocket,
                uid,
                {
                    "type": "error",
                    "code": "agent_vm_draining",
                    "state": "updating",
                    "retryable": True,
                    "message": "Your agent is being updated. Please retry shortly.",
                },
            )
            await _close_client(websocket, uid, 1013, "Agent VM is updating")
            return None
        if (
            candidate_vm is None
            or candidate_vm.get("status") != "ready"
            or not _is_usable_vm_ip(candidate_vm.get("ip"))
        ):
            await _send_startup_event(websocket, uid, await run_blocking(db_executor, _vm_unavailable_event, uid))
            await _close_client(websocket, uid, 4002, "VM startup failed")
            return None
        vm = candidate_vm
        vm_ip = vm["ip"]
        vm_token = vm["authToken"]
        if not await _wait_for_vm_healthy(vm_ip, vm_token):
            await _send_startup_event(
                websocket,
                uid,
                {
                    "type": "error",
                    "code": "agent_vm_not_ready",
                    "state": "provisioning",
                    "retryable": True,
                    "message": "Your agent is still starting. Please try again shortly.",
                },
            )
            await _close_client(websocket, uid, 4003, "VM not healthy")
            return None

    if lease_lost.is_set():
        return None
    return vm, str(vm_ip), str(vm_token)


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
    client = _get_firestore_db()
    user_ref = client.collection('users').document(uid)
    _create_chat_session_if_allowed_txn(
        client.transaction(),
        client.collection('account_deletions').document(uid),
        user_ref.collection('chat_sessions').document(session_data['id']),
        session_data,
    )
    return session_data


@transactional
def _create_chat_session_if_allowed_txn(
    transaction: Any, deletion_ref: Any, session_ref: Any, data: Dict[str, Any]
) -> None:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get('wipe_status') if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        raise AccountDeletionAccessBlocked(status or 'unknown')
    transaction.set(session_ref, data)


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
    client = _get_firestore_db()
    user_ref = client.collection('users').document(uid)
    _save_message_if_allowed_txn(
        client.transaction(),
        client.collection('account_deletions').document(uid),
        user_ref.collection('messages').document(msg_id),
        user_ref.collection('chat_sessions').document(chat_session_id),
        msg_data,
        msg_id,
    )


@transactional
def _save_message_if_allowed_txn(
    transaction: Any,
    deletion_ref: Any,
    message_ref: Any,
    session_ref: Any,
    message: Dict[str, Any],
    message_id: str,
) -> None:
    """Atomically fence late message writes against deletion admission."""
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get('wipe_status') if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        raise AccountDeletionAccessBlocked(status or 'unknown')
    transaction.set(message_ref, message)
    transaction.set(session_ref, {'message_ids': ArrayUnion([message_id])}, merge=True)


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


async def _prepare_first_query_prompt(uid: str, chat_session_id: str, prompt: str, vm_session_active: bool) -> str:
    """Prompt to send the VM for the first query of a connection.

    The VM keeps its Claude session (and full conversation context) alive across
    reconnects and announces it with a ``session_state`` hello on connect. When that
    session is already active, re-injecting the last-N Firestore history duplicates
    context the live session already holds (wasted tokens, muddled context) — so seed
    history only for a fresh (inactive) session. Skipping the fetch too avoids a
    needless Firestore read on every mobile reconnect.
    """
    if vm_session_active:
        return prompt
    history = await run_blocking(db_executor, _fetch_chat_history, uid, chat_session_id)
    return _build_prompt_with_history(prompt, history)


async def _prepare_first_query_prompt_with_fallback(
    uid: str, chat_session_id: str, prompt: str, vm_session_active: bool
) -> str:
    """Keep history seeding failure isolated from per-query prompt metadata."""
    try:
        return await _prepare_first_query_prompt(uid, chat_session_id, prompt, vm_session_active)
    except Exception:
        logger.error(
            "[agent-proxy] uid=%s failed to seed first-query history; forwarding the raw prompt", uid, exc_info=True
        )
        return prompt


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

    try:
        await _require_account_deletion_access_async(uid)
    except AccountDeletionAccessBlocked:
        await websocket.accept()
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "account_deletion_in_progress",
                "retryable": False,
                "message": "Account deletion is in progress.",
            },
        )
        await _close_client(websocket, uid, 4005, "Account deletion in progress")
        return
    except Exception:
        logger.error("[agent-proxy] deletion fence unavailable for uid=%s", uid, exc_info=True)
        await websocket.accept()
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "account_deletion_state_unavailable",
                "retryable": True,
                "message": "Account status is temporarily unavailable. Please try again.",
            },
        )
        await _close_client(websocket, uid, 1013, "Account state unavailable")
        return
    # Look up the user's agent VM and data protection level
    vm, data_protection_level = await run_blocking(db_executor, _get_user_context, uid)
    if not vm:
        logger.warning(f"[agent-proxy] WS rejected: uid={uid} no VM")
        await websocket.accept()
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "agent_vm_not_ready",
                "state": "not_provisioned",
                "retryable": True,
                "message": "Your agent is still being prepared. Please try again shortly.",
            },
        )
        await _close_client(websocket, uid, 4002, "Agent VM not ready")
        return

    # A reconciler drain prevents new sessions while allowing already leased
    # sessions to finish.  The lease is re-read after readiness because a drain
    # can begin while a stopped VM is being started.
    if reconcile_requested(vm):
        # An idle-stop lease uses the same drain fence. Preserve this user's
        # demand before rejecting the socket so the reconciler starts the VM
        # after the stop operation releases its lease.
        try:
            await _ensure_vm_running(uid, vm)
        except Exception:
            logger.warning("[agent-proxy] uid=%s could not queue reconciler demand while draining", uid, exc_info=True)
        await websocket.accept()
        await _send_startup_event(
            websocket,
            uid,
            {
                "type": "error",
                "code": "agent_vm_draining",
                "state": "draining",
                "retryable": True,
                "message": "Your agent is being updated. Please retry shortly.",
            },
        )
        await _close_client(websocket, uid, 1013, "Agent VM is draining")
        return

    # Accept WebSocket first so we can send status messages during VM startup
    await websocket.accept()

    # The marker may have changed while the user/VM document was read. Check
    # again before any GCE lifecycle call can start or mutate owner state.
    if not await _admit_account_access_or_close(websocket, uid):
        return

    lease_id = uuid.uuid4().hex
    lease_claimed = False
    lease_lost = asyncio.Event()
    lease_heartbeat_task: Optional[asyncio.Task[None]] = None
    active_vm_ws: Any = None

    async def session_lease_heartbeat() -> None:
        consecutive_failures_started_at: float | None = None
        while True:
            await asyncio.sleep(30)
            try:
                alive = await run_blocking(db_executor, heartbeat_session_lease, uid, lease_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient Firestore failure is not evidence that the lease
                # is gone.  However, if heartbeat errors persist longer than the
                # lease TTL, the Firestore record will expire and the reconciler
                # can see zero active sessions while the WebSocket stays open.
                # Fail closed before that happens.
                now = time.monotonic()
                if consecutive_failures_started_at is None:
                    consecutive_failures_started_at = now
                elif now - consecutive_failures_started_at >= SESSION_LEASE_TTL_SECONDS:
                    logger.error(
                        "[agent-proxy] uid=%s session lease heartbeat failed for %ds (>= TTL %ds); failing closed",
                        uid,
                        int(now - consecutive_failures_started_at),
                        SESSION_LEASE_TTL_SECONDS,
                    )
                    lease_lost.set()
                    await _send_startup_event(
                        websocket,
                        uid,
                        {
                            "type": "error",
                            "code": "agent_vm_draining",
                            "state": "draining",
                            "retryable": True,
                            "message": "Your agent is being updated. Please retry shortly.",
                        },
                    )
                    if active_vm_ws is not None:
                        try:
                            await active_vm_ws.close()
                        except Exception:
                            pass
                    await _close_client(websocket, uid, 1013, "Agent VM is draining")
                    return
                logger.warning(f"[agent-proxy] uid={uid} session lease heartbeat unavailable", exc_info=True)
                continue
            consecutive_failures_started_at = None
            if alive:
                continue
            lease_lost.set()
            await _send_startup_event(
                websocket,
                uid,
                {
                    "type": "error",
                    "code": "agent_vm_draining",
                    "state": "draining",
                    "retryable": True,
                    "message": "Your agent is being updated. Please retry shortly.",
                },
            )
            if active_vm_ws is not None:
                try:
                    await active_vm_ws.close()
                except Exception:
                    pass
            await _close_client(websocket, uid, 1013, "Agent VM is draining")
            return

    async def release_claimed_session() -> None:
        nonlocal lease_claimed
        if lease_heartbeat_task is not None and not lease_heartbeat_task.done():
            lease_heartbeat_task.cancel()
            await asyncio.gather(lease_heartbeat_task, return_exceptions=True)
        if lease_claimed:
            try:
                await run_blocking(db_executor, release_session_lease, uid, lease_id)
            except Exception:
                logger.warning(f"[agent-proxy] uid={uid} failed to release session lease", exc_info=True)
            finally:
                lease_claimed = False

    try:
        if AGENT_VM_SESSION_LEASES_ENABLED:
            lease_claimed = await run_blocking(
                db_executor,
                claim_session_lease,
                uid,
                str(vm.get("vmName") or ""),
                str(vm.get("authToken") or ""),
                lease_id,
            )
            if not lease_claimed:
                lease_lost.set()
                # A conflicting idle-stop/reconcile lease denied admission.
                # Register demand instead of leaving the owner stopped after
                # that lease completes.
                await _ensure_vm_running(uid, vm)
                await _send_startup_event(
                    websocket,
                    uid,
                    {
                        "type": "error",
                        "code": "agent_vm_draining",
                        "state": "draining",
                        "retryable": True,
                        "message": "Your agent is being updated. Please retry shortly.",
                    },
                )
                await _close_client(websocket, uid, 1013, "Agent VM is draining")
                return
            lease_heartbeat_task = asyncio.create_task(session_lease_heartbeat(), name=f"ws:{uid}:lease-heartbeat")

        prepared = await _prepare_vm_for_session(websocket, uid, vm, lease_lost)
        if prepared is None:
            return
        vm, vm_ip, vm_token = prepared
        vm_uri = f"ws://{vm_ip}:8080/ws?token={vm_token}"

        if not await _admit_account_access_or_close(websocket, uid):
            return
        try:
            chat_session = await run_blocking(db_executor, _get_or_create_chat_session, uid)
        except AccountDeletionAccessBlocked:
            await _admit_account_access_or_close(websocket, uid)
            return
        chat_session_id = chat_session['id']

        logger.info(f"[agent-proxy] uid={uid} connecting to vm={vm_ip}")

        async def _connect_vm_with_retry() -> Any:
            """User-blocking connect: retry transient failures with progress events."""
            for attempt in range(1, 4):
                try:
                    return await websockets.connect(vm_uri, ping_interval=600, ping_timeout=600)
                except Exception as e:
                    if classify_error(e) != "transient" or attempt == 3:
                        raise
                    logger.warning(
                        f"[agent-proxy] uid={uid} vm connect attempt {attempt} failed, retrying", exc_info=True
                    )
                    try:
                        await websocket.send_text(
                            json.dumps({"type": "status", "message": "Connecting to your agent…"})
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(attempt)

        @asynccontextmanager
        async def _connected_vm() -> AsyncIterator[Any]:
            vm_ws = await _connect_vm_with_retry()
            try:
                yield vm_ws
            finally:
                await vm_ws.close()

        async with _connected_vm() as vm_ws:
            active_vm_ws = vm_ws
            logger.info(f"[agent-proxy] uid={uid} connected")

            async def session_access_allowed() -> bool:
                allowed = await _admit_account_access_or_close(websocket, uid)
                if not allowed:
                    try:
                        await vm_ws.close()
                    except Exception:
                        pass
                return allowed

            # Send Firebase token to VM so it can fetch backend tools (calendar, gmail, etc.)
            if not await session_access_allowed():
                return
            for auth_attempt in (1, 2):
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        response = await client.post(
                            f"http://{vm_ip}:8080/auth?token={vm_token}",
                            json={"firebaseToken": token},
                        )
                        response.raise_for_status()
                        logger.info(f"[agent-proxy] uid={uid} sent Firebase token to VM")
                    break
                except Exception:
                    if auth_attempt == 2:
                        # Mode change: session proceeds without backend tools.
                        logger.error(f"[agent-proxy] uid={uid} failed to send Firebase token", exc_info=True)
                        try:
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "status", "message": "Some connected tools are unavailable right now."}
                                )
                            )
                        except Exception:
                            pass
                    else:
                        await asyncio.sleep(2)

            first_query_sent = False
            # Captured from the VM's session_state hello (see vm_to_phone): whether the
            # VM already has a live Claude session carrying this conversation's context.
            vm_session_active = False
            vm_hello_received = asyncio.Event()
            time_zone = websocket.headers.get("x-timezone")

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
                        if not await session_access_allowed():
                            return
                        try:
                            data = json.loads(msg)
                            if data.get('type') == 'query':
                                prompt = data.get('prompt', '')
                                if not isinstance(prompt, str):
                                    # Preserve the VM's Invalid query response instead of
                                    # coercing malformed client data into a model request.
                                    logger.warning(f"[agent-proxy] uid={uid} rejected non-string query prompt")
                                    await vm_ws.send(msg)
                                    continue
                                prompt_to_forward = prompt
                                if not first_query_sent:
                                    first_query_sent = True
                                    # Seed history only when the VM has no live session. Wait
                                    # briefly for its session_state hello (sent on connect); on
                                    # timeout, seed anyway (amnesia is worse than a duplicate).
                                    try:
                                        await asyncio.wait_for(vm_hello_received.wait(), timeout=VM_HELLO_TIMEOUT)
                                    except asyncio.TimeoutError:
                                        logger.warning(
                                            f"[agent-proxy] uid={uid} no session_state hello before first query; seeding history"
                                        )
                                    prompt_to_forward = await _prepare_first_query_prompt_with_fallback(
                                        uid, chat_session_id, prompt, vm_session_active
                                    )
                                    logger.info(
                                        f"[agent-proxy] uid={uid} first query (vm_session_active={vm_session_active}, "
                                        f"history_seeded={prompt_to_forward != prompt})"
                                    )
                                else:
                                    # Subsequent queries: Claude session already has context
                                    logger.info(f"[agent-proxy] uid={uid} follow-up query (session has context)")
                                query_time_zone = data.pop('time_zone', None)
                                if query_time_zone is not None and not isinstance(query_time_zone, str):
                                    query_time_zone = ''
                                effective_time_zone = query_time_zone if query_time_zone is not None else time_zone
                                data['prompt'] = current_time_prompt(
                                    prompt_to_forward, effective_time_zone, now=_utc_now()
                                )
                                msg = json.dumps(data)
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
                        except json.JSONDecodeError:
                            logger.debug(f"[agent-proxy] uid={uid} non-JSON phone message forwarded raw")
                        except Exception:
                            # History injection or save enqueue failed — the raw
                            # message still forwards, but this is a silent mode
                            # change worth full internal detail.
                            logger.error(f"[agent-proxy] uid={uid} failed to process phone message", exc_info=True)
                        await vm_ws.send(msg)
                except WebSocketDisconnect:
                    logger.debug(f"[agent-proxy] uid={uid} phone disconnected")
                except Exception:
                    logger.error(f"[agent-proxy] uid={uid} phone_to_vm pump died", exc_info=True)

            async def vm_to_phone():
                nonlocal vm_session_active
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
                            if evt_type == 'session_state':
                                # The VM's connect hello — records whether it already has a
                                # live session so the first query knows to skip history seeding.
                                vm_session_active = bool(event.get('active'))
                                vm_hello_received.set()
                            elif evt_type == 'text_delta':
                                response_text += evt_text
                            elif evt_type == 'result':
                                # The terminal result is authoritative, including deltas
                                # emitted while a reconnecting phone was detached.
                                if evt_text:
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
                    logger.error(f"[agent-proxy] uid={uid} vm_to_phone pump died", exc_info=True)
                finally:
                    # Save any unsaved partial response (connection dropped mid-query)
                    if response_text.strip():
                        # Use await here since we're in finally — connection is closing anyway
                        await _save_ai_response(uid, response_text.strip(), chat_session_id, data_protection_level)

            async def keepalive_pinger():
                """Periodically ping the VM to prevent idle auto-stop during active WS."""
                ping_failures = 0
                async with httpx.AsyncClient(timeout=5) as client:
                    while True:
                        await asyncio.sleep(VM_KEEPALIVE_INTERVAL)
                        try:
                            response = await client.post(f"http://{vm_ip}:8080/ping?token={vm_token}")
                            response.raise_for_status()
                            ping_failures = 0
                        except Exception:
                            ping_failures += 1
                            if ping_failures == 3:
                                logger.warning(
                                    f"[agent-proxy] uid={uid} keepalive failed 3x consecutively", exc_info=True
                                )

            async def account_deletion_watcher():
                """Terminate an idle relay promptly when deletion is admitted."""
                while True:
                    await asyncio.sleep(ACCOUNT_DELETION_IDLE_RECHECK_INTERVAL)
                    if not await session_access_allowed():
                        return

            t1 = asyncio.create_task(phone_to_vm(), name=f"ws:{uid}:phone_to_vm")
            t2 = asyncio.create_task(vm_to_phone(), name=f"ws:{uid}:vm_to_phone")
            t3 = asyncio.create_task(keepalive_pinger(), name=f"ws:{uid}:keepalive")
            t4 = asyncio.create_task(account_deletion_watcher(), name=f"ws:{uid}:deletion-fence")
            session_tasks = [t1, t2, t3, t4]
            if lease_heartbeat_task is not None:
                session_tasks.append(lease_heartbeat_task)
            done, pending = await asyncio.wait(session_tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)

    except Exception as e:
        category = classify_error(e)
        logger.error(f"[agent-proxy] uid={uid} vm session failed category={category}", exc_info=True)
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "code": "unavailable" if category in ("transient", "unavailable") else category,
                        "message": "Couldn't reach your agent. Please try again.",
                    }
                )
            )
        except Exception:
            pass
    finally:
        await release_claimed_session()
        if not lease_lost.is_set() and not getattr(websocket, "_agent_proxy_typed_close_sent", False):
            try:
                await websocket.close(code=1000, reason="Session ended")
            except Exception:
                pass
        logger.info(f"[agent-proxy] uid={uid} disconnected")
