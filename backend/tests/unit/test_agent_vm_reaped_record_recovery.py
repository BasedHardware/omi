"""A reaped agent VM must clear its Firestore record instead of stranding the user.

``scripts/agent_vm_reaper.py`` deletes aged TERMINATED ``omi-agent-*`` instances but leaves
``users/{uid}.agentVm`` saying ``ready`` with the deleted VM's IP. Both Python readers folded
the GCE ``404`` into ``UNKNOWN``: ``_ensure_vm_running`` returned the stale record ("STAGING,
etc. — let it be") so ``agent-proxy`` dialed a dead address and waited out the full 120s
health timeout before answering "Agent VM is not responding", and ``POST /v1/agent/vm-ensure``
reported ``ready``. Nothing repaired the record and the desktop provision endpoint reports
``exists`` while it is present, so the user's agent chat stayed broken on every later attempt
(20 distinct users in prod over 2026-07-25..26). Only a 404 may clear the record — ``UNKNOWN``
means "could not tell" and must leave a live VM's record alone.
"""

import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import firebase_admin
import pytest
from firebase_admin import firestore

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENT_PROXY_DIR = BACKEND_DIR / "agent-proxy"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
# `agent-proxy/main.py` imports its siblings by bare name (`from resilience import ...`),
# so loading it by file path also needs its own directory importable.
if str(AGENT_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_PROXY_DIR))

from tests.unit.test_tools_agent_route_response_shape import _install_route_stubs  # noqa: E402

READY_VM = {"vmName": "omi-agent-reaped", "zone": "us-central1-a", "status": "ready", "ip": "34.135.118.144"}


@pytest.fixture
def agent_proxy(monkeypatch) -> ModuleType:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(firebase_admin, "initialize_app", MagicMock(return_value=object()))
    monkeypatch.setattr(firestore, "client", MagicMock(return_value=object()))

    spec = importlib.util.spec_from_file_location("agent_proxy_reaped_record_test", AGENT_PROXY_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeUserDoc:
    def __init__(self):
        self.updates = []

    def update(self, payload):
        self.updates.append(payload)


def _stub_gce(agent_proxy, monkeypatch, instance_status_code: int, user_doc: _FakeUserDoc):
    """Point the module's GCE + Firestore seams at a fake instance and user document."""

    class Response:
        status_code = instance_status_code

        def json(self):
            return {"status": "RUNNING", "networkInterfaces": [{"accessConfigs": [{"natIP": "34.9.9.9"}]}]}

    class Client:
        def __init__(self):
            self.post_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

        async def get(self, _url, *, headers=None):
            return Response()

        async def post(self, *_args, **_kwargs):
            self.post_calls += 1
            return Response()

    client = Client()

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    db = MagicMock()
    db.collection.return_value.document.return_value = user_doc

    monkeypatch.setattr(agent_proxy, "_get_gce_access_token", lambda: "test-token")
    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "httpx", types.SimpleNamespace(AsyncClient=lambda **_kwargs: client))
    monkeypatch.setattr(agent_proxy, "_get_firestore_db", lambda: db)
    return client


class TestAgentProxyClearsReapedRecord:
    async def test_deleted_instance_clears_the_record_and_fails_fast(self, agent_proxy, monkeypatch):
        user_doc = _FakeUserDoc()
        client = _stub_gce(agent_proxy, monkeypatch, 404, user_doc)

        result = await agent_proxy._ensure_vm_running("uid-reaped", dict(READY_VM), health_failed=True)

        assert result is None, "a deleted instance must not be reported as usable"
        assert user_doc.updates == [{"agentVm": agent_proxy.DELETE_FIELD}]
        assert client.post_calls == 0, "no reset/start may be attempted against a deleted instance"

    async def test_unknown_status_leaves_the_record_alone(self, agent_proxy, monkeypatch):
        user_doc = _FakeUserDoc()
        _stub_gce(agent_proxy, monkeypatch, 500, user_doc)

        result = await agent_proxy._ensure_vm_running("uid-transient", dict(READY_VM), health_failed=False)

        assert result == READY_VM, "an unreadable GCE status must leave the record untouched"
        assert user_doc.updates == []

    async def test_restart_path_clears_the_record_when_the_instance_is_gone(self, agent_proxy, monkeypatch):
        user_doc = _FakeUserDoc()
        _stub_gce(agent_proxy, monkeypatch, 404, user_doc)
        errored_vm = dict(READY_VM, status="error")

        result = await agent_proxy._ensure_vm_running("uid-errored", errored_vm)

        assert result is None
        assert {"agentVm": agent_proxy.DELETE_FIELD} in user_doc.updates

    async def test_start_vm_and_wait_raises_vm_not_found_on_404(self, agent_proxy, monkeypatch):
        _stub_gce(agent_proxy, monkeypatch, 404, _FakeUserDoc())

        with pytest.raises(agent_proxy.VmNotFoundError):
            await agent_proxy._start_vm_and_wait("omi-agent-reaped", "us-central1-a")


@pytest.fixture
def agent_tools(monkeypatch):
    _install_route_stubs(monkeypatch)
    agentic_mod = types.ModuleType('utils.retrieval.agentic')
    agentic_mod.agent_config_context = types.SimpleNamespace(set=MagicMock())
    agentic_mod.CORE_TOOLS = []
    monkeypatch.setitem(sys.modules, 'utils.retrieval.agentic', agentic_mod)
    sys.modules.pop('routers.agent_tools', None)
    return importlib.import_module('routers.agent_tools')


class TestVmEnsureClearsReapedRecord:
    def test_deleted_instance_reports_no_vm_and_clears_the_record(self, agent_tools, monkeypatch):
        from database.users import get_agent_vm

        get_agent_vm.return_value = dict(READY_VM)
        cleared = []

        async def not_found(_vm_name, _zone):
            return "NOT_FOUND"

        monkeypatch.setattr(agent_tools, "_check_gce_status", not_found)
        monkeypatch.setattr(agent_tools, "_clear_agent_vm", cleared.append)
        background = MagicMock()

        response = asyncio.run(agent_tools.ensure_vm(background, uid="uid-reaped"))

        assert response == {"has_vm": False}
        assert cleared == ["uid-reaped"]
        background.add_task.assert_not_called()

    def test_unknown_status_keeps_the_record(self, agent_tools, monkeypatch):
        from database.users import get_agent_vm

        get_agent_vm.return_value = dict(READY_VM)
        cleared = []

        async def unknown(_vm_name, _zone):
            return "UNKNOWN"

        monkeypatch.setattr(agent_tools, "_check_gce_status", unknown)
        monkeypatch.setattr(agent_tools, "_clear_agent_vm", cleared.append)

        response = asyncio.run(agent_tools.ensure_vm(MagicMock(), uid="uid-transient"))

        assert response == {"has_vm": True, "status": "ready"}
        assert cleared == []
