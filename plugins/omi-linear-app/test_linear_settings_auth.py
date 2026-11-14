"""
Hermetic regression tests for Linear settings session authentication and OAuth workspace rebinding protection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import urllib.parse
import unittest
from unittest.mock import Mock, patch


def load_linear_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def mount(self, *args, **kwargs):
            pass

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class RedirectResponse:
        def __init__(self, url="", status_code=302):
            self.url = url
            self.status_code = status_code
            self.cookies = {}
            self.deleted_cookies = []

        def set_cookie(self, key, value, **kwargs):
            self.cookies[key] = {"value": value, **kwargs}

        def delete_cookie(self, key, **kwargs):
            self.deleted_cookies.append(key)

    class FakeTemplates:
        def TemplateResponse(self, name, context):
            return SimpleNamespace(template=name, context=context, status_code=200)

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default

    staticfiles = ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda **kwargs: None

    templating = ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda **kwargs: FakeTemplates()

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = RedirectResponse
    responses.JSONResponse = dict

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    requests = ModuleType("requests")
    requests.get = Mock()
    requests.post = Mock()

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db = ModuleType("db")
    db.store_linear_tokens = Mock()
    db.get_linear_tokens = Mock(return_value=None)
    db.delete_linear_tokens = Mock()
    db.is_token_expired = Mock(return_value=False)
    db.store_default_team = Mock()
    db.get_default_team = Mock(return_value=None)
    db.get_user_settings = Mock(return_value={})

    models = ModuleType("models")
    models.ChatToolResponse = BaseModel
    models.LinearIssue = BaseModel
    models.LinearTeam = BaseModel
    models.LinearProject = BaseModel
    models.LinearComment = BaseModel
    models.LinearUser = BaseModel
    models.WorkflowState = BaseModel

    stubs = {
        "fastapi": fastapi,
        "fastapi.staticfiles": staticfiles,
        "fastapi.templating": templating,
        "fastapi.responses": responses,
        "pydantic": pydantic,
        "requests": requests,
        "dotenv": dotenv,
        "db": db,
        "models": models,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("linear_main_auth_test", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, HTTPException


linear_main, HTTPException = load_linear_app()
TEST_SECRET = "test-linear-session-secret-key"


def token_response(access_token):
    return SimpleNamespace(
        status_code=200,
        json=lambda: {"access_token": access_token, "refresh_token": "ref", "expires_in": 3600},
    )


def make_request(cookies=None, headers=None, scheme="https"):
    return SimpleNamespace(
        cookies=cookies or {},
        headers=headers or {},
        query_params={},
        url=SimpleNamespace(scheme=scheme),
    )


class LinearSettingsSessionAuthTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k)
            for k in (
                "SESSION_SECRET",
                "LINEAR_SESSION_SECRET",
                "OAUTH_STATE_SECRET",
                "APP_SECRET",
                "LINEAR_CLIENT_SECRET",
            )
        }
        for k in self._saved_env:
            os.environ.pop(k, None)
        linear_main.LINEAR_CLIENT_SECRET = ""
        os.environ["SESSION_SECRET"] = TEST_SECRET

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_fails_closed_when_secrets_unconfigured(self):
        os.environ.pop("SESSION_SECRET", None)
        req = make_request()
        with patch.object(linear_main, "store_default_team") as store_team:
            with self.assertRaises(HTTPException) as ctx1:
                asyncio.run(linear_main.set_default_team("user-1", "t-1", "Core", request=req))
            self.assertEqual(ctx1.exception.status_code, 503)
            store_team.assert_not_called()

            with self.assertRaises(HTTPException) as ctx2:
                asyncio.run(linear_main.linear_auth("user-1", request=req))
            self.assertEqual(ctx2.exception.status_code, 503)

    def test_set_default_team_requires_valid_session_for_uid(self):
        unauthed_req = make_request()
        attacker_cookie = linear_main._create_session_token("attacker-uid")
        cross_user_req = make_request(cookies={linear_main.SESSION_COOKIE_NAME: attacker_cookie})
        valid_cookie = linear_main._create_session_token("victim-uid")
        valid_req = make_request(cookies={linear_main.SESSION_COOKIE_NAME: valid_cookie})

        with patch.object(linear_main, "store_default_team") as store_team:
            for bad_req in (unauthed_req, cross_user_req):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(linear_main.set_default_team("victim-uid", "t-evil", "Evil", request=bad_req))
                self.assertEqual(ctx.exception.status_code, 403)
            store_team.assert_not_called()

            res = asyncio.run(linear_main.set_default_team("victim-uid", "t-1", "Platform", request=valid_req))
            self.assertTrue(res["success"])
            store_team.assert_called_once_with("victim-uid", "t-1", "Platform")

    def test_home_redacts_profile_and_teams_without_session(self):
        with patch.object(linear_main, "get_linear_tokens", return_value={"access_token": "tok"}), \
             patch.object(linear_main, "get_user_profile", return_value={"email": "v@company.com"}) as get_prof, \
             patch.object(linear_main, "get_user_teams", return_value=[{"id": "t1", "name": "Eng"}]) as get_teams, \
             patch.object(linear_main, "get_default_team", return_value={"id": "t1", "name": "Eng"}) as get_def:
            unauthed_resp = asyncio.run(linear_main.home(request=make_request(), uid="victim-uid"))
            self.assertFalse(unauthed_resp.context["authenticated"])
            self.assertIsNone(unauthed_resp.context["user_profile"])
            self.assertEqual(unauthed_resp.context["teams"], [])
            self.assertIsNone(unauthed_resp.context["default_team"])
            get_prof.assert_not_called()
            get_teams.assert_not_called()
            get_def.assert_not_called()

            valid_cookie = linear_main._create_session_token("victim-uid")
            authed_resp = asyncio.run(
                linear_main.home(
                    request=make_request(cookies={linear_main.SESSION_COOKIE_NAME: valid_cookie}),
                    uid="victim-uid",
                )
            )
            self.assertTrue(authed_resp.context["authenticated"])
            self.assertEqual(authed_resp.context["user_profile"]["email"], "v@company.com")
            self.assertEqual(len(authed_resp.context["teams"]), 1)
            get_prof.assert_called_once_with("victim-uid")
            get_teams.assert_called_once_with("victim-uid")
            get_def.assert_called_once_with("victim-uid")

    def test_oauth_rebinding_blocked_for_already_connected_uid_without_session(self):
        with patch.object(linear_main, "get_linear_tokens", return_value={"access_token": "victim-tok"}):
            # Starting the flow is allowed (re-auth path), but the callback must refuse
            # to bind a different Linear account to the victim uid without a session.
            auth_resp = asyncio.run(linear_main.linear_auth("victim-uid", request=make_request()))
            state = urllib.parse.parse_qs(urllib.parse.urlparse(auth_resp.url).query)["state"][0]
            nonce = auth_resp.cookies[linear_main.OAUTH_NONCE_COOKIE_NAME]["value"]
            cb_req = make_request(cookies={linear_main.OAUTH_NONCE_COOKIE_NAME: nonce})
            identities = {
                "victim-tok": {"user_id": "victim-lin", "organization_id": "org-victim"},
                "attacker-tok": {"user_id": "attacker-lin", "organization_id": "org-attacker"},
            }
            with patch.object(linear_main.requests, "post", return_value=token_response("attacker-tok")), \
                 patch.object(linear_main, "get_valid_access_token", return_value="victim-tok"), \
                 patch.object(linear_main, "_fetch_linear_identity", side_effect=identities.get), \
                 patch.object(linear_main, "store_linear_tokens") as store_tokens:
                cb_resp = asyncio.run(
                    linear_main.linear_callback(request=cb_req, code="code-1", state=state)
                )
                self.assertEqual(cb_resp.status_code, 403)
                self.assertFalse(cb_resp.context["authenticated"])
                store_tokens.assert_not_called()
                self.assertNotIn(linear_main.SESSION_COOKIE_NAME, getattr(cb_resp, "cookies", {}))

    def test_oauth_callback_rejects_unsigned_or_mismatched_nonce_state(self):
        with patch.object(linear_main, "get_linear_tokens", return_value=None), \
             patch.object(linear_main.requests, "post") as post_mock, \
             patch.object(linear_main, "store_linear_tokens") as store_tokens:
            # Raw uid as state (legacy unsigned)
            resp1 = asyncio.run(
                linear_main.linear_callback(request=make_request(), code="code-1", state="victim-uid")
            )
            self.assertEqual(resp1.status_code, 400)

            # Signed state but missing browser nonce cookie
            state, _nonce = linear_main._create_oauth_state("victim-uid")
            resp2 = asyncio.run(
                linear_main.linear_callback(request=make_request(), code="code-1", state=state)
            )
            self.assertEqual(resp2.status_code, 400)

            post_mock.assert_not_called()
            store_tokens.assert_not_called()

    def test_full_oauth_flow_supports_colon_uid_and_mints_session_cookie(self):
        uid = "firebase:user:123"
        with patch.object(linear_main, "get_linear_tokens", return_value=None):
            auth_resp = asyncio.run(linear_main.linear_auth(uid, request=make_request()))
            parsed = urllib.parse.urlparse(auth_resp.url)
            state = urllib.parse.parse_qs(parsed.query)["state"][0]
            nonce_cookie = auth_resp.cookies[linear_main.OAUTH_NONCE_COOKIE_NAME]["value"]

            fake_token_resp = SimpleNamespace(
                status_code=200,
                json=lambda: {"access_token": "lin-tok-1", "refresh_token": "lin-ref-1", "expires_in": 3600},
            )
            cb_req = make_request(cookies={linear_main.OAUTH_NONCE_COOKIE_NAME: nonce_cookie})
            with patch.object(linear_main.requests, "post", return_value=fake_token_resp) as post_mock, \
                 patch.object(linear_main, "store_linear_tokens") as store_tokens:
                cb_resp = asyncio.run(
                    linear_main.linear_callback(request=cb_req, code="auth-code", state=state)
                )
                post_mock.assert_called_once()
                store_tokens.assert_called_once()
                self.assertEqual(store_tokens.call_args[0][0], uid)
                self.assertIn(linear_main.SESSION_COOKIE_NAME, cb_resp.cookies)
                self.assertIn(linear_main.OAUTH_NONCE_COOKIE_NAME, cb_resp.deleted_cookies)


    def test_session_secret_does_not_fall_back_to_linear_client_secret(self):
        os.environ.pop("SESSION_SECRET", None)
        os.environ["LINEAR_CLIENT_SECRET"] = "oauth-client-secret"
        linear_main.LINEAR_CLIENT_SECRET = "oauth-client-secret"
        try:
            self.assertIsNone(linear_main._configured_session_secret())
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(linear_main.linear_auth("user-1", request=make_request()))
            self.assertEqual(ctx.exception.status_code, 503)
            with self.assertRaises(HTTPException) as ctx2:
                asyncio.run(linear_main.disconnect_linear("user-1", request=make_request()))
            self.assertEqual(ctx2.exception.status_code, 503)
        finally:
            linear_main.LINEAR_CLIENT_SECRET = ""

    def test_disconnect_requires_valid_session_for_uid(self):
        attacker_cookie = linear_main._create_session_token("attacker-uid")
        with patch.object(linear_main, "delete_linear_tokens") as delete_tokens:
            for bad_req in (make_request(), make_request(cookies={linear_main.SESSION_COOKIE_NAME: attacker_cookie})):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(linear_main.disconnect_linear("victim-uid", request=bad_req))
                self.assertEqual(ctx.exception.status_code, 403)
            delete_tokens.assert_not_called()

            valid_cookie = linear_main._create_session_token("victim-uid")
            resp = asyncio.run(
                linear_main.disconnect_linear(
                    "victim-uid",
                    request=make_request(cookies={linear_main.SESSION_COOKIE_NAME: valid_cookie}),
                )
            )
            self.assertEqual(resp.status_code, 303)
            delete_tokens.assert_called_once_with("victim-uid")

    def test_disconnect_then_rebind_chain_is_blocked(self):
        store = {"victim-uid": {"access_token": "victim-tok", "refresh_token": "r"}}
        identities = {
            "victim-tok": {"user_id": "victim-lin", "organization_id": "org-victim"},
            "attacker-tok": {"user_id": "attacker-lin", "organization_id": "org-attacker"},
        }

        def fake_store(uid, access_token, refresh_token, expires_at):
            store[uid] = {"access_token": access_token, "refresh_token": refresh_token}

        with patch.object(linear_main, "get_linear_tokens", side_effect=lambda uid: store.get(uid)), \
             patch.object(linear_main, "get_valid_access_token", side_effect=lambda uid: (store.get(uid) or {}).get("access_token")), \
             patch.object(linear_main, "delete_linear_tokens", side_effect=lambda uid: store.pop(uid, None)), \
             patch.object(linear_main, "store_linear_tokens", side_effect=fake_store), \
             patch.object(linear_main, "_fetch_linear_identity", side_effect=identities.get), \
             patch.object(linear_main.requests, "post", return_value=token_response("attacker-tok")):
            # Step 1: attacker tries to wipe the victim's tokens without a session
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(linear_main.disconnect_linear("victim-uid", request=make_request()))
            self.assertEqual(ctx.exception.status_code, 403)

            # Step 2: attacker runs OAuth for the victim uid with their own Linear account
            auth_resp = asyncio.run(linear_main.linear_auth("victim-uid", request=make_request()))
            state = urllib.parse.parse_qs(urllib.parse.urlparse(auth_resp.url).query)["state"][0]
            nonce = auth_resp.cookies[linear_main.OAUTH_NONCE_COOKIE_NAME]["value"]
            cb_resp = asyncio.run(
                linear_main.linear_callback(
                    request=make_request(cookies={linear_main.OAUTH_NONCE_COOKIE_NAME: nonce}),
                    code="attacker-code",
                    state=state,
                )
            )
            self.assertEqual(cb_resp.status_code, 403)

        self.assertEqual(store["victim-uid"]["access_token"], "victim-tok")

    def test_connected_user_without_cookie_recovers_session_with_same_linear_account(self):
        with patch.object(linear_main, "get_linear_tokens", return_value={"access_token": "old-tok"}):
            auth_resp = asyncio.run(linear_main.linear_auth("victim-uid", request=make_request()))
            state = urllib.parse.parse_qs(urllib.parse.urlparse(auth_resp.url).query)["state"][0]
            nonce = auth_resp.cookies[linear_main.OAUTH_NONCE_COOKIE_NAME]["value"]
            same = {"user_id": "victim-lin", "organization_id": "org-victim"}
            with patch.object(linear_main.requests, "post", return_value=token_response("new-tok")), \
                 patch.object(linear_main, "get_valid_access_token", return_value="old-tok"), \
                 patch.object(linear_main, "_fetch_linear_identity", return_value=same), \
                 patch.object(linear_main, "store_linear_tokens") as store_tokens:
                cb_resp = asyncio.run(
                    linear_main.linear_callback(
                        request=make_request(cookies={linear_main.OAUTH_NONCE_COOKIE_NAME: nonce}),
                        code="code-1",
                        state=state,
                    )
                )
                store_tokens.assert_called_once()
                self.assertEqual(store_tokens.call_args[0][1], "new-tok")
                self.assertIn(linear_main.SESSION_COOKIE_NAME, cb_resp.cookies)

    def test_recovery_refused_for_same_workspace_different_user_or_unresolved_identity(self):
        cases = [
            ({"user_id": "victim-lin", "organization_id": "org-1"}, {"user_id": "coworker-lin", "organization_id": "org-1"}),
            ({"user_id": "victim-lin", "organization_id": "org-1"}, None),
            (None, {"user_id": "victim-lin", "organization_id": "org-1"}),
        ]
        for current, incoming in cases:
            identities = {"old-tok": current, "new-tok": incoming}
            with patch.object(linear_main, "get_linear_tokens", return_value={"access_token": "old-tok"}), \
                 patch.object(linear_main, "get_valid_access_token", return_value="old-tok"), \
                 patch.object(linear_main, "_fetch_linear_identity", side_effect=identities.get), \
                 patch.object(linear_main.requests, "post", return_value=token_response("new-tok")), \
                 patch.object(linear_main, "store_linear_tokens") as store_tokens:
                state, nonce = linear_main._create_oauth_state("victim-uid")
                cb_resp = asyncio.run(
                    linear_main.linear_callback(
                        request=make_request(cookies={linear_main.OAUTH_NONCE_COOKIE_NAME: nonce}),
                        code="code-1",
                        state=state,
                    )
                )
                self.assertEqual(cb_resp.status_code, 403)
                store_tokens.assert_not_called()

    def test_fetch_linear_identity_parses_viewer_and_organization(self):
        ok = SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"viewer": {"id": "u1", "organization": {"id": "o1"}}}},
        )
        with patch.object(linear_main.requests, "post", return_value=ok):
            self.assertEqual(
                linear_main._fetch_linear_identity("tok"),
                {"user_id": "u1", "organization_id": "o1"},
            )
        bad = SimpleNamespace(status_code=401, json=lambda: {})
        with patch.object(linear_main.requests, "post", return_value=bad):
            self.assertIsNone(linear_main._fetch_linear_identity("tok"))
        self.assertIsNone(linear_main._fetch_linear_identity(None))


if __name__ == "__main__":
    unittest.main()
