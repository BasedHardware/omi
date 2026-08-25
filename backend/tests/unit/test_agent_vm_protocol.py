import asyncio
import importlib
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "agent_vm"
STARTUP = SERVICE / "startup.sh"


def load_app(tmp_path: Path):
    os.environ["AUTH_TOKEN"] = "test-token"
    os.environ["DB_PATH"] = str(tmp_path / "omi.db")
    os.environ["AGENT_VM_WORKSPACE"] = str(tmp_path / "workspace")
    os.environ["STATE_RECEIPT_PATH"] = str(tmp_path / "state-receipt.json")
    sys.path.insert(0, str(SERVICE))
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    return module.app, module


def create_database(path: Path, table: str, value: str) -> bytes:
    connection = sqlite3.connect(path)
    connection.execute(f"CREATE TABLE {table} (value TEXT)")
    connection.execute(f"INSERT INTO {table} VALUES (?)", (value,))
    connection.commit()
    connection.close()
    return path.read_bytes()


def read_database_value(path: Path, table: str) -> str:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f"SELECT value FROM {table}").fetchone()[0]
    finally:
        connection.close()


def test_health_requires_vm_token_and_reports_database_state(tmp_path: Path) -> None:
    app, _ = load_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 401
        response = client.get("/health?token=test-token", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["databaseReady"] is False


def test_health_reports_state_receipt_metadata_without_receipt_contents(tmp_path: Path) -> None:
    receipt = {
        "schemaVersion": 1,
        "migrationId": "migration-1",
        "tree": {"digest": "a" * 64, "count": 2, "bytes": 12},
        "db": {"integrity": "ok"},
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    (tmp_path / "state-receipt.json").write_bytes(receipt_bytes)
    app, _ = load_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/health?token=test-token", headers={"Authorization": "Bearer test-token"})

    body = response.json()
    assert body["stateReady"] is True
    assert body["stateMigrationId"] == "migration-1"
    assert body["stateReceiptSha256"] == hashlib.sha256(receipt_bytes).hexdigest()
    assert body["stateDatabaseExpected"] is True
    assert "tree" not in body
    assert "db" not in body


def test_http_protocol_requires_vm_token(tmp_path: Path) -> None:
    app, _ = load_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/upload", content=b"x").status_code == 401
        assert client.post("/auth", json={"firebaseToken": "firebase"}).status_code == 401
        assert client.post("/ping").status_code == 401
        assert client.post("/sync", json={"table": "screenshots", "rows": [{"id": "1"}]}).status_code == 401
        assert client.post("/screen-activity-status").status_code == 401
        assert client.post("/auth?token=test-token", json={}).status_code == 400
        assert client.post("/ping?token=test-token").json() == {"status": "ok"}


def test_startup_preserves_the_runtime_backend_default_when_override_is_empty():
    source = STARTUP.read_text(encoding="utf-8")

    assert 'if [[ -n "$backend_url" ]]; then' in source
    assert 'backend_env=(--env "BACKEND_URL=$backend_url")' in source
    assert '--env BACKEND_URL="$backend_url"' not in source


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


def test_sync_bootstraps_a_fresh_vm_without_a_prior_upload(tmp_path: Path) -> None:
    """A fresh VM with no uploaded DB must still receive non-screen tables via /sync.

    Closing screen egress may leave a newly provisioned VM with no ``omi.db``
    upload at all. Incremental sync must initialize the sanitized non-screen
    schema itself so the remaining context (action_items, memories,
    transcription_*, ...) can land, while screen/OCR tables stay absent.
    """
    app, module = load_app(tmp_path)
    assert not module.runtime.db_path.is_file()
    assert module.runtime.db is None

    with TestClient(app) as client:
        response = client.post(
            "/sync?token=test-token",
            json={
                "table": "memories",
                "rows": [{"id": "one", "content": "Safari"}],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["applied"] == 1

    # The non-screen table landed and the screen data tables never got created.
    # The TestClient lifespan closes the DB on shutdown, so re-open it to inspect.
    assert module.runtime.open_database()
    tables = {
        str(row[0]) for row in module.runtime.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "memories" in tables
    assert not tables & set(module.SCREEN_DATA_TABLES)


def test_sync_creates_a_missing_whitelisted_table_on_a_loaded_database(tmp_path: Path) -> None:
    """A loaded DB missing one sync table must self-heal instead of failing forever.

    Full database upload is retired with screen egress, so the desktop can no
    longer repair a partial schema by re-uploading ``omi.db``. ``/sync`` owns
    that recovery for whitelisted non-screen tables; a non-whitelisted table is
    still rejected rather than created.
    """
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT)")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    with TestClient(app) as client:
        response = client.post(
            "/sync?token=test-token",
            json={"table": "action_items", "rows": [{"id": "one", "description": "ship"}]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["applied"] == 1

        rejected = client.post(
            "/sync?token=test-token",
            json={"table": "screenshots", "rows": [{"id": "one", "ocrText": "secret"}]},
        )
        assert rejected.status_code == 400

    assert module.runtime.open_database()
    tables = {
        str(row[0]) for row in module.runtime.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "action_items" in tables
    assert not tables & set(module.SCREEN_DATA_TABLES)


def test_execute_sql_allows_fts5_reads(tmp_path: Path) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE VIRTUAL TABLE documents USING fts5(title, body)")
    connection.executemany(
        "INSERT INTO documents (title, body) VALUES (?, ?)",
        [("one", "hello world"), ("two", "other text")],
    )
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    assert json.loads(module.execute_sql("SELECT rowid, title FROM documents WHERE documents MATCH 'hello'")) == {
        "rows": [{"rowid": 1, "title": "one"}],
        "count": 1,
    }


def test_execute_sql_clears_authorizer_after_error(tmp_path: Path) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT)")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    result = json.loads(module.execute_sql("SELECT missing FROM screenshots"))

    assert result["error"]
    module.runtime.db.execute("CREATE TABLE after_authorizer_cleanup (value TEXT)")


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM screenshots",
        "UPDATE screenshots SET id = 'changed'",
        "SELECT 1; DROP TABLE screenshots",
        "SELECT * FROM pragma_journal_mode()",
    ],
)
def test_execute_sql_denies_destructive_queries(tmp_path: Path, query: str) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT)")
    connection.execute("INSERT INTO screenshots VALUES ('one')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    result = json.loads(module.execute_sql(query))

    assert result["error"]
    assert [tuple(row) for row in module.runtime.db.execute("SELECT id FROM screenshots").fetchall()] == [("one",)]


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


def test_screen_activity_status_reports_without_deleting(tmp_path: Path) -> None:
    """Legacy screen data is reported, never destroyed.

    Purging existing records is deliberately out of scope: the VM reports what
    it holds so the desktop can fail closed, and every row stays on disk.
    """
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE focus_sessions (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE ocr_texts (id TEXT PRIMARY KEY, text TEXT)")
    connection.executemany("INSERT INTO screenshots VALUES (?)", [("s1",), ("s2",)])
    connection.execute("INSERT INTO ocr_texts VALUES ('t1', 'secret')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    with TestClient(app) as client:
        rejected = client.post(
            "/sync?token=test-token",
            json={"table": "screenshots", "rows": [{"id": "s3"}]},
        )
        status = client.post("/screen-activity-status?token=test-token")

    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "Table 'screenshots' not in sync whitelist"
    assert status.status_code == 200
    assert status.json()["present"] is True
    assert "screenshots" in status.json()["tables"]
    assert "ocr_texts" in status.json()["tables"]
    # Nothing was deleted: the rows and their tables are still there.
    assert module.runtime.open_database()
    assert module.runtime.db.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0] == 2
    assert module.runtime.db.execute("SELECT COUNT(*) FROM ocr_texts").fetchone()[0] == 1


def test_screen_activity_status_reports_absent_on_a_clean_vm(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT)")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    with TestClient(app) as client:
        status = client.post("/screen-activity-status?token=test-token")

    assert status.status_code == 200
    assert status.json()["present"] is False
    assert status.json()["tables"] == []


def test_screen_activity_status_fails_closed_on_an_existing_uninspectable_database(tmp_path: Path) -> None:
    """A corrupt omi.db is not evidence of absence.

    An older runtime reported ``present: false`` whenever the database was
    merely unopenable, which let the desktop start sync and hand over the
    Firebase token while recoverable OCR bytes were still on disk. A database
    that exists but cannot be inspected must read as present.
    """
    app, module = load_app(tmp_path)
    module.runtime.db_path.write_bytes(b"this is not a sqlite database")

    with TestClient(app) as client:
        health = client.get("/health?token=test-token")
        status = client.post("/screen-activity-status?token=test-token")

    assert health.json()["databaseReady"] is False
    assert status.status_code == 200
    assert status.json()["present"] is True
    assert status.json()["reason"] == "database_uninspectable"


def test_screen_activity_status_stays_absent_when_no_database_file_exists(tmp_path: Path) -> None:
    app, _ = load_app(tmp_path)

    with TestClient(app) as client:
        status = client.post("/screen-activity-status?token=test-token")

    assert status.status_code == 200
    assert status.json()["present"] is False


def test_upload_is_rejected_without_consuming_the_body(tmp_path: Path) -> None:
    """The retired upload route must refuse before any byte is transmitted.

    An already-shipped desktop provisioning a fresh or reaped VM still POSTs
    its full omi.db here; the rejection has to happen before the body is read
    so the screenshot/OCR bytes never leave the Mac.
    """
    _, module = load_app(tmp_path)

    class FakeRequest:
        headers = {"authorization": "Bearer test-token"}

        async def stream(self):
            raise AssertionError("the retired upload route must not read the request body")

    async def call() -> HTTPException:
        try:
            await module.upload(FakeRequest())
        except HTTPException as exc:
            return exc
        raise AssertionError("expected HTTPException")

    rejection = asyncio.run(call())

    assert rejection.status_code == 410
    assert not (tmp_path / "omi.db.uploading").exists()
    assert not (tmp_path / "omi.db").exists()


def test_purge_screen_activity_drops_every_legacy_frame_derived_table(tmp_path: Path) -> None:
    """Old-schema databases lose every frame-derived table, and only those.

    Legacy omi.db uploads carried the retired proactive-extraction schema
    (including FTS shadow tables) and the context-bucket rollup schema whose
    narrative/fact/version rows are derived from frames. The purge is what the
    reconciler requires before it may stamp ``screenPrivacyVersion``.
    """
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE focus_sessions (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE observations (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE ocr_texts (id TEXT PRIMARY KEY, text TEXT)")
    connection.execute("CREATE TABLE proactive_extractions (id TEXT PRIMARY KEY, content TEXT)")
    connection.execute("CREATE VIRTUAL TABLE proactive_extractions_fts USING fts5(content)")
    connection.execute("CREATE TABLE bucket_entries (id TEXT PRIMARY KEY, narrative TEXT)")
    connection.execute("INSERT INTO bucket_entries VALUES ('b1', 'ambient narrative')")
    connection.execute("CREATE TABLE bucket_facts (id TEXT PRIMARY KEY, evidenceText TEXT)")
    connection.execute("INSERT INTO bucket_facts VALUES ('f1', 'evidence')")
    connection.execute("CREATE TABLE bucket_versions (id INTEGER PRIMARY KEY, header TEXT)")
    connection.execute("CREATE TABLE context_buckets (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE context_visits (id INTEGER PRIMARY KEY)")
    connection.execute("CREATE TABLE subject_bindings (referenceHash TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE proactive_candidates (id TEXT PRIMARY KEY)")
    connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT)")
    connection.execute("INSERT INTO memories VALUES ('m1', 'keep me')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    with TestClient(app) as client:
        blocked_before = client.post(
            "/sync?token=test-token",
            json={"table": "proactive_extractions", "rows": [{"id": "x"}]},
        )
        purged = client.post("/purge-screen-activity?token=test-token")
        status = client.post("/screen-activity-status?token=test-token")

    assert blocked_before.status_code == 400
    assert purged.status_code == 200
    purged_tables = set(purged.json()["purged"])
    assert {
        "screenshots",
        "focus_sessions",
        "observations",
        "ocr_texts",
        "proactive_extractions",
        "bucket_entries",
        "bucket_facts",
        "bucket_versions",
        "context_buckets",
        "context_visits",
        "subject_bindings",
        "proactive_candidates",
    } <= purged_tables
    assert status.status_code == 200
    assert status.json()["present"] is False

    assert module.runtime.open_database()
    names = {
        str(row[0])
        for row in module.runtime.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert not any(module.is_screen_data_table(name) for name in names)
    assert "memories" in names
    assert module.runtime.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
    # The FTS shadow tables went with their parent virtual table.
    assert not any(name.startswith("proactive_extractions_fts") for name in names)


def test_agent_vm_hides_and_rejects_legacy_ocr_tables(tmp_path: Path) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE memories (id TEXT)")
    connection.execute("CREATE TABLE ocr_texts (id TEXT, text TEXT)")
    connection.execute("CREATE TABLE bucket_entries (id TEXT, narrative TEXT)")
    connection.execute("CREATE TABLE proactive_extractions_fts_data (id TEXT)")
    connection.execute("INSERT INTO ocr_texts VALUES ('t1', 'secret')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    assert json.loads(module.execute_sql("SELECT text FROM ocr_texts")) == {"error": "Screen activity is unavailable"}
    assert "ocr_texts:" not in module.database_schema()
    assert "memories:" in module.database_schema()
    for table in ("bucket_entries", "proactive_extractions", "proactive_extractions_fts_data"):
        query = f"SELECT id FROM {table}"
        assert json.loads(module.execute_sql(query)) == {"error": "Screen activity is unavailable"}
        assert f"{table}:" not in module.database_schema()


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
    assert options["cwd"] == str(tmp_path / "workspace")
