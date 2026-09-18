"""Hermetic regression test for the manual-import integration route."""

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_app():
    class Flask:
        def __init__(self, *_args, **_kwargs):
            pass

        def route(self, *_args, **_kwargs):
            return lambda handler: handler

    request = SimpleNamespace(json=None)

    flask = ModuleType("flask")
    flask.Flask = Flask
    flask.request = request
    flask.jsonify = lambda payload: payload
    flask.send_from_directory = lambda *args, **kwargs: None

    requests = ModuleType("requests")
    requests.post = lambda *args, **kwargs: None

    class OpenAI:
        def __init__(self, **_kwargs):
            pass

    openai = ModuleType("openai")
    openai.OpenAI = OpenAI
    httpx = ModuleType("httpx")
    httpx.Limits = lambda **kwargs: kwargs
    httpx.Timeout = lambda **kwargs: kwargs
    httpx.Client = lambda **kwargs: SimpleNamespace()
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    spec = importlib.util.spec_from_file_location("manual_import_app", Path(__file__).with_name("app.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {"flask": flask, "requests": requests, "openai": openai, "httpx": httpx, "dotenv": dotenv},
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class ManualImportRouteTests(unittest.TestCase):
    def test_api_url_uses_memories_route(self):
        self.assertTrue(app.API_URL.endswith("/user/memories"))
        self.assertNotIn("/user/facts", app.API_URL)

    def test_submit_memories_posts_route_and_payload(self):
        app.request.json = {"uid": "user-1", "use_ai": False, "memories": ["A sufficiently long learning note."]}
        response = SimpleNamespace(status_code=200, text="")

        with patch.object(app.requests, "post", return_value=response) as post:
            result = app.submit_memories()

        self.assertTrue(result["success"])
        post.assert_called_once()
        url, = post.call_args.args[:1]
        self.assertEqual(url, f"{app.API_URL}?uid=user-1")
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["text_source"], "other")
        self.assertEqual(payload["text_source_spec"], "learning_notes")
        self.assertEqual(post.call_args.kwargs["headers"]["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
