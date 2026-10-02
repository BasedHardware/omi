"""Hermetic tests: IQ Rating page must prevent script-context breakouts and escape errors.

Vulnerabilities tested:
1. Script breakout in `const uid = {uid_json};`: quotes and closing script tags in `uid`.
2. Script breakout in `let peopleData = {people_data_json};`: closing script tags in names/bios.
3. Reflected exception message escaping in error HTML.
"""

import asyncio
import html
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Set dummy credentials so startup hook passes if invoked
os.environ["OMI_APP_ID"] = "test-app-id"
os.environ["OMI_APP_SECRET"] = "test-app-secret"

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))

# Lightweight stubs for hermetic stdlib-only execution, mirroring
# plugins/iq_rating/test_main.py so this suite also runs in the dependency-free
# CI Hygiene lane. The real packages are used whenever they are installed.
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
            # Carries the rendered content through .body so the escaping
            # assertions below still inspect the real generated HTML rather
            # than a placeholder.
            def __init__(self, content=None, **kwargs):
                self.body = content

        class JSONResponse:
            def __init__(self, content=None, **kwargs):
                self.body = content

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "requests" not in sys.modules:
    try:
        import requests  # type: ignore
    except ImportError:
        requests = types.ModuleType("requests")

        def _dummy_request(*args, **kwargs):
            return None

        class RequestException(Exception):
            pass

        requests.post = _dummy_request
        requests.get = _dummy_request
        requests.RequestException = RequestException
        sys.modules["requests"] = requests

import main as iq_main


def _run(coro):
    return asyncio.run(coro)


class IqRatingSecurityTest(unittest.TestCase):
    def test_uid_quote_breakout_prevented(self) -> None:
        malicious_uid = "'; alert('xss'); //"
        with patch.object(iq_main, "get_people_for_user", return_value=[{"name": "Alice", "iq": 120}]):
            resp = _run(iq_main.iq_rating_page(uid=malicious_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertIn(f"const uid = {json.dumps(malicious_uid)};", body)
            self.assertNotIn(f"const uid = '{malicious_uid}';", body)

    def test_uid_script_tag_breakout_sanitized(self) -> None:
        malicious_uid = "</script><script>alert(1)</script>"
        with patch.object(iq_main, "get_people_for_user", return_value=[{"name": "Alice", "iq": 120}]):
            resp = _run(iq_main.iq_rating_page(uid=malicious_uid))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            # Any closing script tag within the string must be escaped
            self.assertNotIn("const uid = \"</script>", body)
            self.assertIn("<\\/script>", body)

    def test_people_data_script_tag_breakout_sanitized(self) -> None:
        malicious_people = [
            {"name": "</script><script>alert('pwned')</script>", "iq": 140}
        ]
        with patch.object(iq_main, "get_people_for_user", return_value=malicious_people):
            resp = _run(iq_main.iq_rating_page(uid="valid_user"))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertNotIn("</script><script>alert('pwned')", body)
            self.assertIn("<\\/script>", body)

    def test_exception_reflection_is_escaped(self) -> None:
        with patch.object(iq_main, "get_people_for_user", side_effect=RuntimeError("<script>alert('error')</script>")):
            resp = _run(iq_main.iq_rating_page(uid="valid_user"))
            body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
            self.assertNotIn("<script>alert('error')</script>", body)
            self.assertIn(html.escape("<script>alert('error')</script>"), body)


if __name__ == "__main__":
    unittest.main()
