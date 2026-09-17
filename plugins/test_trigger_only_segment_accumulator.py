"""Hermetic regression: a trigger-only segment must not poison the
recording session's accumulator.

extract_tweet_content("Tweet now") deliberately returns None (empty
body). The recording transition stored that nullable result raw, and
session.get("accumulated_text", "") does not substitute the default for
a key whose value is None, so the NEXT segment crashed:

    TypeError: unsupported operand type(s) for +=: 'NoneType' and 'str'

The suite drives the real process_segments() through the exact
reproduction: segment 1 is trigger-only, segment 2 continues the
recording. Only fastapi/dotenv/openai are stubbed; session storage is
the plugin's real in-memory store.

Run: python3 plugins/test_trigger_only_segment_accumulator.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _load_plugin():
    fastapi = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *a, **k):
            pass

        get = staticmethod(_decorator)
        post = staticmethod(_decorator)
        on_event = staticmethod(_decorator)
        websocket = staticmethod(_decorator)
        mount = staticmethod(lambda *a, **k: None)

    fastapi.FastAPI = _FastAPI
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kw: default
    fastapi.HTTPException = type("HTTPException", (Exception,), {})

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = lambda content=None, **kw: content
    responses.JSONResponse = lambda content=None, **kw: content
    responses.RedirectResponse = lambda url=None, **kw: types.SimpleNamespace(url=url)
    fastapi.responses = responses

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None

    openai = types.ModuleType("openai")
    openai.AsyncOpenAI = lambda *a, **k: mock.MagicMock(name="AsyncOpenAI")

    env_stubs = {"openai": openai, "dotenv": dotenv}

    # Load the REAL TweetDetector (openai/dotenv stubbed) so the trigger
    # and extraction behave exactly like production: "Tweet now" alone
    # yields None content.
    with mock.patch.dict(sys.modules, env_stubs):
        td_spec = importlib.util.spec_from_file_location(
            "tweet_detector_real_test",
            PLUGINS_DIR / "omi-twitter-app" / "tweet_detector.py",
        )
        real_detector = importlib.util.module_from_spec(td_spec)
        td_spec.loader.exec_module(real_detector)

    twitter_client = types.ModuleType("twitter_client")
    twitter_client.TwitterClient = lambda *a, **k: mock.MagicMock(name="TwitterClient")

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "dotenv": dotenv,
        "openai": openai,
        "twitter_client": twitter_client,
        "tweet_detector": real_detector,
    }
    uvicorn = types.ModuleType("uvicorn")
    stubs["uvicorn"] = uvicorn

    # simple_storage is a real sibling module (stdlib-only); the plugin
    # dir must be importable for main_simple's `from simple_storage import ...`
    plugin_dir = str(PLUGINS_DIR / "omi-twitter-app")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    main_path = PLUGINS_DIR / "omi-twitter-app" / "main_simple.py"
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            "omi_twitter_app_accumulator_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def run():
    module = _load_plugin()

    session = module.SimpleSessionStorage.get_or_create_session(
        "test_sess_14363", "uid_x"
    )
    user = {"user_id": "uid_x"}

    r1 = asyncio.run(
        module.process_segments(session, [{"text": "Tweet now"}], user)
    )
    print(f"PASS? segment1 -> {r1!r} (expected 'collecting_1')")
    assert r1 == "collecting_1", f"segment 1 returned {r1!r}"

    stored = session.get("accumulated_text")
    print(f"PASS? stored accumulator -> {stored!r} (expected '', not None)")
    assert stored == "", f"accumulator must be '' after trigger-only segment, got {stored!r}"

    # This is the call that used to raise
    # TypeError: unsupported operand type(s) for +=: 'NoneType' and 'str'
    r2 = asyncio.run(
        module.process_segments(session, [{"text": "A useful update"}], user)
    )
    print(f"PASS? segment2 -> {r2!r} (expected 'collecting_2')")
    assert r2 == "collecting_2", f"segment 2 returned {r2!r}"
    assert session.get("accumulated_text") == " A useful update", session.get("accumulated_text")

    # A session persisted by the old code with a null accumulator must
    # also keep working (defensive read).
    session_legacy = {
        "session_id": "legacy_sess",
        "tweet_mode": "recording",
        "accumulated_text": None,
        "segments_count": 1,
    }
    r3 = asyncio.run(
        module.process_segments(
            session_legacy, [{"text": "A useful update"}], user
        )
    )
    print(f"PASS? legacy-null session -> {r3!r} (expected 'collecting_2')")
    assert r3 == "collecting_2", f"legacy session returned {r3!r}"

    print("\n4 checks passed")


if __name__ == "__main__":
    run()
