"""Unit tests for timezone-aware daily TTS rate limiting.

Verifies:
1. _get_daily_bucket_and_ttl computes local date and TTL until local midnight
   for non-UTC timezones (e.g. Asia/Tokyo UTC+9, America/Los_Angeles UTC-8).
2. Fallback to UTC occurs cleanly when user_tz is None, empty, or invalid.
3. check_tts_rate_limit passes local daily keys and TTL into Lua script.
4. tts_synthesize passes user_tz from user settings into check_tts_rate_limit.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

from database import redis_db
from models.tts import TtsSynthesizeRequest
from routers import tts as tts_router


def test_get_daily_bucket_and_ttl_utc():
    date_str, ttl = redis_db._get_daily_bucket_and_ttl(None)
    now_utc = datetime.now(timezone.utc)
    assert date_str == now_utc.strftime("%Y%m%d")
    assert 0 < ttl <= 86400


def test_get_daily_bucket_and_ttl_invalid_fallback_to_utc():
    date_str, ttl = redis_db._get_daily_bucket_and_ttl("Invalid/TimeZone")
    now_utc = datetime.now(timezone.utc)
    assert date_str == now_utc.strftime("%Y%m%d")
    assert 0 < ttl <= 86400


def test_get_daily_bucket_and_ttl_timezones():
    tokyo_date, tokyo_ttl = redis_db._get_daily_bucket_and_ttl("Asia/Tokyo")
    tokyo_now = datetime.now(ZoneInfo("Asia/Tokyo"))
    assert tokyo_date == tokyo_now.strftime("%Y%m%d")
    assert 0 < tokyo_ttl <= 86400

    la_date, la_ttl = redis_db._get_daily_bucket_and_ttl("America/Los_Angeles")
    la_now = datetime.now(ZoneInfo("America/Los_Angeles"))
    assert la_date == la_now.strftime("%Y%m%d")
    assert 0 < la_ttl <= 86400


def test_check_tts_rate_limit_passes_timezone_bucket():
    mock_lua = MagicMock(return_value=[0, 0])
    with patch.object(redis_db, "_TTS_RATE_LIMIT_LUA", mock_lua):
        status, retry_after = redis_db.check_tts_rate_limit(
            uid="user123",
            char_count=100,
            user_tz="Asia/Tokyo",
        )
        assert status == 0
        assert retry_after == 0

        call_kwargs = mock_lua.call_args.kwargs
        keys = call_kwargs["keys"]
        args = call_kwargs["args"]

        tokyo_today = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
        assert keys[0] == "tts:burst:user123"
        assert keys[1] == f"tts:chars:user123:{tokyo_today}"
        assert args[3] == 100  # char_count
        assert 0 < args[5] <= 86400  # daily_ttl


@pytest.mark.asyncio
async def test_tts_synthesize_passes_user_tz(monkeypatch):
    captured_kwargs = {}

    async def mock_run_blocking(executor, fn, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return 0, 0

    async def mock_open_stream(**kwargs):
        async def _chunks():
            yield b"data"

        return _chunks()

    monkeypatch.setattr(tts_router, "run_blocking", mock_run_blocking)
    monkeypatch.setattr(tts_router, "_get_user_time_zone", lambda uid: "Asia/Tokyo")
    monkeypatch.setattr(tts_router, "get_tts_provider", lambda: "gemini")
    monkeypatch.setattr(tts_router, "open_gemini_mp3_stream", mock_open_stream)

    req = TtsSynthesizeRequest(text="Hello world")
    await tts_router.tts_synthesize(req, uid="user123")

    assert captured_kwargs.get("user_tz") == "Asia/Tokyo"
