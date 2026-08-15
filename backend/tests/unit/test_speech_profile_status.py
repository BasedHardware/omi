"""Unit tests for GET /v3/speech-profile/status and get_speech_profile_duration.

The redis getter is verified directly. The router endpoint (routers.speech_profile imports
PyAV via `av`) runs in CI; locally `av` is absent so those cases skip. Uses the sanctioned
seams (import + patch.object, no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest

import database.redis_db as rd

try:
    from routers import speech_profile as sp_router

    _SP_IMPORTABLE = True
except Exception:  # PyAV (av) unavailable locally; present in CI
    sp_router = None
    _SP_IMPORTABLE = False


# ---------------------------------------------------------------------------
# redis getter: get_speech_profile_duration
# ---------------------------------------------------------------------------
def test_getter_parses_bytes_value():
    with patch.object(rd, "r") as r:
        r.get.return_value = b"42.5"
        assert rd.get_speech_profile_duration("u1") == 42.5
    assert r.get.call_args[0][0] == "users:u1:speech_profile_duration"


def test_getter_parses_str_value():
    with patch.object(rd, "r") as r:
        r.get.return_value = "7"
        assert rd.get_speech_profile_duration("u1") == 7.0


def test_getter_unset_returns_zero():
    with patch.object(rd, "r") as r:
        r.get.return_value = None
        assert rd.get_speech_profile_duration("u1") == 0.0


def test_getter_fail_open_returns_none():
    # try_catch_decorator swallows the error and returns None; the endpoint coerces it to 0.0.
    with patch.object(rd, "r") as r:
        r.get.side_effect = RuntimeError("redis down")
        assert rd.get_speech_profile_duration("u1") is None


# ---------------------------------------------------------------------------
# router endpoint (runs in CI where routers.speech_profile imports)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_endpoint_full_status():
    with patch.object(sp_router, "get_user_has_speech_profile", return_value=True), patch.object(
        sp_router, "get_speech_profile_duration", return_value=42.5
    ), patch.object(sp_router, "get_profile_audio_if_exists", return_value="http://x/p.wav"):
        resp = sp_router.get_speech_profile_status(uid="u1")
    assert resp == {"has_profile": True, "duration_seconds": 42.5, "url": "http://x/p.wav"}


@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_endpoint_coerces_none_duration_to_zero():
    with patch.object(sp_router, "get_user_has_speech_profile", return_value=False), patch.object(
        sp_router, "get_speech_profile_duration", return_value=None
    ), patch.object(sp_router, "get_profile_audio_if_exists", return_value=None):
        resp = sp_router.get_speech_profile_status(uid="u1")
    assert resp["duration_seconds"] == 0.0
    assert resp["has_profile"] is False
    assert resp["url"] is None


@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_endpoint_zeroes_stale_duration_when_no_profile():
    # Write-ahead cache can outlive a deleted profile: has_profile False must not report a
    # positive duration (the inconsistent state David flagged).
    with patch.object(sp_router, "get_user_has_speech_profile", return_value=False), patch.object(
        sp_router, "get_speech_profile_duration", return_value=42.5
    ), patch.object(sp_router, "get_profile_audio_if_exists", return_value=None):
        resp = sp_router.get_speech_profile_status(uid="u1")
    assert resp["has_profile"] is False
    assert resp["duration_seconds"] == 0.0  # not the stale 42.5
