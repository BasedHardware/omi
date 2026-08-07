"""Unavailable Agent VMs are fenced and handed to the fleet reconciler."""

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


class TestAgentProxyRequestsReconciliation:
    async def test_unavailable_vm_is_fenced_and_deferred_to_the_reconciler(self, agent_proxy, monkeypatch):
        requests = []

        async def direct_run_blocking(_executor, function, *args, **kwargs):
            return function(*args, **kwargs)

        monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
        monkeypatch.setattr(agent_proxy, "request_vm_start", lambda *args: requests.append(args) or True)

        result = await agent_proxy._ensure_vm_running(
            "uid-reaped", {**READY_VM, "authToken": "token"}, health_failed=True
        )

        assert result == {**READY_VM, "authToken": "token", "status": "updating", "ip": None}
        assert requests == [("uid-reaped", "omi-agent-reaped", "token")]


@pytest.fixture
def agent_tools(monkeypatch):
    _install_route_stubs(monkeypatch)
    agentic_mod = types.ModuleType('utils.retrieval.agentic')
    agentic_mod.agent_config_context = types.SimpleNamespace(set=MagicMock())
    agentic_mod.CORE_TOOLS = []
    monkeypatch.setitem(sys.modules, 'utils.retrieval.agentic', agentic_mod)
    sys.modules.pop('routers.agent_tools', None)
    return importlib.import_module('routers.agent_tools')


class TestVmEnsureRequestsReconciliation:
    def test_stopped_vm_queues_a_fenced_reconciler_request(self, agent_tools, monkeypatch):
        requests = []
        monkeypatch.setattr(
            agent_tools, "get_agent_vm", lambda _uid: {**READY_VM, "status": "stopped", "authToken": "token"}
        )
        monkeypatch.setattr(agent_tools, "request_vm_start", lambda *args: requests.append(args) or True)
        background = MagicMock()

        response = asyncio.run(agent_tools.ensure_vm(background, uid="uid-reaped"))

        assert response == {"has_vm": True, "status": "updating"}
        assert requests == [("uid-reaped", "omi-agent-reaped", "token")]
        background.add_task.assert_not_called()

    def test_ready_vm_with_a_cached_ip_queues_reconciliation_demand(self, agent_tools, monkeypatch):
        requests = []
        monkeypatch.setattr(agent_tools, "get_agent_vm", lambda _uid: {**READY_VM, "authToken": "token"})
        monkeypatch.setattr(agent_tools, "request_vm_start", lambda *args: requests.append(args) or True)

        response = asyncio.run(agent_tools.ensure_vm(MagicMock(), uid="uid-transient"))

        assert response == {"has_vm": True, "status": "updating"}
        assert requests == [("uid-transient", "omi-agent-reaped", "token")]

    def test_vm_status_demotes_ready_while_reconciler_marks_missing(self, agent_tools, monkeypatch):
        monkeypatch.setattr(
            agent_tools,
            "get_agent_vm",
            lambda _uid: {
                **READY_VM,
                "authToken": "token",
                "reconcile": {"state": "missing", "missingSince": 1.0},
            },
        )

        response = agent_tools.get_vm_status(uid="uid-missing")

        assert response == {"has_vm": True, "status": "updating"}

    def test_vm_status_reports_ready_only_when_cache_is_uncontested(self, agent_tools, monkeypatch):
        monkeypatch.setattr(agent_tools, "get_agent_vm", lambda _uid: {**READY_VM, "authToken": "token"})

        response = agent_tools.get_vm_status(uid="uid-ready")

        assert response == {"has_vm": True, "status": "ready"}
