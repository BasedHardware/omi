"""Unit tests for the TTS proxy (/v2/tts/synthesize).

Covers input validation (voice_id, text length, empty text) by importing the
pure helpers directly — mirrors the test pattern used by the sibling Rust
implementation in desktop/Backend-Rust/src/routes/tts.rs.

End-to-end wiring (Redis rate-limit + ElevenLabs upstream) is exercised via
integration tests — the unit layer here is intentionally scoped to the bits
that are easy to regress by accident when someone edits the router.
"""

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stub heavy deps pulled in transitively by routers.tts → database.redis_db
# ---------------------------------------------------------------------------
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.credentials",
]:
    _stub_package(mod_name) if "." not in mod_name else _stub_module(mod_name)

redis_stub = _stub_module("redis")
redis_stub.Redis = MagicMock(return_value=MagicMock())


def _load_tts_router_module():
    """Load routers/tts.py while stubbing its heavy collaborators."""
    # Stub the auth dependency chain so importing the router doesn't explode
    endpoints_stub = types.ModuleType("utils.other.endpoints")

    def _fake_dep_factory():
        async def _dep():
            return "test-uid"

        return _dep

    endpoints_stub.get_current_user_uid = _fake_dep_factory()
    endpoints_stub.with_rate_limit = lambda _auth, _policy: _fake_dep_factory()
    sys.modules["utils.other.endpoints"] = endpoints_stub

    # Stub redis_db helpers
    redis_db_stub = types.ModuleType("database.redis_db")
    redis_db_stub.check_tts_rate_limit = MagicMock(return_value=(0, 0))
    sys.modules["database.redis_db"] = redis_db_stub
    sys.modules.setdefault("database", _stub_package("database"))
    sys.modules["database"].redis_db = redis_db_stub

    # Stub http_client
    http_client_stub = types.ModuleType("utils.http_client")
    http_client_stub.get_tts_client = MagicMock()
    http_client_stub.get_tts_semaphore = MagicMock()
    sys.modules["utils.http_client"] = http_client_stub

    # Stub log_sanitizer
    log_sanitizer_stub = types.ModuleType("utils.log_sanitizer")
    log_sanitizer_stub.sanitize = lambda s: str(s)
    sys.modules["utils.log_sanitizer"] = log_sanitizer_stub

    # Stub models.tts (real module is safe — pure pydantic)
    sys.path.insert(0, str(BACKEND_DIR))

    spec = importlib.util.spec_from_file_location(
        "routers.tts",
        str(BACKEND_DIR / "routers" / "tts.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["routers.tts"] = mod
    spec.loader.exec_module(mod)
    return mod


tts_router = _load_tts_router_module()


# ---------------------------------------------------------------------------
# voice_id validation
# ---------------------------------------------------------------------------
def test_valid_voice_id_alphanumeric():
    assert tts_router._is_valid_voice_id("BAMYoBHLZM7lJgJAmFz0")
    assert tts_router._is_valid_voice_id("abc123")
    assert tts_router._is_valid_voice_id("A")


def test_reject_voice_id_path_traversal():
    assert not tts_router._is_valid_voice_id("../../history")
    assert not tts_router._is_valid_voice_id("../v1/voices")
    assert not tts_router._is_valid_voice_id("foo/bar")


def test_reject_voice_id_special_chars():
    assert not tts_router._is_valid_voice_id("id-with-dash")
    assert not tts_router._is_valid_voice_id("id_with_underscore")
    assert not tts_router._is_valid_voice_id("id with space")
    assert not tts_router._is_valid_voice_id("id?query=1")


def test_reject_voice_id_empty():
    assert not tts_router._is_valid_voice_id("")


def test_voice_id_length_boundaries():
    assert tts_router._is_valid_voice_id("a" * 128)
    assert not tts_router._is_valid_voice_id("a" * 129)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
def test_burst_limit_matches_desktop():
    assert tts_router._TTS_BURST_PER_MINUTE == 50


def test_daily_char_limit_matches_desktop():
    assert tts_router._TTS_DAILY_CHAR_LIMIT == 10_000


def test_request_char_limit_matches_desktop():
    assert tts_router._TTS_REQUEST_CHAR_LIMIT == 5_000


def test_burst_window_matches_desktop():
    assert tts_router._TTS_BURST_WINDOW_SECS == 60


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------
def test_default_voice_id_is_sloane():
    from models.tts import DEFAULT_VOICE_ID

    assert DEFAULT_VOICE_ID == "BAMYoBHLZM7lJgJAmFz0"


def test_default_model_id():
    from models.tts import DEFAULT_MODEL_ID

    assert DEFAULT_MODEL_ID == "eleven_turbo_v2_5"


def test_default_output_format():
    from models.tts import DEFAULT_OUTPUT_FORMAT

    assert DEFAULT_OUTPUT_FORMAT == "mp3_44100_128"


def test_request_model_applies_defaults():
    from models.tts import TtsSynthesizeRequest

    req = TtsSynthesizeRequest(text="hello")
    assert req.text == "hello"
    assert req.voice_id == "BAMYoBHLZM7lJgJAmFz0"
    assert req.model_id == "eleven_turbo_v2_5"
    assert req.output_format == "mp3_44100_128"
    assert req.voice_settings is None


def test_request_model_rejects_empty_text():
    from pydantic import ValidationError

    from models.tts import TtsSynthesizeRequest

    with pytest.raises(ValidationError):
        TtsSynthesizeRequest(text="")
