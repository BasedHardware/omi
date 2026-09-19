#!/usr/bin/env python3
"""Hermetic tests for signed Notion OAuth state handling (issue #14690)."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parent


class Router:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class BaseModel:
    pass


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class RedirectResponse:
    def __init__(self, url, **kwargs):
        self.url = url


class Templates:
    def __init__(self, *args, **kwargs):
        pass

    def TemplateResponse(self, *args, **kwargs):
        return SimpleNamespace(args=args, kwargs=kwargs)


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeRequests(ModuleType):
    class exceptions:
        RequestException = Exception

    class utils:
        @staticmethod
        def quote(value, safe="/"):
            from urllib.parse import quote

            return quote(value, safe=safe)


def load_module():
    fastapi = ModuleType("fastapi")
    fastapi.APIRouter = Router
    fastapi.BackgroundTasks = object
    fastapi.Depends = lambda dependency=None: dependency
    fastapi.Form = lambda default=None, **kwargs: default
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    fastapi.status = SimpleNamespace(
        HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401,
        HTTP_500_INTERNAL_SERVER_ERROR=500,
    )

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = object
    responses.RedirectResponse = RedirectResponse

    templating = ModuleType("fastapi.templating")
    templating.Jinja2Templates = Templates

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    requests = FakeRequests("requests")
    requests.post = mock.Mock()
    requests.get = mock.Mock()

    src = ModuleType("src")
    src.__path__ = []
    db = ModuleType("src.db")
    db.store_notion_credentials = mock.Mock()
    db.get_notion_credentials = mock.Mock(return_value=None)
    db.store_memory = mock.Mock()
    omi_api = ModuleType("src.omi_api")
    omi_api.store_fact = mock.AsyncMock()

    patches = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.templating": templating,
        "pydantic": pydantic,
        "requests": requests,
        "src": src,
        "src.db": db,
        "src.omi_api": omi_api,
    }
    spec = importlib.util.spec_from_file_location(
        "src.notion",
        ROOT / "src" / "notion.py",
    )
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, patches):
        spec.loader.exec_module(module)
    return module


class SignedStateTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.module.NOTION_CLIENT_SECRET = "test-secret"

    def test_round_trip_returns_original_uid(self):
        state = self.module.sign_notion_state("user-123")
        self.assertNotEqual(state, "user-123")
        self.assertEqual(self.module.verify_notion_state(state), "user-123")

    def test_tampered_signature_is_rejected(self):
        state = self.module.sign_notion_state("user-123")
        uid, _, signature = state.rpartition(":")
        replacement = "0" if signature[-1] != "0" else "1"
        with self.assertRaises(HTTPException) as raised:
            self.module.verify_notion_state(
                f"{uid}:{signature[:-1]}{replacement}"
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_raw_uid_and_malformed_states_are_rejected(self):
        for state in ("user-123", "", ":", "user-123:", ":signature"):
            with self.subTest(state=state):
                with self.assertRaises(HTTPException) as raised:
                    self.module.verify_notion_state(state)
                self.assertEqual(raised.exception.status_code, 400)

    def test_missing_secret_fails_closed(self):
        self.module.NOTION_CLIENT_SECRET = ""
        with self.assertRaises(HTTPException) as raised:
            self.module.sign_notion_state("user-123")
        self.assertEqual(raised.exception.status_code, 500)


class NotionOAuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.module.NOTION_CLIENT_SECRET = "test-secret"
        self.module.NOTION_CLIENT_ID = "client-id"
        self.module.NOTION_REDIRECT_URI = "https://example.test/callback"

    def test_auth_redirect_uses_signed_state(self):
        response = asyncio.run(self.module.auth_notion(None, "user-123"))
        self.assertIn("state=user-123%3A", response.url)
        self.assertNotIn("state=user-123&", response.url)

    def test_callback_rejects_forged_state_before_token_exchange(self):
        self.module.requests.post.reset_mock()
        self.module.store_notion_credentials.reset_mock()
        background = mock.Mock()

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(
                self.module.notion_callback(
                    None,
                    background,
                    code="attacker-code",
                    state="victim-uid",
                )
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.module.requests.post.assert_not_called()
        self.module.store_notion_credentials.assert_not_called()
        background.add_task.assert_not_called()

    def test_callback_uses_verified_uid_not_raw_state(self):
        self.module.requests.post.return_value = FakeResponse(
            {
                "access_token": "notion-access-token",
                "workspace_id": "workspace-id",
                "workspace_name": "Workspace",
            }
        )
        self.module.store_notion_credentials.reset_mock()
        background = mock.Mock()
        signed_state = self.module.sign_notion_state("user-123")

        response = asyncio.run(
            self.module.notion_callback(
                None,
                background,
                code="valid-code",
                state=signed_state,
            )
        )

        self.assertIsNotNone(response)
        self.module.store_notion_credentials.assert_called_once_with(
            "user-123",
            "notion-access-token",
            "workspace-id",
            "Workspace",
        )
        background.add_task.assert_called_once_with(
            self.module.extract_all_pages,
            "notion-access-token",
            "user-123",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
