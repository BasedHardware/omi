"""
Hermetic regression tests for Hive settings session authentication and API key overwrite protection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_hive_app():
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

        def set_cookie(self, key, value, **kwargs):
            self.cookies[key] = {"value": value, **kwargs}

    class FakeTemplates:
        def TemplateResponse(self, name, context):
            return SimpleNamespace(template=name, context=context)

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.Form = lambda default=None, **kwargs: default

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
    db.store_hive_credentials = Mock()
    db.get_hive_credentials = Mock(return_value=None)
    db.delete_hive_credentials = Mock()
    db.is_connected = Mock(return_value=False)
    db.store_default_project = Mock()
    db.get_default_project = Mock(return_value=None)
    db.get_user_settings = Mock(return_value={})

    models = ModuleType("models")
    models.ChatToolResponse = BaseModel
    models.HiveProject = BaseModel
    models.HiveTask = BaseModel
    models.HiveAction = BaseModel

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
    spec = importlib.util.spec_from_file_location("hive_main_auth_test", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, HTTPException


hive_main, HTTPException = load_hive_app()
TEST_SECRET = "test-hive-session-secret-key"


def make_request(cookies=None, headers=None, scheme="https"):
    return SimpleNamespace(
        cookies=cookies or {},
        headers=headers or {},
        query_params={},
        url=SimpleNamespace(scheme=scheme),
    )


class HiveSettingsSessionAuthTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("SESSION_SECRET", "HIVE_SESSION_SECRET", "OAUTH_STATE_SECRET", "APP_SECRET")
        }
        for k in self._saved_env:
            os.environ.pop(k, None)
        os.environ["SESSION_SECRET"] = TEST_SECRET

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_fails_closed_when_session_secret_unconfigured(self):
        os.environ.pop("SESSION_SECRET", None)
        req = make_request()
        with patch.object(hive_main, "store_default_project") as store_proj, \
             patch.object(hive_main, "store_hive_credentials") as store_creds:
            with self.assertRaises(HTTPException) as ctx1:
                asyncio.run(hive_main.set_default_project("user-1", "proj-1", "Engineering", request=req))
            self.assertEqual(ctx1.exception.status_code, 503)
            store_proj.assert_not_called()

            with self.assertRaises(HTTPException) as ctx2:
                asyncio.run(hive_main.connect_api_key(request=req, uid="user-1", api_key="key-123"))
            self.assertEqual(ctx2.exception.status_code, 503)
            store_creds.assert_not_called()

    def test_first_time_api_key_connection_sets_signed_session_cookie(self):
        req = make_request(scheme="https")
        with patch.object(hive_main, "get_hive_credentials", return_value=None), \
             patch.object(hive_main, "is_connected", return_value=False), \
             patch.object(hive_main, "verify_api_key", return_value={"user_id": "h1", "email": "a@b.com", "workspace_id": "w1"}), \
             patch.object(hive_main, "store_hive_credentials") as store_creds:
            resp = asyncio.run(hive_main.connect_api_key(request=req, uid="user:1", api_key="valid-key"))
            self.assertEqual(resp.status_code, 303)
            store_creds.assert_called_once_with(
                uid="user:1",
                api_key="valid-key",
                hive_user_id="h1",
                hive_email="a@b.com",
                workspace_id="w1",
            )
            self.assertIn(hive_main.SESSION_COOKIE_NAME, resp.cookies)
            cookie = resp.cookies[hive_main.SESSION_COOKIE_NAME]
            self.assertTrue(cookie["httponly"])
            self.assertEqual(cookie["samesite"], "lax")
            self.assertTrue(cookie["secure"])
            authed_req = make_request(cookies={hive_main.SESSION_COOKIE_NAME: cookie["value"]})
            self.assertTrue(hive_main._has_valid_session(authed_req, "user:1"))
            self.assertFalse(hive_main._has_valid_session(authed_req, "other-user"))

    def test_connected_user_api_key_overwrite_blocked_without_valid_session(self):
        unauthed_req = make_request()
        wrong_user_cookie = hive_main._create_session_token("attacker-uid")
        wrong_user_req = make_request(cookies={hive_main.SESSION_COOKIE_NAME: wrong_user_cookie})

        with patch.object(hive_main, "get_hive_credentials", return_value={"api_key": "victim-key"}), \
             patch.object(hive_main, "verify_api_key") as verify_mock, \
             patch.object(hive_main, "store_hive_credentials") as store_creds:
            for bad_req in (unauthed_req, wrong_user_req):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(hive_main.connect_api_key(request=bad_req, uid="victim-uid", api_key="attacker-key"))
                self.assertEqual(ctx.exception.status_code, 403)
            verify_mock.assert_not_called()
            store_creds.assert_not_called()

    def test_connected_user_can_rotate_api_key_with_valid_session(self):
        valid_cookie = hive_main._create_session_token("victim-uid")
        authed_req = make_request(cookies={hive_main.SESSION_COOKIE_NAME: valid_cookie})

        with patch.object(hive_main, "get_hive_credentials", return_value={"api_key": "old-key"}), \
             patch.object(hive_main, "verify_api_key", return_value={"user_id": "h1", "email": "v@b.com", "workspace_id": "w1"}), \
             patch.object(hive_main, "store_hive_credentials") as store_creds:
            resp = asyncio.run(hive_main.connect_api_key(request=authed_req, uid="victim-uid", api_key="new-key"))
            self.assertEqual(resp.status_code, 303)
            store_creds.assert_called_once()

    def test_set_default_project_requires_valid_session_for_uid(self):
        unauthed_req = make_request()
        attacker_cookie = hive_main._create_session_token("attacker-uid")
        cross_user_req = make_request(cookies={hive_main.SESSION_COOKIE_NAME: attacker_cookie})
        valid_cookie = hive_main._create_session_token("victim-uid")
        valid_req = make_request(cookies={hive_main.SESSION_COOKIE_NAME: valid_cookie})

        with patch.object(hive_main, "store_default_project") as store_proj:
            for bad_req in (unauthed_req, cross_user_req):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(hive_main.set_default_project("victim-uid", "p-attacker", "Hijacked", request=bad_req))
                self.assertEqual(ctx.exception.status_code, 403)
            store_proj.assert_not_called()

            res = asyncio.run(hive_main.set_default_project("victim-uid", "p-1", "Roadmap", request=valid_req))
            self.assertTrue(res["success"])
            store_proj.assert_called_once_with("victim-uid", "p-1", "Roadmap")

    def test_home_redacts_connected_account_info_and_projects_without_session(self):
        creds = {
            "hive_email": "victim@company.com",
            "hive_name": "Victim Name",
            "hive_user_id": "hive-user-1",
        }
        with patch.object(hive_main, "get_hive_credentials", return_value=creds), \
             patch.object(hive_main, "get_user_projects", return_value=[{"id": "p1", "name": "Secret Project"}]) as get_projs, \
             patch.object(hive_main, "get_default_project", return_value={"id": "p1", "name": "Secret Project"}) as get_def:
            unauthed_resp = asyncio.run(hive_main.home(request=make_request(), uid="victim-uid"))
            self.assertFalse(unauthed_resp.context["connected"])
            self.assertIsNone(unauthed_resp.context["user_info"])
            self.assertEqual(unauthed_resp.context["projects"], [])
            self.assertIsNone(unauthed_resp.context["default_project"])
            get_projs.assert_not_called()
            get_def.assert_not_called()

            valid_cookie = hive_main._create_session_token("victim-uid")
            authed_resp = asyncio.run(
                hive_main.home(
                    request=make_request(cookies={hive_main.SESSION_COOKIE_NAME: valid_cookie}),
                    uid="victim-uid",
                )
            )
            self.assertTrue(authed_resp.context["connected"])
            self.assertEqual(authed_resp.context["user_info"]["email"], "victim@company.com")
            self.assertEqual(len(authed_resp.context["projects"]), 1)
            get_projs.assert_called_once_with("victim-uid")
            get_def.assert_called_once_with("victim-uid")


if __name__ == "__main__":
    unittest.main()
