"""Hermetic unit tests for IQ Rating Omi Plugin.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def load_app():
    class DummyAPIRouter:
        def __init__(self, **kwargs):
            self.routes = []

        def include_router(self, router, **kwargs):
            pass

        def on_event(self, event_name):
            def decorator(func):
                return func

            return decorator

        def get(self, path, **kwargs):
            def decorator(func):
                return func

            return decorator

        def post(self, path, **kwargs):
            def decorator(func):
                return func

            return decorator

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyAPIRouter
    fastapi.APIRouter = DummyAPIRouter
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.HTTPException = Exception

    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    fastapi_responses.JSONResponse = dict

    spec = importlib.util.spec_from_file_location("iq_rating_hermetic", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
        },
    ):
        spec.loader.exec_module(module)
    return module


main = load_app()


class TestIqRatingExceptionGuards(unittest.TestCase):

    @patch.object(main.requests, "post")
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

    @patch.object(main.requests, "post")
    def test_filter_names_empty_choices_retains_batch(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post")
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

    @patch.object(main.requests, "post")
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

    @patch.object(main.requests, "post")
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

    @patch.object(main.requests, "post")
    def test_filter_names_network_exception_recovery(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = main.filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])


if __name__ == "__main__":
    unittest.main()
