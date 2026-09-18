"""
Hermetic regression tests for Linear OAuth callback state signing (#14444).

Ensures /auth/linear and /auth/linear/callback enforce cryptographically signed state
parameters to prevent OAuth login CSRF and arbitrary account rebinding.
"""

import asyncio
import hashlib
import hmac
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    requests = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    exceptions = types.ModuleType("requests.exceptions")
    exceptions.RequestException = _RequestException
    requests.exceptions = exceptions
    requests.post = mock.Mock()
    requests.get = mock.Mock()
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        post = get
        mount = lambda *args, **kwargs: None

    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            self.status_code = status_code
            self.detail = detail

    class Request:
        pass

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Request = Request
    fastapi.Query = lambda *a, **k: None
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class Response:
        def __init__(self, *a, **k):
            pass

    responses.HTMLResponse = Response
    responses.RedirectResponse = lambda url: {"redirect_url": url}
    responses.JSONResponse = Response
    sys.modules["fastapi.responses"] = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *a, **k: None
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")

    class Jinja2Templates:
        def __init__(self, *a, **k):
            pass

        def TemplateResponse(self, template, context, **kwargs):
            return {"template": template, "context": context}

    templating.Jinja2Templates = Jinja2Templates
    sys.modules["fastapi.templating"] = templating

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
    sys.modules["pydantic"] = pydantic

    sdk_pkg = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")

    class _Model:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    for name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, name, type(name, (_Model,), {}))
    sdk_pkg.models = sdk_models
    sys.modules["omi_plugin_sdk"] = sdk_pkg
    sys.modules["omi_plugin_sdk.models"] = sdk_models


_install_module_stubs()
import main as linear_main  # noqa: E402


class TestLinearOAuthStateSecurity(unittest.TestCase):
    def setUp(self):
        self.secret = linear_main.LINEAR_CLIENT_SECRET or "test_secret"
        linear_main.LINEAR_CLIENT_SECRET = self.secret

    def test_state_signing_valid_roundtrip(self):
        uid = "usr_valid_linear_user"
        state = linear_main._oauth_state_for(uid)
        recovered = linear_main._verify_and_extract_state_uid(state)
        self.assertEqual(recovered, uid)

    def test_state_signing_supports_colons_in_uid(self):
        uid = "auth0|user:123:456"
        state = linear_main._oauth_state_for(uid)
        recovered = linear_main._verify_and_extract_state_uid(state)
        self.assertEqual(recovered, uid)

    def test_state_signing_rejects_tampered_uid(self):
        uid = "victim_uid"
        state = linear_main._oauth_state_for(uid)
        tampered_state = "attacker_uid:" + state.rsplit(":", 1)[1]
        self.assertIsNone(linear_main._verify_and_extract_state_uid(tampered_state))

    def test_state_signing_rejects_unsigned_or_malformed(self):
        self.assertIsNone(linear_main._verify_and_extract_state_uid("raw_unsigned_uid"))
        self.assertIsNone(linear_main._verify_and_extract_state_uid(""))
        self.assertIsNone(linear_main._verify_and_extract_state_uid(None))

    def test_fails_closed_when_secret_unset(self):
        linear_main.LINEAR_CLIENT_SECRET = ""
        with self.assertRaises(ValueError):
            linear_main._oauth_state_for("user_123")

        valid_state = "user_123:some_signature"
        self.assertIsNone(linear_main._verify_and_extract_state_uid(valid_state))

        with self.assertRaises(linear_main.HTTPException) as ctx:
            asyncio.run(linear_main.linear_auth("user_123"))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_auth_route_issues_signed_state(self):
        with mock.patch.object(linear_main, "RedirectResponse", side_effect=lambda url: {"redirect_url": url}):
            resp = asyncio.run(linear_main.linear_auth("user_123"))
            redirect_url = resp.get("redirect_url", "")
            self.assertIn("state=user_123%3A", redirect_url)

    def test_callback_rejects_tampered_state(self):
        with mock.patch.object(linear_main.templates, "TemplateResponse", side_effect=lambda template, context, **kw: {"template": template, "context": context}), \
             mock.patch.object(linear_main.requests, "post") as mock_post:
            req = mock.Mock()
            resp = asyncio.run(
                linear_main.linear_callback(
                    request=req,
                    code="auth_code_xyz",
                    state="victim:tampered_signature"
                )
            )
            context = resp.get("context", {})
            self.assertIn("Invalid or tampered state", context.get("error", ""))
            mock_post.assert_not_called()

    def test_callback_accepts_valid_signed_state(self):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "lin_tok_123",
            "expires_in": 3600
        }

        req = mock.Mock()
        valid_state = linear_main._oauth_state_for("user_legit")

        with mock.patch.object(linear_main, "RedirectResponse", side_effect=lambda url: {"redirect_url": url}), \
             mock.patch.object(linear_main.requests, "post", return_value=mock_resp) as mock_post, \
             mock.patch.object(linear_main, "store_linear_tokens") as mock_store:
            resp = asyncio.run(
                linear_main.linear_callback(
                    request=req,
                    code="valid_code",
                    state=valid_state
                )
            )
            self.assertEqual(resp.get("redirect_url"), "/?uid=user_legit")
            mock_store.assert_called_once()
            self.assertEqual(mock_store.call_args[0][0], "user_legit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
