"""Hermetic regression tests for Composio's Notion OAuth state binding.

Before this fix, `/api/notion/auth` sent the raw uid as the OAuth `state`
and `notion_callback` treated it as the uid verbatim, so an attacker
could complete Notion OAuth for their own workspace and call the callback
with a victim's uid as `state` — binding the attacker's workspace grant
to the victim's account. The state is now HMAC-signed at initiation and
the callback recovers the uid only from states this server issued.

Framework-only stubs (fastapi, pydantic, requests, src.db, src.omi_api, src.tools_auth);
the real handlers are driven. No network, no third-party packages.
"""

import asyncio
import importlib.util
import sys
import unittest
import urllib.parse
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP_ROOT = Path(__file__).resolve().parent
SRC_DIR = APP_ROOT / "src"


class Router:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class RedirectResponse:
    def __init__(self, url, status_code=307, **kwargs):
        self.url = url
        self.status_code = status_code


def load_app():
    requests_stub = ModuleType("requests")
    requests_stub.post = Mock()
    requests_stub.get = Mock()
    requests_stub.RequestException = Exception
    requests_stub.utils = SimpleNamespace(quote=urllib.parse.quote)

    db_stub = ModuleType("src.db")
    db_stub.store_notion_credentials = Mock()
    db_stub.get_notion_credentials = Mock(return_value=None)
    db_stub.store_memory = Mock()

    omi_stub = ModuleType("src.omi_api")
    omi_stub.store_fact = Mock()

    # notion.py imports the shared-secret guard added in #14700; stub it so this
    # suite stays hermetic (their sandbox only materializes declared stubs).
    tools_auth_stub = ModuleType("src.tools_auth")
    tools_auth_stub.require_composio_tools_auth = lambda *_args, **_kwargs: None

    src_pkg = ModuleType("src")
    src_pkg.__path__ = [str(SRC_DIR)]

    modules = {
        "fastapi": ModuleType("fastapi"),
        "fastapi.responses": ModuleType("fastapi.responses"),
        "fastapi.templating": ModuleType("fastapi.templating"),
        "pydantic": ModuleType("pydantic"),
        "requests": requests_stub,
        "src": src_pkg,
        "src.db": db_stub,
        "src.omi_api": omi_stub,
        "src.tools_auth": tools_auth_stub,
    }
    modules["fastapi"].__dict__.update(
        APIRouter=Router,
        HTTPException=HTTPException,
        Depends=Mock(),
        Request=object,
        status=SimpleNamespace(
            HTTP_200_OK=200,
            HTTP_400_BAD_REQUEST=400,
            HTTP_500_INTERNAL_SERVER_ERROR=500,
        ),
        Form=Mock(),
        BackgroundTasks=Mock(),
    )
    modules["fastapi.responses"].__dict__.update(
        HTMLResponse=object,
        RedirectResponse=RedirectResponse,
    )
    modules["fastapi.templating"].__dict__.update(Jinja2Templates=Mock(return_value=Mock()))
    modules["pydantic"].__dict__.update(BaseModel=object)

    spec = importlib.util.spec_from_file_location("src.notion", SRC_DIR / "notion.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
        spec.loader.exec_module(module)
    module.init_notion_credentials("client-id", "test-secret", "https://example.com/api/notion/callback")
    return module


notion = load_app()


class TestSignedState(unittest.TestCase):
    def test_round_trip(self):
        state = notion._signed_state("uid-abc")
        self.assertEqual(notion._uid_from_state(state), "uid-abc")

    def test_tampered_uid_rejected(self):
        state = notion._signed_state("uid-abc")
        self.assertIsNone(notion._uid_from_state("uid-xyz:" + state.split(":", 1)[1]))

    def test_tampered_signature_rejected(self):
        state = notion._signed_state("uid-abc")
        self.assertIsNone(notion._uid_from_state(state[:-2] + "00"))

    def test_unsigned_state_rejected(self):
        self.assertIsNone(notion._uid_from_state("uid-abc"))
        self.assertIsNone(notion._uid_from_state(""))
        self.assertIsNone(notion._uid_from_state(":sig"))

    def test_empty_secret_rejected(self):
        with patch.object(notion, "NOTION_CLIENT_SECRET", ""):
            with self.assertRaises(RuntimeError):
                notion._signed_state("uid-abc")
            forged = "uid-abc:e3b0c44298fc1c149afbf4c8996fb924"
            self.assertIsNone(notion._uid_from_state(forged))

    def test_auth_quotes_the_signed_state(self):
        uid = "uid with/slash?and&more=1"
        response = asyncio.run(notion.auth_notion(Mock(), uid=uid))
        encoded = urllib.parse.quote(notion._signed_state(uid), safe="")
        self.assertIn(f"state={encoded}", response.url)
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query)["state"][0],
            notion._signed_state(uid),
        )


class TestCallbackGuardsState(unittest.TestCase):
    def setUp(self):
        self.post_patcher = patch.object(notion.requests, "post")
        self.mock_post = self.post_patcher.start()
        self.addCleanup(self.post_patcher.stop)

    def test_unsigned_callback_never_reaches_token_exchange(self):
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(notion.notion_callback(Mock(), Mock(), code="c", state="victim-uid"))
        self.assertEqual(caught.exception.status_code, 400)
        self.mock_post.assert_not_called()

    def test_signed_callback_reaches_token_exchange_for_that_uid(self):
        self.mock_post.return_value = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "access_token": "token",
                    "workspace_id": "ws-id",
                    "workspace_name": "Test Workspace",
                }
            ),
        )
        background_tasks = Mock()
        state = notion._signed_state("uid-abc")
        asyncio.run(notion.notion_callback(Mock(), background_tasks, code="c", state=state))
        self.mock_post.assert_called_once()
        notion.store_notion_credentials.assert_called_once_with("uid-abc", "token", "ws-id", "Test Workspace")
        self.assertEqual(background_tasks.add_task.call_args[0][2], "uid-abc")


if __name__ == "__main__":
    unittest.main()
