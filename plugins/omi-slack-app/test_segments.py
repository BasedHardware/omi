"""Hermetic regression for non-dict transcript segments in process_segments.

Omi's realtime webhook can deliver transcript segments as raw strings; the
debug print already guards with isinstance, but the extraction comprehension
called seg.get("text") on every segment and crashed the handler with
AttributeError for any non-dict segment.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProcessSegmentsTests(unittest.TestCase):
    def setUp(self):
        framework = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = Exception
        framework.Query = lambda *a, **k: None
        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = Response
        storage = types.ModuleType("simple_storage")
        storage.SimpleUserStorage = Mock()
        self.session_storage = Mock()
        self.session_storage.get_session_idle_time = Mock(return_value=None)
        storage.SimpleSessionStorage = self.session_storage
        detector = types.ModuleType("message_detector")
        self.detector = Mock()
        detector.MessageDetector = Mock(return_value=self.detector)
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        slack = types.ModuleType("slack_sdk")
        slack.WebClient = Mock()
        errors = types.ModuleType("slack_sdk.errors")
        errors.SlackApiError = Exception
        modules = {"fastapi": framework, "fastapi.responses": responses,
                   "simple_storage": storage, "message_detector": detector,
                   "dotenv": dotenv, "requests": types.ModuleType("requests"),
                   "slack_sdk": slack, "slack_sdk.errors": errors}
        originals = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            client_mod = load("slack_client_under_test", "slack_client.py")
            with patch.dict(sys.modules, {"slack_client": client_mod}):
                self.handler = load("slack_handler_under_test", "main.py")
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def process(self, segments):
        session = {"session_id": "omi_session_u1", "uid": "u1", "message_mode": "idle"}
        user = {"uid": "u1", "access_token": "token"}
        return asyncio.run(self.handler.process_segments(session, segments, user))

    def test_dict_segments_still_work(self):
        self.detector.detect_trigger.return_value = False
        self.assertEqual(self.process([{"text": "hello world"}]), "listening")

    def test_string_segments_do_not_crash(self):
        self.detector.detect_trigger.return_value = False
        self.assertEqual(self.process(["hello world"]), "listening")

    def test_mixed_segments_do_not_crash(self):
        self.detector.detect_trigger.return_value = False
        self.assertEqual(self.process([{"text": "hi"}, "raw string", 42]), "listening")

    def test_trigger_in_string_segment_starts_recording(self):
        self.detector.detect_trigger.side_effect = lambda text: "send slack" in text
        self.detector.extract_message_content.return_value = "hello team"
        result = self.process(["send slack hello team"])
        self.assertEqual(result, "collecting_1")
        self.detector.extract_message_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
