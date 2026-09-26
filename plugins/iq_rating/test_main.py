"""Hermetic unit tests for IQ Rating Omi Plugin.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Lightweight stubs for hermetic stdlib-only execution
if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class APIRouter:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def on_event(self, *args, **kwargs):
                return lambda f: f

        class Query:
            def __init__(self, *args, **kwargs):
                pass

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass
            def include_router(self, *args, **kwargs):
                pass

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi.APIRouter = APIRouter
        fastapi.FastAPI = FastAPI
        fastapi.Query = Query
        fastapi.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "requests" not in sys.modules:
    try:
        import requests  # type: ignore
    except ImportError:
        requests = types.ModuleType("requests")

        def _dummy_post(*args, **kwargs):
            return None

        def _dummy_get(*args, **kwargs):
            return None

        class RequestException(Exception):
            pass

        requests.post = _dummy_post
        requests.get = _dummy_get
        requests.RequestException = RequestException
        sys.modules["requests"] = requests

PLUGIN_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("iq_rating_main", PLUGIN_DIR / "main.py")
main = importlib.util.module_from_spec(spec)
sys.modules["iq_rating_main"] = main
spec.loader.exec_module(main)


class TestIqRatingExceptionGuards(unittest.TestCase):

    @patch.object(main.requests, "post", create=True)
    def test_filter_names_null_message_content_retains_batch(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": None}}
            ]
        }
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post", create=True)
    def test_filter_names_empty_choices_retains_batch(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post", create=True)
    def test_filter_names_valid_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "Alice, Bob"}}
            ]
        }
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob", "Forbes"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post", create=True)
    def test_calculate_iq_invalid_iq_type_fallback(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"name": "Alice", "iq": "invalid_number", "is_name": true}]'
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        people = {
            "alice": {"name": "Alice", "context_snippets": ["Alice is very smart"]}
        }

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.calculate_iq_with_ai(people)
            self.assertIn("alice", result)
            self.assertEqual(result["alice"]["iq"], 100)

    @patch.object(main.requests, "post", create=True)
    def test_calculate_iq_null_name_field(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"name": null, "iq": 130, "is_name": true}]'
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        people = {
            "alice": {"name": "Alice", "context_snippets": ["Alice is smart"]}
        }

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.calculate_iq_with_ai(people)
            self.assertIn("alice", result)

    @patch.object(main.requests, "post", create=True)
    def test_filter_names_network_exception_recovery(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])


class IQRatingCalculateAITests(unittest.TestCase):
    def setUp(self):
        self.sample_people = {
            "alice": {
                "name": "Alice",
                "context_snippets": ["Alice is a brilliant engineer and visionary leader."],
            },
            "bob": {
                "name": "Bob",
                "context_snippets": ["Bob helped with some questions."],
            },
        }

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch.object(main.requests, "post", create=True)
    def test_valid_ai_response_assigns_scores(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": "Alice", "iq": 145, "is_name": True},
                                {"name": "Bob", "iq": 115, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 145)
        self.assertTrue(scores["alice"]["is_name"])
        self.assertEqual(scores["bob"]["iq"], 115)
        self.assertTrue(scores["bob"]["is_name"])

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch.object(main.requests, "post", create=True)
    def test_leading_non_object_element_keeps_valid_scores(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                1,
                                None,
                                "invalid_entry",
                                {"name": "Alice", "iq": 140, "is_name": True},
                                {"name": "Bob", "iq": 110, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 140)
        self.assertEqual(scores["bob"]["iq"], 110)

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch.object(main.requests, "post", create=True)
    def test_null_and_non_integer_iq_values_fallback_without_dropping_batch(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": "Alice", "iq": None, "is_name": True},
                                {"name": "Bob", "iq": "invalid_number", "is_name": "yes"},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 100)
        self.assertTrue(scores["alice"]["is_name"])
        self.assertEqual(scores["bob"]["iq"], 100)
        self.assertTrue(scores["bob"]["is_name"])

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch.object(main.requests, "post", create=True)
    def test_invalid_name_entries_skipped_safely(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": None, "iq": 130},
                                {"name": "   ", "iq": 125},
                                {"name": 12345, "iq": 120},
                                {"name": "Alice", "iq": 135, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 135)
        self.assertIn("bob", scores)
        self.assertIsInstance(scores["bob"]["iq"], int)

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch.object(main.requests, "post", create=True)
    def test_non_list_json_response_handled_gracefully(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"error": "not a list"})}}]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertIn("alice", scores)
        self.assertIn("bob", scores)

    @patch.object(main, "OPENAI_API_KEY", "")
    def test_no_api_key_uses_random_fallback(self):
        scores = main.calculate_iq_with_ai(self.sample_people)
        self.assertIn("alice", scores)
        self.assertIn("bob", scores)
        self.assertTrue(
            (isinstance(scores["alice"], dict) and 70 <= scores["alice"]["iq"] <= 160)
            or (isinstance(scores["alice"], (int, float)) and 70 <= scores["alice"] <= 160)
        )


class TestIqRatingEndpointExceptionSanitization(unittest.TestCase):
    """Hermetic verification: GET /iq and GET /iq/api must never leak raw exceptions or reflect XSS."""

    def test_iq_rating_page_exception_sanitization(self):
        with patch.object(main, "get_people_for_user", side_effect=RuntimeError("disk image malformed /secret/path <script>alert(1)</script>")):
            resp = asyncio.run(main.iq_rating_page("test_uid"))
            self.assertIn("Failed to generate IQ ratings due to an internal error.", resp.content)
            self.assertNotIn("disk image malformed", resp.content)
            self.assertNotIn("/secret/path", resp.content)
            self.assertNotIn("<script>", resp.content)

    def test_iq_rating_api_exception_sanitization(self):
        with patch.object(main, "get_people_for_user", side_effect=RuntimeError("internal postgres connection lost at 10.0.0.1")):
            with self.assertRaises(main.HTTPException) as ctx:
                asyncio.run(main.iq_rating_api("test_uid"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to get IQ ratings due to an internal error.")
            self.assertNotIn("internal postgres connection lost", ctx.exception.detail)
            self.assertNotIn("10.0.0.1", ctx.exception.detail)

    def test_iq_rating_page_empty_and_success_states(self):
        with patch.object(main, "get_people_for_user", return_value={}):
            resp = asyncio.run(main.iq_rating_page("test_uid"))
            self.assertIn("No names found in your memories yet", resp.content)

        sample_people = {"alice": {"name": "Alice", "iq": 125}}
        with patch.object(main, "get_people_for_user", return_value=sample_people):
            resp = asyncio.run(main.iq_rating_page("test_uid"))
            self.assertIn("Alice", resp.content)

    def test_iq_rating_api_loading_and_ready_states(self):
        with patch.object(main, "get_people_for_user", return_value=None), \
             patch.object(main, "is_loading", return_value=True):
            resp = asyncio.run(main.iq_rating_api("test_uid"))
            self.assertEqual(resp.content["status"], "loading")

        sample_people = {"alice": {"name": "Alice", "iq": 125}}
        with patch.object(main, "get_people_for_user", return_value=sample_people):
            resp = asyncio.run(main.iq_rating_api("test_uid"))
            self.assertEqual(resp.content["status"], "ready")
            self.assertEqual(resp.content["total_people"], 1)


if __name__ == "__main__":
    unittest.main()
