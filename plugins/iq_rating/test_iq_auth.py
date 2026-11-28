"""Hermetic tests for the iq-rating auth guard (#14430).

Verifies that the uid-keyed iq-rating data-plane routes are bound to a shared
secret (IQ_RATING_SECRET) and reject unauthenticated callers, while the
uid-less landing state and /iq/setup-status stay public.

No third-party runtime dependencies required: runs under stdlib `python3 -S`
and `pytest` alike, using the same lightweight fastapi stub as test_main.py.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

# --- Lightweight fastapi stub (mirrors test_main.py) ------------------------
if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class _Dummy:
            def __init__(self, *args, **kwargs):
                pass

        class APIRouter(_Dummy):
            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def on_event(self, *args, **kwargs):
                return lambda f: f

        class Query(_Dummy):
            pass

        class Depends(_Dummy):
            def __init__(self, dependency=None, *args, **kwargs):
                self.dependency = dependency

        class Request:
            pass

        class FastAPI(_Dummy):
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
        fastapi.Depends = Depends
        fastapi.Request = Request
        fastapi.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            pass

        class JSONResponse:
            pass

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

PLUGIN_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("iq_auth", PLUGIN_DIR / "iq_auth.py")
iq_auth = importlib.util.module_from_spec(spec)
sys.modules["iq_auth"] = iq_auth
spec.loader.exec_module(iq_auth)


class _FakeRequest:
    """Minimal stand-in for starlette Request (headers + query_params)."""

    def __init__(self, headers=None, query=None):
        self.headers = headers or {}
        self.query_params = query or {}


class TestIqRatingAuth(unittest.TestCase):
    SECRET = "super-secret-token-xyz"

    def setUp(self):
        import os
        self._orig = os.environ.get("IQ_RATING_SECRET")
        os.environ["IQ_RATING_SECRET"] = self.SECRET

    def tearDown(self):
        import os
        if self._orig is None:
            os.environ.pop("IQ_RATING_SECRET", None)
        else:
            os.environ["IQ_RATING_SECRET"] = self._orig

    # --- fail-closed --------------------------------------------------------
    def test_missing_secret_fails_closed_503(self):
        import os
        os.environ.pop("IQ_RATING_SECRET", None)
        req = _FakeRequest(headers={"Authorization": f"Bearer {self.SECRET}"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_fails_closed_503(self):
        import os
        os.environ["IQ_RATING_SECRET"] = "   "
        req = _FakeRequest(headers={"Authorization": "Bearer whatever"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 503)

    # --- rejects unauthenticated -------------------------------------------
    def test_no_token_rejected_401(self):
        req = _FakeRequest()
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_rejected_401(self):
        req = _FakeRequest(headers={"Authorization": "Bearer nope"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_scheme_rejected_401(self):
        req = _FakeRequest(headers={"Authorization": f"Basic {self.SECRET}"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_ascii_token_rejected_401_not_500(self):
        # A non-ASCII bearer token must fail closed with 401, never raise an
        # unhandled TypeError (which would surface as HTTP 500). This guards
        # the hmac.compare_digest UTF-8 byte-encoding path.
        req = _FakeRequest(headers={"Authorization": "Bearer tökén-ünicode-秘密"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "alice")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_ascii_secret_still_matches(self):
        # A non-ASCII *configured* secret must still authenticate correctly
        # (byte comparison), proving the fix does not break legitimate use.
        import os
        os.environ["IQ_RATING_SECRET"] = "sëcret-秘密-🔒"
        req = _FakeRequest(headers={"Authorization": "Bearer sëcret-秘密-🔒"})
        self.assertEqual(iq_auth.require_iq_rating_auth(req, "dave"), "dave")

    # --- accepts valid credentials -----------------------------------------
    def test_valid_bearer_header_returns_uid(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {self.SECRET}"})
        self.assertEqual(iq_auth.require_iq_rating_auth(req, "alice"), "alice")

    def test_valid_query_token_returns_uid(self):
        req = _FakeRequest(query={"iq_rating_token": self.SECRET})
        self.assertEqual(iq_auth.require_iq_rating_auth(req, "bob"), "bob")

    def test_uid_is_trimmed(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {self.SECRET}"})
        self.assertEqual(iq_auth.require_iq_rating_auth(req, "  carol  "), "carol")

    def test_blank_uid_rejected_422(self):
        req = _FakeRequest(headers={"Authorization": f"Bearer {self.SECRET}"})
        with self.assertRaises(iq_auth.HTTPException) as ctx:
            iq_auth.require_iq_rating_auth(req, "   ")
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)