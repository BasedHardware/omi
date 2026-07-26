import importlib
import asyncio
import json
import os
import sqlite3
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "agent_vm"


def load_app(tmp_path: Path):
    os.environ["AUTH_TOKEN"] = "test-token"
    os.environ["DB_PATH"] = str(tmp_path / "omi.db")
    sys.path.insert(0, str(SERVICE))
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    return module.app, module


def test_health_is_unauthenticated_and_reports_database_state(tmp_path: Path) -> None:
    app, _ = load_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["databaseReady"] is False


def test_http_protocol_requires_vm_token(tmp_path: Path) -> None:
    app, _ = load_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/upload", content=b"x").status_code == 401
        assert client.post("/auth", json={"firebaseToken": "firebase"}).status_code == 401
        assert client.post("/ping").status_code == 401
        assert client.post("/sync", json={"table": "screenshots", "rows": [{"id": "1"}]}).status_code == 401
        assert client.post("/auth?token=test-token", json={}).status_code == 400
        assert client.post("/ping?token=test-token").json() == {"status": "ok"}


def test_websocket_prewarm_query_and_stop_use_one_connection_session(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    calls = []

    class Session:
        def __init__(self, _):
            return None

        async def prewarm(self):
            calls.append("prewarm")
            return True

        async def query(self, prompt):
            calls.append(("query", prompt))

        async def stop(self):
            calls.append("stop")

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(module, "AgentSession", Session)
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=test-token") as websocket:
            assert websocket.receive_json() == {"type": "init", "sessionId": ""}
            websocket.send_json({"type": "prewarm"})
            assert websocket.receive_json() == {"type": "prewarm_ack", "success": True}
            websocket.send_json({"type": "query", "prompt": "hello"})
            websocket.send_json({"type": "stop"})

    assert calls == ["prewarm", ("query", "hello"), "stop", "close"]


def test_dynamic_backend_tool_request_uses_authenticated_protocol(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": "done"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return Response()

    module.runtime.firebase_token = "firebase-token"
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())
    assert asyncio.run(module.execute_backend_tool("get_calendar_events", {"days": 7})) == "done"
    assert captured["url"] == "https://api.omi.me/v1/agent/execute-tool"
    assert captured["headers"] == {"Authorization": "Bearer firebase-token"}
    assert captured["json"] == {"tool_name": "get_calendar_events", "params": {"days": 7}}


def test_execute_sql_serializes_sqlite_rows(tmp_path: Path) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT, appName TEXT)")
    connection.execute("INSERT INTO screenshots VALUES ('one', 'Safari')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    assert json.loads(module.execute_sql("SELECT id, appName FROM screenshots")) == {
        "rows": [{"id": "one", "appName": "Safari"}],
        "count": 1,
    }


def test_dynamic_tool_keeps_complete_json_schema_and_announces_sdk_session(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    sqlite3.connect(module.runtime.db_path).close()
    assert module.runtime.open_database()
    schema = {
        "type": "object",
        "properties": {"days": {"type": "integer", "minimum": 1}},
        "required": ["days"],
        "additionalProperties": False,
    }
    module.runtime.backend_tools = [{"name": "get_calendar_events", "description": "Calendar", "parameters": schema}]
    captured = {}

    def tool(name, _description, input_schema):
        captured[name] = input_schema
        return lambda function: function

    class Client:
        def __init__(self, **_):
            return None

        async def connect(self):
            return None

        async def query(self, _):
            return None

        async def disconnect(self):
            return None

        async def receive_response(self):
            yield {"type": "system", "session_id": "sdk-session"}
            yield {"type": "result", "subtype": "success", "result": "", "total_cost_usd": 0}

    fake_sdk = types.SimpleNamespace(
        ClaudeAgentOptions=lambda **kwargs: kwargs,
        ClaudeSDKClient=Client,
        create_sdk_mcp_server=lambda *_args, **_kwargs: object(),
        tool=tool,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    class Socket:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    async def run():
        socket = Socket()
        session = module.AgentSession(socket)
        assert await session.prewarm()
        await session.close()
        return socket.events

    events = asyncio.run(run())
    assert captured["get_calendar_events"] == schema
    assert {"type": "init", "sessionId": "sdk-session"} in events
