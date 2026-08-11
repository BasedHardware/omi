import asyncio
import base64
import copy
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import zlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

SYNC_TABLES = frozenset(
    {
        "screenshots",
        "action_items",
        "transcription_sessions",
        "transcription_segments",
        "memories",
        "staged_tasks",
        "focus_sessions",
        "observations",
        "live_notes",
        "ai_user_profiles",
        "task_dedup_log",
    }
)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024


class Runtime:
    def __init__(self) -> None:
        self.db_path = Path(os.environ.get("DB_PATH", "/root/omi-agent/data/omi.db"))
        self.workspace_path = Path(os.environ.get("AGENT_VM_WORKSPACE", "/root/omi-agent/workspace"))
        self.state_receipt_path = Path(os.environ.get("STATE_RECEIPT_PATH", "/root/omi-agent/state-receipt.json"))
        self.auth_token = os.environ.get("AUTH_TOKEN", "")
        self.backend_url = os.environ.get("BACKEND_URL", "https://api.omi.me")
        self.db: sqlite3.Connection | None = None
        self.firebase_token: str | None = None
        self.backend_tools: list[dict[str, Any]] = []
        self.started_at = time.monotonic()
        self.last_activity_at = time.monotonic()
        self.release_id = os.environ.get("AGENT_VM_RELEASE_ID", "")
        self.image_digest = os.environ.get("AGENT_VM_IMAGE_DIGEST", "")
        self.startup_sha256 = os.environ.get("AGENT_VM_STARTUP_SHA256", "")
        self.state_ready = False
        self.state_migration_id = ""
        self.state_receipt_sha256 = ""
        self.state_database_expected = False
        self.lock = threading.RLock()
        self.upload_lock = asyncio.Lock()

    def load_state_receipt(self) -> None:
        self.state_ready = False
        self.state_migration_id = ""
        self.state_receipt_sha256 = ""
        self.state_database_expected = False
        try:
            receipt_bytes = self.state_receipt_path.read_bytes()
            receipt = json.loads(receipt_bytes)
            if not isinstance(receipt, dict):
                return
            tree = receipt.get("tree")
            db = receipt.get("db")
            migration_id = receipt.get("migrationId")
            if (
                receipt.get("schemaVersion") != 1
                or not isinstance(migration_id, str)
                or not migration_id
                or not isinstance(tree, dict)
                or not isinstance(tree.get("digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", tree.get("digest", "")) is None
                or not isinstance(tree.get("count"), int)
                or isinstance(tree.get("count"), bool)
                or tree.get("count") < 0
                or not isinstance(tree.get("bytes"), int)
                or isinstance(tree.get("bytes"), bool)
                or tree.get("bytes") < 0
                or not isinstance(db, dict)
                or db.get("integrity") not in {"ok", "not_present"}
            ):
                return
        except (OSError, TypeError, ValueError):
            return
        self.state_ready = True
        self.state_migration_id = migration_id
        self.state_receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        self.state_database_expected = db.get("integrity") == "ok"

    def open_database(self) -> bool:
        if self.db is not None:
            self.close_database()
        if not self.db_path.is_file():
            return False
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.db_path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("SELECT 1")
        except sqlite3.Error:
            if connection is not None:
                connection.close()
            return False
        self.db = connection
        return True

    def close_database(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None

    def authorized(self, request: Request) -> bool:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.startswith("Bearer ") else request.query_params.get("token", "")
        return bool(self.auth_token) and token == self.auth_token

    def require_auth(self, request: Request) -> None:
        if not self.authorized(request):
            raise HTTPException(status_code=401, detail="Unauthorized")


runtime = Runtime()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    runtime.db_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.workspace_path.mkdir(parents=True, exist_ok=True)
    runtime.db_path.with_suffix(runtime.db_path.suffix + ".uploading").unlink(missing_ok=True)
    previous = runtime.db_path.with_suffix(runtime.db_path.suffix + ".previous")
    if previous.is_file() and not runtime.db_path.exists():
        previous.replace(runtime.db_path)
    runtime.load_state_receipt()
    if runtime.open_database():
        previous.unlink(missing_ok=True)
    elif previous.is_file():
        runtime.db_path.unlink(missing_ok=True)
        previous.replace(runtime.db_path)
        runtime.open_database()
    idle_task = asyncio.create_task(runtime_maintenance(), name="agent-vm-maintenance")
    try:
        yield
    finally:
        idle_task.cancel()
        await asyncio.gather(idle_task, return_exceptions=True)
        runtime.close_database()


app = FastAPI(lifespan=lifespan)


async def metadata(path: str) -> str:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(
            f"http://metadata.google.internal/computeMetadata/v1/{path}", headers={"Metadata-Flavor": "Google"}
        )
        response.raise_for_status()
        return response.text


async def stop_instance() -> None:
    """Ask the backend stop broker to stop this exact VM.

    The VM identity token is verified by the backend against the Compute Engine
    instance claims and the Firestore owner record.  Agent VMs therefore do not
    need ``compute.instances.stop`` in their runtime service account.
    """
    audience = os.environ.get("AGENT_VM_STOP_AUDIENCE", "").strip()
    backend_url = runtime.backend_url.rstrip("/")
    if not audience or not backend_url:
        return
    try:
        identity = await metadata(
            "instance/service-accounts/default/identity" f"?audience={quote(audience, safe='')}&format=full"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{backend_url}/v2/agent/vm/stop-self",
                headers={"Authorization": f"Bearer {identity}"},
            )
            response.raise_for_status()
    except (httpx.HTTPError, OSError):
        return


async def runtime_maintenance() -> None:
    while True:
        await asyncio.sleep(300)
        if time.monotonic() - runtime.last_activity_at >= 1800:
            await stop_instance()


def quoted(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid identifier")
    return f'"{value}"'


def json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return value


def run_sync(table: str, rows: list[dict[str, Any]]) -> int:
    if runtime.db is None:
        raise RuntimeError("Database not loaded. Upload omi.db first.")
    table_sql = quoted(table)
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        columns = tuple(sorted(row))
        if columns:
            groups.setdefault(columns, []).append(row)
    if not groups:
        return 0
    with runtime.lock:
        existing = {row[1] for row in runtime.db.execute(f"PRAGMA table_info({table_sql})")}
        if not existing:
            raise ValueError(f"Table '{table}' does not exist")
        for column in {column for columns in groups for column in columns}:
            if column not in existing:
                runtime.db.execute(f"ALTER TABLE {table_sql} ADD COLUMN {quoted(column)}")
        applied = 0
        for columns, grouped_rows in groups.items():
            column_sql = [quoted(column) for column in columns]
            placeholders = ", ".join("?" for _ in columns)
            statement = f"INSERT OR REPLACE INTO {table_sql} ({', '.join(column_sql)}) VALUES ({placeholders})"
            values = [
                tuple(
                    (
                        base64.b64decode(row[column], validate=True)
                        if column == "embedding" and isinstance(row[column], str) and row[column]
                        else json_value(row[column])
                    )
                    for column in columns
                )
                for row in grouped_rows
            ]
            runtime.db.executemany(statement, values)
            applied += len(values)
        runtime.db.commit()
    return applied


def validate_database_integrity(path: Path) -> list[Any]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
        return [row[0] for row in connection.execute("PRAGMA integrity_check")]
    finally:
        if connection is not None:
            connection.close()


def fsync_file(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(str(path), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_database_files(path: Path) -> None:
    fsync_file(path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_file():
            fsync_file(sidecar)


def remove_database_sidecars(path: Path) -> None:
    removed = False
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_file():
            sidecar.unlink()
            removed = True
    if removed:
        fsync_directory(path.parent)


def close_runtime_database() -> None:
    connection = runtime.db
    try:
        runtime.close_database()
    except Exception:
        runtime.db = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


async def run_thread_operation(function: Any, *args: Any) -> Any:
    """Run a blocking operation without abandoning it when the caller is cancelled."""
    operation = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(operation)
    except asyncio.CancelledError:
        while not operation.done():
            try:
                await asyncio.shield(operation)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if operation.done():
            try:
                operation.result()
            except BaseException:
                pass
        raise


def restore_previous_database(
    previous: Path,
    prior_moved: bool,
    uploaded_moved: bool,
    was_open: bool,
    previous_available: bool,
) -> None:
    close_runtime_database()
    if uploaded_moved:
        remove_database_sidecars(runtime.db_path)
    if prior_moved or (uploaded_moved and previous_available):
        if not previous.is_file():
            raise RuntimeError("Previous database is missing")
        fsync_file(previous)
        previous.replace(runtime.db_path)
        fsync_directory(runtime.db_path.parent)
    elif uploaded_moved:
        runtime.db_path.unlink(missing_ok=True)
        fsync_directory(runtime.db_path.parent)
    if was_open and runtime.db is None and runtime.db_path.is_file() and not runtime.open_database():
        raise RuntimeError("Failed to reopen previous database")
    if was_open and runtime.db is not None:
        fsync_database_files(runtime.db_path)
        fsync_directory(runtime.db_path.parent)


def install_uploaded_database(temporary: Path) -> None:
    with runtime.lock:
        previous = runtime.db_path.with_suffix(runtime.db_path.suffix + ".previous")
        was_open = runtime.db is not None
        previous_available = previous.is_file()
        prior_moved = False
        uploaded_moved = False
        try:
            if runtime.db is not None:
                runtime.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            runtime.close_database()
            if runtime.db_path.is_file():
                fsync_file(runtime.db_path)
            remove_database_sidecars(runtime.db_path)
            if runtime.db_path.is_file():
                runtime.db_path.replace(previous)
                prior_moved = True
                fsync_directory(runtime.db_path.parent)
            temporary.replace(runtime.db_path)
            uploaded_moved = True
            fsync_directory(runtime.db_path.parent)
            if not runtime.open_database():
                raise RuntimeError("Failed to open uploaded database")
            fsync_database_files(runtime.db_path)
            fsync_directory(runtime.db_path.parent)
            previous.unlink(missing_ok=True)
        except Exception:
            try:
                restore_previous_database(previous, prior_moved, uploaded_moved, was_open, previous_available)
            except Exception as restore_exc:
                raise RuntimeError("Failed to restore previous database") from restore_exc
            raise


async def upload_database(request: Request) -> tuple[int, int]:
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    if content_length > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"error": "File too large", "maxBytes": MAX_UPLOAD_BYTES})
    encoding = request.headers.get("content-encoding", "").lower()
    if encoding not in {"", "gzip", "deflate", "zlib"}:
        raise HTTPException(status_code=415, detail="Unsupported Content-Encoding")
    temporary = runtime.db_path.with_suffix(runtime.db_path.suffix + ".uploading")
    received = 0
    final_size = 0
    decompressor: zlib.Decompress | None = None
    if encoding == "gzip":
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding in {"deflate", "zlib"}:
        decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                received += len(chunk)
                if received > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail={"error": "File too large", "maxBytes": MAX_UPLOAD_BYTES}
                    )
                data = decompressor.decompress(chunk) if decompressor else chunk
                output.write(data)
                final_size += len(data)
                if final_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail={"error": "File too large", "maxBytes": MAX_UPLOAD_BYTES}
                    )
            if decompressor:
                data = decompressor.flush()
                output.write(data)
                final_size += len(data)
            output.flush()
        await run_thread_operation(fsync_file, temporary)
        await run_thread_operation(fsync_directory, temporary.parent)
        if final_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail={"error": "File too large", "maxBytes": MAX_UPLOAD_BYTES})
        try:
            integrity = await run_thread_operation(validate_database_integrity, temporary)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=400, detail="Uploaded database is not valid SQLite") from exc
        if integrity != ["ok"]:
            raise HTTPException(status_code=400, detail="Uploaded database failed SQLite integrity check")

        await run_thread_operation(install_uploaded_database, temporary)
        runtime.last_activity_at = time.monotonic()
        return received, final_size
    except HTTPException:
        raise
    except (OSError, zlib.error) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)


async def fetch_backend_tools() -> list[dict[str, Any]]:
    if not runtime.firebase_token:
        return []
    headers = {"Authorization": f"Bearer {runtime.firebase_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{runtime.backend_url}/v1/agent/tools", headers=headers)
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, list) else data.get("tools", [])


async def execute_backend_tool(name: str, params: dict[str, Any]) -> str:
    if not runtime.firebase_token:
        return "Error: Firebase token is not set"
    headers = {"Authorization": f"Bearer {runtime.firebase_token}"}
    payload = {"tool_name": name, "params": params}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{runtime.backend_url}/v1/agent/execute-tool", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        return f"Error calling {name}: {exc}"
    if result.get("error"):
        return f"Error: {result['error']}"
    return result.get("result") or json.dumps(result, default=str)


def read_only_sql_authorizer(
    action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None
) -> int:
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 is not None and arg1.casefold() == "data_version" and arg2 is None:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_sql(query: str) -> str:
    if runtime.db is None:
        return json.dumps({"error": "Database not loaded. Upload omi.db first."})
    upper = query.upper()
    if any(
        re.search(rf"\b{word}\b", upper) for word in ("DROP", "ALTER", "CREATE", "PRAGMA", "ATTACH", "DETACH", "VACUUM")
    ):
        return json.dumps({"error": "Blocked statement"})
    if re.search(r";\s*\S", query):
        return json.dumps({"error": "Multi-statement queries not allowed"})
    if not upper.lstrip().startswith("SELECT"):
        return json.dumps({"error": "Database is in read-only mode (cloud copy)"})
    if not re.search(r"\bLIMIT\b", query, re.I):
        query = query.rstrip().rstrip(";") + " LIMIT 200"
    try:
        with runtime.lock:
            try:
                runtime.db.set_authorizer(read_only_sql_authorizer)
                cursor = runtime.db.execute(query)
                rows = [dict(row) for row in cursor.fetchall()]
            finally:
                runtime.db.set_authorizer(None)
        return json.dumps({"rows": rows, "count": len(rows)}, default=str)
    except sqlite3.Error as exc:
        return json.dumps({"error": str(exc)})


async def semantic_search(query: str, days: int = 7, app_filter: str | None = None) -> str:
    if runtime.db is None:
        return json.dumps({"error": "Database not loaded. Upload omi.db first."})
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY not set"})
    body = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": query}]},
        "taskType": "RETRIEVAL_QUERY",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}",
                json=body,
            )
            response.raise_for_status()
            vector = [float(value) for value in response.json()["embedding"]["values"]]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return json.dumps({"error": str(exc)})
    norm = sum(value * value for value in vector) ** 0.5
    vector = [value / norm for value in vector] if norm else vector
    parameters: list[Any] = [f"-{max(1, min(days, 3650))} days"]
    sql = "SELECT id, timestamp, appName, windowTitle, substr(ocrText, 1, 300), embedding FROM screenshots WHERE embedding IS NOT NULL AND timestamp >= datetime('now', ?)"
    if app_filter:
        sql += " AND appName = ?"
        parameters.append(app_filter)
    sql += " ORDER BY timestamp DESC LIMIT 10000"
    try:
        with runtime.lock:
            rows = runtime.db.execute(sql, parameters).fetchall()
    except sqlite3.Error as exc:
        return json.dumps({"error": str(exc)})
    matches = []
    for row in rows:
        blob = row[5]
        if not isinstance(blob, bytes) or len(blob) != len(vector) * 4:
            continue
        values = memoryview(blob).cast("f")
        score = sum(left * right for left, right in zip(vector, values))
        matches.append(
            {
                "id": row[0],
                "timestamp": row[1],
                "appName": row[2],
                "windowTitle": row[3],
                "ocrPreview": row[4],
                "similarity": round(score, 3),
            }
        )
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return json.dumps({"results": matches[:20], "count": len(matches[:20])}, default=str)


def daily_recap(days_ago: int = 0) -> str:
    if runtime.db is None:
        return json.dumps({"error": "Database not loaded. Upload omi.db first."})
    days_ago = max(0, min(days_ago, 3650))
    try:
        with runtime.lock:
            apps = runtime.db.execute(
                "SELECT appName, COUNT(*) FROM screenshots WHERE timestamp >= datetime('now', 'start of day', ?, 'localtime') AND timestamp < datetime('now', 'start of day', ?, 'localtime') GROUP BY appName ORDER BY COUNT(*) DESC LIMIT 10",
                (f"-{days_ago} days", f"-{days_ago - 1} days" if days_ago else "+1 day"),
            ).fetchall()
        return json.dumps({"apps": [{"appName": row[0], "screenshots": row[1]} for row in apps]})
    except sqlite3.Error as exc:
        return json.dumps({"error": str(exc)})


def database_schema() -> str:
    if runtime.db is None:
        return "No database is loaded."
    try:
        with runtime.lock:
            tables = runtime.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE 'grdb_%' ORDER BY name"
            ).fetchall()
            entries = []
            for table in tables:
                name = table[0]
                columns = runtime.db.execute(f"PRAGMA table_info({quoted(name)})").fetchall()
                count = runtime.db.execute(f"SELECT COUNT(*) FROM {quoted(name)}").fetchone()[0]
                entries.append(
                    f"{name}:\n" + "\n".join(f"  {column[1]} {column[2]}" for column in columns) + f"\n  ({count} rows)"
                )
        return "\n\n".join(entries)
    except sqlite3.Error:
        return "Schema unavailable."


def system_prompt() -> str:
    return """You are an AI assistant with access to the user's OMI desktop database and connected services.
This database contains their screen history, tasks, transcriptions, memories, and focus sessions.

DATABASE SCHEMA:
%s

TOOLS:
- execute_sql: Run read-only SQL queries. SELECT auto-limits to 200 rows. Use it for structured queries.
- semantic_search: Search screenshot OCR text by semantic similarity for fuzzy or conceptual queries.
- get_daily_recap: Use this for what the user did today, yesterday, or this week.
- Backend tools: Use these for calendar, email, health, conversations, memories, action items, and web search.

GUIDELINES:
- For activity summaries, use get_daily_recap before issuing multiple SQL queries.
- For time-filtered screenshots, use timestamp range comparisons instead of date() or strftime() in WHERE clauses.
- Key tables include screenshots, action_items, memories, transcription_sessions, transcription_segments, focus_sessions, observations, and staged_tasks.
- Be concise and helpful. Format results clearly.""" % database_schema()


def message_payload(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump()
    if isinstance(message, dict):
        return message
    return vars(message)


class AgentSession:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.client: Any = None
        self.task: asyncio.Task[None] | None = None
        self.ready = asyncio.Event()
        self.closed = False
        self.session_id = ""
        self.turn_active = False
        self.pending_tools: list[str] = []

    async def start(self) -> bool:
        if runtime.db is None:
            return False
        if self.task:
            return True
        try:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool
        except ImportError:
            await self.websocket.send_json({"type": "error", "message": "claude-agent-sdk is not installed"})
            return False

        @tool("execute_sql", "Run a read-only SQL query against the uploaded Omi database.", {"query": str})
        async def sql_tool(arguments: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": execute_sql(str(arguments["query"]))}]}

        @tool(
            "semantic_search",
            "Search screenshot OCR text by semantic similarity.",
            {"query": str, "days": int, "app_filter": str},
        )
        async def search_tool(arguments: dict[str, Any]) -> dict[str, Any]:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": await semantic_search(
                            str(arguments["query"]), int(arguments.get("days", 7)), arguments.get("app_filter") or None
                        ),
                    }
                ]
            }

        @tool("get_daily_recap", "Get a compact activity recap for a day offset from today.", {"days_ago": int})
        async def recap_tool(arguments: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": daily_recap(int(arguments.get("days_ago", 0)))}]}

        tools = [sql_tool, search_tool, recap_tool]
        for definition in runtime.backend_tools:
            name = definition.get("name")
            if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                continue
            schema = (
                definition.get("parameters") if isinstance(definition.get("parameters"), dict) else {"type": "object"}
            )

            def build_tool(tool_name: str, description: str, parameters: dict[str, Any]):
                @tool(tool_name, description, parameters)
                async def backend_tool(arguments: dict[str, Any]) -> dict[str, Any]:
                    result = await execute_backend_tool(tool_name, arguments)
                    return {"content": [{"type": "text", "text": result}]}

                return backend_tool

            tools.append(
                build_tool(name, str(definition.get("description") or f"Backend tool: {name}"), copy.deepcopy(schema))
            )
        server = create_sdk_mcp_server("omi-tools", "1.0", tools=tools)
        mcp_servers: dict[str, Any] = {"omi-tools": server}
        playwright_command = os.environ.get("PLAYWRIGHT_MCP_COMMAND")
        if playwright_command:
            mcp_servers["playwright"] = {
                "type": "stdio",
                "command": playwright_command,
                "args": json.loads(
                    os.environ.get(
                        "PLAYWRIGHT_MCP_ARGS",
                        '["@playwright/mcp", "--user-data-dir", "/app/chrome-profile", "--headless", "--no-sandbox"]',
                    )
                ),
            }
        options = ClaudeAgentOptions(
            model="claude-sonnet-4-6",
            system_prompt=system_prompt(),
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"],
            mcp_servers=mcp_servers,
            permission_mode="bypassPermissions",
            cwd=str(runtime.workspace_path),
        )
        self.client = ClaudeSDKClient(options=options)
        await self.client.connect()
        self.task = asyncio.create_task(self._run(), name="agent-vm-session")
        await self.client.query("ready")
        return True

    async def _run(self) -> None:
        try:
            async for message in self.client.receive_response():
                payload = message_payload(message)
                kind = payload.get("type", "")
                if kind == "system" and payload.get("session_id"):
                    self.session_id = payload["session_id"]
                    await self.websocket.send_json({"type": "init", "sessionId": self.session_id})
                if kind == "stream_event":
                    event = payload.get("event") or {}
                    if event.get("type") == "content_block_start":
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            name = block.get("name", "unknown")
                            self.pending_tools.append(name)
                            await self.websocket.send_json({"type": "tool_activity", "name": name, "status": "started"})
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            for name in self.pending_tools:
                                await self.websocket.send_json(
                                    {"type": "tool_activity", "name": name, "status": "completed"}
                                )
                            self.pending_tools.clear()
                            await self.websocket.send_json({"type": "text_delta", "text": delta.get("text", "")})
                if kind == "result":
                    for name in self.pending_tools:
                        await self.websocket.send_json({"type": "tool_activity", "name": name, "status": "completed"})
                    self.pending_tools.clear()
                    if not self.ready.is_set():
                        self.ready.set()
                    elif payload.get("subtype") == "success":
                        await self.websocket.send_json(
                            {
                                "type": "result",
                                "text": payload.get("result", ""),
                                "sessionId": self.session_id,
                                "costUsd": payload.get("total_cost_usd", 0),
                            }
                        )
                    else:
                        await self.websocket.send_json(
                            {"type": "error", "message": f"Agent error ({payload.get('subtype', 'unknown')})"}
                        )
                    self.turn_active = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self.closed:
                await self.websocket.send_json({"type": "error", "message": str(exc)})
            self.ready.set()

    async def prewarm(self) -> bool:
        if not await self.start():
            return False
        await asyncio.wait_for(self.ready.wait(), timeout=60)
        return True

    async def query(self, prompt: str) -> None:
        if not await self.prewarm():
            return
        if self.turn_active:
            await self.stop()
        self.turn_active = True
        await self.websocket.send_json({"type": "status", "message": "Processing..."})
        await self.client.query(prompt)

    async def stop(self) -> None:
        if self.client and self.turn_active:
            interrupt = getattr(self.client, "interrupt", None)
            if interrupt:
                result = interrupt()
                if hasattr(result, "__await__"):
                    await result
        self.turn_active = False

    async def close(self) -> None:
        self.closed = True
        await self.stop()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.client:
            await self.client.disconnect()


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    # Unauthenticated /health previously leaked databaseReady on public :8080.
    runtime.require_auth(request)
    return {
        "status": "ok",
        "uptime": round(time.monotonic() - runtime.started_at),
        "databaseReady": runtime.db is not None,
        "stateReady": runtime.state_ready,
        "stateMigrationId": runtime.state_migration_id,
        "stateReceiptSha256": runtime.state_receipt_sha256,
        "stateDatabaseExpected": runtime.state_database_expected,
        "release": runtime.release_id,
        "imageDigest": runtime.image_digest,
        "startupSha256": runtime.startup_sha256,
    }


@app.post("/upload")
async def upload(request: Request) -> dict[str, Any]:
    runtime.require_auth(request)
    async with runtime.upload_lock:
        received, final_size = await upload_database(request)
    return {"status": "ok", "bytesReceived": received, "finalSize": final_size, "databaseReady": True}


@app.post("/auth")
async def authenticate(request: Request) -> dict[str, Any]:
    runtime.require_auth(request)
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    token = payload.get("firebaseToken") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=400, detail="Missing firebaseToken")
    first_token = runtime.firebase_token is None
    runtime.firebase_token = token
    runtime.last_activity_at = time.monotonic()
    if first_token:
        try:
            runtime.backend_tools = await fetch_backend_tools()
        except httpx.HTTPError:
            runtime.backend_tools = []
    return {"status": "ok", "toolsRegistered": len(runtime.backend_tools)}


@app.post("/ping")
async def ping(request: Request) -> dict[str, str]:
    runtime.require_auth(request)
    runtime.last_activity_at = time.monotonic()
    return {"status": "ok"}


@app.post("/sync")
async def sync(request: Request) -> dict[str, Any]:
    runtime.require_auth(request)
    if runtime.db is None:
        raise HTTPException(status_code=503, detail="Database not loaded. Upload omi.db first.")
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    table = payload.get("table") if isinstance(payload, dict) else None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if (
        not isinstance(table, str)
        or not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        raise HTTPException(status_code=400, detail="Required: { table: string, rows: [{...}, ...] }")
    if table not in SYNC_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table}' not in sync whitelist")
    try:
        applied = run_sync(table, rows)
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    runtime.last_activity_at = time.monotonic()
    return {"applied": applied, "table": table}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.headers.get("authorization", "").removeprefix("Bearer ") or websocket.query_params.get(
        "token", ""
    )
    if not runtime.auth_token or token != runtime.auth_token:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await websocket.send_json({"type": "init", "sessionId": ""})
    session = AgentSession(websocket)

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "prewarm":
                try:
                    ready = await session.prewarm()
                except TimeoutError:
                    ready = False
                await websocket.send_json({"type": "prewarm_ack", "success": ready})
            elif message_type == "query":
                prompt = message.get("prompt")
                if not isinstance(prompt, str):
                    await websocket.send_json({"type": "error", "message": "Invalid query"})
                    continue
                runtime.last_activity_at = time.monotonic()
                await session.query(prompt)
            elif message_type == "stop":
                await session.stop()
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {message_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
