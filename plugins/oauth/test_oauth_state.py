"""Hermetic regression for OAuth state binding in the Notion CRM plugin.

The callback trusted the `state` query parameter as the uid, so anyone could
complete an OAuth flow with `state=<victim_uid>` and bind their own Notion
credentials to the victim's account - silently writing the victim's
conversations into the attacker's database. The fix stores a random
single-use state token in Redis (TTL 600s) and resolves uid from it.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


PLUGIN_DIR = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def delete(self, key):
        self.store.pop(key, None)

    def eval(self, script, numkeys, *keys):
        key = keys[0]
        val = self.get(key)
        self.delete(key)
        return val


class OAuthStateTests(unittest.TestCase):
    def setUp(self):
        fastapi = types.ModuleType("fastapi")
        router = Mock()
        router.get = router.post = lambda *a, **k: lambda f: f

        class HTTPException(Exception):
            def __init__(self, status_code=None, detail=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi.HTTPException = HTTPException
        fastapi.Request = object
        fastapi.APIRouter = Mock(return_value=router)
        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = object
        templating = types.ModuleType("fastapi.templating")

        class Jinja2Templates:
            def __init__(self, directory=None):
                self.calls = []

            def TemplateResponse(self, name, context):
                self.calls.append((name, context))
                return ("template", name, context)

        templating.Jinja2Templates = lambda directory=None: Jinja2Templates(directory)
        self.templates = Jinja2Templates()

        self.redis_client = FakeRedis()
        redis_mod = types.ModuleType("redis")
        redis_mod.Redis = Mock(return_value=self.redis_client)

        db = types.ModuleType("db")
        db.store_oauth_state = lambda state, uid: self.redis_client.setex(
            f"oauth_state:{state}", 600, uid
        )

        def pop_state(state):
            val = self.redis_client.eval(
                "GETDEL",
                1,
                f"oauth_state:{state}",
            )
            return val.decode("utf-8") if val else None

        db.pop_oauth_state = pop_state
        db.store_notion_crm_api_key = Mock()
        db.store_notion_database_id = Mock()
        db.get_notion_crm_api_key = Mock(return_value=None)
        db.get_notion_database_id = Mock(return_value=None)
        self.db = db

        models = types.ModuleType("models")
        models.Conversation = Mock
        models.EndpointResponse = dict
        models.TranscriptSegment = Mock

        templates_mod = types.ModuleType("templates")
        requests_mod = types.ModuleType("requests")

        # oauth package boundary: stub oauth.client, load real conversation_created
        oauth_pkg = types.ModuleType("oauth")
        oauth_pkg.__path__ = [str(PLUGIN_DIR)]
        client_stub = types.ModuleType("oauth.client")
        self.notion = Mock()
        client_stub.get_notion = Mock(return_value=self.notion)

        modules = {
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "fastapi.templating": templating,
            "redis": redis_mod,
            "db": db,
            "models": models,
            "templates": templates_mod,
            "requests": requests_mod,
            "oauth": oauth_pkg,
            "oauth.client": client_stub,
        }
        originals = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            self.module = load("oauth.conversation_created", "conversation_created.py")
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
        self.HTTPException = HTTPException
        self.notion.get_access_token.return_value = {"error": "denied"}

    def callback(self, state):
        return asyncio.run(
            self.module.callback_auth_notion_crm(request=Mock(), state=state, code="c")
        )

    def test_forged_uid_state_rejected(self):
        with self.assertRaises(self.HTTPException) as caught:
            self.callback("victim-uid")
        self.assertEqual(caught.exception.status_code, 400)
        self.notion.get_access_token.assert_not_called()

    def test_unknown_state_rejected(self):
        with self.assertRaises(self.HTTPException):
            self.callback("AAAAAAAAAAAAAAAAAAAAAA")
        self.notion.get_access_token.assert_not_called()

    def test_issued_state_resolves_uid(self):
        self.redis_client.setex("oauth_state:real-token", 600, "real-uid")
        self.callback("real-token")
        # uid resolved -> flow proceeded to token exchange
        self.notion.get_access_token.assert_called_once_with("c")

    def test_state_is_single_use(self):
        self.redis_client.setex("oauth_state:once", 600, "uid-1")
        self.callback("once")
        with self.assertRaises(self.HTTPException):
            self.callback("once")

    def test_setup_issues_random_state_not_uid(self):
        asyncio.run(self.module.setup_notion_crm(request=Mock(), uid="uid-9"))
        call = self.module.get_notion().get_oauth_url.call_args
        issued_state = call.args[0]
        self.assertEqual(self.db.pop_oauth_state(issued_state), "uid-9")

    def test_pop_oauth_state_is_a_single_redis_round_trip(self):
        ops = []

        class RecordingRedis:
            def eval(self, script, numkeys, *keys):
                ops.append(("eval", keys[0]))
                return b"uid-1"

            def get(self, key):
                ops.append(("get", key))
                return b"uid-1"

            def delete(self, key):
                ops.append(("delete", key))

        redis_mod = types.ModuleType("redis")
        redis_mod.Redis = Mock(return_value=RecordingRedis())
        models = types.ModuleType("models")
        models.TranscriptSegment = object
        originals = {name: sys.modules.get(name) for name in ("redis", "models")}
        sys.modules["redis"] = redis_mod
        sys.modules["models"] = models
        try:
            spec = importlib.util.spec_from_file_location(
                "plugins_db_under_test", PLUGIN_DIR.parent / "db.py"
            )
            db_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(db_mod)
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
        self.assertEqual(db_mod.pop_oauth_state("once"), "uid-1")
        self.assertEqual(ops, [("eval", "oauth_state:once")])


if __name__ == "__main__":
    unittest.main()
