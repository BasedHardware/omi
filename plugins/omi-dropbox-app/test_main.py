"""Hermetic unit tests for Omi Dropbox Integration App.

Runs with standard library unittest and asyncio without requiring external network access.
"""

import asyncio
import io
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure plugins/omi-dropbox-app is at index 0 and SDK is available
APP_DIR = Path(__file__).resolve().parent
SDK_SRC = APP_DIR.parent / "omi-plugin-sdk" / "src"

if str(SDK_SRC) not in sys.path:
    sys.path.append(str(SDK_SRC))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Lightweight runtime stubs for environments lacking third-party libraries
if "requests" not in sys.modules:
    try:
        import requests
    except ImportError:
        requests = types.ModuleType("requests")
        requests.get = lambda *a, **k: None
        requests.post = lambda *a, **k: None
        requests.put = lambda *a, **k: None
        requests.delete = lambda *a, **k: None
        sys.modules["requests"] = requests

if "tenacity" not in sys.modules:
    try:
        import tenacity
    except ImportError:
        tenacity = types.ModuleType("tenacity")

        def dummy_retry(*args, **kwargs):
            def decorator(f):
                return f
            return decorator

        tenacity.retry = dummy_retry
        tenacity.stop_after_attempt = lambda n: n
        tenacity.wait_exponential = lambda *a, **k: None
        tenacity.retry_if_exception_type = lambda *a, **k: None
        sys.modules["tenacity"] = tenacity

if "dotenv" not in sys.modules:
    try:
        import dotenv
    except ImportError:
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda *a, **k: None
        sys.modules["dotenv"] = dotenv

if "omi_plugin_sdk" not in sys.modules:
    try:
        import omi_plugin_sdk
    except ImportError:
        sdk = types.ModuleType("omi_plugin_sdk")
        sdk_models = types.ModuleType("omi_plugin_sdk.models")

        class EndpointResponse:
            def __init__(self, message=""):
                self.message = message

        class Conversation:
            pass

        sdk_models.ActionItem = None
        sdk_models.Conversation = Conversation
        sdk_models.EndpointResponse = EndpointResponse
        sdk_models.Structured = None
        sdk_models.TranscriptSegment = None
        sdk.models = sdk_models
        sys.modules["omi_plugin_sdk"] = sdk
        sys.modules["omi_plugin_sdk.models"] = sdk_models

if "fastapi" not in sys.modules:
    try:
        import fastapi
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                def decorator(f):
                    return f
                return decorator

            def post(self, *args, **kwargs):
                def decorator(f):
                    return f
                return decorator

        class Query:
            def __init__(self, default=None):
                self.default = default

        class Request:
            pass

        fastapi.FastAPI = FastAPI
        fastapi.Query = Query
        fastapi.Request = Request

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code

        class RedirectResponse:
            def __init__(self, url, status_code=307):
                self.url = url
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.RedirectResponse = RedirectResponse
        responses.JSONResponse = JSONResponse

        sys.modules["fastapi"] = fastapi
        sys.modules["fastapi.responses"] = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
        sys.modules["pydantic"] = pydantic

# Now import application modules
import main
import models
from models import ChatToolResponse


class MockRequest:
    """Mock FastAPI Request object for testing."""

    def __init__(self, json_data=None, json_error=False, body_bytes=b""):
        self._json_data = json_data
        self._json_error = json_error
        self._body_bytes = body_bytes

    async def json(self):
        if self._json_error:
            raise ValueError("Malformed JSON body")
        return self._json_data

    async def body(self):
        return self._body_bytes


class ToolsManifestTests(unittest.TestCase):
    """Tests for Omi chat tools manifest endpoint."""

    def test_tools_manifest_structure(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        tools = manifest["tools"]
        self.assertEqual(len(tools), 3)

        tool_names = [t["name"] for t in tools]
        self.assertIn("search_dropbox", tool_names)
        self.assertIn("list_dropbox_conversations", tool_names)
        self.assertIn("read_dropbox_file", tool_names)

        for t in tools:
            self.assertTrue(t.get("auth_required"))
            self.assertEqual(t.get("method"), "POST")
            self.assertTrue(t.get("endpoint").startswith("/tools/"))
            self.assertIn("properties", t.get("parameters", {}))


class SearchDropboxHandlerTests(unittest.TestCase):
    """Tests for POST /tools/search endpoint."""

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_search_happy_path(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.search_files.return_value = (
            [
                {"name": "meeting_notes.txt", "path": "/notes/meeting_notes.txt", "type": "file", "size": 2048},
                {"name": "Audio", "path": "/Audio", "type": "folder", "size": 0},
            ],
            None,
        )
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "query": "meeting"})
        res = asyncio.run(main.tool_search_dropbox(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIsNone(res.error)
        self.assertIsNotNone(res.result)
        self.assertIn("Found 2 file(s)", res.result)
        self.assertIn("meeting_notes.txt", res.result)
        self.assertIn("2.0 KB", res.result)
        self.assertIn("📁 **Audio**", res.result)

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_search_no_results(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.search_files.return_value = ([], None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "query": "nonexistent"})
        res = asyncio.run(main.tool_search_dropbox(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No files found matching 'nonexistent'")

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_search_client_error(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.search_files.return_value = (None, "Rate limit exceeded")
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "query": "test"})
        res = asyncio.run(main.tool_search_dropbox(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Search failed: Rate limit exceeded")

    @patch.object(main, "get_valid_access_token", return_value=None)
    def test_search_unauthenticated(self, _mock_token):
        req = MockRequest(json_data={"uid": "u1", "query": "notes"})
        res = asyncio.run(main.tool_search_dropbox(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIn("Please connect your Dropbox account first", res.error)

    def test_search_missing_uid(self):
        req = MockRequest(json_data={"query": "notes"})
        res = asyncio.run(main.tool_search_dropbox(req))
        self.assertEqual(res.error, "Missing user ID")

    def test_search_empty_or_whitespace_query(self):
        req1 = MockRequest(json_data={"uid": "u1", "query": ""})
        res1 = asyncio.run(main.tool_search_dropbox(req1))
        self.assertEqual(res1.error, "Please provide a search query")

        req2 = MockRequest(json_data={"uid": "u1", "query": "    "})
        res2 = asyncio.run(main.tool_search_dropbox(req2))
        self.assertEqual(res2.error, "Please provide a search query")

    def test_search_null_query(self):
        req = MockRequest(json_data={"uid": "u1", "query": None})
        res = asyncio.run(main.tool_search_dropbox(req))
        self.assertEqual(res.error, "Please provide a search query")

    def test_search_non_dict_payload(self):
        req = MockRequest(json_data=["query", "notes"])
        res = asyncio.run(main.tool_search_dropbox(req))
        self.assertEqual(res.error, "Payload must be a JSON object")

    def test_search_malformed_json(self):
        req = MockRequest(json_error=True)
        res = asyncio.run(main.tool_search_dropbox(req))
        self.assertEqual(res.error, "Invalid JSON payload")


class ListDropboxHandlerTests(unittest.TestCase):
    """Tests for POST /tools/list endpoint."""

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_list_custom_folder_happy_path(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = (
            [
                {
                    "name": "meeting.wav",
                    "type": "file",
                    "size": 10240,
                    "modified": "2026-03-15T10:00:00Z",
                },
                {
                    "name": "SubFolder",
                    "type": "folder",
                    "size": 0,
                    "modified": "2026-03-14T09:00:00Z",
                },
            ],
            None,
        )
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "folder": "/CustomFolder"})
        res = asyncio.run(main.tool_list_dropbox(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIsNone(res.error)
        self.assertIn("Files in `/CustomFolder`:", res.result)
        self.assertIn("meeting.wav", res.result)
        self.assertIn("10.0 KB", res.result)
        self.assertIn("2026-03-15", res.result)
        self.assertIn("SubFolder", res.result)

    @patch.object(main, "get_user_settings", return_value={"folder_name": "Saved Chats"})
    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_list_default_folder_when_omitted(self, mock_client_cls, _mock_token, _mock_settings):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = ([], None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1"})
        res = asyncio.run(main.tool_list_dropbox(req))

        mock_client.list_folder.assert_called_once_with("/Saved Chats", limit=20)
        self.assertEqual(res.result, "No files found in `/Saved Chats`")

    @patch.object(main, "get_user_settings", return_value={"folder_name": "Saved Chats"})
    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_list_default_folder_when_null(self, mock_client_cls, _mock_token, _mock_settings):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = ([], None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "folder": None})
        res = asyncio.run(main.tool_list_dropbox(req))

        mock_client.list_folder.assert_called_once_with("/Saved Chats", limit=20)
        self.assertEqual(res.result, "No files found in `/Saved Chats`")

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_list_folder_client_error(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = (None, "Folder not found")
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "folder": "/Missing"})
        res = asyncio.run(main.tool_list_dropbox(req))

        self.assertEqual(res.error, "Could not list folder: Folder not found")

    @patch.object(main, "get_valid_access_token", return_value=None)
    def test_list_unauthenticated(self, _mock_token):
        req = MockRequest(json_data={"uid": "u1"})
        res = asyncio.run(main.tool_list_dropbox(req))
        self.assertIn("Please connect your Dropbox account first", res.error)

    def test_list_missing_uid(self):
        req = MockRequest(json_data={"folder": "/test"})
        res = asyncio.run(main.tool_list_dropbox(req))
        self.assertEqual(res.error, "Missing user ID")

    def test_list_non_dict_payload(self):
        req = MockRequest(json_data="string_payload")
        res = asyncio.run(main.tool_list_dropbox(req))
        self.assertEqual(res.error, "Payload must be a JSON object")


class ReadDropboxHandlerTests(unittest.TestCase):
    """Tests for POST /tools/read endpoint."""

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_read_text_file_happy_path(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.download_file.return_value = (b"Meeting summary:\nAction 1\nAction 2", None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "path": "/notes/summary.txt"})
        res = asyncio.run(main.tool_read_dropbox_file(req))

        self.assertIsInstance(res, ChatToolResponse)
        self.assertIsNone(res.error)
        self.assertIn("Contents of `summary.txt`:", res.result)
        self.assertIn("Meeting summary:\nAction 1\nAction 2", res.result)

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_read_empty_file_error(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.download_file.return_value = (b"", None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "path": "/notes/empty.txt"})
        res = asyncio.run(main.tool_read_dropbox_file(req))

        self.assertEqual(res.error, "File is empty")

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_read_download_failure(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.download_file.return_value = (None, "File not found")
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "path": "/notes/missing.txt"})
        res = asyncio.run(main.tool_read_dropbox_file(req))

        self.assertEqual(res.error, "Could not download file: File not found")

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_read_unsupported_extensions(self, mock_client_cls, _mock_token):
        mock_client = MagicMock()
        mock_client.download_file.return_value = (b"some bytes", None)
        mock_client_cls.return_value = mock_client

        unsupported = [
            ("doc.docx", "Word documents (.doc/.docx) are not yet supported"),
            ("image.png", "Image files cannot be read as text"),
            ("song.mp3", "Audio files cannot be read as text"),
            ("clip.mp4", "Video files cannot be read as text"),
        ]

        for filename, expected_err in unsupported:
            req = MockRequest(json_data={"uid": "u1", "path": f"/files/{filename}"})
            res = asyncio.run(main.tool_read_dropbox_file(req))
            self.assertIn(expected_err, res.error)

    @patch.object(main, "get_valid_access_token", return_value="test_token")
    @patch("main.DropboxClient")
    def test_read_large_file_truncation(self, mock_client_cls, _mock_token):
        large_content = b"x" * 20000
        mock_client = MagicMock()
        mock_client.download_file.return_value = (large_content, None)
        mock_client_cls.return_value = mock_client

        req = MockRequest(json_data={"uid": "u1", "path": "/large.txt"})
        res = asyncio.run(main.tool_read_dropbox_file(req))

        self.assertIn("[Truncated - file has 20000 characters total]", res.result)

    def test_read_missing_path(self):
        req1 = MockRequest(json_data={"uid": "u1", "path": ""})
        res1 = asyncio.run(main.tool_read_dropbox_file(req1))
        self.assertEqual(res1.error, "Please provide a file path")

        req2 = MockRequest(json_data={"uid": "u1", "path": None})
        res2 = asyncio.run(main.tool_read_dropbox_file(req2))
        self.assertEqual(res2.error, "Please provide a file path")

    def test_read_missing_uid(self):
        req = MockRequest(json_data={"path": "/file.txt"})
        res = asyncio.run(main.tool_read_dropbox_file(req))
        self.assertEqual(res.error, "Missing user ID")

    def test_read_non_dict_payload(self):
        req = MockRequest(json_data=123)
        res = asyncio.run(main.tool_read_dropbox_file(req))
        self.assertEqual(res.error, "Payload must be a JSON object")


class AudioAndBufferTests(unittest.TestCase):
    """Tests for audio buffer handling and WAV file generation."""

    def setUp(self):
        main.audio_buffers.clear()
        main.audio_sample_rates.clear()

    def test_create_wav_file_valid_header(self):
        pcm_bytes = b"\x00\x00" * 160
        wav = main.create_wav_file(pcm_bytes, 16000)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav[:16])

    def test_create_wav_file_invalid_sample_rate_fallback(self):
        pcm_bytes = b"\x00\x00" * 80
        wav = main.create_wav_file(pcm_bytes, -1)
        self.assertTrue(wav.startswith(b"RIFF"))

    def test_audio_buffer_normal_accumulation(self):
        req = MockRequest(body_bytes=b"sample_audio_chunk")
        res = asyncio.run(main.receive_audio(req, uid="user1", sample_rate=16000))
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(main.audio_buffers["user1"], b"sample_audio_chunk")

        wav = main.get_and_clear_audio("user1")
        self.assertIsNotNone(wav)
        self.assertNotIn("user1", main.audio_buffers)

    def test_audio_buffer_overflow_protection(self):
        main.audio_buffers["user_overflow"] = b"x" * (main.MAX_AUDIO_BUFFER_BYTES - 10)
        req = MockRequest(body_bytes=b"excessive_audio_bytes_beyond_cap")
        res = asyncio.run(main.receive_audio(req, uid="user_overflow", sample_rate=16000))
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Audio buffer limit exceeded", res.get("message", ""))


class ModelsAndContractTests(unittest.TestCase):
    """Tests for Pydantic models contract."""

    def test_chat_tool_response_model(self):
        resp_success = ChatToolResponse(result="Done")
        self.assertEqual(resp_success.result, "Done")
        self.assertIsNone(resp_success.error)

        resp_error = ChatToolResponse(error="Failed")
        self.assertEqual(resp_error.error, "Failed")
        self.assertIsNone(resp_error.result)

    def test_request_models(self):
        s_req = models.SearchDropboxRequest(uid="u1", query="test")
        self.assertEqual(s_req.uid, "u1")
        self.assertEqual(s_req.query, "test")

        l_req = models.ListDropboxRequest(uid="u1")
        self.assertEqual(l_req.uid, "u1")
        self.assertIsNone(l_req.folder)

        r_req = models.ReadDropboxRequest(uid="u1", path="/a.txt")
        self.assertEqual(r_req.uid, "u1")
        self.assertEqual(r_req.path, "/a.txt")


if __name__ == "__main__":
    unittest.main()
