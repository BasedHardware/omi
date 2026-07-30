"""A client that vanishes during agent-VM startup must end the connection, not crash agent_ws.

``agent_ws`` accepts the client socket and only then boots/waits for the user's VM —
``_wait_for_vm_healthy`` alone polls for 120s, far past uvicorn's WebSocket keepalive
window. When the phone is dropped mid-wait (``sent 1011 keepalive ping timeout``), the
startup path's unguarded ``send_text``/``close`` raised ``WebSocketDisconnect`` straight
out of the handler: 24 "Exception in ASGI application" tracebacks per day on prod
agent-proxy, all at the "Agent VM is not responding" send. The relay loop below already
owned this (``except Exception`` + guarded close); the startup path did not.
"""

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import firebase_admin
import pytest
from fastapi import WebSocketDisconnect
from firebase_admin import firestore

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENT_PROXY_DIR = BACKEND_DIR / "agent-proxy"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
# `agent-proxy/main.py` imports its siblings by bare name (`from resilience import ...`),
# so loading it by file path also needs its own directory importable.
if str(AGENT_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_PROXY_DIR))


@pytest.fixture
def agent_proxy(monkeypatch) -> ModuleType:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(firebase_admin, "initialize_app", MagicMock(return_value=object()))
    monkeypatch.setattr(firestore, "client", MagicMock(return_value=object()))

    spec = importlib.util.spec_from_file_location("agent_proxy_startup_client_gone_test", AGENT_PROXY_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _GoneClientWebSocket:
    """A client socket that uvicorn already dropped: every write reports the disconnect."""

    def __init__(self) -> None:
        self.headers = {"authorization": "Bearer test-token"}
        self.accepted = False
        self.send_attempts: list[str] = []
        self.close_attempts: list[int] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.send_attempts.append(text)
        raise WebSocketDisconnect(code=1006)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_attempts.append(code)
        raise WebSocketDisconnect(code=1006)


def _stub_startup(agent_proxy: ModuleType, monkeypatch, *, ensure_result, healthy: bool) -> None:
    """Drive agent_ws down the restart path with an authenticated uid and no live VM."""

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def ensure_vm_running(_uid, _vm, health_failed=False):
        return ensure_result

    async def wait_for_vm_healthy(_ip, _token, timeout=120):
        return healthy

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_verify_id_token", lambda _token: {"uid": "uid-gone"})
    monkeypatch.setattr(
        agent_proxy,
        "_get_user_context",
        lambda _uid: ({"vmName": "omi-agent-gone", "zone": "us-central1-a", "status": "stopped"}, "standard"),
    )
    monkeypatch.setattr(agent_proxy, "_ensure_vm_running", ensure_vm_running)
    monkeypatch.setattr(agent_proxy, "_wait_for_vm_healthy", wait_for_vm_healthy)
    monkeypatch.setattr(agent_proxy, "_vm_unavailable_event", lambda _uid: {"type": "error", "code": "unavailable"})
    monkeypatch.setattr(agent_proxy, "httpx", types.SimpleNamespace(AsyncClient=MagicMock()))


class TestAgentWsStartupSurvivesAGoneClient:
    async def test_unavailable_vm_does_not_raise_when_the_client_is_gone(self, agent_proxy, monkeypatch):
        _stub_startup(agent_proxy, monkeypatch, ensure_result=None, healthy=False)
        websocket = _GoneClientWebSocket()

        await agent_proxy.agent_ws(websocket)

        assert websocket.accepted
        assert websocket.close_attempts == [4002], "the connection must still be closed with its startup-failure code"

    async def test_unhealthy_vm_does_not_raise_when_the_client_is_gone(self, agent_proxy, monkeypatch):
        ready_vm = {"vmName": "omi-agent-gone", "status": "ready", "ip": "34.9.9.9", "authToken": "vm-token"}
        _stub_startup(agent_proxy, monkeypatch, ensure_result=ready_vm, healthy=False)
        websocket = _GoneClientWebSocket()

        await agent_proxy.agent_ws(websocket)

        assert [s for s in websocket.send_attempts if "not responding" in s], "the error event must still be attempted"
        assert websocket.close_attempts == [4003], "the connection must still be closed with its not-healthy code"
