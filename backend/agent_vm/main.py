import asyncio
import base64
import copy
import hashlib
import hmac
import json
import os
import re
import sqlite3
import sys
import threading
import time
import zlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

SYNC_TABLES = frozenset(
    {
        "action_items",
        "transcription_sessions",
        "transcription_segments",
        "memories",
        "staged_tasks",
        "live_notes",
        "ai_user_profiles",
        "task_dedup_log",
    }
)
SCREEN_DATA_TABLES = frozenset({"screenshots", "focus_sessions", "observations"})
SCREEN_DATA_TABLE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:screenshots|focus_sessions|observations|ocr_[A-Za-z0-9_]*)(?![A-Za-z0-9_])", re.I
)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024


class Runtime:
    def __init__(self) -> None:
        self.db_path = Path(os.environ.get("DB_PATH", str(Path.home() / "omi-agent/data/omi.db")))
        self.auth_token = os.environ.get("AUTH_TOKEN", "")
        self.backend_url = os.environ.get("BACKEND_URL", "https://api.omi.me")
        self.db: sqlite3.Connection | None = None
        self.firebase_token: str | None = None
        self.backend_tools: list[dict[str, Any]] = []
        self.started_at = time.monotonic()
        self.last_activity_at = time.monotonic()
        self.current_version: str | None = None
        self.lock = threading.RLock()

    def open_database(self) -> bool:
        self.close_database()
        if not self.db_path.is_file():
            return False
        try:
            connection = sqlite3.connect(self.db_path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("SELECT 1")
        except sqlite3.Error:
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
    runtime.db_path.with_suffix(runtime.db_path.suffix + ".uploading").unlink(missing_ok=True)
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
    try:
        name, zone, token = await asyncio.gather(
            metadata("instance/name"),
            metadata("instance/zone"),
            metadata("instance/service-accounts/default/token"),
        )
        access_token = json.loads(token)["access_token"]
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"https://compute.googleapis.com/compute/v1/{zone}/instances/{name}/stop",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except (httpx.HTTPError, KeyError, json.JSONDecodeError):
        return


def validate_signed_update_manifest(manifest_bytes: bytes, signature: bytes, source: bytes) -> dict[str, str]:
    """Validate the signed, content-addressed update artifact before execution."""
    try:
        public_key = base64.b64decode(os.environ["AGENT_UPDATE_ED25519_PUBLIC_KEY"], validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, manifest_bytes)
        manifest = json.loads(manifest_bytes)
        path = manifest["path"]
        version = manifest["version"]
        expected_sha256 = manifest["sha256"]
    except (KeyError, TypeError, ValueError, InvalidSignature, json.JSONDecodeError):
        raise ValueError("invalid signed Agent VM update manifest") from None

    if (
        not isinstance(path, str)
        or not isinstance(version, str)
        or not version
        or not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        or not hmac.compare_digest(hashlib.sha256(source).hexdigest(), expected_sha256)
    ):
        raise ValueError("invalid signed Agent VM update artifact")
    return {"path": path, "version": version}


async def check_update() -> None:
    base = os.environ.get("AGENT_GCS_BASE", "https://storage.googleapis.com/based-hardware-agent")
    manifest_path = os.environ.get("AGENT_UPDATE_MANIFEST_PATH", "manifest.json")
    signature_path = f"{manifest_path}.sig"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            manifest_response, signature_response = await asyncio.gather(
                client.get(f"{base}/{manifest_path}"),
                client.get(f"{base}/{signature_path}"),
            )
            manifest_response.raise_for_status()
            signature_response.raise_for_status()
            untrusted_manifest = json.loads(manifest_response.content)
            path = untrusted_manifest.get("path") if isinstance(untrusted_manifest, dict) else None
            if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
                return
            source_response = await client.get(f"{base}/{path}")
            source_response.raise_for_status()
        update = validate_signed_update_manifest(
            manifest_response.content,
            base64.b64decode(signature_response.content, validate=True),
            source_response.content,
        )
        if runtime.current_version is None:
            runtime.current_version = update["version"]
            return
        if update["version"] == runtime.current_version:
            return
        target = Path(__file__).resolve()
        temporary = target.with_suffix(".updating")
        temporary.write_bytes(source_response.content)
        temporary.replace(target)
        runtime.current_version = update["version"]
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError):
        return


async def runtime_maintenance() -> None:
    while True:
        await asyncio.sleep(300)
        if time.monotonic() - runtime.last_activity_at >= 1800:
            await stop_instance()
        await check_update()


def quoted(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid identifier")
    return f'"{value}"'


def is_screen_data_table(name: str) -> bool:
    return name in SCREEN_DATA_TABLES or name.lower().startswith("ocr_")


def screen_data_tables() -> list[str]:
    if runtime.db is None:
        return []
    rows = runtime.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [str(row[0]) for row in rows if is_screen_data_table(str(row[0]))]


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


async def upload_database(request: Request) -> tuple[int, int]:
    content_length = int(request.headers.get("content-length", "0"))
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
        if final_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail={"error": "File too large", "maxBytes": MAX_UPLOAD_BYTES})
        with runtime.lock:
            runtime.close_database()
            for suffix in ("-wal", "-shm"):
                Path(str(runtime.db_path) + suffix).unlink(missing_ok=True)
            temporary.replace(runtime.db_path)
            if not runtime.open_database():
                raise RuntimeError("Failed to open uploaded database")
        runtime.last_activity_at = time.monotonic()
        return received, final_size
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except (OSError, zlib.error) as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    if SCREEN_DATA_TABLE_PATTERN.search(query):
        return json.dumps({"error": "Screen activity is unavailable"})
    if not re.search(r"\bLIMIT\b", query, re.I):
        query = query.rstrip().rstrip(";") + " LIMIT 200"
    try:
        with runtime.lock:
            cursor = runtime.db.execute(query)
            rows = [dict(row) for row in cursor.fetchall()]
        return json.dumps({"rows": rows, "count": len(rows)}, default=str)
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
                if is_screen_data_table(str(name)):
                    continue
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
This database contains their tasks, transcriptions, memories, and connected services.

DATABASE SCHEMA:
%s

TOOLS:
- execute_sql: Run read-only SQL queries. SELECT auto-limits to 200 rows. Use it for structured queries.
- Backend tools: Use these for calendar, email, health, conversations, memories, action items, and web search.

GUIDELINES:
- Key tables include action_items, memories, transcription_sessions, transcription_segments, and staged_tasks.
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

        tools = [sql_tool] if runtime.db is not None else []
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
            cwd=os.environ.get("HOME", "/"),
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
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "uptime": round(time.monotonic() - runtime.started_at),
        "databaseReady": runtime.db is not None,
    }


@app.post("/upload")
async def upload(request: Request) -> dict[str, Any]:
    runtime.require_auth(request)
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


@app.post("/purge-screen-activity")
async def purge_screen_activity(request: Request) -> dict[str, Any]:
    runtime.require_auth(request)
    if runtime.db is None:
        return {"status": "ok", "deleted": 0}
    deleted = 0
    with runtime.lock:
        for table in screen_data_tables():
            try:
                cursor = runtime.db.execute(f"DELETE FROM {quoted(table)}")
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    continue
                raise HTTPException(status_code=400, detail="Unable to purge screen activity") from exc
            deleted += max(cursor.rowcount, 0)
        runtime.db.commit()
    runtime.last_activity_at = time.monotonic()
    return {"status": "ok", "deleted": deleted}


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
