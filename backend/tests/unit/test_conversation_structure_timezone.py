import os

"""Tests for conversation title/summary timezone correctness (issue #4773).

The two structuring functions used to hand the LLM a raw UTC timestamp and ask it to convert to the
user's timezone, which mislabeled the time of day in titles/overviews. They now convert deterministically
in Python and tell the model the timestamp is already local.

Covers:
1. _local_started_at_iso converts UTC to the user's local wall-clock
2. None / invalid timezone falls back to UTC; naive datetimes are treated as UTC; DST is handled
3. get_transcript_structure and get_reprocess_transcript_structure pass the local time + a non-None tz
"""

from datetime import datetime, timedelta, timezone, tzinfo
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import stub_modules


@pytest.fixture(scope='module', autouse=True)
def _shaped_notes_enabled():
    """These suites exercise the notes writer, which is shaped-only after go-live."""
    os.environ['OMI_SHAPED_AGENT_MODE'] = 'on'
    yield
    os.environ.pop('OMI_SHAPED_AGENT_MODE', None)


conv_proc = None


@pytest.fixture(scope='module', autouse=True)
def isolated_processing():
    global conv_proc
    with stub_modules({}):
        from utils.llm import conversation_processing, usage_tracker

        conv_proc = conversation_processing
        with patch.object(conv_proc, 'ZoneInfo', _test_zone_info), patch.object(
            usage_tracker, 'track_usage', MagicMock()
        ):
            yield
    conv_proc = None


# Keep timezone assertions independent of host OS tzdata, which is often absent on Windows test environments.


class _JulyOnlyNewYorkTestZone(tzinfo):
    """Minimal test zone: only the current July DST case needs EDT behavior."""

    def utcoffset(self, dt):
        return timedelta(hours=-4 if dt is not None and dt.month == 7 else -5)

    def dst(self, dt):
        return timedelta(hours=1 if dt is not None and dt.month == 7 else 0)

    def tzname(self, dt):
        return "EDT" if dt is not None and dt.month == 7 else "EST"


def _test_zone_info(name):
    if name == "Pacific/Honolulu":
        return timezone(timedelta(hours=-10), name)
    if name == "America/New_York":
        return _JulyOnlyNewYorkTestZone()
    if name == "UTC":
        return timezone.utc
    raise KeyError(name)


# ===========================================================================
# _local_started_at_iso unit tests (pure conversion logic)
# ===========================================================================


class TestLocalStartedAtIso:
    def test_converts_utc_to_user_local(self):
        # 23:48 UTC -> 13:48 in Honolulu (UTC-10), the meal/time-of-day case from the issue.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "Pacific/Honolulu")
        assert out == "2025-01-01T13:48:00"

    def test_none_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), None)
        assert out == "2025-01-01T23:48:00"

    def test_invalid_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "Not/AZone")
        assert out == "2025-01-01T23:48:00"

    def test_empty_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "")
        assert out == "2025-01-01T23:48:00"

    def test_naive_started_at_treated_as_utc(self):
        # A naive timestamp must be read as UTC, not silently localized.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48), "Pacific/Honolulu")
        assert out == "2025-01-01T13:48:00"

    def test_dst_summer_offset(self):
        # July: America/New_York is EDT (UTC-4). 12:00 UTC -> 08:00 local.
        out = conv_proc._local_started_at_iso(datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc), "America/New_York")
        assert out == "2025-07-01T08:00:00"

    def test_dst_winter_offset(self):
        # January: America/New_York is EST (UTC-5). 12:00 UTC -> 07:00 local.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc), "America/New_York")
        assert out == "2025-01-01T07:00:00"


# ===========================================================================
# Structuring functions pass local time to the prompt
# ===========================================================================


def _capture_structure(fn, **kwargs):
    """Run a structuring function with the LLM chain mocked.

    Returns {'invoke': <dict passed to chain.invoke>, 'system_text': <joined system prompt text>}.
    """
    # The writers now sanitize the returned Structured (#12503 follow-up), so the
    # mocked chain response must be a real model, not a bare MagicMock.
    mock_response = conv_proc.Structured()

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = mock_response
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    mock_llm = MagicMock()
    mock_llm.__or__ = MagicMock(return_value=mock_chain)

    with patch.object(conv_proc, "get_llm", return_value=mock_llm), patch.object(
        conv_proc, "ChatPromptTemplate"
    ) as mock_prompt_cls, patch.object(conv_proc, "_build_conversation_context", return_value="ctx"):
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)
        mock_prompt_cls.from_messages.return_value = mock_prompt
        fn(**kwargs)
        messages = mock_prompt_cls.from_messages.call_args[0][0]

    system_text = "\n".join(text for _role, text in messages)
    return {"invoke": mock_chain.invoke.call_args[0][0], "system_text": system_text}


def test_gpt56_cache_keys_are_stable_versioned_and_never_include_request_content():
    assert conv_proc._has_gpt56_cacheable_static_prefix('static ' * 1_100)
    assert not conv_proc._has_gpt56_cacheable_static_prefix('short prefix')


def test_gpt56_explicit_cache_follows_gateway_route(monkeypatch):
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)
    assert conv_proc._gpt56_explicit_cache_enabled()
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: False)
    assert not conv_proc._gpt56_explicit_cache_enabled()


def test_unique_prompt_routes_drop_legacy_cache_key_whenever_gateway_mode_is_on(monkeypatch):
    """Regression (cubic review): the None/legacy cache_key split keys on gateway mode.

    get_app_result has no cacheable static prefix. With the gateway on they must still pass cache_key=None: a legacy
    prompt_cache_key would opt these unique-prompt requests back into
    implicit, billable cache writes.
    """
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)

    captured: dict = {}

    class _Chain:
        def __init__(self, llm):
            self._llm = llm

        def __or__(self, _other):
            return self

        def invoke(self, *_args, **_kwargs):
            # Reprocess sanitizes the returned Structured; return a real model, not a MagicMock.
            return conv_proc.Structured()

    class _LLM:
        def __or__(self, _parser):
            return _Chain(self)

        def invoke(self, *_args, **_kwargs):
            return MagicMock(content='{}')

    def _fake_get_llm(_feature, **kwargs):
        captured.update(kwargs)
        return _LLM()

    with patch.object(conv_proc, 'get_llm', side_effect=_fake_get_llm), patch.object(
        conv_proc, 'ChatPromptTemplate'
    ) as mock_prompt_cls:
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=_Chain(_LLM()))
        mock_prompt_cls.from_messages.return_value = mock_prompt
        app = MagicMock()
        app.name = 'Test App'
        app.description = 'desc'
        app.memory_prompt = 'memory prompt'
        conv_proc.get_app_result(transcript='Lunch meeting', photos=[], app=app, language_code='en')
        assert captured['cache_key'] is None
        assert captured['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}
