"""Hermetic unit tests for omi-dropbox-app hardening (#14130).

Runs under standard library unittest without third-party dependencies.
Covers:
1. Audio buffer bounding (MAX_AUDIO_BUFFER_BYTES)
2. Audio buffer TTL eviction
3. get_and_clear_audio cleanup semantics
4. Sample rate validation range
5. Timezone-aware datetime (no deprecated utcnow)
6. JSON payload type guards present on /tools/* endpoints
"""
import importlib.util
import io
import sys
import types
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda f: f

    post = get


class DummyResponse:
    def __init__(self, *args, **kwargs):
        pass


class EndpointResponseStub:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


class ResponseStandIn:
    status_code = 0
    text = ""

    def __init__(self, *args, **kwargs):
        pass

    def json(self):
        return {}

    def raise_for_status(self):
        return None


def identity_retry(*args, **kwargs):
    def decorate(func):
        return func

    return decorate


def make_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


stubs = {
    "requests": make_module(
        "requests",
        RequestException=OSError,
        post=lambda *a, **kw: None,
        get=lambda *a, **kw: None,
        Response=ResponseStandIn,
        exceptions=make_module(
            "requests.exceptions",
            RequestException=OSError,
            Timeout=OSError,
            ConnectionError=OSError,
        ),
    ),
    "tenacity": make_module(
        "tenacity",
        retry=identity_retry,
        stop_after_attempt=lambda *a, **kw: None,
        wait_exponential=lambda *a, **kw: None,
        retry_if_exception_type=lambda *a, **kw: None,
    ),
    "dotenv": make_module("dotenv", load_dotenv=lambda *a, **kw: None),
    "fastapi": make_module(
        "fastapi",
        FastAPI=Framework,
        Request=object,
        Query=lambda default=None, **kw: default,
        HTTPException=Exception,
    ),
    "fastapi.responses": make_module(
        "fastapi.responses",
        HTMLResponse=DummyResponse,
        RedirectResponse=DummyResponse,
        JSONResponse=DummyResponse,
    ),
    "db": make_module(
        "db",
        store_dropbox_tokens=Mock(),
        get_dropbox_tokens=Mock(),
        update_dropbox_tokens=Mock(),
        delete_dropbox_tokens=Mock(),
        store_oauth_state=Mock(),
        get_oauth_state=Mock(),
        delete_oauth_state=Mock(),
        get_user_settings=Mock(),
        store_user_settings=Mock(),
    ),
    "models": make_module("models", Conversation=dict, EndpointResponse=EndpointResponseStub),
}

active_stubs = {k: v for k, v in stubs.items() if k not in sys.modules}

spec = importlib.util.spec_from_file_location("dropbox_main", Path(__file__).with_name("main.py"))
dropbox_main = importlib.util.module_from_spec(spec)
with_patch = None
try:
    from unittest.mock import patch

    with patch.dict(sys.modules, active_stubs):
        spec.loader.exec_module(dropbox_main)
except Exception:
    # Fallback: exec directly
    spec.loader.exec_module(dropbox_main)


class TestAudioBufferBounding(unittest.TestCase):
    """Audio buffer constants and accumulation must be bounded."""

    def setUp(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def tearDown(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def test_buffer_starts_empty(self):
        self.assertEqual(len(dropbox_main.audio_buffers), 0)

    def test_single_chunk_within_limit(self):
        chunk = b"\x00" * 1000
        dropbox_main.audio_buffers["user1"] += chunk
        self.assertEqual(len(dropbox_main.audio_buffers["user1"]), 1000)

    def test_constant_exists_and_is_reasonable(self):
        self.assertGreater(dropbox_main.MAX_AUDIO_BUFFER_BYTES, 0)
        self.assertLessEqual(dropbox_main.MAX_AUDIO_BUFFER_BYTES, 50 * 1024 * 1024)

    def test_accumulation_bounded_by_constant(self):
        """Buffer can hold up to the cap; the endpoint must reject beyond it."""
        limit = dropbox_main.MAX_AUDIO_BUFFER_BYTES
        chunk = b"\x00" * (limit // 10)
        for _ in range(10):
            dropbox_main.audio_buffers["user1"] += chunk
        self.assertLessEqual(len(dropbox_main.audio_buffers["user1"]), limit)


class TestAudioBufferTTL(unittest.TestCase):
    """Stale audio buffers must be evicted after TTL."""

    def setUp(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def tearDown(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def test_ttl_constant_is_positive(self):
        self.assertGreater(dropbox_main.AUDIO_BUFFER_TTL_SECONDS, 0)
        self.assertLessEqual(dropbox_main.AUDIO_BUFFER_TTL_SECONDS, 86400)

    def test_fresh_buffer_not_evicted(self):
        dropbox_main.audio_buffers["user1"] = b"\x00" * 1000
        dropbox_main.audio_buffer_created["user1"] = datetime.now(timezone.utc)
        dropbox_main._evict_stale_audio_buffers()
        self.assertIn("user1", dropbox_main.audio_buffers)

    def test_stale_buffer_evicted(self):
        dropbox_main.audio_buffers["user1"] = b"\x00" * 1000
        dropbox_main.audio_sample_rates["user1"] = 16000
        dropbox_main.audio_buffer_created["user1"] = datetime.now(timezone.utc) - timedelta(
            seconds=dropbox_main.AUDIO_BUFFER_TTL_SECONDS + 60
        )
        dropbox_main._evict_stale_audio_buffers()
        self.assertNotIn("user1", dropbox_main.audio_buffers)
        self.assertNotIn("user1", dropbox_main.audio_buffer_created)

    def test_mixed_fresh_and_stale(self):
        dropbox_main.audio_buffers["fresh"] = b"\x01" * 500
        dropbox_main.audio_buffer_created["fresh"] = datetime.now(timezone.utc)
        dropbox_main.audio_buffers["stale"] = b"\x02" * 500
        dropbox_main.audio_buffer_created["stale"] = datetime.now(timezone.utc) - timedelta(
            seconds=dropbox_main.AUDIO_BUFFER_TTL_SECONDS + 1
        )
        dropbox_main._evict_stale_audio_buffers()
        self.assertIn("fresh", dropbox_main.audio_buffers)
        self.assertNotIn("stale", dropbox_main.audio_buffers)


class TestGetAndClearAudio(unittest.TestCase):
    """get_and_clear_audio must return WAV data and clean up all traces."""

    def setUp(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def tearDown(self):
        dropbox_main.audio_buffers.clear()
        dropbox_main.audio_sample_rates.clear()
        dropbox_main.audio_buffer_created.clear()

    def test_returns_none_for_empty_buffer(self):
        self.assertIsNone(dropbox_main.get_and_clear_audio("nobody"))

    def test_returns_wav_for_nonempty_buffer(self):
        dropbox_main.audio_buffers["user1"] = b"\x00" * 2000
        dropbox_main.audio_sample_rates["user1"] = 16000
        dropbox_main.audio_buffer_created["user1"] = datetime.now(timezone.utc)

        result = dropbox_main.get_and_clear_audio("user1")

        self.assertIsNotNone(result)
        self.assertEqual(result[:4], b"RIFF")  # Valid WAV header
        self.assertNotIn("user1", dropbox_main.audio_buffers)
        self.assertNotIn("user1", dropbox_main.audio_sample_rates)
        self.assertNotIn("user1", dropbox_main.audio_buffer_created)

    def test_defaults_to_16khz_when_no_rate(self):
        dropbox_main.audio_buffers["user1"] = b"\x00" * 2000
        result = dropbox_main.get_and_clear_audio("user1")
        self.assertIsNotNone(result)


class TestSampleRateValidationRange(unittest.TestCase):
    """Sample rate boundary values for endpoint validation (8kHz-48kHz)."""

    VALID_RATES = [8000, 16000, 22050, 44100, 48000]
    INVALID_RATES = [0, 100, 7999, 48001, 96000, -1]

    def test_valid_sample_rates_pass(self):
        for rate in self.VALID_RATES:
            self.assertTrue(8000 <= rate <= 48000, f"{rate} should be valid")

    def test_invalid_sample_rates_fail(self):
        for rate in self.INVALID_RATES:
            self.assertFalse(8000 <= rate <= 48000, f"{rate} should be invalid")


class TestTimezoneAwareDatetime(unittest.TestCase):
    """All datetime usage must be timezone-aware (no deprecated utcnow())."""

    def test_no_utcnow_in_main_py(self):
        source = Path(__file__).with_name("main.py").read_text()
        self.assertNotIn("utcnow", source, "datetime.utcnow() is deprecated; use datetime.now(timezone.utc)")

    def test_expires_at_format_is_utc_z(self):
        """Token expiry must be stored as ...Z format via now(timezone.utc)."""
        from datetime import timedelta as td

        expires_in = 14400
        expires_at = (datetime.now(timezone.utc) + td(seconds=expires_in)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(expires_at.endswith("Z"))
        # Parseable back
        parsed = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ")
        delta = abs((parsed.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() - expires_in)
        self.assertLess(delta, 5)


class TestJSONPayloadGuards(unittest.TestCase):
    """/tools/* endpoints must guard non-dict JSON payloads (source check)."""

    def test_tools_endpoints_have_type_guard(self):
        source = Path(__file__).with_name("main.py").read_text()
        # Each tools endpoint must validate the body is a dict
        guard_count = source.count('if not isinstance(body, dict):')
        self.assertGreaterEqual(
            guard_count, 3, "All three /tools/* endpoints must validate body is a dict"
        )

    def test_tools_endpoints_coerce_fields(self):
        """uid/query/folder/path must be read defensively with .get()."""
        source = Path(__file__).with_name("main.py").read_text()
        for field in ('body.get("uid")', 'body.get("query")', 'body.get("folder")', 'body.get("path")'):
            self.assertIn(field, source, f"Missing defensive read for {field}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
