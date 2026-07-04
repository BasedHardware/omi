"""Unit tests for the TTS proxy (/v2/tts/synthesize).

Covers input validation (voice_id, text length, empty text) by importing the
pure helpers directly — mirrors the test pattern used by the sibling Rust
implementation in desktop/macos/Backend-Rust/src/routes/tts.rs.

End-to-end wiring (Redis rate-limit + ElevenLabs upstream) is exercised via
integration tests — the unit layer here is intentionally scoped to the bits
that are easy to regress by accident when someone edits the router.
"""

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models.tts import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    TtsSynthesizeRequest,
)
from routers import tts as tts_router


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
    assert DEFAULT_VOICE_ID == "BAMYoBHLZM7lJgJAmFz0"


def test_default_model_id():
    assert DEFAULT_MODEL_ID == "eleven_turbo_v2_5"


def test_default_output_format():
    assert DEFAULT_OUTPUT_FORMAT == "mp3_44100_128"


def test_request_model_applies_defaults():
    req = TtsSynthesizeRequest(text="hello")
    assert req.text == "hello"
    assert req.voice_id == "BAMYoBHLZM7lJgJAmFz0"
    assert req.model_id == "eleven_turbo_v2_5"
    assert req.output_format == "mp3_44100_128"
    assert req.voice_settings is None


def test_request_model_rejects_empty_text():
    with pytest.raises(ValidationError):
        TtsSynthesizeRequest(text="")


# ---------------------------------------------------------------------------
# /v2/tts/voices helpers
# ---------------------------------------------------------------------------
def test_normalize_voices_maps_fields():
    raw = {
        "voices": [
            {
                "voice_id": "v1",
                "name": "Sloane",
                "category": "premade",
                "preview_url": "http://p",
                "labels": {"accent": "american"},
            }
        ]
    }
    assert tts_router._normalize_voices(raw) == [
        {
            "voice_id": "v1",
            "name": "Sloane",
            "category": "premade",
            "preview_url": "http://p",
            "labels": {"accent": "american"},
        }
    ]


def test_normalize_voices_defaults_missing_fields():
    assert tts_router._normalize_voices({"voices": [{"voice_id": "v1"}]}) == [
        {"voice_id": "v1", "name": None, "category": None, "preview_url": None, "labels": {}}
    ]


def test_normalize_voices_empty_or_non_list():
    assert tts_router._normalize_voices({"voices": []}) == []
    assert tts_router._normalize_voices({}) == []
    assert tts_router._normalize_voices({"voices": "not-a-list"}) == []
    assert tts_router._normalize_voices("not-a-dict") == []


def test_normalize_voices_skips_bad_entries():
    raw = {
        "voices": [
            {"voice_id": "v1", "name": "Ok"},
            "not-a-dict",
            {"name": "no-id"},
            {"voice_id": "", "name": "empty-id"},
        ]
    }
    assert [v["voice_id"] for v in tts_router._normalize_voices(raw)] == ["v1"]


def test_normalize_voices_non_dict_labels_defaulted():
    result = tts_router._normalize_voices({"voices": [{"voice_id": "v1", "labels": "bad"}]})
    assert result[0]["labels"] == {}


def test_is_cache_fresh_boundary():
    ttl = tts_router._VOICES_CACHE_TTL_SECS
    assert tts_router._is_cache_fresh(100.0, 100.0)  # same instant is fresh
    assert tts_router._is_cache_fresh(100.0, 100.0 + ttl - 1)
    assert not tts_router._is_cache_fresh(100.0, 100.0 + ttl)  # boundary: expired
    assert not tts_router._is_cache_fresh(100.0, 100.0 + ttl + 10)


def test_voices_constants():
    assert tts_router._ELEVENLABS_VOICES_URL == "https://api.elevenlabs.io/v1/voices"
    assert tts_router._VOICES_CACHE_TTL_SECS == 3600


# ---------------------------------------------------------------------------
# get_voices upstream-error contract (async handler)
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status_code, json_exc=None, json_val=None):
        self.status_code = status_code
        self._json_exc = json_exc
        self._json_val = json_val

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_val


class _FakeSemaphore:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def get(self, *args, **kwargs):
        return self._resp


def _wire_upstream(monkeypatch, resp):
    tts_router._voices_cache = None
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(tts_router, "get_tts_semaphore", lambda: _FakeSemaphore())
    monkeypatch.setattr(tts_router, "get_tts_client", lambda: _FakeClient(resp))


def test_get_voices_502_on_non_json_body(monkeypatch):
    # 200 OK but a non-JSON body must map to 502, not bubble up as a 500.
    _wire_upstream(monkeypatch, _FakeResp(200, json_exc=ValueError("not json")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tts_router.get_voices(uid="u1"))
    assert exc.value.status_code == 502


def test_get_voices_502_on_upstream_non_200(monkeypatch):
    _wire_upstream(monkeypatch, _FakeResp(500))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tts_router.get_voices(uid="u1"))
    assert exc.value.status_code == 502


def test_get_voices_success_normalizes_and_caches(monkeypatch):
    _wire_upstream(monkeypatch, _FakeResp(200, json_val={"voices": [{"voice_id": "v1", "name": "Sloane"}]}))
    result = asyncio.run(tts_router.get_voices(uid="u1"))
    assert result == {
        "voices": [{"voice_id": "v1", "name": "Sloane", "category": None, "preview_url": None, "labels": {}}]
    }
    assert tts_router._voices_cache is not None and tts_router._voices_cache[1] == result["voices"]
    tts_router._voices_cache = None  # reset shared module cache for later tests


def test_get_voices_503_when_unconfigured(monkeypatch):
    tts_router._voices_cache = None
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tts_router.get_voices(uid="u1"))
    assert exc.value.status_code == 503
