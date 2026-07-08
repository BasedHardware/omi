import asyncio
import ast
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
TOOLS_DIR = BACKEND_DIR / "utils" / "retrieval" / "tools"


class _ToolWrapper:
    def __init__(self, func):
        self.func = func
        if asyncio.iscoroutinefunction(func):
            self.coroutine = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gmail_module(monkeypatch):
    for name, path in (
        ("utils", BACKEND_DIR / "utils"),
        ("utils.retrieval", BACKEND_DIR / "utils" / "retrieval"),
        ("utils.retrieval.tools", TOOLS_DIR),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        monkeypatch.setitem(sys.modules, name, pkg)

    agentic = types.ModuleType("utils.retrieval.agentic")
    agentic.agent_config_context = MagicMock()
    monkeypatch.setitem(sys.modules, "utils.retrieval.agentic", agentic)

    database = types.ModuleType("database")
    database.__path__ = []
    users_db = types.ModuleType("database.users")
    users_db.get_integration = MagicMock()
    monkeypatch.setitem(sys.modules, "database", database)
    monkeypatch.setitem(sys.modules, "database.users", users_db)

    tools_mod = types.ModuleType("langchain_core.tools")
    tools_mod.tool = _ToolWrapper
    runnables_mod = types.ModuleType("langchain_core.runnables")
    runnables_mod.RunnableConfig = dict
    monkeypatch.setitem(sys.modules, "langchain_core.tools", tools_mod)
    monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables_mod)

    log_sanitizer = types.ModuleType("utils.log_sanitizer")
    log_sanitizer.sanitize = lambda value: value
    monkeypatch.setitem(sys.modules, "utils.log_sanitizer", log_sanitizer)

    http_client = types.ModuleType("utils.http_client")
    http_client.get_auth_client = MagicMock()
    monkeypatch.setitem(sys.modules, "utils.http_client", http_client)

    _load_module("utils.retrieval.tools.integration_base", TOOLS_DIR / "integration_base.py")
    _load_module("utils.retrieval.tools.google_utils", TOOLS_DIR / "google_utils.py")
    module = _load_module("utils.retrieval.tools.gmail_tools", TOOLS_DIR / "gmail_tools.py")
    yield module

    for name in [
        "utils.retrieval.tools.gmail_tools",
        "utils.retrieval.tools.google_utils",
        "utils.retrieval.tools.integration_base",
    ]:
        sys.modules.pop(name, None)


@pytest.mark.asyncio
async def test_gmail_tool_exercises_async_interface_and_refreshes_once(gmail_module, monkeypatch):
    calls = []

    async def fake_get_gmail_messages(access_token, query=None, max_results=10, label_ids=None):
        calls.append(access_token)
        if access_token == "old-token":
            raise Exception("Google API error 401: expired")
        return [
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "hello",
                "payload": {"headers": [{"name": "Subject", "value": "Async"}]},
            }
        ]

    async def fake_refresh(uid, integration):
        assert uid == "uid-1"
        assert integration == {"connected": True, "access_token": "old-token"}
        return "new-token"

    monkeypatch.setattr(
        gmail_module,
        "prepare_access",
        lambda *args, **kwargs: ("uid-1", {"connected": True, "access_token": "old-token"}, "old-token", None),
    )
    monkeypatch.setattr(gmail_module, "get_gmail_messages", fake_get_gmail_messages)
    monkeypatch.setattr(gmail_module, "refresh_google_token", fake_refresh)

    result = await gmail_module.get_gmail_messages_tool.coroutine(query="subject:async", config={})

    assert calls == ["old-token", "new-token"]
    assert "Gmail Messages (1 found)" in result
    assert "Async" in result


@pytest.mark.asyncio
async def test_get_gmail_messages_awaits_list_and_fetch_requests(gmail_module, monkeypatch):
    awaited_urls = []

    async def fake_google_api_request(method, url, access_token, params=None, body=None, allow_204=False):
        awaited_urls.append(url)
        if url.endswith("/messages"):
            return {"messages": [{"id": "m1"}, {"id": "m2"}]}
        return {"id": url.rsplit("/", 1)[-1], "payload": {"headers": []}, "snippet": "ok"}

    monkeypatch.setattr(gmail_module, "google_api_request", fake_google_api_request)

    messages = await gmail_module.get_gmail_messages("token", max_results=2)

    assert [message["id"] for message in messages] == ["m1", "m2"]
    assert len(awaited_urls) == 3


@pytest.mark.asyncio
async def test_retry_on_auth_async_preserves_refresh_flow(gmail_module):
    integration_base = sys.modules["utils.retrieval.tools.integration_base"]
    attempts = []

    async def call_fn(access_token):
        attempts.append(access_token)
        if access_token == "old-token":
            raise Exception("401 token may be expired")
        return "ok"

    async def refresh_fn(uid, integration):
        return "new-token"

    result, err = await integration_base.retry_on_auth_async(
        call_fn,
        {"access_token": "old-token"},
        refresh_fn,
        "uid-1",
        {},
        "expired",
    )

    assert (result, err) == ("ok", None)
    assert attempts == ["old-token", "new-token"]


def test_speech_profile_closes_audio_file_handle(monkeypatch, tmp_path):
    storage = types.ModuleType("utils.other.storage")
    for attr in (
        "get_profile_audio_if_exists",
        "get_additional_profile_recordings",
        "get_user_people_ids",
        "get_user_person_speech_samples",
    ):
        setattr(storage, attr, MagicMock())
    monkeypatch.setitem(sys.modules, "utils.other.storage", storage)

    http_client = types.ModuleType("utils.http_client")
    http_client.get_stt_client = MagicMock()
    monkeypatch.setitem(sys.modules, "utils.http_client", http_client)

    executors = types.ModuleType("utils.executors")
    executors.storage_executor = MagicMock()
    executors.run_blocking = MagicMock()
    monkeypatch.setitem(sys.modules, "utils.executors", executors)

    log_sanitizer = types.ModuleType("utils.log_sanitizer")
    log_sanitizer.sanitize = lambda value: value
    monkeypatch.setitem(sys.modules, "utils.log_sanitizer", log_sanitizer)

    pydub = types.ModuleType("pydub")
    setattr(pydub, "AudioSegment", MagicMock())
    monkeypatch.setitem(sys.modules, "pydub", pydub)

    module_name = "utils.stt.speech_profile"
    module = _load_module(module_name, BACKEND_DIR / "utils" / "stt" / "speech_profile.py")
    try:
        audio_path = tmp_path / "sample.wav"
        audio_path.write_bytes(b"RIFF....WAVEfmt ")
        captured = {}

        def fake_post(url, data=None, files=None, **kwargs):
            assert files is not None
            captured["fh"] = files[0][1][1]
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = [False]
            return response

        monkeypatch.setenv("HOSTED_SPEECH_PROFILE_API_URL", "http://speech.test/match")
        monkeypatch.setattr(module.httpx, "post", fake_post)

        module.get_speech_profile_matching_predictions("uid-1", str(audio_path), [{"text": "hi"}])

        assert captured["fh"].closed is True
    finally:
        sys.modules.pop(module_name, None)


def test_scan_async_blockers_treats_run_blocking_lambda_as_safe():
    scanner = _load_module("scan_async_blockers_for_test", BACKEND_DIR / "scripts" / "scan_async_blockers.py")
    source = """
async def helper():
    await run_blocking(db_executor, lambda: open('x').read())
"""
    tree = ast.parse(source)
    node = next(n for n in tree.body if getattr(n, "name", None) == "helper")

    _db, file_io, _network, _sleeps, _body_call_lines = scanner.scan_async_function(node, set(), set(), set())

    assert file_io == []


def test_scan_async_blockers_keeps_deletion_only_hunks_in_changed_scope(monkeypatch):
    scanner = _load_module(
        "scan_async_blockers_diff_scope_for_test", BACKEND_DIR / "scripts" / "scan_async_blockers.py"
    )
    captured = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        return types.SimpleNamespace(stdout="""
diff --git a/backend/routers/example.py b/backend/routers/example.py
index 1111111..2222222 100644
--- a/backend/routers/example.py
+++ b/backend/routers/example.py
@@ -42 +42,0 @@ async def endpoint():
-    await run_blocking(db_executor, expensive_sync_call)
diff --git a/backend/routers/old_name.py b/backend/routers/new_name.py
similarity index 96%
rename from backend/routers/old_name.py
rename to backend/routers/new_name.py
--- a/backend/routers/old_name.py
+++ b/backend/routers/new_name.py
@@ -10 +10 @@ async def renamed_endpoint():
-    await old_call()
+    await new_call()
""")

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    scope = scanner.changed_scope("origin/main", ["backend/routers"])

    assert "--diff-filter=ACMR" in captured["cmd"]
    assert scope["ranges"]["backend/routers/example.py"] == [(42, 42)]
    assert scope["ranges"]["backend/routers/new_name.py"] == [(10, 10)]
    assert scanner.finding_in_changed_scope(
        {"file": "backend/routers/example.py", "line": 40, "end_line": 45},
        scope,
    )


def test_scan_async_blockers_honors_no_await_fail_on_without_blocking_calls():
    scanner = _load_module("scan_async_blockers_fail_on_for_test", BACKEND_DIR / "scripts" / "scan_async_blockers.py")

    results = {
        "no_await_should_be_def": [
            {
                "file": "backend/routers/example.py",
                "line": 12,
                "end_line": 16,
                "endpoint": "endpoint",
                "method": "GET",
                "path": "/example",
                "has_await": False,
                "db_calls": [],
                "all_blocking": [],
                "all_calls_are_blocking": False,
            }
        ]
    }

    assert scanner.selected_failures(results, ("no_await_should_be_def",)) == [
        ("no_await_should_be_def", results["no_await_should_be_def"][0])
    ]
