"""
Hermetic tests for setup template and redirect URL hardening across plugin apps:
- plugins/omi-linear-app
- plugins/omi-hive-app
- plugins/omi-shopify-app

Verifies that uid and parameter injection across setup page links, form actions,
inline fetch scripts, and post-auth / disconnect redirects are safely percent-encoded.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

if "fastapi" not in sys.modules:
    try:
        import fastapi  # noqa: F401
        import fastapi.responses  # noqa: F401
        import fastapi.staticfiles  # noqa: F401
        import fastapi.templating  # noqa: F401
    except ImportError:
        fastapi = types.ModuleType("fastapi")

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

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail="", headers=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail
                self.headers = headers or {}

        class Request:
            def __init__(self, *args, **kwargs):
                pass

        class _Default:
            def __init__(self, *args, **kwargs):
                pass

        fastapi.FastAPI = FastAPI
        fastapi.HTTPException = HTTPException
        fastapi.Request = Request
        fastapi.Query = _Default
        fastapi.Form = _Default
        fastapi.Depends = _Default
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.body = content.encode("utf-8") if isinstance(content, str) else content

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.body = content

        class RedirectResponse:
            # Starlette exposes the target through the location header, which is
            # what the redirect assertions below read.
            def __init__(self, url=None, status_code=307, headers=None, **kwargs):
                self.url = url
                self.status_code = status_code
                self.headers = dict(headers or {})
                self.headers.setdefault("location", url)

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        responses.RedirectResponse = RedirectResponse
        sys.modules["fastapi.responses"] = responses

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

if "omi_plugin_sdk" not in sys.modules:
    sdk = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")
    for _name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, _name, MagicMock())
    sys.modules["omi_plugin_sdk"] = sdk
    sys.modules["omi_plugin_sdk.models"] = sdk_models
    sdk.models = sdk_models

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugins" / "omi-plugin-sdk" / "src"))


def _setup_template(app_dir_name: str) -> str:
    return (REPO_ROOT / "plugins" / app_dir_name / "templates" / "setup.html").read_text(encoding="utf-8")


def load_plugin_main(app_dir_name: str):
    app_dir = REPO_ROOT / "plugins" / app_dir_name
    for mod in ["db", "models", "client", "shopify_client", "hive_client"]:
        sys.modules.pop(mod, None)
    if str(app_dir) in sys.path:
        sys.path.remove(str(app_dir))
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location(f"{app_dir_name.replace('-', '_')}_main", app_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPluginsSetupUrlHardening(unittest.TestCase):
    def setUp(self):
        self.malicious_uid = 'test"user&injected=1#fragment'
        self.expected_encoded_uid = quote(self.malicious_uid, safe="")

    # -------------------------------------------------------------------------
    # Linear App Hardening Tests
    # -------------------------------------------------------------------------
    def test_linear_home_passes_uid_q_and_oauth_url_encoded(self):
        linear_main = load_plugin_main("omi-linear-app")
        with patch.object(linear_main, "get_linear_tokens", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(linear_main.home(mock_request, uid=self.malicious_uid))
            ctx = resp.context
            self.assertEqual(ctx["uid"], self.malicious_uid)
            self.assertEqual(ctx["uid_q"], self.expected_encoded_uid)
            self.assertIn(f"/auth/linear?uid={self.expected_encoded_uid}", ctx["oauth_url"])
            self.assertNotIn('"', ctx["oauth_url"])

    def test_linear_template_renders_uid_q_and_escapes_links(self):
        linear_main = load_plugin_main("omi-linear-app")
        with patch.object(linear_main, "get_linear_tokens", return_value={"access_token": "token"}), \
             patch.object(linear_main, "get_user_profile", return_value={"name": "Test User"}), \
             patch.object(linear_main, "get_user_teams", return_value=[]), \
             patch.object(linear_main, "get_default_team", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(linear_main.home(mock_request, uid=self.malicious_uid))
            self.assertEqual(resp.context["uid_q"], self.expected_encoded_uid)

        template = _setup_template("omi-linear-app")
        self.assertIn('/auth/linear?uid={{ uid_q|default(uid) }}', template)
        self.assertIn('/disconnect?uid={{ uid_q|default(uid) }}', template)

    def test_linear_template_script_encodes_uid_and_team_id(self):
        template_path = REPO_ROOT / "plugins" / "omi-linear-app" / "templates" / "setup.html"
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("encodeURIComponent(uid)", content)
        self.assertIn("encodeURIComponent(teamId)", content)
        self.assertIn("encodeURIComponent(teamName", content)

    def test_linear_redirects_encode_uid(self):
        linear_main = load_plugin_main("omi-linear-app")
        with patch.object(linear_main, "delete_linear_tokens"):
            resp = asyncio.run(linear_main.disconnect_linear(uid=self.malicious_uid))
            self.assertEqual(resp.headers["location"], f"/?uid={self.expected_encoded_uid}")

    # -------------------------------------------------------------------------
    # Hive App Hardening Tests
    # -------------------------------------------------------------------------
    def test_hive_home_passes_uid_q(self):
        hive_main = load_plugin_main("omi-hive-app")
        with patch.object(hive_main, "get_hive_credentials", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(hive_main.home(mock_request, uid=self.malicious_uid))
            ctx = resp.context
            self.assertEqual(ctx["uid"], self.malicious_uid)
            self.assertEqual(ctx["uid_q"], self.expected_encoded_uid)

    def test_hive_template_renders_uid_q_in_disconnect_and_form(self):
        hive_main = load_plugin_main("omi-hive-app")
        # Connected state
        with patch.object(hive_main, "get_hive_credentials", return_value={"hive_email": "a@b.com"}), \
             patch.object(hive_main, "get_user_projects", return_value=[]), \
             patch.object(hive_main, "get_default_project", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(hive_main.home(mock_request, uid=self.malicious_uid))
            self.assertEqual(resp.context["uid_q"], self.expected_encoded_uid)

        template = _setup_template("omi-hive-app")
        self.assertIn('/disconnect?uid={{ uid_q|default(uid) }}', template)
        self.assertIn('/settings/api-key?uid={{ uid_q|default(uid) }}', template)

        # Unconnected state
        with patch.object(hive_main, "get_hive_credentials", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(hive_main.home(mock_request, uid=self.malicious_uid))
            self.assertEqual(resp.context["uid_q"], self.expected_encoded_uid)

    def test_hive_template_script_encodes_uid_and_project_id(self):
        template_path = REPO_ROOT / "plugins" / "omi-hive-app" / "templates" / "setup.html"
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("encodeURIComponent(uid)", content)
        self.assertIn("encodeURIComponent(projectId)", content)
        self.assertIn("encodeURIComponent(projectName", content)

    def test_hive_redirects_encode_uid(self):
        hive_main = load_plugin_main("omi-hive-app")
        with patch.object(hive_main, "delete_hive_credentials"):
            resp = asyncio.run(hive_main.disconnect_hive(uid=self.malicious_uid))
            self.assertEqual(resp.headers["location"], f"/?uid={self.expected_encoded_uid}")

        with patch.object(hive_main, "verify_api_key", return_value=None):
            resp = asyncio.run(hive_main.connect_api_key(uid=self.malicious_uid, api_key="bad-key"))
            self.assertIn(f"/?uid={self.expected_encoded_uid}&error=", resp.headers["location"])

        with patch.object(hive_main, "verify_api_key", return_value={"user_id": "u1", "email": "e@x.com"}), \
             patch.object(hive_main, "store_hive_credentials"):
            resp = asyncio.run(hive_main.connect_api_key(uid=self.malicious_uid, api_key="valid-key"))
            self.assertEqual(resp.headers["location"], f"/?uid={self.expected_encoded_uid}")

    # -------------------------------------------------------------------------
    # Shopify App Hardening Tests
    # -------------------------------------------------------------------------
    def test_shopify_home_passes_uid_q(self):
        shopify_main = load_plugin_main("omi-shopify-app")
        with patch.object(shopify_main, "get_shopify_tokens", return_value=None):
            mock_request = MagicMock()
            resp = asyncio.run(shopify_main.home(mock_request, uid=self.malicious_uid))
            ctx = resp.context
            self.assertEqual(ctx["uid"], self.malicious_uid)
            self.assertEqual(ctx["uid_q"], self.expected_encoded_uid)

    def test_shopify_template_renders_uid_q_in_disconnect(self):
        shopify_main = load_plugin_main("omi-shopify-app")
        with patch.object(shopify_main, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com"}), \
             patch.object(shopify_main, "shopify_api_request", return_value={}):
            mock_request = MagicMock()
            resp = asyncio.run(shopify_main.home(mock_request, uid=self.malicious_uid))
            self.assertEqual(resp.context["uid_q"], self.expected_encoded_uid)

        template = _setup_template("omi-shopify-app")
        self.assertIn('/disconnect?uid={{ uid_q|default(uid) }}', template)

    def test_shopify_template_script_encodes_uid_and_shop_domain(self):
        template_path = REPO_ROOT / "plugins" / "omi-shopify-app" / "templates" / "setup.html"
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("encodeURIComponent(uid)", content)
        self.assertIn("encodeURIComponent(shopDomain)", content)

    def test_shopify_redirects_encode_uid(self):
        shopify_main = load_plugin_main("omi-shopify-app")
        with patch.object(shopify_main, "delete_shopify_tokens"):
            resp = asyncio.run(shopify_main.disconnect_shopify(uid=self.malicious_uid))
            self.assertEqual(resp.headers["location"], f"/?uid={self.expected_encoded_uid}")


if __name__ == "__main__":
    unittest.main()
