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


class TestStructureFunctionsTimezone:
    def test_get_transcript_structure_passes_local_time(self):
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz="Pacific/Honolulu",
            uid="u1",
        )
        # 1:48 PM local, not 23:48 UTC — this is the value the model sees.
        assert result["invoke"]["started_at"] == "2025-01-01T13:48:00"
        assert result["invoke"]["tz"] == "Pacific/Honolulu"

    def test_get_transcript_structure_none_tz_labels_utc(self):
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz=None,
            uid="u1",
        )
        assert result["invoke"]["started_at"] == "2025-01-01T23:48:00"
        # The prompt must never say the timezone is "None".
        assert result["invoke"]["tz"] == "UTC"

    def test_get_transcript_structure_dst_offset(self):
        # America/New_York in July is EDT (UTC-4): 12:00 UTC -> 08:00 local end to end.
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Morning standup",
            started_at=datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc),
            language_code="en",
            tz="America/New_York",
            uid="u1",
        )
        assert result["invoke"]["started_at"] == "2025-07-01T08:00:00"
        assert result["invoke"]["tz"] == "America/New_York"

    def test_get_reprocess_transcript_structure_passes_local_time(self):
        result = _capture_structure(
            conv_proc.get_reprocess_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz="Pacific/Honolulu",
        )
        assert result["invoke"]["started_at"] == "2025-01-01T13:48:00"
        assert result["invoke"]["tz"] == "Pacific/Honolulu"

    def test_reprocess_regenerates_title_and_emoji_from_current_content(self):
        result = _capture_structure(
            conv_proc.get_reprocess_transcript_structure,
            transcript="The corrected transcript is about a product launch",
            started_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            language_code="en",
            tz="UTC",
        )

        assert "generate a concise title from the current content" in result["system_text"]
        assert "select a single emoji" in result["system_text"]
        assert "For the title, use" not in result["system_text"]
        assert "title" not in result["invoke"]

    def test_both_prompts_state_local_and_drop_convert_instruction(self):
        # The semantic core of the fix is the prompt wording; pin it so a revert can't pass silently.
        for fn, kwargs in [
            (
                conv_proc.get_transcript_structure,
                dict(transcript="x", language_code="en", tz="Pacific/Honolulu", uid="u1"),
            ),
            (
                conv_proc.get_reprocess_transcript_structure,
                dict(transcript="x", language_code="en", tz="Pacific/Honolulu"),
            ),
        ]:
            result = _capture_structure(fn, started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), **kwargs)
            text = result["system_text"]
            assert "already the user's local time" in text
            assert "do not re-interpret this timestamp as UTC" in text
            # The old buggy instruction asking the model to convert must be gone.
            assert "respond in user local timezone" not in text


def test_gpt56_cache_keys_are_stable_versioned_and_never_include_request_content():
    assert conv_proc.TRANSCRIPT_STRUCTURE_CACHE_KEY == 'omi-transcript-structure-v1'
    assert conv_proc.ACTION_ITEMS_CACHE_KEY == 'omi-extract-actions-v1'
    assert conv_proc._has_gpt56_cacheable_static_prefix('static ' * 1_100)
    assert not conv_proc._has_gpt56_cacheable_static_prefix('short prefix')


def test_gpt56_explicit_cache_defaults_on_in_gateway_and_honors_kill_switch(monkeypatch):
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.delenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    assert conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'false')
    assert not conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'true')
    assert conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: False)
    assert not conv_proc._gpt56_explicit_cache_enabled()


def test_unique_prompt_routes_drop_legacy_cache_key_whenever_gateway_mode_is_on(monkeypatch):
    """Regression (cubic review): the None/legacy cache_key split keys on gateway mode.

    get_reprocess_transcript_structure and get_app_result have no cacheable
    static prefix. With the gateway on they must still pass cache_key=None: a legacy
    prompt_cache_key would opt these unique-prompt requests back into
    implicit, billable cache writes. The explicit cache kill switch is set
    below to verify the old fully-disabled behavior remains available.
    """
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'false')

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
    ) as mock_prompt_cls, patch.object(conv_proc, '_build_conversation_context', return_value='ctx'):
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=_Chain(_LLM()))
        mock_prompt_cls.from_messages.return_value = mock_prompt
        conv_proc.get_reprocess_transcript_structure(
            transcript='Lunch meeting',
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code='en',
            tz='UTC',
        )
        assert captured['cache_key'] is None
        assert captured['prompt_cache_options'] is None

        captured.clear()
        app = MagicMock()
        app.name = 'Test App'
        app.description = 'desc'
        app.memory_prompt = 'memory prompt'
        conv_proc.get_app_result(transcript='Lunch meeting', photos=[], app=app, language_code='en')
        assert captured['cache_key'] is None
        assert captured['prompt_cache_options'] is None
