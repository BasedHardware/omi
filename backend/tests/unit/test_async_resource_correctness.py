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
    users_db.set_integration = MagicMock()
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


@pytest.mark.asyncio
async def test_refresh_google_token_offloads_firestore_write(gmail_module, monkeypatch):
    """refresh_google_token must offload the sync Firestore set_integration
    call to the DB executor so it does not block the event loop."""
    google_utils = sys.modules["utils.retrieval.tools.google_utils"]

    # Fake auth client that returns a successful token refresh response.
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"access_token": "fresh-token"}
    fake_response.text = ""

    async def fake_post(*args, **kwargs):
        return fake_response

    fake_client = MagicMock()
    fake_client.post = fake_post
    monkeypatch.setattr(google_utils, "get_auth_client", lambda: fake_client)

    # Capture run_blocking calls to verify the Firestore write is offloaded.
    captured = []

    async def fake_run_blocking(executor, fn, *args, **kwargs):
        captured.append((executor, fn, args, kwargs))
        return fn(*args, **kwargs)  # execute synchronously for the test

    monkeypatch.setattr(google_utils, "run_blocking", fake_run_blocking)
    monkeypatch.setattr(google_utils, "db_executor", "db-exec-mock")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    # users_db.set_integration is already a MagicMock from the fixture.
    integration = {"connected": True, "access_token": "old", "refresh_token": "rt"}
    token = await google_utils.refresh_google_token("uid-1", integration)

    assert token == "fresh-token"
    # Verify the Firestore write was offloaded via run_blocking with db_executor.
    assert len(captured) == 1
    executor, fn, args, kwargs = captured[0]
    assert executor == "db-exec-mock"
    assert fn == google_utils.users_db.set_integration
    assert args[0] == "uid-1"


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

    _db, file_io, _network, _sleeps = scanner.scan_async_function(node, set(), set(), set())

    assert file_io == []
