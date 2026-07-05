"""Unit tests for POST /v1/agent/vm-stop.

routers.agent_vm imports cleanly, so the async handler is driven via asyncio.run with the
GCE token, Firestore, and httpx calls mocked (no network). run_blocking is replaced with a
passthrough so the offloaded sync helpers run inline. Uses monkeypatch (no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import asyncio

import httpx
import pytest

from routers import agent_vm


async def _fake_run_blocking(executor, fn, *args):
    return fn(*args)


class _FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._resp


def _wire(monkeypatch, vm, resp=None, exc=None):
    """Wire the module seams; return the list of (uid, status) status writes."""
    monkeypatch.setattr(agent_vm, "run_blocking", _fake_run_blocking)
    monkeypatch.setattr(agent_vm, "get_agent_vm", lambda uid: vm)
    monkeypatch.setattr(agent_vm, "_get_gce_access_token", lambda: "fake-token")
    status_writes = []
    monkeypatch.setattr(agent_vm, "_set_vm_status", lambda uid, status: status_writes.append((uid, status)))
    if resp is not None or exc is not None:
        monkeypatch.setattr(agent_vm.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(resp=resp, exc=exc))
    return status_writes


def test_no_vm(monkeypatch):
    _wire(monkeypatch, vm=None)
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": False, "reason": "no_vm"}


def test_missing_vm_name(monkeypatch):
    _wire(monkeypatch, vm={"zone": "us-central1-a", "status": "ready"})
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": False, "reason": "missing_vm_info"}


def test_already_stopped_is_idempotent(monkeypatch):
    writes = _wire(monkeypatch, vm={"vmName": "vm1", "status": "stopped"})
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": True, "status": "stopped"}
    assert writes == []  # no GCE call, no extra status write


def test_success_stops_and_records_status(monkeypatch):
    writes = _wire(monkeypatch, vm={"vmName": "vm1", "zone": "z", "status": "ready"}, resp=_FakeResp(200))
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": True, "status": "stopped"}
    assert writes == [("u1", "stopped")]


def test_gce_non_2xx_is_stop_failed_without_status_write(monkeypatch):
    writes = _wire(monkeypatch, vm={"vmName": "vm1", "zone": "z", "status": "ready"}, resp=_FakeResp(500, "boom"))
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": False, "reason": "stop_failed"}
    assert writes == []


def test_httpx_error_is_unreachable(monkeypatch):
    _wire(monkeypatch, vm={"vmName": "vm1", "zone": "z", "status": "ready"}, exc=httpx.ConnectError("down"))
    assert asyncio.run(agent_vm.stop_agent_vm(uid="u1")) == {"ok": False, "reason": "unreachable"}
