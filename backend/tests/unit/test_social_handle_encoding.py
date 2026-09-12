"""Regression tests for utils/social.py Twitter URL construction.

The RapidAPI helpers interpolated the user-supplied ``handle`` into the
query string without percent-encoding, so a handle containing ``&``, ``#``
or ``%`` corrupted the request (e.g. ``screenname=a&b=1`` injected a second
query parameter). Stubs go through ``testing.import_isolation`` so a stub-fed
``utils.social`` cannot leak into a shared pytest process.
"""

import asyncio
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _install_stubs():
    """Return {name: original} after registering lightweight stub modules."""
    stubs = {}

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    stubs["pydantic"] = pydantic

    ulid = types.ModuleType("ulid")
    ulid.ULID = lambda: "01TESTULID"
    stubs["ulid"] = ulid

    database = types.ModuleType("database")
    database.__path__ = []
    db_apps = types.ModuleType("database.apps")
    for name in (
        "update_app_in_db",
        "upsert_app_to_db",
        "get_persona_by_id_db",
        "get_persona_by_username_twitter_handle_db",
    ):
        setattr(db_apps, name, Mock())
    db_redis = types.ModuleType("database.redis_db")
    db_redis.delete_generic_cache = Mock()
    db_redis.save_username = Mock()
    stubs["database"] = database
    stubs["database.apps"] = db_apps
    stubs["database.redis_db"] = db_redis

    utils = types.ModuleType("utils")
    utils.__path__ = []
    llm = types.ModuleType("utils.llm")
    llm.__path__ = []
    persona = types.ModuleType("utils.llm.persona")
    persona.generate_twitter_persona_prompt = Mock()
    conversations = types.ModuleType("utils.conversations")
    conversations.__path__ = []
    memories = types.ModuleType("utils.conversations.memories")
    memories.process_twitter_memories = Mock()
    executors = types.ModuleType("utils.executors")
    executors.db_executor = Mock()
    executors.llm_executor = Mock()
    executors.postprocess_executor = Mock()
    executors.run_blocking = Mock()
    stubs["utils"] = utils
    stubs["utils.llm"] = llm
    stubs["utils.llm.persona"] = persona
    stubs["utils.conversations"] = conversations
    stubs["utils.conversations.memories"] = memories
    stubs["utils.executors"] = executors

    return stubs


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _make_httpx(captured):
    httpx = types.ModuleType("httpx")

    class Timeout:
        def __init__(self, *args, **kwargs):
            pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            captured.append(url)
            return _FakeResponse(
                {
                    "name": "n",
                    "profile": "p",
                    "rest_id": "1",
                    "avatar": "",
                    "desc": "",
                    "friends": 0,
                    "sub_count": 0,
                    "id": "1",
                }
            )

    httpx.Timeout = Timeout
    httpx.AsyncClient = AsyncClient
    return httpx


@contextmanager
def loaded_social(captured):
    stubs = _install_stubs()
    stubs["httpx"] = _make_httpx(captured)
    with stub_modules(stubs):
        yield load_module_fresh("utils.social", str(_BACKEND / "utils" / "social.py"))


class TwitterHandleEncodingTests(unittest.TestCase):
    def test_profile_url_encodes_ampersand(self):
        captured = []
        with loaded_social(captured) as social:
            asyncio.run(social.get_twitter_profile("foo&x=1"))
        self.assertTrue(captured)
        self.assertIn("screenname=foo%26x%3D1", captured[0])

    def test_profile_url_encodes_fragment(self):
        captured = []
        with loaded_social(captured) as social:
            asyncio.run(social.get_twitter_profile("foo#bar"))
        self.assertIn("screenname=foo%23bar", captured[0])

    def test_profile_url_keeps_plain_handle(self):
        captured = []
        with loaded_social(captured) as social:
            asyncio.run(social.get_twitter_profile("jack"))
        self.assertIn("screenname=jack", captured[0])
        self.assertNotIn("%", captured[0])

    def test_timeline_url_encodes_ampersand(self):
        captured = []
        with loaded_social(captured) as social:
            social.TwitterTimeline = Mock(return_value=Mock())
            try:
                asyncio.run(social.get_twitter_timeline("a&b=1"))
            except Exception:
                pass  # parsing details are irrelevant; the URL is what we assert
        self.assertTrue(captured)
        self.assertIn("screenname=a%26b%3D1", captured[0])


if __name__ == "__main__":
    unittest.main()
