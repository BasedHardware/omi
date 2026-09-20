"""Hermetic Dropbox-app chat-tool and audio-buffer regressions (#14130).

Loads the production modules (db.py, dropbox_client.py, models.py, main.py)
with framework-only stubs so the suite runs on a bare stdlib interpreter: no
FastAPI, pydantic, requests, Redis, Dropbox API, or network access required.
Handlers are exercised through a fake Request seam, and the Dropbox client and
DB functions are patched at the loaded module surface.

Coverage: tools manifest structure, malformed/non-dict JSON bodies, null and
whitespace parameter coercion, typed ChatToolResponse contract, and the
bounded /audio accumulation buffer.
"""

import importlib.util
import io
import sys
import time
import unittest
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parent


def _exec_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_stubs():
    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def Field(default=None, **kwargs):
        return default

    def _decorator(*args, **kwargs):
        return lambda fn: fn

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = _decorator
    pydantic.model_validator = _decorator

    class SdkModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    sdk = ModuleType("omi_plugin_sdk")
    sdk_models = ModuleType("omi_plugin_sdk.models")
    for name in ("ActionItem", "Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, name, type(name, (SdkModel,), {}))
    sdk.models = sdk_models

    class _Timeout(Exception):
        pass

    class _ConnectionError(Exception):
        pass

    requests = ModuleType("requests")
    requests_exceptions = ModuleType("requests.exceptions")
    requests_exceptions.Timeout = _Timeout
    requests_exceptions.ConnectionError = _ConnectionError
    requests.exceptions = requests_exceptions

    def _offline_post(*args, **kwargs):
        raise AssertionError("requests.post must be patched inside tests")

    requests.post = _offline_post
    # dropbox_client annotates _download_request -> requests.Response; on
    # Pythons that evaluate annotations eagerly (pre-3.14) the class body
    # resolves the attribute at import time, so the stub needs it.
    requests.Response = type("Response", (), {})

    tenacity = ModuleType("tenacity")
    tenacity.retry = _decorator
    tenacity.stop_after_attempt = lambda *a, **k: None
    tenacity.wait_exponential = lambda *a, **k: None
    tenacity.retry_if_exception_type = lambda *a, **k: None

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None

    class FastAPI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get
        put = get
        delete = get

    def Query(default=None, **kwargs):
        return default

    class Request:
        pass

    class _Response:
        def __init__(self, content=None, status_code=None, **kwargs):
            self.content = content
            self.status_code = status_code
            for key, value in kwargs.items():
                setattr(self, key, value)

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Query = Query
    fastapi.Request = Request
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = type("HTMLResponse", (_Response,), {})
    responses.RedirectResponse = type("RedirectResponse", (_Response,), {})
    responses.JSONResponse = type("JSONResponse", (_Response,), {})

    return {
        "pydantic": pydantic,
        "omi_plugin_sdk": sdk,
        "omi_plugin_sdk.models": sdk_models,
        "requests": requests,
        "tenacity": tenacity,
        "dotenv": dotenv,
        "fastapi": fastapi,
        "fastapi.responses": responses,
    }


def load_app():
    """Import the production modules under stubbed frameworks."""
    with patch.dict(sys.modules, _build_stubs()):
        db = _exec_module("db", PLUGIN_DIR / "db.py")
        sys.modules["db"] = db
        client = _exec_module("dropbox_client", PLUGIN_DIR / "dropbox_client.py")
        sys.modules["dropbox_client"] = client
        models = _exec_module("models", PLUGIN_DIR / "models.py")
        sys.modules["models"] = models
        main = _exec_module("main", PLUGIN_DIR / "main.py")
    return SimpleNamespace(main=main, models=models, db=db, client=client)


APP = load_app()
MAIN = APP.main
MODELS = APP.models

_BAD_JSON = object()


class FakeRequest:
    """Minimal stand-in for fastapi.Request over the two read paths main.py uses."""

    def __init__(self, payload=_BAD_JSON, body=b""):
        self._payload = payload
        self._body = body

    async def json(self):
        if self._payload is _BAD_JSON:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload

    async def body(self):
        return self._body


def make_client(search_results=None, search_error=None, list_results=None, list_error=None,
                download_bytes=None, download_error=None):
    """Fake DropboxClient recording the arguments it was called with."""
    client = SimpleNamespace()
    client.calls = []

    def search_files(query, max_results=10):
        client.calls.append(("search", query, max_results))
        return search_results, search_error

    def list_folder(path="", limit=20):
        client.calls.append(("list", path, limit))
        return list_results, list_error

    def download_file(path):
        client.calls.append(("download", path))
        return download_bytes, download_error

    client.search_files = search_files
    client.list_folder = list_folder
    client.download_file = download_file
    return client


def assert_tool_contract(case, response):
    """Every chat-tool reply must be a typed ChatToolResponse with exactly one field set."""
    case.assertIsInstance(response, MODELS.ChatToolResponse)
    case.assertTrue(
        (response.result is None) != (response.error is None),
        f"expected exactly one of result/error, got {response.__dict__}",
    )
    return response


def connected_client(client):
    """Patch context: a connected user whose DropboxClient is the fake."""
    return patch.multiple(
        MAIN,
        get_valid_access_token=lambda uid: "test-token",
        DropboxClient=lambda token: client,
    )


class ToolManifestTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_lists_three_tools(self):
        manifest = await MAIN.get_omi_tools_manifest()
        self.assertEqual(len(manifest["tools"]), 3)

    async def test_manifest_tool_names_match_endpoints(self):
        manifest = await MAIN.get_omi_tools_manifest()
        by_name = {tool["name"]: tool for tool in manifest["tools"]}
        self.assertEqual(by_name["search_dropbox"]["endpoint"], "/tools/search")
        self.assertEqual(by_name["list_dropbox_conversations"]["endpoint"], "/tools/list")
        self.assertEqual(by_name["read_dropbox_file"]["endpoint"], "/tools/read")
        for tool in manifest["tools"]:
            self.assertEqual(tool["method"], "POST")

    async def test_manifest_required_parameters(self):
        manifest = await MAIN.get_omi_tools_manifest()
        by_name = {tool["name"]: tool for tool in manifest["tools"]}
        self.assertEqual(by_name["search_dropbox"]["parameters"]["required"], ["query"])
        self.assertEqual(by_name["read_dropbox_file"]["parameters"]["required"], ["path"])
        self.assertEqual(by_name["list_dropbox_conversations"]["parameters"]["required"], [])

    async def test_manifest_tools_declare_auth_and_status(self):
        manifest = await MAIN.get_omi_tools_manifest()
        for tool in manifest["tools"]:
            self.assertTrue(tool["auth_required"], tool["name"])
            self.assertTrue(tool["status_message"], tool["name"])


class ToolPayloadParsingTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_malformed_json_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest())
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_search_json_array_body_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload=[1, 2, 3]))
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_search_json_scalar_body_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload=42))
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_search_json_null_body_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload=None))
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_list_malformed_json_returns_tool_error(self):
        response = await MAIN.tool_list_dropbox(FakeRequest())
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_list_non_dict_body_returns_tool_error(self):
        response = await MAIN.tool_list_dropbox(FakeRequest(payload="just a string"))
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_read_non_dict_body_returns_tool_error(self):
        response = await MAIN.tool_read_dropbox_file(FakeRequest(payload=[("uid", "u")]))
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)

    async def test_read_malformed_json_returns_tool_error(self):
        response = await MAIN.tool_read_dropbox_file(FakeRequest())
        assert_tool_contract(self, response)
        self.assertIsNotNone(response.error)


class ToolParameterTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_missing_uid_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"query": "report"}))
        self.assertEqual(assert_tool_contract(self, response).error, "Missing user ID")

    async def test_search_null_uid_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": None, "query": "report"}))
        self.assertEqual(assert_tool_contract(self, response).error, "Missing user ID")

    async def test_search_blank_uid_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "   ", "query": "report"}))
        self.assertEqual(assert_tool_contract(self, response).error, "Missing user ID")

    async def test_search_null_query_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": None}))
        self.assertEqual(assert_tool_contract(self, response).error, "Please provide a search query")

    async def test_search_whitespace_query_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "   "}))
        self.assertEqual(assert_tool_contract(self, response).error, "Please provide a search query")

    async def test_search_container_query_returns_tool_error(self):
        response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": ["a", "b"]}))
        self.assertEqual(assert_tool_contract(self, response).error, "Please provide a search query")

    async def test_search_numeric_uid_and_query_are_coerced(self):
        client = make_client(search_results=[])
        with connected_client(client):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": 123, "query": "report"}))
        self.assertIsNone(assert_tool_contract(self, response).error)
        self.assertEqual(client.calls, [("search", "report", 10)])

    async def test_read_null_path_returns_tool_error(self):
        response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": None}))
        self.assertEqual(assert_tool_contract(self, response).error, "Please provide a file path")

    async def test_read_whitespace_path_returns_tool_error(self):
        response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "  \t "}))
        self.assertEqual(assert_tool_contract(self, response).error, "Please provide a file path")

    async def test_list_null_folder_falls_back_to_settings_default(self):
        client = make_client(list_results=[])
        with connected_client(client), patch.object(
            MAIN, "get_user_settings", lambda uid: {"folder_name": "My Docs"}
        ):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1", "folder": None}))
        self.assertIsNone(assert_tool_contract(self, response).error)
        self.assertEqual(client.calls, [("list", "/My Docs", 20)])

    async def test_list_whitespace_folder_falls_back_to_settings_default(self):
        client = make_client(list_results=[])
        with connected_client(client), patch.object(
            MAIN, "get_user_settings", lambda uid: {"folder_name": "Omi Conversations"}
        ):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1", "folder": "   "}))
        self.assertIsNone(assert_tool_contract(self, response).error)
        self.assertEqual(client.calls, [("list", "/Omi Conversations", 20)])


class ToolHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoint(self):
        self.assertEqual(await MAIN.health(), {"status": "healthy"})

    async def test_search_requires_connection(self):
        with patch.object(MAIN, "get_valid_access_token", lambda uid: None):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "x"}))
        self.assertEqual(
            assert_tool_contract(self, response).error,
            "Please connect your Dropbox account first in the app settings.",
        )

    async def test_search_formats_results(self):
        client = make_client(search_results=[
            {"name": "summary.md", "path": "/Omi/summary.md", "type": "file", "size": 2048},
            {"name": "Archive", "path": "/Omi/Archive", "type": "folder", "size": 0},
        ])
        with connected_client(client):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "summary"}))
        result = assert_tool_contract(self, response).result
        self.assertIn("Found 2 file(s)", result)
        self.assertIn("summary.md", result)
        self.assertIn("/Omi/Archive", result)

    async def test_search_propagates_client_error(self):
        client = make_client(search_error="rate limited")
        with connected_client(client):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "x"}))
        self.assertIn("Search failed", assert_tool_contract(self, response).error)

    async def test_search_empty_results_message(self):
        client = make_client(search_results=[])
        with connected_client(client):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "zzz"}))
        self.assertIn("No files found", assert_tool_contract(self, response).result)

    async def test_raised_client_exception_never_leaks_into_search_error(self):
        """A throwing client must produce a fixed error string, not str(e)."""
        client = SimpleNamespace()
        marker = "s3cr3t-internal-db-host.internal.example"
        client.search_files = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(marker))
        client.list_folder = lambda *a, **k: ([], None)
        client.download_file = lambda *a, **k: (None, "nf")
        with connected_client(client):
            response = await MAIN.tool_search_dropbox(FakeRequest(payload={"uid": "u1", "query": "x"}))
        error = assert_tool_contract(self, response).error
        self.assertEqual(error, "Search error")
        self.assertNotIn(marker, error)

    async def test_raised_client_exception_never_leaks_into_list_error(self):
        client = SimpleNamespace()
        marker = "s3cr3t-internal-db-host.internal.example"
        client.search_files = lambda *a, **k: ([], None)
        client.list_folder = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(marker))
        client.download_file = lambda *a, **k: (None, "nf")
        with connected_client(client):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1"}))
        error = assert_tool_contract(self, response).error
        self.assertEqual(error, "List error")
        self.assertNotIn(marker, error)

    async def test_raised_client_exception_never_leaks_into_read_error(self):
        client = SimpleNamespace()
        marker = "s3cr3t-internal-db-host.internal.example"
        client.search_files = lambda *a, **k: ([], None)
        client.list_folder = lambda *a, **k: ([], None)
        client.download_file = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(marker))
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/x.txt"}))
        error = assert_tool_contract(self, response).error
        self.assertEqual(error, "Read error")
        self.assertNotIn(marker, error)

    async def test_list_formats_results(self):
        client = make_client(list_results=[
            {"name": "Meeting (2024-01-20)", "path": "/Omi/Meeting", "type": "folder", "size": 0, "modified": "2024-01-20T10:00:00Z"},
            {"name": "audio.wav", "path": "/Omi/audio.wav", "type": "file", "size": 4096, "modified": ""},
        ])
        with connected_client(client):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1", "folder": "/Omi"}))
        result = assert_tool_contract(self, response).result
        self.assertIn("Files in `/Omi`", result)
        self.assertIn("Meeting (2024-01-20)", result)
        self.assertIn("audio.wav", result)

    async def test_list_empty_folder_message(self):
        client = make_client(list_results=[])
        with connected_client(client), patch.object(
            MAIN, "get_user_settings", lambda uid: {"folder_name": "Omi Conversations"}
        ):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1"}))
        self.assertIn("No files found", assert_tool_contract(self, response).result)

    async def test_list_propagates_client_error(self):
        client = make_client(list_error="not a folder")
        with connected_client(client):
            response = await MAIN.tool_list_dropbox(FakeRequest(payload={"uid": "u1", "folder": "/nope"}))
        self.assertIn("Could not list folder", assert_tool_contract(self, response).error)

    async def test_read_returns_text_content(self):
        client = make_client(download_bytes=b"hello dropbox")
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/notes.txt"}))
        result = assert_tool_contract(self, response).result
        self.assertIn("notes.txt", result)
        self.assertIn("hello dropbox", result)

    async def test_read_download_error(self):
        client = make_client(download_error="path not found")
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/missing.txt"}))
        self.assertIn("Could not download file", assert_tool_contract(self, response).error)

    async def test_read_empty_file_error(self):
        client = make_client(download_bytes=b"")
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/empty.txt"}))
        self.assertEqual(assert_tool_contract(self, response).error, "File is empty")

    async def test_read_rejects_image_file(self):
        client = make_client(download_bytes=b"\x89PNG\r\n\x1a\n")
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/pic.png"}))
        self.assertIn("Image files cannot be read", assert_tool_contract(self, response).error)

    async def test_read_truncates_long_text(self):
        client = make_client(download_bytes=("x" * 20000).encode())
        with connected_client(client):
            response = await MAIN.tool_read_dropbox_file(FakeRequest(payload={"uid": "u1", "path": "/big.txt"}))
        result = assert_tool_contract(self, response).result
        self.assertIn("Truncated", result)
        self.assertLess(len(result), 20000)


class ChatToolContractTests(unittest.TestCase):
    def test_response_result_only_passes_contract(self):
        response = MODELS.ChatToolResponse(result="ok")
        self.assertIs(response.validate_result_or_error(), response)

    def test_response_error_only_passes_contract(self):
        response = MODELS.ChatToolResponse(error="bad")
        self.assertIs(response.validate_result_or_error(), response)

    def test_response_rejects_result_and_error_together(self):
        try:
            response = MODELS.ChatToolResponse(result="ok", error="bad")
        except Exception:
            return  # real pydantic rejects at construction time
        with self.assertRaises(Exception):
            response.validate_result_or_error()

    def test_response_rejects_neither_field_set(self):
        try:
            response = MODELS.ChatToolResponse()
        except Exception:
            return
        with self.assertRaises(Exception):
            response.validate_result_or_error()

    def test_coerce_tool_text_rejects_null_containers_and_blank(self):
        for value in (None, "", "   ", ["a"], {"a": 1}, True, False, (1, 2)):
            with self.subTest(value=value):
                self.assertIsNone(MODELS.coerce_tool_text(value))

    def test_coerce_tool_text_strips_and_accepts_scalars(self):
        self.assertEqual(MODELS.coerce_tool_text("  report  "), "report")
        self.assertEqual(MODELS.coerce_tool_text(42), "42")
        self.assertEqual(MODELS.coerce_tool_text(1.5), "1.5")

    def test_request_models_coerce_payload_fields(self):
        req = MODELS.SearchDropboxRequest.from_payload({"uid": " u1 ", "query": None})
        self.assertEqual(req.uid, "u1")
        self.assertIsNone(req.query)
        req = MODELS.ListDropboxRequest.from_payload({"uid": "u1", "folder": " /F "})
        self.assertEqual(req.folder, "/F")
        req = MODELS.ReadDropboxRequest.from_payload({"uid": "u1"})
        self.assertIsNone(req.path)


class AudioBufferTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        MAIN.audio_buffers.clear()
        MAIN.audio_sample_rates.clear()
        MAIN.audio_buffer_updated_at.clear()

    async def test_max_buffer_is_50mb(self):
        self.assertEqual(MAIN.MAX_AUDIO_BUFFER_BYTES, 50 * 1024 * 1024)

    async def test_audio_accumulates_chunks(self):
        response = await MAIN.receive_audio(FakeRequest(body=b"abc"), uid="u1", sample_rate=16000)
        self.assertEqual(response["status"], "ok")
        response = await MAIN.receive_audio(FakeRequest(body=b"def"), uid="u1", sample_rate=16000)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(MAIN.audio_buffers["u1"], b"abcdef")
        self.assertEqual(MAIN.audio_sample_rates["u1"], 16000)

    async def test_audio_rejects_chunk_over_limit(self):
        with patch.object(MAIN, "MAX_AUDIO_BUFFER_BYTES", 8):
            response = await MAIN.receive_audio(FakeRequest(body=b"012345678"), uid="u1", sample_rate=16000)
        self.assertEqual(response["status"], "error")
        self.assertEqual(len(MAIN.audio_buffers.get("u1", b"")), 0)

    async def test_audio_keeps_prior_bytes_after_overflow_reject(self):
        with patch.object(MAIN, "MAX_AUDIO_BUFFER_BYTES", 8):
            ok = await MAIN.receive_audio(FakeRequest(body=b"0123"), uid="u1", sample_rate=16000)
            self.assertEqual(ok["status"], "ok")
            rejected = await MAIN.receive_audio(FakeRequest(body=b"456789"), uid="u1", sample_rate=16000)
            self.assertEqual(rejected["status"], "error")
            self.assertEqual(MAIN.audio_buffers["u1"], b"0123")
            accepted = await MAIN.receive_audio(FakeRequest(body=b"45"), uid="u1", sample_rate=16000)
            self.assertEqual(accepted["status"], "ok")
            self.assertEqual(MAIN.audio_buffers["u1"], b"012345")

    async def test_audio_buffer_never_exceeds_cap(self):
        with patch.object(MAIN, "MAX_AUDIO_BUFFER_BYTES", 10):
            for _ in range(5):
                await MAIN.receive_audio(FakeRequest(body=b"xxxx"), uid="u1", sample_rate=16000)
        self.assertLessEqual(len(MAIN.audio_buffers["u1"]), 10)

    async def test_audio_rejects_out_of_range_sample_rates(self):
        for rate in (0, -1, 7999, 48001, "16000"):
            with self.subTest(rate=rate):
                response = await MAIN.receive_audio(FakeRequest(body=b"x"), uid="u1", sample_rate=rate)
                self.assertEqual(response["status"], "error")
                self.assertNotIn("u1", MAIN.audio_buffers)

    async def test_audio_rejects_missing_or_blank_uid(self):
        for uid in ("", "   "):
            with self.subTest(uid=uid):
                response = await MAIN.receive_audio(FakeRequest(body=b"x"), uid=uid, sample_rate=16000)
                self.assertEqual(response["status"], "error")

    async def test_audio_evicts_stale_buffers(self):
        MAIN.audio_buffers["old"] = b"stale"
        MAIN.audio_sample_rates["old"] = 16000
        MAIN.audio_buffer_updated_at["old"] = time.time() - 7200
        response = await MAIN.receive_audio(FakeRequest(body=b"x"), uid="fresh", sample_rate=16000)
        self.assertEqual(response["status"], "ok")
        self.assertNotIn("old", MAIN.audio_buffers)
        self.assertNotIn("old", MAIN.audio_buffer_updated_at)
        self.assertEqual(MAIN.audio_buffers["fresh"], b"x")

    async def test_get_and_clear_returns_wav_and_clears(self):
        await MAIN.receive_audio(FakeRequest(body=b"\x00\x01" * 100), uid="u1", sample_rate=8000)
        wav_bytes = MAIN.get_and_clear_audio("u1")
        self.assertIsNotNone(wav_bytes)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 8000)
        self.assertNotIn("u1", MAIN.audio_buffers)
        self.assertIsNone(MAIN.get_and_clear_audio("u1"))


class AccessTokenTests(unittest.TestCase):
    def test_no_tokens_returns_none(self):
        with patch.object(MAIN, "get_dropbox_tokens", lambda uid: None):
            self.assertIsNone(MAIN.get_valid_access_token("u1"))

    def test_fresh_token_returned(self):
        future = (MAIN.datetime.now(MAIN.timezone.utc) + MAIN.timedelta(hours=1)).isoformat()
        tokens = {"access_token": "tok", "refresh_token": "ref", "expires_at": future}
        with patch.object(MAIN, "get_dropbox_tokens", lambda uid: tokens):
            self.assertEqual(MAIN.get_valid_access_token("u1"), "tok")

    def test_expired_token_triggers_refresh(self):
        past = (MAIN.datetime.now(MAIN.timezone.utc) - MAIN.timedelta(hours=1)).isoformat()
        tokens = {"access_token": "old", "refresh_token": "ref", "expires_at": past}
        with patch.object(MAIN, "get_dropbox_tokens", lambda uid: tokens), patch.object(
            MAIN, "refresh_access_token", lambda refresh: "new-tok"
        ):
            self.assertEqual(MAIN.get_valid_access_token("u1"), "new-tok")


class HelperTests(unittest.TestCase):
    def test_create_wav_file_produces_parseable_wav(self):
        wav_bytes = MAIN.create_wav_file(b"\x00\x01" * 50, sample_rate=24000)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.getnframes(), 50)

    def test_create_folder_name_sanitizes_and_stamps_date(self):
        name = MAIN.create_folder_name('Bad:/Title*?', MAIN.datetime(2024, 1, 20, 10, 30))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)
        self.assertIn("2024-01-20", name)

    def test_generate_summary_markdown(self):
        item = SimpleNamespace(description="Ship it", completed=False)
        conversation = SimpleNamespace(
            structured=SimpleNamespace(
                title="Sync", emoji=":memo:", category="work",
                overview="Discussed the launch.", action_items=[item],
            ),
            finished_at=None,
            created_at=MAIN.datetime(2024, 1, 20, 10, 30),
            plugins_results=[],
        )
        markdown = MAIN.generate_summary_markdown(conversation)
        self.assertIn("# Sync", markdown)
        self.assertIn("Discussed the launch.", markdown)
        self.assertIn("- [ ] Ship it", markdown)


if __name__ == "__main__":
    unittest.main()
