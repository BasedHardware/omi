"""Hermetic MS365 Graph path-encoding regressions.

Graph resource ids are not URL-safe: message ids are base64 of the store
entry id and can contain `/`, `+`, `=`; Teams chat ids contain `:`/`@`; drive
item names can contain `#`, `?`, `%`. Interpolating them raw splits the path
or truncates the URL. This suite stubs the framework layer, loads the real
service modules, and records the path each operation hands to the Graph
client. No network or credentials required.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from urllib.parse import quote

PLUGIN_DIR = Path(__file__).resolve().parent


def _stub(name, **attrs):
    module = ModuleType(name)
    module.__dict__.update(attrs)
    return module


class _AsyncClient:
    def __init__(self, *args, **kwargs):
        pass


class _Serializer:
    def dumps(self, value):
        return "signed"

    def loads(self, value):
        return value


class _Settings:
    log_level = "INFO"
    session_secret = "test-secret"
    app_base_url = "http://localhost:8000"
    redis_url = None


STUBS = {
    "httpx": _stub("httpx", AsyncClient=_AsyncClient, HTTPError=Exception, HTTPStatusError=Exception),
    "msal": _stub(
        "msal", ConfidentialClientApplication=object, SerializableTokenCache=object
    ),
    "config": _stub("config", GRAPH_SCOPES=[], get_settings=lambda: _Settings()),
    "services.storage": _stub("services.storage", get_store=lambda: None),
    "itsdangerous": _stub(
        "itsdangerous", BadSignature=Exception, URLSafeSerializer=lambda *a, **k: _Serializer()
    ),
    "pydantic_settings": _stub("pydantic_settings", BaseSettings=object, SettingsConfigDict=dict),
}


class RecordingClient:
    """Stands in for GraphClient and records every path it is asked for."""

    def __init__(self, user_id):
        self.user_id = user_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, path, **kwargs):
        self.last_path = path
        return {"value": [], "id": "x"}

    async def post(self, path, **kwargs):
        self.last_path = path
        return {"id": "m1"}

    async def put_bytes(self, path, data, content_type=None):
        self.last_path = path
        return {"id": "f1"}

    async def get_bytes(self, path):
        self.last_path = path
        return b"text"


class GraphPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.dict(sys.modules, STUBS)
        cls._patch.start()
        sys.path.insert(0, str(PLUGIN_DIR))
        import services.graph_client as graph_client
        import services.mail as mail
        import services.sharepoint as sharepoint
        import services.teams as teams

        cls.graph_client = graph_client
        cls.mail = mail
        cls.sharepoint = sharepoint
        cls.teams = teams

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()
        sys.path.remove(str(PLUGIN_DIR))

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_path_segment_encodes_reserved_characters(self):
        self.assertEqual(self.graph_client.path_segment("AAMk/abc=+"), "AAMk%2Fabc%3D%2B")

    def test_message_id_with_slash_stays_one_segment(self):
        client = RecordingClient("u1")
        with patch.object(self.mail, "GraphClient", lambda uid: client):
            self.run_async(self.mail.read("u1", "AAMkAGI2/body+/AAA="))
        self.assertEqual(client.last_path, "/me/messages/AAMkAGI2%2Fbody%2B%2FAAA%3D")

    def test_chat_id_reserved_characters_are_encoded(self):
        client = RecordingClient("u1")
        with patch.object(self.teams, "GraphClient", lambda uid: client):
            self.run_async(self.teams.send_chat_message("u1", "19:abc@thread.v2", "hi"))
        self.assertEqual(client.last_path, "/chats/19%3Aabc%40thread.v2/messages")

    def test_search_query_cannot_break_out_of_odata_literal(self):
        client = RecordingClient("u1")
        with patch.object(self.sharepoint, "GraphClient", lambda uid: client):
            self.run_async(self.sharepoint.search_files("u1", "it's ?done& #1"))
        self.assertEqual(
            client.last_path,
            "/me/drive/root/search(q='it%27%27s%20%3Fdone%26%20%231')",
        )

    def test_upload_filename_cannot_inject_path_segments(self):
        client = RecordingClient("u1")
        with patch.object(self.sharepoint, "GraphClient", lambda uid: client):
            self.run_async(
                self.sharepoint.upload_text_file("u1", "Documents/OMI Notes", "a#b?.txt", "x")
            )
        self.assertEqual(
            client.last_path,
            "/me/drive/root:/Documents/OMI%20Notes/a%23b%3F.txt:/content",
        )

    def test_item_id_is_encoded_for_reads(self):
        client = RecordingClient("u1")
        with patch.object(self.sharepoint, "GraphClient", lambda uid: client):
            self.run_async(self.sharepoint.read_file_text("u1", "01ABC/def#2"))
        self.assertEqual(client.last_path, "/me/drive/items/01ABC%2Fdef%232/content")


class SetupPageTests(unittest.TestCase):
    """`setup_page` reflects `uid` into an HTML href and a URL query."""

    def test_uid_cannot_escape_the_href_attribute(self):
        class FastAPI:
            def __init__(self, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda handler: handler

            def post(self, *args, **kwargs):
                return lambda handler: handler

        stubs = dict(STUBS)
        stubs["fastapi"] = _stub(
            "fastapi",
            FastAPI=FastAPI,
            HTTPException=Exception,
            Query=lambda *a, **k: None,
            Request=object,
        )
        stubs["fastapi.responses"] = _stub(
            "fastapi.responses",
            HTMLResponse=str,
            JSONResponse=dict,
            RedirectResponse=object,
        )
        permissive = lambda *a, **k: None
        for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
            stubs[f"services.{name}"] = _stub(
                f"services.{name}", __getattr__=lambda attr: permissive
            )
        stubs["services.storage"] = _stub(
            "services.storage", get_store=lambda: None, __getattr__=lambda attr: permissive
        )
        stubs["config"] = _stub("config", GRAPH_SCOPES=[], get_settings=lambda: _Settings())

        spec = importlib.util.spec_from_file_location("ms365_main", PLUGIN_DIR / "main.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)

        html = asyncio.run(module.setup_page(uid='x" onmouseover="alert(1)&admin=1'))
        self.assertNotIn('" onmouseover=', html)
        self.assertIn(quote('x" onmouseover="alert(1)&admin=1', safe=""), html)


if __name__ == "__main__":
    unittest.main()
