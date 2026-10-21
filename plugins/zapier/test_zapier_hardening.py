"""Hermetic regression tests for Zapier plugin services hardening.

Standard library only: runs under python3 -S with zero external dependencies.
Covers defensive null guards, timeout parameters, webhook status codes,
conversation payload building, and bytes/str subscription URL handling.
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure plugins directory and zapier directory are in path
_zapier_dir = os.path.dirname(os.path.abspath(__file__))
_plugins_dir = os.path.dirname(_zapier_dir)
if _zapier_dir not in sys.path:
    sys.path.insert(0, _zapier_dir)
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

    class TooManyRedirects(RequestException):
        pass

    req_exc.RequestException = RequestException
    req_exc.HTTPError = HTTPError
    req_exc.Timeout = Timeout
    req_exc.TooManyRedirects = TooManyRedirects

    class Response:
        def __init__(self, status_code=200, text="{}", json_data=None):
            self.status_code = status_code
            self.text = text
            self._json_data = json_data if json_data is not None else {}

        def json(self):
            return self._json_data

    req.Response = Response
    req.exceptions = req_exc
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

        def delete(self, *args, **kwargs):
            return lambda fn: fn

    class Request:
        pass

    def Form(default=None, **kwargs):
        return default

    fa.HTTPException = HTTPException
    fa.APIRouter = APIRouter
    fa.Request = Request
    fa.Form = Form
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

        def TemplateResponse(self, *args, **kwargs):
            return "rendered_html"

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
        db_mod.get_zapier_user_status = MagicMock(return_value="enabled")
        db_mod.store_zapier_user_status = MagicMock()
        db_mod.get_zapier_subscribes = MagicMock(return_value=[])
        db_mod.store_zapier_subscribes = MagicMock()
        db_mod.remove_zapier_subscribes = MagicMock()
        sys.modules["db"] = db_mod

    if "models" not in sys.modules:
        models_mod = types.ModuleType("models")

        class Conversation:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class ExternalIntegrationCreateConversation:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self, mode="json"):
                return self.__dict__.copy()

        class EndpointResponse:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class ExternalIntegrationConversationSource:
            pass

        class Geolocation:
            pass

        models_mod.Conversation = Conversation
        models_mod.ExternalIntegrationCreateConversation = ExternalIntegrationCreateConversation
        models_mod.EndpointResponse = EndpointResponse
        models_mod.ExternalIntegrationConversationSource = ExternalIntegrationConversationSource
        models_mod.Geolocation = Geolocation
        sys.modules["models"] = models_mod


def _install_hermetic_stubs():
    """Install lightweight stdlib stubs for dependencies if running in minimal environment."""
    _stub_requests()
    _stub_fastapi()
    _stub_pydantic()
    _stub_db_and_models()


_install_hermetic_stubs()

# Import target modules
from zapier import client, conversation_created
from zapier.client import (
    ZapierClient,
    OmiClient,
    ZapierDatabasePropertyModel,
    ZapierDatabaseModel,
    ZapierOAuthModel,
)
from zapier.conversation_created import _build_zapier_conversation_payload
from zapier.models import ZapierCreateConversation, ZapierSubcribeModel


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "{}", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class ZapierClientHardeningTests(unittest.TestCase):
    def test_send_hook_timeout_parameter(self):
        zc = ZapierClient(timeout=7.5)
        conv = ZapierCreateConversation(
            icon={"type": "emoji", "emoji": "🧠"},
            title="Test Conversation",
            speakers=1,
            category="other",
            duration=60,
            overview="Test overview",
            transcript="User: Hello",
        )

        with patch("requests.post") as mock_post:
            mock_post.return_value = FakeResponse(status_code=200, text="{}")
            res = zc.send_hook_conversation_created("https://hooks.zapier.com/hook/123", conv)
            self.assertEqual(res, {"result": "{}"})
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs.get("timeout"), 7.5)

    def test_send_hook_201_and_204_treated_as_success(self):
        zc = ZapierClient()
        conv = ZapierCreateConversation(
            icon={"type": "emoji", "emoji": "🧠"},
            title="Test",
            speakers=1,
            category="other",
            duration=10,
            overview="Test",
            transcript="Test",
        )

        with patch("requests.post") as mock_post:
            # HTTP 201 Created from webhook
            mock_post.return_value = FakeResponse(status_code=201, text='{"status": "success"}')
            res201 = zc.send_hook_conversation_created("https://hooks.zapier.com/hook/123", conv)
            self.assertEqual(res201, {"result": "{}"})

            # HTTP 204 No Content
            mock_post.return_value = FakeResponse(status_code=204, text="")
            res204 = zc.send_hook_conversation_created("https://hooks.zapier.com/hook/123", conv)
            self.assertEqual(res204, {"result": "{}"})

    def test_send_hook_timeout_and_error_envelopes(self):
        zc = ZapierClient()
        conv = ZapierCreateConversation(
            icon={"type": "emoji", "emoji": "🧠"},
            title="Test",
            speakers=0,
            category="other",
            duration=0,
            overview="",
            transcript="",
        )

        import requests.exceptions as req_exc

        with patch("requests.post") as mock_post:
            # Timeout
            mock_post.side_effect = req_exc.Timeout("Connection timed out")
            res_timeout = zc.send_hook_conversation_created("https://hooks.zapier.com/hook/123", conv)
            self.assertIn("error", res_timeout)
            self.assertEqual(res_timeout["error"]["message"], "Timeout")

            # HTTP 500
            mock_post.side_effect = None
            mock_post.return_value = FakeResponse(status_code=500, text="Internal Server Error")
            res_500 = zc.send_hook_conversation_created("https://hooks.zapier.com/hook/123", conv)
            self.assertIn("error", res_500)
            self.assertEqual(res_500["error"]["status"], 500)


class OmiClientHardeningTests(unittest.TestCase):
    def test_create_conversation_timeout_and_201_success(self):
        oc = OmiClient(base_url="https://api.omi.me", zapier_app_id="app_123", zapier_app_sk="sk_abc", timeout=5.0)

        class DummyPayload:
            def model_dump(self, mode="json"):
                return {"text": "hello"}

        with patch("requests.post") as mock_post:
            mock_post.return_value = FakeResponse(status_code=201, text='{"id": "conv_1"}')
            res = oc.create_conversation(DummyPayload(), "uid_test")
            self.assertEqual(res, {"result": "{}"})
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs.get("timeout"), 5.0)

    def test_get_latest_conversation_list_and_dict_handling(self):
        oc = OmiClient(base_url="https://api.omi.me", zapier_app_id="app_123", zapier_app_sk="sk_abc")

        with patch("requests.get") as mock_get:
            # 1. Bare list of conversations
            mock_get.return_value = FakeResponse(status_code=200, json_data=[{"id": "c1", "title": "Conv 1"}])
            res1 = oc.get_latest_conversation("uid_1")
            self.assertIsNotNone(res1.get("result"))
            self.assertEqual(res1["result"].id, "c1")

            # 2. Wrapped dictionary with "conversations" key
            mock_get.return_value = FakeResponse(status_code=200, json_data={"conversations": [{"id": "c2"}]})
            res2 = oc.get_latest_conversation("uid_1")
            self.assertIsNotNone(res2.get("result"))
            self.assertEqual(res2["result"].id, "c2")

            # 3. Direct single conversation dictionary
            mock_get.return_value = FakeResponse(status_code=200, json_data={"id": "c3"})
            res3 = oc.get_latest_conversation("uid_1")
            self.assertIsNotNone(res3.get("result"))
            self.assertEqual(res3["result"].id, "c3")

            # 4. Empty list returns None result
            mock_get.return_value = FakeResponse(status_code=200, json_data=[])
            res4 = oc.get_latest_conversation("uid_1")
            self.assertEqual(res4, {"result": None})

            # 5. Invalid JSON returns None result without crashing
            mock_get.return_value = FakeResponse(status_code=200, json_data=ValueError("Malformed JSON"))
            res5 = oc.get_latest_conversation("uid_1")
            self.assertEqual(res5, {"result": None})


class ZapierModelsHardeningTests(unittest.TestCase):
    def test_database_property_model_defensive(self):
        # Malformed input
        p1 = ZapierDatabasePropertyModel.from_dict(None)
        self.assertEqual(p1.id, "")

        p2 = ZapierDatabasePropertyModel.from_dict("invalid")
        self.assertEqual(p2.id, "")

        # Valid input with missing keys
        p3 = ZapierDatabasePropertyModel.from_dict({"id": "prop_1"})
        self.assertEqual(p3.id, "prop_1")
        self.assertEqual(p3.name, "")
        self.assertEqual(p3.property_type, "")

    def test_database_model_defensive_and_multi(self):
        # from_dict with None properties
        m1 = ZapierDatabaseModel.from_dict({"id": "db_1", "properties": None})
        self.assertEqual(m1.id, "db_1")
        self.assertEqual(m1.properties, [])

        # from_dict with dict properties
        m2 = ZapierDatabaseModel.from_dict({
            "id": "db_2",
            "properties": {"p1": {"id": "1", "name": "Name", "type": "title"}}
        })
        self.assertEqual(len(m2.properties), 1)
        self.assertEqual(m2.properties[0].id, "1")

        # multi_from_dict with list of dicts
        multi1 = ZapierDatabaseModel.multi_from_dict([{"id": "d1"}, {"id": "d2"}])
        self.assertEqual(len(multi1), 2)
        self.assertEqual(multi1[0].id, "d1")

        # multi_from_dict with single dict (doesn't iterate over keys)
        multi2 = ZapierDatabaseModel.multi_from_dict({"id": "d3"})
        self.assertEqual(len(multi2), 1)
        self.assertEqual(multi2[0].id, "d3")

    def test_oauth_model_defensive(self):
        o1 = ZapierOAuthModel.from_dict(None)
        self.assertEqual(o1.access_token, "")

        o2 = ZapierOAuthModel.from_dict({"access_token": "tok_xyz"})
        self.assertEqual(o2.access_token, "tok_xyz")


class ConversationPayloadHardeningTests(unittest.TestCase):
    def test_payload_builder_null_structured(self):
        # Conversation with structured = None
        conv = types.SimpleNamespace(
            structured=None,
            transcript_segments=[],
            started_at=None,
            finished_at=None,
            get_transcript=lambda: "Hello transcript",
        )

        payload = _build_zapier_conversation_payload(conv)
        self.assertEqual(payload.title, "Omi Conversation")
        self.assertEqual(payload.icon["emoji"], "🧠")
        self.assertEqual(payload.category, "other")
        self.assertEqual(payload.speakers, 0)
        self.assertEqual(payload.duration, 0)
        self.assertEqual(payload.overview, "")
        self.assertEqual(payload.transcript, "Hello transcript")

    def test_payload_builder_emoji_unicode_safety(self):
        # Emoji as str with latin1 encoding quirk
        structured = types.SimpleNamespace(
            emoji="🤖",
            title="Bot Meeting",
            category="work",
            overview="Tech discussion",
        )
        conv = types.SimpleNamespace(
            structured=structured,
            transcript_segments=[types.SimpleNamespace(speaker="SPEAKER_00")],
            started_at=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 16, 10, 15, tzinfo=timezone.utc),
            get_transcript=lambda: "Meeting notes",
        )

        payload = _build_zapier_conversation_payload(conv)
        self.assertEqual(payload.title, "Bot Meeting")
        self.assertEqual(payload.icon["emoji"], "🤖")
        self.assertEqual(payload.speakers, 1)
        self.assertEqual(payload.duration, 900)

    def test_payload_builder_speakers_dedup_and_none_safety(self):
        structured = types.SimpleNamespace(title="Multi-speaker", emoji="🧠", category="social", overview="")
        conv = types.SimpleNamespace(
            structured=structured,
            transcript_segments=[
                types.SimpleNamespace(speaker="SPEAKER_01"),
                types.SimpleNamespace(speaker="SPEAKER_02"),
                types.SimpleNamespace(speaker="SPEAKER_01"),  # duplicate
                {"speaker": "SPEAKER_03"},                    # dict representation
                None,                                         # null segment guard
            ],
            started_at=None,
            finished_at=None,
        )

        payload = _build_zapier_conversation_payload(conv)
        self.assertEqual(payload.speakers, 3)

    def test_payload_builder_duration_clamping(self):
        structured = types.SimpleNamespace(title="Skewed dates", emoji="🧠", category="other", overview="")
        # finished_at is earlier than started_at (clock skew)
        conv = types.SimpleNamespace(
            structured=structured,
            transcript_segments=[],
            started_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 16, 11, 0, tzinfo=timezone.utc),
        )

        payload = _build_zapier_conversation_payload(conv)
        self.assertEqual(payload.duration, 0)  # Clamped to 0, not negative

    def test_create_zapier_conversation_str_and_bytes_subscribers(self):
        conv = types.SimpleNamespace(
            structured=types.SimpleNamespace(title="Test", emoji="🧠", category="other", overview=""),
            transcript_segments=[],
            started_at=None,
            finished_at=None,
            get_transcript=lambda: "Test",
        )

        with patch("zapier.conversation_created.get_zapier_subscribes") as mock_subs, \
             patch("zapier.conversation_created.get_zapier") as mock_gz:
            mock_client = MagicMock()
            mock_client.send_hook_conversation_created.return_value = {"result": "{}"}
            mock_gz.return_value = mock_client

            # Mix of bytes and str subscriber URLs
            mock_subs.return_value = [
                b"https://hooks.zapier.com/bytes_hook",
                "https://hooks.zapier.com/str_hook",
                "",  # empty should be skipped
            ]

            success = conversation_created.create_zapier_conversation("user_123", conv)
            self.assertTrue(success)
            self.assertEqual(mock_client.send_hook_conversation_created.call_count, 2)


    def test_subscribe_trigger_validation(self):
        import asyncio
        from fastapi import HTTPException

        async def run():
            # 1. Missing UID
            with self.assertRaises(HTTPException) as ctx:
                await conversation_created.subscribe_zapier_trigger(
                    ZapierSubcribeModel(target_url="https://hooks.zapier.com/123"), ""
                )
            self.assertEqual(ctx.exception.status_code, 400)

            # 2. Invalid URL scheme
            with self.assertRaises(HTTPException) as ctx:
                await conversation_created.subscribe_zapier_trigger(
                    ZapierSubcribeModel(target_url="ftp://invalid.com"), "u1"
                )
            self.assertEqual(ctx.exception.status_code, 400)

            # 3. Valid URL with enabled user
            with patch("zapier.conversation_created.get_zapier_user_status", return_value="enabled"), \
                 patch("zapier.conversation_created.store_zapier_subscribes") as mock_store:
                res = await conversation_created.subscribe_zapier_trigger(
                    ZapierSubcribeModel(target_url="https://hooks.zapier.com/valid"), "u1"
                )
                self.assertEqual(res, {})
                mock_store.assert_called_once_with("u1", "https://hooks.zapier.com/valid")

        asyncio.run(run())

    def test_sample_endpoint_extraction_and_fallback(self):
        import asyncio

        async def run():
            # 1. When Omi returns valid conversation
            mock_conv = types.SimpleNamespace(
                structured=types.SimpleNamespace(title="Meeting", emoji="🚀", category="work", overview="Sync"),
                transcript_segments=[types.SimpleNamespace(speaker="Alice")],
                started_at=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
                get_transcript=lambda: "Alice: Hi",
            )
            with patch("zapier.conversation_created.get_omi") as mock_omi:
                mock_client = MagicMock()
                mock_client.get_latest_conversation.return_value = {"result": mock_conv}
                mock_omi.return_value = mock_client

                samples = await conversation_created.get_trigger_conversation_sample(None, "u1")
                self.assertEqual(len(samples), 1)
                self.assertEqual(samples[0].title, "Meeting")
                self.assertEqual(samples[0].icon["emoji"], "🚀")

            # 2. When Omi returns error
            from fastapi import HTTPException
            with patch("zapier.conversation_created.get_omi") as mock_omi:
                mock_client = MagicMock()
                mock_client.get_latest_conversation.return_value = {"error": {"status": 404}}
                mock_omi.return_value = mock_client

                with self.assertRaises(HTTPException) as ctx:
                    await conversation_created.get_trigger_conversation_sample(None, "u1")
                self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(run())

    def test_zapier_action_conversations_error_mapping(self):
        from fastapi import HTTPException

        action = types.SimpleNamespace(
            text="Take notes",
            source="zapier",
            started_at=None,
            finished_at=None,
            language="en",
            geolocation=None,
        )

        # 1. Success path
        with patch("zapier.conversation_created.get_omi") as mock_omi:
            mock_client = MagicMock()
            mock_client.create_conversation.return_value = {"result": "{}"}
            mock_omi.return_value = mock_client

            resp = conversation_created.zapier_action_conversations(action, "u1")
            self.assertEqual(resp.message, "Your memories are synced with Omi.")

        # 2. Error status mapping
        with patch("zapier.conversation_created.get_omi") as mock_omi:
            mock_client = MagicMock()
            mock_client.create_conversation.return_value = {"error": {"status": "403"}}
            mock_omi.return_value = mock_client

            with self.assertRaises(HTTPException) as ctx:
                conversation_created.zapier_action_conversations(action, "u1")
            self.assertEqual(ctx.exception.status_code, 403)

    def test_zapier_conversations_disabled_status_guard(self):
        conv = types.SimpleNamespace()
        with patch("zapier.conversation_created.get_zapier_user_status", return_value="disabled"), \
             patch("zapier.conversation_created.create_zapier_conversation") as mock_create:
            res = conversation_created.zapier_conversations(conv, "u1")
            self.assertEqual(res, {})
            mock_create.assert_not_called()

    def test_type_annotations_evaluate_cleanly_on_all_runtimes(self):
        """Verify type annotations in conversation_created resolve without NameError on all Python versions."""
        import typing
        hints = typing.get_type_hints(_build_zapier_conversation_payload)
        self.assertIn("conversation", hints)
        self.assertIn("return", hints)


if __name__ == "__main__":
    unittest.main()
