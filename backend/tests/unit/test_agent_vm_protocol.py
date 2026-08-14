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
        assert client.post("/auth?token=test-token", json={}).status_code == 400
        assert client.post("/ping?token=test-token").json() == {"status": "ok"}


def test_invalid_database_upload_preserves_open_database(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE durable (value TEXT)")
    connection.execute("INSERT INTO durable VALUES ('preserved')")
    connection.commit()
    connection.close()

    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=b"not sqlite",
            headers={"Authorization": "Bearer test-token"},
        )
        value = module.runtime.db.execute("SELECT value FROM durable").fetchone()[0]

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded database is not valid SQLite"
    assert value == "preserved"
    assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_malformed_database_validation_closes_connection_and_temp_file(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)

    class MalformedConnection:
        closed = False

        def execute(self, _statement):
            raise sqlite3.DatabaseError("malformed")

        def close(self):
            self.closed = True

    connection = MalformedConnection()
    monkeypatch.setattr(module.sqlite3, "connect", lambda *_args, **_kwargs: connection)

    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=b"not sqlite",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400
    assert connection.closed
    assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_database_integrity_check_does_not_block_event_loop(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    payload = create_database(tmp_path / "uploaded.db", "replacement", "ready")
    started = threading.Event()
    release = threading.Event()
    worker = None

    def slow_validation(_path):
        nonlocal worker
        worker = threading.current_thread()
        started.set()
        assert release.wait(2)
        return ["ok"]

    monkeypatch.setattr(module, "validate_database_integrity", slow_validation)

    class Request:
        headers = {"content-length": str(len(payload))}

        async def stream(self):
            yield payload

    async def run_upload():
        upload_task = asyncio.create_task(module.upload_database(Request()))
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.01)
        elapsed = time.monotonic() - started_at
        release.set()
        result = await upload_task
        return elapsed, result

    timer = threading.Timer(0.2, release.set)
    started_at = time.monotonic()
    timer.start()
    try:
        elapsed, result = asyncio.run(run_upload())
    finally:
        release.set()
        timer.cancel()
        module.runtime.close_database()

    assert elapsed < 0.15
    assert worker is not threading.main_thread()
    assert result == (len(payload), len(payload))


def test_database_upload_fsync_does_not_block_event_loop(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    payload = create_database(tmp_path / "uploaded.db", "replacement", "ready")
    started = threading.Event()
    release = threading.Event()
    worker = None
    calls = 0

    def slow_fsync(_path):
        nonlocal calls, worker
        calls += 1
        if calls == 1:
            worker = threading.current_thread()
            started.set()
            assert release.wait(2)

    monkeypatch.setattr(module, "fsync_file", slow_fsync)

    class Request:
        headers = {"content-length": str(len(payload))}

        async def stream(self):
            yield payload

    async def run_upload():
        upload_task = asyncio.create_task(module.upload_database(Request()))
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.01)
        elapsed = time.monotonic() - started_at
        release.set()
        result = await upload_task
        return elapsed, result

    timer = threading.Timer(0.2, release.set)
    started_at = time.monotonic()
    timer.start()
    try:
        elapsed, result = asyncio.run(run_upload())
    finally:
        release.set()
        timer.cancel()
        module.runtime.close_database()

    assert elapsed < 0.15
    assert worker is not threading.main_thread()
    assert result == (len(payload), len(payload))


def test_database_installation_is_offloaded_and_serialized_with_db_use(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")
    assert module.runtime.open_database()

    install_started = threading.Event()
    release_install = threading.Event()
    query_started = threading.Event()
    install_thread = None
    original_close = module.runtime.close_database
    original_execute_sql = module.execute_sql

    def blocking_close():
        nonlocal install_thread
        if not install_started.is_set():
            install_thread = threading.current_thread()
            install_started.set()
            assert release_install.wait(2)
        return original_close()

    def tracked_execute_sql(query):
        query_started.set()
        return original_execute_sql(query)

    monkeypatch.setattr(module.runtime, "close_database", blocking_close)
    monkeypatch.setattr(module, "execute_sql", tracked_execute_sql)

    class Request:
        headers = {"content-length": str(len(payload))}

        async def stream(self):
            yield payload

    async def run_upload():
        upload_task = asyncio.create_task(module.upload_database(Request()))
        assert await asyncio.to_thread(install_started.wait, 1)
        query_task = asyncio.create_task(asyncio.to_thread(module.execute_sql, "SELECT 1"))
        assert await asyncio.to_thread(query_started.wait, 1)
        await asyncio.sleep(0.01)
        query_blocked = not query_task.done()
        release_install.set()
        result = await upload_task
        query_result = await query_task
        return query_blocked, result, query_result

    timer = threading.Timer(0.2, release_install.set)
    started_at = time.monotonic()
    timer.start()
    try:
        query_blocked, result, query_result = asyncio.run(run_upload())
    finally:
        release_install.set()
        timer.cancel()
        module.runtime.close_database()

    assert time.monotonic() - started_at < 0.15
    assert install_thread is not threading.main_thread()
    assert query_blocked
    assert result == (len(payload), len(payload))
    assert json.loads(query_result) == {"rows": [{"1": 1}], "count": 1}


def test_cancelled_database_upload_waits_for_install_before_reusing_temp_path(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    payload = create_database(tmp_path / "uploaded.db", "replacement", "ready")
    temporary = module.runtime.db_path.with_suffix(".db.uploading")
    install_started = threading.Event()
    release_install = threading.Event()
    worker_saw_temp_path = []
    install_calls = 0

    monkeypatch.setattr(module.runtime, "require_auth", lambda _request: None)

    def blocking_install(path):
        nonlocal install_calls
        install_calls += 1
        install_started.set()
        assert release_install.wait(2)
        worker_saw_temp_path.append(path.exists())

    monkeypatch.setattr(module, "install_uploaded_database", blocking_install)

    class Request:
        headers = {"content-length": str(len(payload))}

        async def stream(self):
            yield payload

    async def run_uploads():
        first = asyncio.create_task(module.upload(Request()))
        assert await asyncio.to_thread(install_started.wait, 1)
        second = asyncio.create_task(module.upload(Request()))
        await asyncio.sleep(0.01)
        first.cancel()
        await asyncio.sleep(0.01)
        assert not first.done()
        assert not second.done()
        assert temporary.exists()
        release_install.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        result = await second
        return result

    try:
        result = asyncio.run(run_uploads())
    finally:
        release_install.set()
        module.runtime.close_database()

    assert result == {"status": "ok", "bytesReceived": len(payload), "finalSize": len(payload), "databaseReady": True}
    assert install_calls == 2
    assert worker_saw_temp_path == [True, True]
    assert not temporary.exists()


def test_valid_database_upload_atomically_replaces_open_database(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    sqlite3.connect(module.runtime.db_path).close()
    uploaded = tmp_path / "uploaded.db"
    connection = sqlite3.connect(uploaded)
    connection.execute("CREATE TABLE replacement (value TEXT)")
    connection.execute("INSERT INTO replacement VALUES ('ready')")
    connection.commit()
    connection.close()

    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=uploaded.read_bytes(),
            headers={"Authorization": "Bearer test-token"},
        )
        value = module.runtime.db.execute("SELECT value FROM replacement").fetchone()[0]

    assert response.status_code == 200
    assert value == "ready"
    assert not module.runtime.db_path.with_suffix(".db.previous").exists()


def test_database_upload_durability_order_keeps_rollback_until_new_db_is_synced(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")
    previous = module.runtime.db_path.with_suffix(".db.previous")
    temporary = module.runtime.db_path.with_suffix(".db.uploading")
    events = []
    original_fsync_file = module.fsync_file
    original_fsync_directory = module.fsync_directory
    original_replace = Path.replace
    original_unlink = Path.unlink

    def record_fsync_file(path):
        events.append(("file_fsync", Path(path)))
        original_fsync_file(path)

    def record_fsync_directory(path):
        events.append(("directory_fsync", Path(path)))
        original_fsync_directory(path)

    def record_replace(source, target):
        source_path = Path(source)
        target_path = Path(target)
        if source_path in {module.runtime.db_path, temporary}:
            events.append(("replace", source_path, target_path))
        return original_replace(source, target)

    def record_unlink(path, *args, **kwargs):
        if Path(path) == previous:
            events.append(("unlink", previous))
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(module, "fsync_file", record_fsync_file)
    monkeypatch.setattr(module, "fsync_directory", record_fsync_directory)
    monkeypatch.setattr(Path, "replace", record_replace)
    monkeypatch.setattr(Path, "unlink", record_unlink)

    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=payload,
            headers={"Authorization": "Bearer test-token"},
        )

    prior_replace = events.index(("replace", module.runtime.db_path, previous))
    uploaded_replace = events.index(("replace", temporary, module.runtime.db_path))
    rollback_unlink = max(index for index, event in enumerate(events) if event == ("unlink", previous))
    uploaded_fsync = events.index(("file_fsync", temporary))
    new_db_fsync = max(index for index, event in enumerate(events) if event == ("file_fsync", module.runtime.db_path))

    assert response.status_code == 200
    assert uploaded_fsync < prior_replace
    assert events[prior_replace + 1] == ("directory_fsync", module.runtime.db_path.parent)
    assert events[uploaded_replace + 1] == ("directory_fsync", module.runtime.db_path.parent)
    assert uploaded_replace < new_db_fsync < rollback_unlink


def test_database_upload_directory_sync_failure_restores_prior_database(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")
    previous = module.runtime.db_path.with_suffix(".db.previous")
    original_fsync_directory = module.fsync_directory
    failed = False

    def fail_after_uploaded_rename(path):
        nonlocal failed
        if not failed and module.runtime.db_path.is_file() and previous.is_file():
            failed = True
            raise OSError("power loss during database swap")
        original_fsync_directory(path)

    monkeypatch.setattr(module, "fsync_directory", fail_after_uploaded_rename)

    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        database_is_open = module.runtime.db is not None

    assert response.status_code == 400
    assert failed
    assert database_is_open
    assert read_database_value(module.runtime.db_path, "durable") == "preserved"
    assert not previous.exists()
    assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_checkpoint_failure_cleans_upload_and_preserves_prior_database(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")

    with TestClient(app) as client:
        original = module.runtime.db

        class FailingConnection:
            def execute(self, _statement):
                raise sqlite3.OperationalError("checkpoint failed")

            def close(self):
                original.close()

        module.runtime.db = FailingConnection()
        with pytest.raises(sqlite3.OperationalError, match="checkpoint failed"):
            client.post(
                "/upload?token=test-token",
                content=payload,
                headers={"Authorization": "Bearer test-token"},
            )

        assert read_database_value(module.runtime.db_path, "durable") == "preserved"
        assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_close_failure_cleans_upload_and_preserves_prior_database(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")

    with TestClient(app) as client:
        original_close = module.runtime.close_database

        def fail_close():
            raise RuntimeError("close failed")

        monkeypatch.setattr(module.runtime, "close_database", fail_close)
        try:
            with pytest.raises(RuntimeError, match="close failed"):
                client.post(
                    "/upload?token=test-token",
                    content=payload,
                    headers={"Authorization": "Bearer test-token"},
                )
        finally:
            monkeypatch.setattr(module.runtime, "close_database", original_close)

        assert read_database_value(module.runtime.db_path, "durable") == "preserved"
        assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_swap_failure_restores_prior_database_and_cleans_upload(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")
    original_replace = Path.replace

    def fail_uploaded_replace(source, target):
        if source == module.runtime.db_path.with_suffix(".db.uploading") and Path(target) == module.runtime.db_path:
            raise OSError("swap failed")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_uploaded_replace)
    with TestClient(app) as client:
        response = client.post(
            "/upload?token=test-token",
            content=payload,
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400
    assert read_database_value(module.runtime.db_path, "durable") == "preserved"
    assert not module.runtime.db_path.with_suffix(".db.uploading").exists()


def test_uploaded_database_open_failure_restores_prior_database(tmp_path: Path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    create_database(module.runtime.db_path, "durable", "preserved")
    uploaded = tmp_path / "uploaded.db"
    payload = create_database(uploaded, "replacement", "ready")
    original_open = module.runtime.open_database
    calls = 0

    def fail_uploaded_open():
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return original_open()

    with TestClient(app) as client:
        monkeypatch.setattr(module.runtime, "open_database", fail_uploaded_open)
        with pytest.raises(RuntimeError, match="Failed to open uploaded database"):
            client.post(
                "/upload?token=test-token",
                content=payload,
                headers={"Authorization": "Bearer test-token"},
            )

        assert read_database_value(module.runtime.db_path, "durable") == "preserved"
        assert not module.runtime.db_path.with_suffix(".db.uploading").exists()
        assert not module.runtime.db_path.with_suffix(".db.previous").exists()


def test_database_uploads_are_serialized(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    active = 0
    maximum = 0

    monkeypatch.setattr(module.runtime, "require_auth", lambda _request: None)

    async def fake_upload(_request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1, 1

    monkeypatch.setattr(module, "upload_database", fake_upload)

    async def run_uploads():
        await asyncio.gather(module.upload(object()), module.upload(object()))

    asyncio.run(run_uploads())

    assert maximum == 1


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
    connection.execute("CREATE TABLE screenshots (id TEXT, appName TEXT)")
    connection.execute("INSERT INTO screenshots VALUES ('one', 'Safari')")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    assert json.loads(module.execute_sql("SELECT id, appName FROM screenshots")) == {
        "rows": [{"id": "one", "appName": "Safari"}],
        "count": 1,
    }


def test_sync_groups_rows_by_present_columns(tmp_path: Path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT PRIMARY KEY, appName TEXT, ocrText TEXT)")
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    with TestClient(app) as client:
        response = client.post(
            "/sync?token=test-token",
            json={
                "table": "screenshots",
                "rows": [
                    {"id": "one", "appName": "Safari"},
                    {"id": "two", "appName": "Terminal", "ocrText": "build passed"},
                    {},
                ],
            },
        )
        rows = [
            tuple(row) for row in module.runtime.db.execute("SELECT id, appName, ocrText FROM screenshots ORDER BY id")
        ]

    assert response.status_code == 200
    assert response.json() == {"applied": 2, "table": "screenshots"}
    assert rows == [
        ("one", "Safari", None),
        ("two", "Terminal", "build passed"),
    ]


def test_dynamic_tool_keeps_complete_json_schema_and_announces_sdk_session(tmp_path: Path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute("CREATE TABLE screenshots (id TEXT)")
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
    assert "screenshots:" in options["system_prompt"]
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
