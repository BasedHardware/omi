import ast
import importlib.util
import threading
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import firebase_admin
import pytest
from firebase_admin import firestore

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENT_PROXY_DIR = BACKEND_DIR / "agent-proxy"


@pytest.fixture
def agent_proxy(monkeypatch) -> ModuleType:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
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


@pytest.mark.asyncio
async def test_gce_status_refreshes_credentials_off_the_event_loop(agent_proxy, monkeypatch):
    event_loop_thread = threading.get_ident()
    credential_thread = None
    client = _AsyncClient()
    executor_calls = []
    shared_run_blocking = agent_proxy.run_blocking

    def refresh_credentials():
        nonlocal credential_thread
        credential_thread = threading.get_ident()
        return "test-token"

    async def tracking_run_blocking(executor, func, *args, **kwargs):
        executor_calls.append(executor)
        return await shared_run_blocking(executor, func, *args, **kwargs)

    monkeypatch.setattr(agent_proxy, "_get_gce_access_token", refresh_credentials)
    monkeypatch.setattr(agent_proxy, "run_blocking", tracking_run_blocking)
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", lambda: client)

    status = await agent_proxy._check_gce_status("omi-agent-test", "us-central1-a")

    assert status == "RUNNING"
    assert credential_thread is not None
    assert credential_thread != event_loop_thread
    assert executor_calls == [agent_proxy.critical_executor]
    assert client.headers == {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_gce_credential_refresh_failure_still_propagates(agent_proxy, monkeypatch):
    def refresh_credentials():
        raise RuntimeError("credential refresh failed")

    monkeypatch.setattr(agent_proxy, "_get_gce_access_token", refresh_credentials)

    with pytest.raises(RuntimeError, match="credential refresh failed"):
        await agent_proxy._check_gce_status("omi-agent-test", "us-central1-a")


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


def test_agent_proxy_image_packages_the_shared_executor_boundary():
    dockerfile = (AGENT_PROXY_DIR / "Dockerfile").read_text(encoding="utf-8")

    package_copy = "COPY backend/utils/executors.py ./utils/executors.py"
    entrypoint_copy = "COPY backend/agent-proxy/main.py ."
    assert "COPY backend/utils/__init__.py ./utils/__init__.py" in dockerfile
    assert package_copy in dockerfile
    assert dockerfile.index(package_copy) < dockerfile.index(entrypoint_copy)


def test_static_all_async_gce_refreshes_use_the_critical_executor():
    tree = ast.parse((AGENT_PROXY_DIR / "main.py").read_text(encoding="utf-8"))
    direct_refresh_calls = []
    wrapped_refresh_calls = []

    for function in (node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)):
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            if isinstance(call.func, ast.Name) and call.func.id == "_get_gce_access_token":
                direct_refresh_calls.append(call)
            if not isinstance(call.func, ast.Name) or call.func.id != "run_blocking" or len(call.args) < 2:
                continue
            executor, target = call.args[:2]
            if (
                isinstance(executor, ast.Name)
                and executor.id == "critical_executor"
                and isinstance(target, ast.Name)
                and target.id == "_get_gce_access_token"
            ):
                wrapped_refresh_calls.append(call)

    assert direct_refresh_calls == []
    assert len(wrapped_refresh_calls) == 6


def test_static_agent_proxy_uses_managed_blocking_and_named_lifetime_tasks():
    source = (AGENT_PROXY_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "asyncio.to_thread" not in source
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "create_task":
            continue
        assert any(keyword.arg == "name" for keyword in call.keywords)
