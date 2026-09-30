"""Hermetic regression test suite for plugins/oauth hardening.

Verifies:
1. NotionClient requests include default timeouts and propagate custom timeouts.
2. Network exceptions (Timeout, ConnectionError, RequestException) are safely caught
   and returned as structured error dictionaries.
3. Non-JSON responses (e.g. 502/504 Bad Gateway) are defensively parsed without JSONDecodeError.
4. NotionDatabasePropertyModel, NotionDatabaseModel, and NotionOAuthModel safely handle
   None, empty dicts, missing keys, and malformed collections.
5. Conversation payload parsing defensively handles None structured data, invalid emoji
   encodings, None/empty transcript segments, missing timestamps, and clock skew.
6. Database validation and create_notion_row gracefully handle timeouts, HTTP errors,
   and missing database schema fields.

Executes under pure standard library Python (python3 -S) with zero external dependencies.
"""

from datetime import datetime, timedelta
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

_plugins_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugins_dir not in sys.path:
    sys.path.insert(0, _plugins_dir)



def _stub_requests():
    if "requests" in sys.modules:
        return
    req = types.ModuleType("requests")
    req_exc = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        pass

    class Timeout(RequestException):
        pass

    class ConnectionError(RequestException):
        pass

    req_exc.RequestException = RequestException
    req_exc.HTTPError = HTTPError
    req_exc.Timeout = Timeout
    req_exc.ConnectionError = ConnectionError

    class Response:
        def __init__(self, status_code=200, text="{}", json_data=None):
            self.status_code = status_code
            self.text = text
            self._json_data = json_data if json_data is not None else {}

        def json(self):
            if isinstance(self._json_data, Exception):
                raise self._json_data
            return self._json_data

    req.Response = Response
    req.exceptions = req_exc
    req.RequestException = RequestException
    req.post = MagicMock(return_value=Response(200))
    req.get = MagicMock(return_value=Response(200))

    sys.modules["requests"] = req
    sys.modules["requests.exceptions"] = req_exc


def _stub_fastapi():
    if "fastapi" in sys.modules:
        return
    fa = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

    class Request:
        pass

    fa.HTTPException = HTTPException
    fa.APIRouter = APIRouter
    fa.Request = Request
    sys.modules["fastapi"] = fa

    far = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        pass

    far.HTMLResponse = HTMLResponse
    sys.modules["fastapi.responses"] = far

    fat = types.ModuleType("fastapi.templating")

    class Jinja2Templates:
        def __init__(self, *args, **kwargs):
            pass

        def TemplateResponse(self, name, context):
            return {"template": name, "context": context}

    fat.Jinja2Templates = Jinja2Templates
    sys.modules["fastapi.templating"] = fat


def _stub_pydantic():
    if "pydantic" in sys.modules:
        return
    pyd = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, mode="json"):
            return self.__dict__.copy()

        def dict(self):
            return self.__dict__.copy()

    def Field(default=None, **kwargs):
        return default

    pyd.BaseModel = BaseModel
    pyd.Field = Field
    sys.modules["pydantic"] = pyd


def _stub_db_and_models():
    if "db" not in sys.modules:
        db_mod = types.ModuleType("db")
        db_mod.get_notion_crm_api_key = MagicMock(return_value="test_api_key")
        db_mod.get_notion_database_id = MagicMock(return_value="test_db_id")
        db_mod.store_notion_crm_api_key = MagicMock()
        db_mod.store_notion_database_id = MagicMock()
        sys.modules["db"] = db_mod

    if "models" not in sys.modules:
        models_mod = types.ModuleType("models")

        class Conversation:
            def __init__(
                self,
                id="conv_1",
                structured=None,
                transcript_segments=None,
                started_at=None,
                finished_at=None,
            ):
                self.id = id
                self.structured = structured
                self.transcript_segments = transcript_segments or []
                self.started_at = started_at
                self.finished_at = finished_at

        class Structured:
            def __init__(self, title="Test Title", overview="Test Overview", emoji="🧠", category="Work"):
                self.title = title
                self.overview = overview
                self.emoji = emoji
                self.category = category

        class TranscriptSegment:
            def __init__(self, speaker="Speaker 1", text="Hello world"):
                self.speaker = speaker
                self.text = text

        class EndpointResponse:
            def __init__(self, message=""):
                self.message = message

        models_mod.Conversation = Conversation
        models_mod.Structured = Structured
        models_mod.TranscriptSegment = TranscriptSegment
        models_mod.EndpointResponse = EndpointResponse
        sys.modules["models"] = models_mod


def _install_hermetic_stubs():
    _stub_requests()
    _stub_fastapi()
    _stub_pydantic()
    _stub_db_and_models()


_install_hermetic_stubs()

# Import target modules under test
from oauth import client
from oauth.client import (
    DEFAULT_TIMEOUT,
    NotionClient,
    NotionDatabaseModel,
    NotionDatabasePropertyModel,
    NotionOAuthModel,
)
from oauth import conversation_created
from oauth.conversation_created import (
    _build_notion_conversation_properties,
    create_notion_row,
    validate_database,
)
from models import Conversation, Structured, TranscriptSegment
from fastapi import HTTPException


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="{}"):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class NotionClientHardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = NotionClient(
            oauth_client_id="test_id",
            oauth_client_secret="test_secret",
            oauth_redirect_uri="https://test.omi.me/callback",
            auth_url="https://api.notion.com/v1/oauth/authorize?test=1",
        )

    @patch("requests.get")
    def test_get_database_default_timeout(self, mock_get):
        mock_get.return_value = FakeResponse(200, {"id": "db_1", "properties": {}})
        res = self.client.get_database("db_1", "tok_1")
        self.assertIn("result", res)
        self.assertEqual(res["result"].id, "db_1")
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs.get("timeout"), DEFAULT_TIMEOUT)

    @patch("requests.get")
    def test_get_database_custom_timeout(self, mock_get):
        mock_get.return_value = FakeResponse(200, {"id": "db_2", "properties": {}})
        res = self.client.get_database("db_2", "tok_2", timeout=25.0)
        self.assertIn("result", res)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs.get("timeout"), 25.0)

    @patch("requests.get")
    def test_get_database_request_exception(self, mock_get):
        req_exc = sys.modules["requests.exceptions"].Timeout("Connection timed out")
        mock_get.side_effect = req_exc
        res = self.client.get_database("db_1", "tok_1")
        self.assertIn("error", res)
        self.assertEqual(res["error"]["status"], 500)
        self.assertEqual(res["error"]["code"], "Timeout")

    @patch("requests.get")
    def test_get_database_non_json_error(self, mock_get):
        mock_get.return_value = FakeResponse(
            502,
            json_data=ValueError("No JSON could be decoded"),
            text="<html>502 Bad Gateway</html>",
        )
        res = self.client.get_database("db_1", "tok_1")
        self.assertIn("error", res)
        self.assertEqual(res["error"]["status"], 502)

    @patch("requests.post")
    def test_get_access_token_default_timeout(self, mock_post):
        mock_post.return_value = FakeResponse(200, {"access_token": "secret_tok"})
        res = self.client.get_access_token("code_123")
        self.assertIn("result", res)
        self.assertEqual(res["result"].access_token, "secret_tok")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs.get("timeout"), DEFAULT_TIMEOUT)

    @patch("requests.post")
    def test_get_access_token_request_exception(self, mock_post):
        conn_err = sys.modules["requests.exceptions"].ConnectionError("Failed to connect")
        mock_post.side_effect = conn_err
        res = self.client.get_access_token("code_123")
        self.assertIn("error", res)
        self.assertEqual(res["error"]["status"], 500)
        self.assertEqual(res["error"]["code"], "ConnectionError")

    @patch("requests.post")
    def test_get_databases_edited_time_desc_default_timeout(self, mock_post):
        mock_post.return_value = FakeResponse(
            200,
            {"results": [{"id": "db_abc", "properties": {}}]},
        )
        res = self.client.get_databases_edited_time_desc("tok_1")
        self.assertIn("result", res)
        self.assertEqual(len(res["result"]), 1)
        self.assertEqual(res["result"][0].id, "db_abc")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs.get("timeout"), DEFAULT_TIMEOUT)

    @patch("requests.post")
    def test_get_databases_edited_time_desc_missing_results_key(self, mock_post):
        mock_post.return_value = FakeResponse(200, {})
        res = self.client.get_databases_edited_time_desc("tok_1")
        self.assertIn("result", res)
        self.assertEqual(res["result"], [])


class NotionModelsHardeningTests(unittest.TestCase):
    def test_property_model_defensive_empty_or_none(self):
        m1 = NotionDatabasePropertyModel.from_dict(None)
        self.assertEqual(m1.id, "")
        self.assertEqual(m1.name, "")
        self.assertEqual(m1.property_type, "")

        m2 = NotionDatabasePropertyModel.from_dict({})
        self.assertEqual(m2.id, "")
        self.assertEqual(m2.name, "")

    def test_property_model_valid(self):
        m = NotionDatabasePropertyModel.from_dict({"id": "p1", "name": "Title", "type": "title"})
        self.assertEqual(m.id, "p1")
        self.assertEqual(m.name, "Title")
        self.assertEqual(m.property_type, "title")

    def test_database_model_defensive_empty_or_none(self):
        m1 = NotionDatabaseModel.from_dict(None)
        self.assertEqual(m1.id, "")
        self.assertEqual(m1.properties, [])

        m2 = NotionDatabaseModel.from_dict({})
        self.assertEqual(m2.id, "")
        self.assertEqual(m2.properties, [])

    def test_database_model_malformed_properties(self):
        m = NotionDatabaseModel.from_dict({"id": "db_1", "properties": "not_a_dict"})
        self.assertEqual(m.id, "db_1")
        self.assertEqual(m.properties, [])

    def test_database_model_multi_from_dict_non_list(self):
        self.assertEqual(NotionDatabaseModel.multi_from_dict(None), [])
        self.assertEqual(NotionDatabaseModel.multi_from_dict("string"), [])

    def test_database_model_multi_from_dict_with_invalid_items(self):
        items = [None, 123, {"id": "db_valid", "properties": {}}]
        res = NotionDatabaseModel.multi_from_dict(items)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, "db_valid")

    def test_oauth_model_defensive_empty_or_none(self):
        m1 = NotionOAuthModel.from_dict(None)
        self.assertEqual(m1.access_token, "")

        m2 = NotionOAuthModel.from_dict({})
        self.assertEqual(m2.access_token, "")

        m3 = NotionOAuthModel.from_dict({"access_token": "secret_abc"})
        self.assertEqual(m3.access_token, "secret_abc")


class ConversationPayloadHardeningTests(unittest.TestCase):
    def test_build_properties_none_structured(self):
        conv = Conversation(id="conv_100", structured=None)
        props, emoji = _build_notion_conversation_properties(conv)
        self.assertEqual(emoji, "🧠")
        self.assertEqual(props["Title"]["title"][0]["text"]["content"], "Conversation conv_100")
        self.assertEqual(props["Category"]["select"]["name"], "Other")
        self.assertEqual(props["Overview"]["rich_text"][0]["text"]["content"], "")
        self.assertEqual(props["Speakers"]["number"], 0)
        self.assertEqual(props["Duration (seconds)"]["number"], 0)

    def test_build_properties_emoji_latin1_and_decode_error(self):
        # Normal emoji
        s1 = Structured(emoji="🚀")
        _, e1 = _build_notion_conversation_properties(Conversation(structured=s1))
        self.assertIn(e1, ["🚀", "🚀".encode("latin1", errors="replace").decode("utf-8", errors="replace")])

        # None emoji
        s2 = Structured(emoji=None)
        _, e2 = _build_notion_conversation_properties(Conversation(structured=s2))
        self.assertEqual(e2, "🧠")

    def test_build_properties_speakers_dedup_and_nulls(self):
        segments = [
            TranscriptSegment(speaker="Alice"),
            TranscriptSegment(speaker="Bob"),
            TranscriptSegment(speaker="Alice"),
            TranscriptSegment(speaker=None),
            None,
        ]
        conv = Conversation(structured=Structured(), transcript_segments=segments)
        props, _ = _build_notion_conversation_properties(conv)
        self.assertEqual(props["Speakers"]["number"], 2)

    def test_build_properties_duration_clamped_and_nulls(self):
        now = datetime.now()

        # Normal duration
        conv1 = Conversation(structured=Structured(), started_at=now, finished_at=now + timedelta(seconds=75))
        props1, _ = _build_notion_conversation_properties(conv1)
        self.assertEqual(props1["Duration (seconds)"]["number"], 75)

        # Missing started_at
        conv2 = Conversation(structured=Structured(), started_at=None, finished_at=now)
        props2, _ = _build_notion_conversation_properties(conv2)
        self.assertEqual(props2["Duration (seconds)"]["number"], 0)

        # Clock skew (finished_at < started_at)
        conv3 = Conversation(structured=Structured(), started_at=now + timedelta(seconds=60), finished_at=now)
        props3, _ = _build_notion_conversation_properties(conv3)
        self.assertEqual(props3["Duration (seconds)"]["number"], 0)

    @patch("oauth.conversation_created.validate_database")
    @patch("requests.post")
    def test_create_notion_row_success(self, mock_post, mock_validate):
        mock_validate.return_value = True
        mock_post.return_value = FakeResponse(200)
        conv = Conversation(id="conv_1", structured=Structured(title="Doc Review"))
        success = create_notion_row("tok_1", "db_1", conv)
        self.assertTrue(success)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs.get("timeout"), DEFAULT_TIMEOUT)

    @patch("oauth.conversation_created.validate_database")
    @patch("requests.post")
    def test_create_notion_row_post_timeout(self, mock_post, mock_validate):
        mock_validate.return_value = True
        mock_post.side_effect = sys.modules["requests.exceptions"].Timeout("Timed out")
        conv = Conversation(id="conv_1", structured=Structured())
        success = create_notion_row("tok_1", "db_1", conv)
        self.assertFalse(success)

    @patch("oauth.conversation_created.get_notion")
    def test_validate_database_missing_fields(self, mock_get_notion):
        fake_client = MagicMock()
        mock_db = NotionDatabaseModel()
        mock_db.properties = [
            NotionDatabasePropertyModel(name="Title"),
            NotionDatabasePropertyModel(name="Speakers"),
            # Missing Category, Duration (seconds), Overview
        ]
        fake_client.get_database.return_value = {"result": mock_db}
        mock_get_notion.return_value = fake_client

        with self.assertRaises(HTTPException) as cm:
            validate_database("db_1", "tok_1")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Fields are missing", cm.exception.detail)

    @patch("oauth.conversation_created.get_notion")
    def test_validate_database_invalid_schema(self, mock_get_notion):
        fake_client = MagicMock()
        fake_client.get_database.return_value = {"result": None}
        mock_get_notion.return_value = fake_client

        with self.assertRaises(HTTPException) as cm:
            validate_database("db_1", "tok_1")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid database schema", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
