"""Authenticated finops pullers must not follow a redirect that would carry a credential."""

import asyncio
import http.client
import importlib.util
import io
import pathlib
import sys
import types
import urllib.request
import urllib.response

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"
SECRET = "vendor-secret-do-not-leak"


def load(path):
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Capture(urllib.request.BaseHandler):
    handler_order = 100

    def __init__(self):
        self.seen = []

    def https_open(self, req):
        self.seen.append((req.full_url, req.header_items()))
        headers = http.client.HTTPMessage()
        headers["Location"] = "https://evil.example/collect?echo=" + SECRET
        response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
        response.msg = "Found"
        return response

    http_open = https_open


def refuse(monkeypatch, module):
    capture = Capture()

    def build(ssl_context=None):
        return urllib.request.build_opener(module.auth_http.NoRedirect(), capture)

    monkeypatch.setattr(module.auth_http, "build_opener", build)
    return capture


def test_prometheus_redirect_does_not_send_the_credential(monkeypatch):
    prom = load(FINOPS / "pull_prometheus.py")
    capture = refuse(monkeypatch, prom)
    with pytest.raises(RuntimeError, match="prometheus redirect refused") as error:
        prom.call("https://monitor.example/api/v1", SECRET, "query_range", [("query", "up")])
    assert SECRET not in str(error.value)
    assert len(capture.seen) == 1
    assert capture.seen[0][0].startswith("https://monitor.example/")
    assert ("Authorization", "Bearer " + SECRET) in capture.seen[0][1]
    assert "evil.example" not in capture.seen[0][0]


def test_openai_redirect_does_not_send_the_credential(monkeypatch):
    admin = load(FINOPS / "vendor" / "openai_admin.py")
    capture = refuse(monkeypatch, admin)
    monkeypatch.setenv("OPENAI_ADMIN_KEY", SECRET)
    with pytest.raises(SystemExit, match="openai redirect refused") as error:
        admin.api_get("/v1/organization/costs")
    assert SECRET not in str(error.value)
    assert len(capture.seen) == 1
    assert capture.seen[0][0].startswith("https://api.openai.com/")
    assert ("Authorization", "Bearer " + SECRET) in capture.seen[0][1]
    assert "evil.example" not in capture.seen[0][0]


def test_anthropic_redirect_does_not_send_the_credential(monkeypatch):
    anthropic = load(FINOPS / "vendor" / "anthropic-platform" / "anthropic_platform.py")
    capture = refuse(monkeypatch, anthropic)
    with pytest.raises(RuntimeError, match="redirect refused") as error:
        anthropic.fetch_all("/v1/organizations/cost_report", {}, SECRET)
    assert SECRET not in str(error.value)
    assert len(capture.seen) == 1
    assert capture.seen[0][0].startswith("https://api.anthropic.com/")
    assert ("X-api-key", SECRET) in capture.seen[0][1]
    assert "evil.example" not in capture.seen[0][0]


def test_posthog_client_does_not_follow_redirects(monkeypatch):
    shim = load(FINOPS / "posthog_client_shim" / "posthog_http.py")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", httpx)
    shim._no_redirect_client(headers={"Authorization": "Bearer " + SECRET})
    assert captured["follow_redirects"] is False


def test_posthog_session_refuses_a_redirect_following_client(monkeypatch):
    shim = load(FINOPS / "posthog_client_shim" / "posthog_http.py")
    mcp = types.ModuleType("mcp")
    mcp.__path__ = []
    mcp.ClientSession = object
    client_pkg = types.ModuleType("mcp.client")
    client_pkg.__path__ = []
    stream = types.ModuleType("mcp.client.streamable_http")

    def streamablehttp_client(url, headers=None):
        raise AssertionError("redirect-following client must not be opened")

    stream.streamablehttp_client = streamablehttp_client
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", client_pkg)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", stream)
    monkeypatch.setenv("MCP_POSTHOG_API_KEY", SECRET)
    with pytest.raises(RuntimeError, match="cannot refuse redirects") as error:
        asyncio.run(shim.posthog_mcp_session())
    assert SECRET not in str(error.value)
