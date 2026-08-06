import ast
import asyncio
import importlib.util
import json
import threading
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import firebase_admin
import pytest
from firebase_admin import firestore

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENT_PROXY_DIR = BACKEND_DIR / "agent-proxy"


@pytest.fixture
def agent_proxy(monkeypatch) -> ModuleType:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.syspath_prepend(str(AGENT_PROXY_DIR))
    initialize_app = MagicMock(return_value=object())
    firestore_client = MagicMock(return_value=object())
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize_app)
    monkeypatch.setattr(firestore, "client", firestore_client)

    spec = importlib.util.spec_from_file_location("agent_proxy_async_boundary_test", AGENT_PROXY_DIR / "main.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    initialize_app.assert_not_called()
    firestore_client.assert_not_called()
    return module


class _Response:
    status_code = 200

    def json(self):
        return {"status": "RUNNING"}

    def raise_for_status(self):
        return None


class _ErrorResponse(_Response):
    def raise_for_status(self):
        raise RuntimeError("HTTP 500")


class _AsyncClient:
    def __init__(self):
        self.headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def get(self, _url, *, headers):
        self.headers = headers
        return _Response()


class _AgentWebSocket:
    headers = {"authorization": "Bearer firebase-token"}

    def __init__(self):
        self.accepted = False
        self.sent = []
        self.closed = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, text):
        self.sent.append(text)

    async def close(self, *, code, reason):
        self.closed.append((code, reason))

    async def iter_text(self):
        yield '{"type":"query","prompt":"hello"}'


class _VMProtocol:
    def __init__(self):
        self.sent = []
        self.closed = False
        self.message_sent = asyncio.Event()
        self.hello_sent = False
        self.events = iter(
            [
                '{"type":"text_delta","text":"tail"}',
                '{"type":"result","text":"full answer tail"}',
            ]
        )

    async def send(self, message):
        self.sent.append(message)
        self.message_sent.set()

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        # The real VM announces its session state on connect, before any query — the
        # proxy waits for this hello to decide on history seeding. Emit it first so the
        # proxy doesn't block on the hello-timeout grace window.
        if not self.hello_sent:
            self.hello_sent = True
            return '{"type":"session_state","active":false}'
        await self.message_sent.wait()
        try:
            return next(self.events)
        except StopIteration:
            raise StopAsyncIteration


class _ProxyHTTPClient:
    post_calls = 0

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def get(self, _url, **_kwargs):
        return _Response()

    async def post(self, _url, **_kwargs):
        type(self).post_calls += 1
        if type(self).post_calls == 1:
            return _ErrorResponse()
        return _Response()


class _HealthyProxyHTTPClient(_ProxyHTTPClient):
    async def post(self, _url, **_kwargs):
        return _Response()


class _IdleAgentWebSocket(_AgentWebSocket):
    async def iter_text(self):
        await asyncio.Event().wait()
        if False:
            yield ""


class _IdleVMProtocol:
    def __init__(self):
        self.closed = False

    async def send(self, _message):
        return None

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_agent_ws_owns_and_closes_connected_websocket_protocol(agent_proxy, monkeypatch):
    phone_ws = _AgentWebSocket()
    vm_ws = _VMProtocol()
    _ProxyHTTPClient.post_calls = 0
    real_sleep = asyncio.sleep
    saved_messages = []

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def connect(*_args, **_kwargs):
        return vm_ws

    async def no_retry_sleep(seconds):
        if seconds == 2:
            return None
        await real_sleep(seconds)

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: ({"status": "ready", "ip": "127.0.0.1", "authToken": "vm-token"}, "standard"),
    )
    monkeypatch.setattr(agent_proxy, "_get_or_create_chat_session", lambda _uid: {"id": "session-1"})
    monkeypatch.setattr(agent_proxy, "_fetch_chat_history", lambda *_args: [])
    monkeypatch.setattr(agent_proxy, "_save_message", lambda *args: saved_messages.append(args))
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", _ProxyHTTPClient)
    monkeypatch.setattr(agent_proxy.websockets, "connect", connect)
    monkeypatch.setattr(agent_proxy.asyncio, "sleep", no_retry_sleep)

    await agent_proxy.agent_ws(phone_ws)
    await agent_proxy.drain_background_tasks(timeout=1.0)

    assert phone_ws.accepted is True
    # Query forwarded to the VM (empty history → prompt passes through unchanged; assert
    # on parsed content, not exact serialization whitespace).
    assert len(vm_ws.sent) == 1
    assert json.loads(vm_ws.sent[0]) == {"type": "query", "prompt": "hello"}
    assert vm_ws.closed is True
    assert _ProxyHTTPClient.post_calls == 2
    assert phone_ws.closed == [(1000, "Session ended")]
    assert any(args[1:3] == ("full answer tail", "ai") for args in saved_messages)


@pytest.mark.asyncio
async def test_session_admission_queues_recovery_when_a_lifecycle_lease_wins(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()
    ensure_running = AsyncMock(return_value={})

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "AGENT_VM_SESSION_LEASES_ENABLED", True)
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "stopped", "ip": None, "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "claim_session_lease", lambda *_args: False)
    monkeypatch.setattr(agent_proxy, "_ensure_vm_running", ensure_running)

    await agent_proxy.agent_ws(websocket)

    ensure_running.assert_awaited_once()
    assert json.loads(websocket.sent[-1])["code"] == "agent_vm_draining"
    assert websocket.closed == [(1013, "Agent VM is draining")]


@pytest.mark.asyncio
async def test_existing_reconciler_lease_queues_recovery_before_rejecting_socket(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()
    ensure_running = AsyncMock(return_value={})

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "running", "ip": "10.0.0.5", "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "reconcile_requested", lambda _vm: True)
    monkeypatch.setattr(agent_proxy, "_ensure_vm_running", ensure_running)

    await agent_proxy.agent_ws(websocket)

    ensure_running.assert_awaited_once()
    assert json.loads(websocket.sent[-1])["code"] == "agent_vm_draining"
    assert websocket.closed == [(1013, "Agent VM is draining")]


@pytest.mark.asyncio
async def test_existing_reconciler_lease_still_returns_typed_error_when_demand_write_fails(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def unavailable(_uid, _vm):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "running", "ip": "10.0.0.5", "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "reconcile_requested", lambda _vm: True)
    monkeypatch.setattr(agent_proxy, "_ensure_vm_running", unavailable)

    await agent_proxy.agent_ws(websocket)

    assert websocket.accepted is True
    assert json.loads(websocket.sent[-1])["code"] == "agent_vm_draining"
    assert websocket.closed == [(1013, "Agent VM is draining")]


@pytest.mark.asyncio
async def test_claimed_session_lease_is_released_when_setup_raises(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()
    released = []

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "AGENT_VM_SESSION_LEASES_ENABLED", True)
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "ready", "ip": "127.0.0.1", "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "claim_session_lease", lambda *_args: True)
    monkeypatch.setattr(agent_proxy, "release_session_lease", lambda uid, lease_id: released.append((uid, lease_id)))
    monkeypatch.setattr(agent_proxy, "_get_or_create_chat_session", MagicMock(side_effect=RuntimeError("setup failed")))
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", _HealthyProxyHTTPClient)

    await agent_proxy.agent_ws(websocket)

    assert len(released) == 1
    assert released[0][0] == "user-1"


@pytest.mark.asyncio
async def test_transient_lease_heartbeat_error_retries_then_confirmed_loss_drains_session(agent_proxy, monkeypatch):
    websocket = _IdleAgentWebSocket()
    vm_ws = _IdleVMProtocol()
    heartbeat_results = iter([RuntimeError("firestore unavailable"), False])
    heartbeat_calls = []
    released = []
    real_sleep = asyncio.sleep

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def connect(*_args, **_kwargs):
        return vm_ws

    async def task_controlled_sleep(_seconds):
        task = asyncio.current_task()
        if task is not None and task.get_name().endswith(":lease-heartbeat"):
            await real_sleep(0)
            return
        await asyncio.Event().wait()

    def heartbeat(uid, lease_id):
        heartbeat_calls.append((uid, lease_id))
        result = next(heartbeat_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(agent_proxy, "AGENT_VM_SESSION_LEASES_ENABLED", True)
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "ready", "ip": "127.0.0.1", "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "claim_session_lease", lambda *_args: True)
    monkeypatch.setattr(agent_proxy, "heartbeat_session_lease", heartbeat)
    monkeypatch.setattr(agent_proxy, "release_session_lease", lambda uid, lease_id: released.append((uid, lease_id)))
    monkeypatch.setattr(agent_proxy, "_get_or_create_chat_session", lambda _uid: {"id": "session-1"})
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", _HealthyProxyHTTPClient)
    monkeypatch.setattr(agent_proxy.websockets, "connect", connect)
    monkeypatch.setattr(agent_proxy.asyncio, "sleep", task_controlled_sleep)

    await agent_proxy.agent_ws(websocket)

    assert len(heartbeat_calls) == 2
    assert json.loads(websocket.sent[-1])["code"] == "agent_vm_draining"
    assert websocket.closed == [(1013, "Agent VM is draining")]
    assert vm_ws.closed is True
    assert len(released) == 1


@pytest.mark.asyncio
async def test_persistent_lease_heartbeat_failure_fails_closed_before_ttl_expires(agent_proxy, monkeypatch):
    """If the heartbeat errors persistently beyond the lease TTL, the session
    must close rather than keep the WebSocket open while the Firestore record
    can expire invisibly to the reconciler."""
    websocket = _IdleAgentWebSocket()
    vm_ws = _IdleVMProtocol()
    heartbeat_calls = []
    released = []
    real_sleep = asyncio.sleep

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def connect(*_args, **_kwargs):
        return vm_ws

    heartbeat_count = 0

    async def task_controlled_sleep(seconds):
        nonlocal heartbeat_count
        task = asyncio.current_task()
        if task is not None and task.get_name().endswith(":lease-heartbeat"):
            heartbeat_count += 1
            # Simulate elapsed time exceeding the TTL on the second heartbeat
            # iteration so the fail-closed guard triggers.
            if heartbeat_count >= 2:
                monkeypatch.setattr(agent_proxy.time, "monotonic", lambda: float(heartbeat_count * 100))
            await real_sleep(0)
            return
        await asyncio.Event().wait()

    def heartbeat(uid, lease_id):
        heartbeat_calls.append((uid, lease_id))
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(agent_proxy, "AGENT_VM_SESSION_LEASES_ENABLED", True)
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "user-1"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: (
            {"vmName": "omi-agent-user", "status": "ready", "ip": "127.0.0.1", "authToken": "vm-token"},
            "standard",
        ),
    )
    monkeypatch.setattr(agent_proxy, "claim_session_lease", lambda *_args: True)
    monkeypatch.setattr(agent_proxy, "heartbeat_session_lease", heartbeat)
    monkeypatch.setattr(agent_proxy, "release_session_lease", lambda uid, lease_id: released.append((uid, lease_id)))
    monkeypatch.setattr(agent_proxy, "_get_or_create_chat_session", lambda _uid: {"id": "session-1"})
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", _HealthyProxyHTTPClient)
    monkeypatch.setattr(agent_proxy.websockets, "connect", connect)
    monkeypatch.setattr(agent_proxy.asyncio, "sleep", task_controlled_sleep)

    await agent_proxy.agent_ws(websocket)

    assert len(heartbeat_calls) >= 2
    assert json.loads(websocket.sent[-1])["code"] == "agent_vm_draining"
    assert websocket.closed == [(1013, "Agent VM is draining")]
    assert vm_ws.closed is True


@pytest.mark.asyncio
async def test_first_connect_without_vm_returns_typed_retryable_not_ready(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "fresh-firebase-uid"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: None)
    monkeypatch.setattr(agent_proxy, "_get_user_context", lambda _uid: (None, "standard"))

    await agent_proxy.agent_ws(websocket)

    assert websocket.accepted is True
    assert [json.loads(event) for event in websocket.sent] == [
        {
            "type": "error",
            "code": "agent_vm_not_ready",
            "state": "not_provisioned",
            "retryable": True,
            "message": "Your agent is still being prepared. Please try again shortly.",
        }
    ]
    assert websocket.closed == [(4002, "Agent VM not ready")]


@pytest.mark.asyncio
async def test_deletion_marker_blocks_proxy_before_vm_lookup(agent_proxy, monkeypatch):
    websocket = _AgentWebSocket()
    vm_lookup = MagicMock()

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "deleted-uid"})
    monkeypatch.setattr(agent_proxy, "_get_account_deletion_status", lambda _uid: "pending")
    monkeypatch.setattr(agent_proxy, "_get_user_context", vm_lookup)

    await agent_proxy.agent_ws(websocket)

    assert websocket.accepted is True
    assert json.loads(websocket.sent[0])["code"] == "account_deletion_in_progress"
    assert websocket.closed == [(4005, "Account deletion in progress")]
    vm_lookup.assert_not_called()


def test_firestore_client_is_initialized_lazily_and_cached(agent_proxy, monkeypatch):
    initialize_app = MagicMock(return_value=object())
    firestore_client = MagicMock(return_value=object())
    monkeypatch.setattr(agent_proxy.firebase_admin, "get_app", MagicMock(side_effect=ValueError("missing app")))
    monkeypatch.setattr(agent_proxy.firebase_admin, "initialize_app", initialize_app)
    monkeypatch.setattr(agent_proxy.firestore, "client", firestore_client)
    agent_proxy._firestore_db = None

    first = agent_proxy._get_firestore_db()
    second = agent_proxy._get_firestore_db()

    assert first is second
    initialize_app.assert_called_once_with()
    firestore_client.assert_called_once_with()


def test_firebase_token_verification_uses_lazy_app_boundary(agent_proxy, monkeypatch):
    verified = {"uid": "user-1"}
    monkeypatch.setattr(agent_proxy.firebase_admin, "get_app", MagicMock(return_value=object()))
    verify_id_token = MagicMock(return_value=verified)
    monkeypatch.setattr(agent_proxy.auth, "verify_id_token", verify_id_token)

    assert agent_proxy._verify_id_token("token") == verified
    verify_id_token.assert_called_once_with("token")


@pytest.mark.asyncio
async def test_lifespan_initializes_providers_on_owned_lanes_and_drains_background_tasks(agent_proxy, monkeypatch):
    firebase_init = MagicMock()
    firestore_db = object()
    firestore_init = MagicMock(return_value=firestore_db)
    events = []

    async def tracking_run_blocking(executor, func, *args, **kwargs):
        events.append(("run_blocking", executor, func))
        return func(*args, **kwargs)

    async def tracking_drain_background_tasks(*, timeout):
        events.append(("drain_background_tasks", timeout))
        return 0

    monkeypatch.setattr(agent_proxy, "_ensure_firebase_initialized", firebase_init)
    monkeypatch.setattr(agent_proxy, "_get_firestore_db", firestore_init)
    monkeypatch.setattr(agent_proxy, "run_blocking", tracking_run_blocking)
    monkeypatch.setattr(agent_proxy, "drain_background_tasks", tracking_drain_background_tasks)

    async with agent_proxy.lifespan(agent_proxy.app):
        assert events == [
            ("run_blocking", agent_proxy.critical_executor, firebase_init),
            ("run_blocking", agent_proxy.db_executor, firestore_init),
        ]

    assert events == [
        ("run_blocking", agent_proxy.critical_executor, firebase_init),
        ("run_blocking", agent_proxy.db_executor, firestore_init),
        ("drain_background_tasks", 10.0),
    ]
    firebase_init.assert_called_once_with()
    firestore_init.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_provider", ["firebase", "firestore"])
async def test_lifespan_provider_failure_prevents_startup(agent_proxy, monkeypatch, failing_provider):
    entered = False
    drain_calls = []

    def initialize_firebase():
        if failing_provider == "firebase":
            raise RuntimeError("firebase unavailable")

    def initialize_firestore():
        if failing_provider == "firestore":
            raise RuntimeError("firestore unavailable")
        return object()

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def tracking_drain_background_tasks(*, timeout):
        drain_calls.append(timeout)
        return 0

    monkeypatch.setattr(agent_proxy, "_ensure_firebase_initialized", initialize_firebase)
    monkeypatch.setattr(agent_proxy, "_get_firestore_db", initialize_firestore)
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "drain_background_tasks", tracking_drain_background_tasks)

    with pytest.raises(RuntimeError, match=f"{failing_provider} unavailable"):
        async with agent_proxy.lifespan(agent_proxy.app):
            entered = True

    assert entered is False
    assert drain_calls == []


def test_agent_proxy_image_packages_the_shared_executor_boundary():
    dockerfile = (AGENT_PROXY_DIR / "Dockerfile").read_text(encoding="utf-8")

    package_copy = "COPY backend/utils/executors.py ./utils/executors.py"
    entrypoint_copy = "COPY backend/agent-proxy/main.py ."
    assert "COPY backend/utils/__init__.py ./utils/__init__.py" in dockerfile
    assert package_copy in dockerfile
    assert dockerfile.index(package_copy) < dockerfile.index(entrypoint_copy)


def test_agent_proxy_has_no_direct_compute_control_plane_path():
    source = (AGENT_PROXY_DIR / "main.py").read_text(encoding="utf-8")
    assert "compute.googleapis.com" not in source


def test_static_agent_proxy_uses_managed_blocking_and_named_lifetime_tasks():
    source = (AGENT_PROXY_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "asyncio.to_thread" not in source
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "create_task":
            continue
        assert any(keyword.arg == "name" for keyword in call.keywords)


def test_unresolved_vm_ip_is_not_treated_as_dialable(agent_proxy):
    assert not agent_proxy._is_usable_vm_ip(agent_proxy.UNRESOLVED_VM_IP)
    assert not agent_proxy._is_usable_vm_ip("")
    assert not agent_proxy._is_usable_vm_ip(None)
    assert agent_proxy._is_usable_vm_ip("34.121.9.4")

    # The placeholder is truthy — this is the property that made it dangerous.
    assert bool(agent_proxy.UNRESOLVED_VM_IP)


def test_agent_proxy_never_assigns_the_unresolved_ip_placeholder():
    """Only the named legacy sentinel may use the string ``unknown``."""
    source = (AGENT_PROXY_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or node.value.value != "unknown":
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        assert targets == ["UNRESOLVED_VM_IP"], f"'unknown' assigned to {targets} at line {node.lineno}"
