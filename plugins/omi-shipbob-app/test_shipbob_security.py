"""Hermetic security tests for the ShipBob plugin.

Runs with the Python standard library only: the CI "Hygiene" lane installs just
pyyaml, so fastapi, jinja2, pydantic, requests and dotenv are absent. Stubs are
registered in sys.modules before main.py is imported, following the pattern
already used by plugins/omi-shipbob-app/test_main.py (omi_plugin_sdk) and
plugins/chatgpt/test_main.py (Jinja2Templates).

Coverage note: jinja2 cannot be reproduced faithfully without writing a template
engine, so these tests assert on the values main.py hands to the template plus the
template's own interpolation wiring. That is where the escaping for this PR is
enforced: main.py builds safe_uid_json/safe_uid_param, and Jinja autoescape is
what neutralises the error string, which holds only while {{ error }} is not
marked |safe.
"""

import asyncio
import json
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if "fastapi" not in sys.modules:
    try:
        import fastapi  # noqa: F401
        import fastapi.exceptions  # noqa: F401
        import fastapi.responses  # noqa: F401
        import fastapi.staticfiles  # noqa: F401
        import fastapi.templating  # noqa: F401
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class APIRouter:
            def __init__(self, *args, **kwargs):
                pass

            def _decorator(self, *args, **kwargs):
                return lambda f: f

            get = post = put = delete = patch_ = on_event = websocket = _decorator

        class Depends:
            def __init__(self, *args, **kwargs):
                pass

        class Query:
            def __init__(self, *args, **kwargs):
                pass

        class Request:
            def __init__(self, *args, **kwargs):
                pass

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail="", headers=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail
                self.headers = headers or {}

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = []

            @staticmethod
            def _decorator(*args, **kwargs):
                return lambda f: f

            @staticmethod
            def _statement(*args, **kwargs):
                return None

            get = post = put = delete = patch_ = on_event = middleware = exception_handler = _decorator
            mount = include_router = add_exception_handler = _statement

        fastapi.APIRouter = APIRouter
        fastapi.Depends = Depends
        fastapi.Query = Query
        fastapi.Request = Request
        fastapi.HTTPException = HTTPException
        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            # Starlette encodes str content to bytes; mirror that so assertions
            # read the same bytes in the hermetic lane and with real fastapi.
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.body = content.encode("utf-8") if isinstance(content, str) else content

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.body = content

        class RedirectResponse:
            def __init__(self, url=None, status_code=307, **kwargs):
                self.url = url
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        responses.RedirectResponse = RedirectResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

        staticfiles = types.ModuleType("fastapi.staticfiles")

        class StaticFiles:
            def __init__(self, *args, **kwargs):
                pass

        staticfiles.StaticFiles = StaticFiles
        sys.modules["fastapi.staticfiles"] = staticfiles

        templating = types.ModuleType("fastapi.templating")

        class TemplateResponse:
            def __init__(self, name, context=None, **kwargs):
                self.name = name
                self.template = name
                self.context = context or {}
                self.body = ""

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                pass

            def TemplateResponse(self, name, context=None, **kwargs):
                return TemplateResponse(name, context, **kwargs)

            def get_template(self, name):
                raise LookupError(name)

        templating.Jinja2Templates = Jinja2Templates
        templating.TemplateResponse = TemplateResponse
        sys.modules["fastapi.templating"] = templating

        exceptions = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            def errors(self):
                return []

        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions

if "pydantic" not in sys.modules:
    try:
        import pydantic  # noqa: F401
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **data):
                for key, value in data.items():
                    setattr(self, key, value)

        class Field:
            def __init__(self, *args, **kwargs):
                pass

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except ImportError:
        requests = types.ModuleType("requests")

        def _unavailable(*args, **kwargs):
            raise AssertionError("tests must not perform real HTTP")

        class RequestException(Exception):
            pass

        requests.post = _unavailable
        requests.get = _unavailable
        requests.request = _unavailable
        requests.RequestException = RequestException
        sys.modules["requests"] = requests

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = dotenv

if "omi_plugin_sdk" not in sys.modules:
    sdk = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")
    for _name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, _name, MagicMock())
    sys.modules["omi_plugin_sdk"] = sdk
    sys.modules["omi_plugin_sdk.models"] = sdk_models
    sdk.models = sdk_models

os.environ.setdefault("OMI_APP_ID", "test-app-id")
os.environ.setdefault("OMI_APP_SECRET", "test-app-secret")

APP_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = APP_ROOT / "templates" / "setup.html"
sys.path.insert(0, str(APP_ROOT))

import main as shipbob_main  # noqa: E402

Request = sys.modules["fastapi"].Request


def _run(coro):
    return asyncio.run(coro)


def _context_of(resp):
    return getattr(resp, "context", {})


def _template_name(resp):
    name = getattr(resp, "name", None)
    if name is None:
        name = getattr(getattr(resp, "template", None), "name", None)
    return name


class ShipBobSecurityTests(unittest.TestCase):
    def setUp(self):
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.scope = {"type": "http", "method": "GET"}
        self.mock_request.method = "GET"

    def _home_context(self, uid):
        with patch.object(shipbob_main, "get_shipbob_tokens", return_value={"access_token": "tok"}), \
             patch.object(shipbob_main, "get_channels", return_value=[]):
            resp = _run(shipbob_main.home(request=self.mock_request, uid=uid))
        self.assertEqual(_template_name(resp), "setup.html")
        return _context_of(resp)

    def test_uid_cannot_close_a_script_block(self):
        evil_uid = "attacker</script><script>alert('pwned')</script>"
        context = self._home_context(evil_uid)
        safe_uid_json = context["safe_uid_json"]
        self.assertNotIn("</script>", safe_uid_json)
        self.assertIn("<\\/script>", safe_uid_json)
        # Still a faithful JSON encoding of the original value.
        self.assertEqual(json.loads(safe_uid_json.replace("<\\/", "</")), evil_uid)

    def test_uid_cannot_break_out_of_a_js_string(self):
        evil_uid = "user' + alert(1) + '"
        context = self._home_context(evil_uid)
        safe_uid_json = context["safe_uid_json"]
        # A JSON string literal is safe inside a double-quoted JS string as long
        # as no unescaped double quote survives inside it; quotes of the other
        # kind and backslashes are untouched by json.dumps and are harmless here.
        inner = safe_uid_json[1:-1]
        self.assertNotIn('"', inner.replace('\\"', ""))
        self.assertEqual(json.loads(safe_uid_json), evil_uid)

    def test_uid_is_url_encoded_in_action_links(self):
        context = self._home_context("user with spaces")
        self.assertEqual(context["safe_uid_param"], "user%20with%20spaces")
        template = TEMPLATE_PATH.read_text()
        self.assertIn("{{ safe_uid_param|default(uid) }}", template)

    def test_callback_error_is_autoescaped(self):
        evil_err = "<script>alert('xss')</script>"
        resp = _run(shipbob_main.handle_shipbob_callback(
            request=self.mock_request,
            error=evil_err,
        ))
        self.assertEqual(_template_name(resp), "setup.html")
        # main.py must hand the error over untouched, leaving Jinja autoescape
        # responsible for neutralising it.
        self.assertIn(evil_err, _context_of(resp)["error"])
        template = TEMPLATE_PATH.read_text()
        interpolations = re.findall(r"\{\{\s*error\s*(\|[^}]*)?\}\}", template)
        self.assertTrue(interpolations, "setup.html must interpolate the error")
        for extra in interpolations:
            self.assertNotIn("safe", extra)


if __name__ == "__main__":
    unittest.main()