import asyncio
import base64
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import types
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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


def test_signed_update_manifest_requires_valid_signature_and_content_hash(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    source = b"print('verified update')\n"
    manifest = json.dumps(
        {
            "path": "main.py",
            "sha256": hashlib.sha256(source).hexdigest(),
            "version": "2026.07.28.1",
        },
        separators=(",", ":"),
    ).encode()
    signing_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "AGENT_UPDATE_ED25519_PUBLIC_KEY",
        base64.b64encode(
            signing_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode(),
    )

    assert module.validate_signed_update_manifest(manifest, signing_key.sign(manifest), source) == {
        "path": "main.py",
        "version": "2026.07.28.1",
    }


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
        assert client.post("/purge-screen-activity").status_code == 401
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
    connection.execute("CREATE TABLE memories (id TEXT, content TEXT)")
    connection.execute("INSERT INTO memories VALUES ('one', 'Safari')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    assert json.loads(module.execute_sql("SELECT id, content FROM memories")) == {
        "rows": [{"id": "one", "content": "Safari"}],
        "count": 1,
    }


def test_sync_groups_rows_by_present_columns(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT)")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    with TestClient(app) as client:
        response = client.post(
            "/sync?token=test-token",
            json={
                "table": "memories",
                "rows": [
                    {"id": "one", "content": "Safari"},
                    {"id": "two", "content": "build passed"},
                    {},
                ],
            },
        )
        rows = [tuple(row) for row in module.runtime.db.execute("SELECT id, content FROM memories ORDER BY id")]

    assert response.status_code == 200
    assert response.json() == {"applied": 2, "table": "memories"}
    assert rows == [
        ("one", "Safari"),
        ("two", "build passed"),
    ]


def test_purge_screen_activity_removes_legacy_screen_tables(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE focus_sessions (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE observations (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE ocr_texts (id TEXT PRIMARY KEY, text TEXT)")
    connection.execute("CREATE TABLE ocr_occurrences (id TEXT PRIMARY KEY, text_id TEXT)")
    connection.execute("CREATE VIRTUAL TABLE ocr_texts_fts USING fts5(text)")
    connection.executemany("INSERT INTO screenshots VALUES (?)", [("s1",), ("s2",)])
    connection.execute("INSERT INTO focus_sessions VALUES ('f1')")
    connection.execute("INSERT INTO observations VALUES ('o1')")
    connection.execute("INSERT INTO ocr_texts VALUES ('t1', 'secret')")
    connection.execute("INSERT INTO ocr_occurrences VALUES ('o1', 't1')")
    connection.execute("INSERT INTO ocr_texts_fts VALUES ('secret')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    with TestClient(app) as client:
        response = client.post(
            "/sync?token=test-token",
            json={"table": "screenshots", "rows": [{"id": "s3"}]},
        )
        purge = client.post("/purge-screen-activity?token=test-token")
        remaining = [
            module.runtime.db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("screenshots", "focus_sessions", "observations")
        ]
        ocr_remaining = [
            module.runtime.db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("ocr_texts", "ocr_occurrences", "ocr_texts_fts")
        ]

    assert response.status_code == 400
    assert response.json()["detail"] == "Table 'screenshots' not in sync whitelist"
    assert purge.status_code == 200
    assert purge.json()["status"] == "ok"
    assert purge.json()["deleted"] >= 7
    assert remaining == [0, 0, 0]
    assert ocr_remaining == [0, 0, 0]


def test_agent_vm_hides_and_rejects_legacy_ocr_tables(tmp_path: Path) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT)")
    connection.execute("CREATE TABLE ocr_texts (id TEXT, text TEXT)")
    connection.execute("INSERT INTO ocr_texts VALUES ('t1', 'secret')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    assert json.loads(module.execute_sql("SELECT text FROM ocr_texts")) == {"error": "Screen activity is unavailable"}
    assert "ocr_texts:" not in module.database_schema()
    assert "memories:" in module.database_schema()


def test_agent_session_starts_without_local_database(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    options = {}

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
            yield {"type": "result", "subtype": "success", "result": "", "total_cost_usd": 0}

    def tool(*_):
        return lambda function: function

    fake_sdk = types.SimpleNamespace(
        ClaudeAgentOptions=lambda **kwargs: options.update(kwargs) or kwargs,
        ClaudeSDKClient=Client,
        create_sdk_mcp_server=lambda *_args, **_kwargs: object(),
        tool=tool,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    class Socket:
        async def send_json(self, _event):
            return None

    async def run() -> None:
        session = module.AgentSession(Socket())
        assert await session.prewarm()
        await session.close()

    asyncio.run(run())
    assert options["allowed_tools"] == ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]


def test_dynamic_tool_keeps_complete_json_schema_and_announces_sdk_session(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT)")
    connection.close()
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

    options = {}
    fake_sdk = types.SimpleNamespace(
        ClaudeAgentOptions=lambda **kwargs: options.update(kwargs) or kwargs,
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
    assert "memories:" in options["system_prompt"]
    assert "screenshots:" not in options["system_prompt"]
    assert "WebSearch" in options["allowed_tools"]


def test_agent_session_adds_configured_playwright_mcp_server(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    sqlite3.connect(module.runtime.db_path).close()
    assert module.runtime.open_database()
    monkeypatch.setenv("PLAYWRIGHT_MCP_COMMAND", "bunx")
    options = {}

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
            yield {"type": "result", "subtype": "success", "result": "", "total_cost_usd": 0}

    def tool(*_):
        return lambda function: function

    fake_sdk = types.SimpleNamespace(
        ClaudeAgentOptions=lambda **kwargs: options.update(kwargs) or kwargs,
        ClaudeSDKClient=Client,
        create_sdk_mcp_server=lambda *_args, **_kwargs: object(),
        tool=tool,
    )
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    class Socket:
        async def send_json(self, _):
            return None

    async def run():
        session = module.AgentSession(Socket())
        assert await session.prewarm()
        await session.close()

    asyncio.run(run())
    assert options["mcp_servers"]["playwright"] == {
        "type": "stdio",
        "command": "bunx",
        "args": ["@playwright/mcp", "--user-data-dir", "/app/chrome-profile", "--headless", "--no-sandbox"],
    }
