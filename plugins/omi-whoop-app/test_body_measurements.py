"""Regression tests for the get_body_measurements chat tool.

The tool used to request ``/developer/v1/body_measurement``, a path the WHOOP
API has never served (it answers 404 before even checking the bearer token),
so the tool could never return data. WHOOP documents body measurements at
``/user/measurement/body``.

The suite executes the production handler through the ``requests.get`` seam
and runs on a stdlib-only interpreter: ``requests``/``dotenv`` are always
stubbed (no network is ever attempted) and ``fastapi``/``pydantic`` are only
stubbed when they are not installed, matching the sibling plugin suites.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def _stub_requests():
    module = types.ModuleType("requests")
    module.get = module.post = None
    return module


def _stub_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


def _stub_fastapi():
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def _route(self, *args, **kwargs):
            return lambda fn: fn

        get = post = _route

    class Request:
        pass

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Query(default=None, *args, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = Query

    responses = types.ModuleType("fastapi.responses")

    class _Response:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = _Response
    fastapi.responses = responses
    return fastapi, responses


def _stub_pydantic():
    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for name in ("result", "error"):
                setattr(self, name, kwargs.get(name))

    pydantic.BaseModel = BaseModel
    return pydantic


def _load_main():
    stubs = {"requests": _stub_requests(), "dotenv": _stub_dotenv()}
    if importlib.util.find_spec("fastapi") is None:
        fastapi, responses = _stub_fastapi()
        stubs["fastapi"] = fastapi
        stubs["fastapi.responses"] = responses
    if importlib.util.find_spec("pydantic") is None:
        stubs["pydantic"] = _stub_pydantic()

    spec = importlib.util.spec_from_file_location("whoop_main", HERE / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE))
    try:
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(HERE))
    return module


main = _load_main()


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


DOCUMENTED_BODY_MEASUREMENT_URL = "https://api.prod.whoop.com/developer/v1/user/measurement/body"


class BodyMeasurementEndpointTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(main, "get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    def _run(self, fake_get):
        with patch.object(main.requests, "get", side_effect=fake_get) as get:
            response = asyncio.run(main.tool_get_body_measurements(FakeRequest({"uid": "u1"})))
        return response, get

    def test_requests_documented_body_measurement_path(self):
        payload = {"height_meter": 1.8288, "weight_kilogram": 90.7185, "max_heart_rate": 200}

        def fake_get(url, headers=None, params=None):
            # Mirror WHOOP: the documented path answers with data; anything else is 404.
            if url == DOCUMENTED_BODY_MEASUREMENT_URL:
                return FakeResponse(200, payload)
            return FakeResponse(404, text="")

        response, get = self._run(fake_get)

        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], DOCUMENTED_BODY_MEASUREMENT_URL)
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer test-token"})
        self.assertIsNone(response.error)
        self.assertIn("**Height:** 183 cm (6'0\")", response.result)
        self.assertIn("**Weight:** 90.7 kg (200.0 lb)", response.result)
        self.assertIn("**Max Heart Rate:** 200 bpm", response.result)

    def test_upstream_404_is_reported_with_status_not_as_empty_measurements(self):
        response, _ = self._run(lambda url, headers=None, params=None: FakeResponse(404, text=""))

        self.assertIsNone(response.result)
        self.assertIn("404", response.error)


if __name__ == "__main__":
    unittest.main()
