"""The metadata-extraction fail-soft boundary must name its failures and survive provider blips.

Live prod signature (pusher container, GCP, 2026-10-20/21, x42-69/30m, #4 in
the Loop S feed):

    ERROR:utils.llm.chat:e Request timed out.

The tick-162/164 fix moved the whole-content extractors onto the foreground
deadline, but the boundary that catches a failed extraction still logged the
raw ``f'e {e}'`` line: no exception type (transport exceptions stringify
empty), no path, no uid-bound context — an ERROR record impossible to
attribute or alert on. The same blind spot existed on the message/text
sibling (``Error extracting metadata: {e}``) and on two more fail-soft
catches in the same module (LangSmith prompt fetch, memory-discard topics).
The boundary also treated a transient provider fault as terminal: one
timeout permanently erased that conversation's people/topics/entities/dates
search filters, and the whole silent-degradation class emitted no
``omi_fallback_total`` event, in violation of the repo observability contract
("silent UX healing is allowed; silent ops is not").

Failure-Class: FC-untyped-empty-error-payload-hides-failure-class — a
fail-soft boundary logs the caught exception through ``{e}``, which
stringifies empty for the exact transport faults that dominate the lane, so
the dominant failure class is invisible to attribution and alerting while
the silent empty-filters degrade bypasses the shared fallback counter. Fixed
by a typed, bounded, path-attributed log token, one immediate whole-request
retry for genuinely transient faults, a shared ``omi_fallback_total`` event
for every degrade, and a regression suite that drives the real production
functions against a scripted provider.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-hermetic-tests")

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import httpx
import openai
import pytest

# Import anthropic (which imports jiter) and the observability package BEFORE
# any stub fixture runs — the same import-order traps the sibling deadline
# suites document: jiter's evict/re-import cycle, Prometheus's Duplicated
# timeseries on re-exec, and the google.ai.* proto descriptor pool. The real
# utils.observability.fallback must be the module this suite's production
# code calls, so it joins the restore set, never the eviction set.
import anthropic  # noqa: F401
import langchain_google_genai  # noqa: F401
import utils.observability  # noqa: F401

from testing.import_isolation import load_module_fresh, stub_modules
from utils.metrics import OMI_FALLBACK_TOTAL

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Populated by the autouse ``_load_modules`` fixture before any test runs.
llm_chat = None
model_config = None


def _build_fakes() -> dict[str, ModuleType]:
    """Stub the heavy chat.py dependency chain the sanctioned way."""
    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    database_pkg = ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    add("database", database_pkg)

    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db
    client_mod.get_data_plane_firestore_client = lambda: client_mod.db
    add("database._client", client_mod)

    for name in (
        "database.users",
        "database.notifications",
        "database.goals",
        "database.apps",
        "database.redis_db",
        "database.auth",
    ):
        add(name, MagicMock(name=name))

    usage_tracker_mod = ModuleType("utils.llm.usage_tracker")
    usage_tracker_mod.track_usage = MagicMock(name="track_usage")
    usage_tracker_mod.get_usage_callback = MagicMock(return_value=None)
    usage_tracker_mod.Features = type(
        "Features", (), {"CONVERSATION_PROCESSING": "conversation_processing", "CHAT": "chat"}
    )
    add("utils.llm.usage_tracker", usage_tracker_mod)

    prompt_cache_mod = ModuleType("utils.llm.prompt_cache")
    prompt_cache_mod.with_cache_write_opt_out = lambda runnable: runnable
    add("utils.llm.prompt_cache", prompt_cache_mod)

    temporal_real = _load_real_temporal()
    add("utils.llm.temporal", temporal_real)

    llms_pkg = ModuleType("utils.llms")
    llms_pkg.__path__ = [str(BACKEND_DIR / "utils" / "llms")]
    add("utils.llms", llms_pkg)
    llms_memory = ModuleType("utils.llms.memory")
    llms_memory.get_prompt_memories = MagicMock(return_value="")
    add("utils.llms.memory", llms_memory)

    return fakes


def _load_real_temporal() -> ModuleType:
    """Load the real pure module (date grounding) — it imports no DB layer."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "utils.llm.temporal", str(BACKEND_DIR / "utils" / "llm" / "temporal.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def _load_modules(request):
    """Load utils.llm.chat fresh against the stubbed deps."""
    import utils.llm.model_config as real_model_config

    fakes = _build_fakes()
    with stub_modules(fakes):
        chat = load_module_fresh(
            "utils.llm.chat",
            str(BACKEND_DIR / "utils" / "llm" / "chat.py"),
        )
        request.module.llm_chat = chat
        request.module.model_config = real_model_config
        yield


# ---------------------------------------------------------------------------
# Scripted provider: each get_llm consumer call pops one outcome
# ---------------------------------------------------------------------------


class _Extraction:
    people = ["David"]
    topics = ["running"]
    entities = ["Boston"]
    dates = ["next friday"]


def _api_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://gateway.example.invalid/v1"))


def _api_connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://gateway.example.invalid/v1"))


def _connect_error(message: str = "") -> httpx.ConnectError:
    return httpx.ConnectError(message, request=httpx.Request("POST", "https://gateway.example.invalid/v1"))


class _ScriptedProvider:
    """get_llm stub whose invoke outcomes follow a caller-provided script."""

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def __call__(self, feature, *args, **kwargs):
        self.calls.append(feature)
        return _ScriptedClient(self)

    def invoke_next(self, prompt):
        self.prompts.append(prompt)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _ScriptedClient:
    def __init__(self, provider: _ScriptedProvider):
        self._provider = provider

    def with_structured_output(self, _schema):
        return _ScriptedInvoker(self._provider)


class _ScriptedInvoker:
    def __init__(self, provider: _ScriptedProvider):
        self._provider = provider

    def invoke(self, prompt: str):
        return self._provider.invoke_next(prompt)


@pytest.fixture
def provider():
    """Install the scripted provider as the fresh chat module's get_llm.

    Patch the module object the tests call (the module-global ``llm_chat``),
    NOT a fresh ``import utils.llm.chat`` — the documented combined-run trap.
    """
    scripted = _ScriptedProvider()
    original = llm_chat.get_llm
    llm_chat.get_llm = scripted
    yield scripted
    llm_chat.get_llm = original


@contextmanager
def _captured_filter_writes():
    calls: list = []
    original = llm_chat.add_filter_category_item
    llm_chat.add_filter_category_item = lambda uid, category, value: calls.append((category, value))
    try:
        yield calls
    finally:
        llm_chat.add_filter_category_item = original


@contextmanager
def _counted_usage_tracking():
    calls: list = []

    @contextmanager
    def fake_track_usage(uid, feature):
        calls.append((uid, feature))
        yield

    original = llm_chat.track_usage
    llm_chat.track_usage = fake_track_usage
    try:
        yield calls
    finally:
        llm_chat.track_usage = original


def _fallback_child_value(reason: str) -> float:
    labels = OMI_FALLBACK_TOTAL.labels(
        "conversation_finalization", "metadata_extraction", "empty_filters", reason, "degraded"
    )
    return labels._value.get()


def _transcript_call(uid="uid-meta-boundary"):
    return llm_chat.retrieve_metadata_fields_from_transcript(
        uid=uid,
        created_at=datetime(2026, 10, 21, 12, 0, 0),
        transcript_segment=[{"text": "I went running with David near Boston, we talked about next friday."}],
        tz="UTC",
    )


def _message_call(uid="uid-meta-boundary"):
    return llm_chat.retrieve_metadata_from_message(
        uid,
        datetime(2026, 10, 21, 12, 0, 0),
        "Message from David about running in Boston next friday.",
        "UTC",
        source_spec="telegram",
    )


def _text_call(uid="uid-meta-boundary"):
    return llm_chat.retrieve_metadata_from_text(
        uid,
        datetime(2026, 10, 21, 12, 0, 0),
        "Document text mentioning David and Boston.",
        "UTC",
        source_spec="notion",
    )


_EMPTY = {"people": [], "topics": [], "entities": [], "dates": []}


def _error_records(caplog, needle: str | None = None):
    records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    if needle is not None:
        records = [record for record in records if needle in record.getMessage()]
    return records


# ---------------------------------------------------------------------------
# 1. The typed, attributed log line (the sensor signature class)
# ---------------------------------------------------------------------------


def test_transcript_timeout_logs_the_typed_attributed_line(provider, caplog):
    """Against unmodified source this logs the bare ``e Request timed out.`` line."""
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    errors = _error_records(caplog)
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "metadata extraction failed" in message
    assert "path=transcript" in message
    assert "returning empty filters" in message
    assert "APITimeoutError: Request timed out." in message
    assert not any(record.getMessage().startswith("e ") for record in caplog.records)


def test_empty_stringify_exception_still_names_its_type(provider, caplog):
    """httpx-style exceptions stringify empty; the line must carry the type."""
    provider.outcomes = [_connect_error(""), _connect_error("")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "ConnectError" in message


def test_multiline_exception_message_is_flattened_to_one_line(provider, caplog):
    provider.outcomes = [ValueError("\n".join(f"line {i}" for i in range(50)))]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "\n" not in message


def test_exception_message_is_capped_so_log_lines_stay_bounded(provider, caplog):
    provider.outcomes = [ValueError("x" * 5000)]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert len(message) < 400


def test_message_path_logs_path_message(provider, caplog):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _message_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "path=message" in message
    assert "APITimeoutError" in message


def test_text_path_logs_path_text(provider, caplog):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _text_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "path=text" in message
    assert "APITimeoutError" in message


def test_the_legacy_bare_signature_is_gone_from_source():
    """Source pin: the typo'd f-string and the old sibling text are gone; the
    typed arm exists exactly on the two metadata boundaries."""
    source = (BACKEND_DIR / "utils" / "llm" / "chat.py").read_text()
    assert "f'e {e}'" not in source
    assert "logger.error(f'e " not in source
    assert source.count("metadata extraction failed; returning empty filters") == 2
    assert "Error extracting metadata: {e}" not in source


def test_failure_lines_carry_no_conversation_content(provider, caplog):
    """The token carries the exception, never the prompt payload (privacy)."""
    provider.outcomes = [_api_timeout()]
    transcript_words = "running with David near Boston"
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert transcript_words not in joined


def test_failure_lines_carry_no_uid(provider, caplog):
    provider.outcomes = [_api_timeout()]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call(uid="uid-privacy-probe") == _EMPTY
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "uid-privacy-probe" not in joined


# ---------------------------------------------------------------------------
# 2. The bounded retry: transient faults get one more whole-request attempt
# ---------------------------------------------------------------------------


def test_transient_timeout_retries_and_succeeds(provider, caplog):
    """Against unmodified source the first timeout erased the filters forever."""
    provider.outcomes = [_api_timeout(), _Extraction()]
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        metadata = _transcript_call()
    assert metadata["people"] == ["david"]
    assert metadata["topics"] == ["running"]
    # One client construction, two whole-request attempts (the retry).
    assert len(provider.calls) == 1
    assert len(provider.prompts) == 2
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert any(
        "llm extraction retryable failure" in record.getMessage() and "APITimeoutError" in record.getMessage()
        for record in warnings
    )


def test_retry_exhaustion_returns_empty_with_one_typed_error(provider, caplog):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    assert len(provider.prompts) == 2
    assert len(_error_records(caplog)) == 1


def test_connect_error_family_retries(provider):
    provider.outcomes = [_connect_error("connection reset"), _Extraction()]
    assert _transcript_call()["people"] == ["david"]
    assert len(provider.prompts) == 2


def test_deterministic_rejection_never_retries(provider, caplog):
    """A repeat call can only reproduce a schema/parse rejection."""
    provider.outcomes = [ValueError("model returned people as a string, not a list")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    assert len(provider.calls) == 1
    assert len(provider.prompts) == 1
    assert len(_error_records(caplog)) == 1


def test_builtin_timeout_is_terminal_not_retried(provider, caplog):
    """Deadline floors raise builtin TimeoutError (test seams, budget aborts):
    a second call inherits the same deadline and can only reproduce it."""
    provider.outcomes = [TimeoutError("Request timed out.")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    assert len(provider.calls) == 1
    assert len(provider.prompts) == 1


def test_retry_budget_is_one_extra_attempt(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    assert llm_chat._EXTRACTION_ATTEMPTS == 2
    assert _transcript_call() == _EMPTY
    assert len(provider.prompts) == 2


def test_message_path_retries_transients_too(provider):
    provider.outcomes = [_api_timeout(), _Extraction()]
    assert _message_call()["people"] == ["david"]
    assert len(provider.prompts) == 2


def test_text_path_retries_transients_too(provider):
    provider.outcomes = [_api_connection_error(), _Extraction()]
    assert _text_call()["people"] == ["david"]
    assert len(provider.prompts) == 2


def test_retry_warning_and_terminal_error_are_distinct_records(provider, caplog):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    retry_warnings = [r for r in caplog.records if "llm extraction retryable failure" in r.getMessage()]
    terminal_errors = _error_records(caplog)
    assert len(retry_warnings) == 1
    assert len(terminal_errors) == 1


def test_retry_never_sleeps_in_the_extraction_lane(provider, monkeypatch):
    """The boundary runs on sync finalization workers and inside the live
    pipeline's event loop; the retry must stay immediate (no sync sleep)."""

    def _boom(*_a, **_k):
        raise AssertionError("the extraction retry must not sleep")

    monkeypatch.setattr("time.sleep", _boom)
    provider.outcomes = [_api_timeout(), _Extraction()]
    assert _transcript_call()["people"] == ["david"]


def test_structured_alias_rides_the_same_retry(provider):
    class _Structured:
        title = "Morning run"
        overview = "Ran with David in Boston."

    provider.outcomes = [_api_timeout(), _Extraction()]
    metadata = llm_chat.retrieve_metadata_fields_from_structured(
        "uid-meta-boundary", datetime(2026, 10, 21, 12, 0, 0), _Structured(), "UTC"
    )
    assert metadata["people"] == ["david"]
    assert len(provider.prompts) == 2


# ---------------------------------------------------------------------------
# 3. Shared fallback telemetry: the degrade is countable
# ---------------------------------------------------------------------------


def test_timeout_degrade_emits_the_fallback_event_with_reason_timeout(provider, caplog):
    """Against unmodified source: no omi_fallback_event at all."""
    provider.outcomes = [_api_timeout(), _api_timeout()]
    before = _fallback_child_value("timeout")
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    assert _fallback_child_value("timeout") == before + 1.0
    events = [record for record in caplog.records if "omi_fallback_event" in record.getMessage()]
    assert any(
        "component=conversation_finalization" in record.getMessage()
        and "from=metadata_extraction" in record.getMessage()
        and "to=empty_filters" in record.getMessage()
        and "reason=timeout" in record.getMessage()
        and "outcome=degraded" in record.getMessage()
        for record in events
    )


def test_schema_rejection_degrade_buckets_reason_other(provider, caplog):
    provider.outcomes = [ValueError("bad shape")]
    before = _fallback_child_value("other")
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    assert _fallback_child_value("other") == before + 1.0
    events = [record for record in caplog.records if "omi_fallback_event" in record.getMessage()]
    assert any("reason=other" in record.getMessage() for record in events)


def test_read_timeout_family_buckets_reason_timeout(provider):
    provider.outcomes = [httpx.ReadTimeout("first byte never came"), httpx.ReadTimeout("first byte never came")]
    before = _fallback_child_value("timeout")
    assert _message_call() == _EMPTY
    assert _fallback_child_value("timeout") == before + 1.0


def test_connection_error_buckets_reason_other_not_timeout(provider):
    provider.outcomes = [_api_connection_error(), _api_connection_error()]
    before_other = _fallback_child_value("other")
    assert _text_call() == _EMPTY
    assert _fallback_child_value("other") == before_other + 1.0


def test_recovered_retry_records_no_degrade_event(provider, caplog):
    provider.outcomes = [_api_timeout(), _Extraction()]
    before = _fallback_child_value("timeout")
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call()["people"] == ["david"]
    assert _fallback_child_value("timeout") == before
    assert not any("omi_fallback_event" in record.getMessage() for record in caplog.records)


def test_message_and_text_paths_emit_the_event_on_exhaustion(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    before_message = _fallback_child_value("timeout")
    assert _message_call() == _EMPTY
    assert _fallback_child_value("timeout") == before_message + 1.0

    provider.outcomes = [_api_timeout(), _api_timeout()]
    before_text = _fallback_child_value("timeout")
    assert _text_call() == _EMPTY
    assert _fallback_child_value("timeout") == before_text + 1.0


# ---------------------------------------------------------------------------
# 4. The fail-soft contract with conversation finalization is unchanged
# ---------------------------------------------------------------------------


def test_transcript_boundary_returns_exact_empty_shape(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    assert _transcript_call() == {"people": [], "topics": [], "entities": [], "dates": []}


def test_message_boundary_returns_exact_empty_shape(provider):
    provider.outcomes = [ValueError("bad shape")]
    assert _message_call() == {"people": [], "topics": [], "entities": [], "dates": []}


def test_text_boundary_returns_exact_empty_shape(provider):
    provider.outcomes = [ValueError("bad shape")]
    assert _text_call() == {"people": [], "topics": [], "entities": [], "dates": []}


def test_successful_extraction_still_seeds_the_filter_categories(provider):
    provider.outcomes = [_Extraction()]
    with _captured_filter_writes() as writes:
        metadata = _transcript_call()
    assert metadata["people"] == ["david"]
    assert ("people", "david") in writes
    assert ("topics", "running") in writes


def test_failed_extraction_never_seeds_the_filter_categories(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with _captured_filter_writes() as writes:
        assert _transcript_call() == _EMPTY
    assert writes == []


def test_usage_is_tracked_exactly_once_across_a_retry(provider):
    provider.outcomes = [_api_timeout(), _Extraction()]
    with _counted_usage_tracking() as usage_calls:
        assert _transcript_call()["people"] == ["david"]
    assert len(usage_calls) == 1


def test_usage_is_tracked_once_even_on_terminal_failure(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with _counted_usage_tracking() as usage_calls:
        assert _transcript_call() == _EMPTY
    assert len(usage_calls) == 1


def test_retried_call_keeps_the_cache_opt_out_binding(provider):
    """The retry re-runs the composed runnable: the cache-write opt-out the
    deadline/cache suites pin must survive onto the second attempt too."""
    seen_kwargs: list = []

    def fake_opt_out(runnable):
        class _Bound:
            def invoke(self, prompt):
                seen_kwargs.append("invoked-through-opt-out")
                return provider.invoke_next(prompt)

        return _Bound()

    original = llm_chat.with_cache_write_opt_out
    llm_chat.with_cache_write_opt_out = fake_opt_out
    try:
        provider.outcomes = [_api_timeout(), _Extraction()]
        assert _transcript_call()["people"] == ["david"]
    finally:
        llm_chat.with_cache_write_opt_out = original
    assert seen_kwargs == ["invoked-through-opt-out", "invoked-through-opt-out"]


# ---------------------------------------------------------------------------
# 5. Helper units: the typed token and the retry loop
# ---------------------------------------------------------------------------


def test_token_carries_type_and_message():
    assert llm_chat._llm_failure_token(ValueError("boom")) == "ValueError: boom"


def test_token_for_empty_string_exception_is_the_type_name():
    assert llm_chat._llm_failure_token(_connect_error("")) == "ConnectError"


def test_token_flattens_multiline_messages():
    token = llm_chat._llm_failure_token(ValueError("a\nb\nc"))
    assert token == "ValueError: a b c"
    assert "\n" not in token


def test_token_caps_long_messages():
    token = llm_chat._llm_failure_token(ValueError("y" * 1000))
    assert token.startswith("ValueError: ")
    assert len(token) <= 200


def test_token_names_the_most_specific_class():
    token = llm_chat._llm_failure_token(_api_timeout())
    assert token == "APITimeoutError: Request timed out."


def test_token_survives_exceptions_without_args():
    """``Exception()`` stringifies empty — exactly the transport-error shape."""
    assert llm_chat._llm_failure_token(Exception()) == "Exception"


def test_retryable_set_covers_the_real_transport_family():
    assert isinstance(_api_timeout(), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    assert isinstance(_api_connection_error(), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    assert isinstance(httpx.ReadTimeout("x"), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    assert isinstance(_connect_error(""), llm_chat._RETRYABLE_EXTRACTION_FAILURES)


def test_deterministic_faults_are_outside_the_retryable_set():
    assert not isinstance(ValueError("bad shape"), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    assert not isinstance(KeyError("k"), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    assert not isinstance(TimeoutError("deadline floor"), llm_chat._RETRYABLE_EXTRACTION_FAILURES)
    import json

    assert not isinstance(json.JSONDecodeError("bad", "doc", 1), llm_chat._RETRYABLE_EXTRACTION_FAILURES)


def test_retry_loop_returns_the_invoked_result():
    sentinel = object()
    assert llm_chat._invoke_with_bounded_retry(lambda: sentinel) is sentinel


def test_retry_loop_reraises_the_final_instance_unchanged():
    err = _api_timeout()
    attempts: list = []

    def always_fail():
        attempts.append(1)
        raise err

    with pytest.raises(openai.APITimeoutError) as excinfo:
        llm_chat._invoke_with_bounded_retry(always_fail)
    assert excinfo.value is err
    assert len(attempts) == 2


def test_fallback_helper_uses_the_shared_recorder():
    captured: dict = {}

    def fake_record_fallback(**kwargs):
        captured.update(kwargs)

    original = llm_chat.record_fallback
    llm_chat.record_fallback = fake_record_fallback
    try:
        llm_chat._record_extraction_fallback(outcome="degraded", reason="timeout")
    finally:
        llm_chat.record_fallback = original
    assert captured["component"] == "conversation_finalization"
    assert captured["from_mode"] == "metadata_extraction"
    assert captured["to_mode"] == "empty_filters"
    assert captured["reason"] == "timeout"
    assert captured["outcome"] == "degraded"


def test_fallback_counter_buckets_are_label_ready_before_the_first_event():
    """The extraction pair's five-label child must construct on demand and
    register into the shared Counter: proves the label vocabulary is valid
    against the production metric schema (an invalid label set would raise
    here instead of degrading)."""
    labels = OMI_FALLBACK_TOTAL.labels(
        "conversation_finalization", "metadata_extraction", "empty_filters", "timeout", "degraded"
    )
    assert labels._value.get() >= 0.0
    assert ("conversation_finalization", "metadata_extraction", "empty_filters", "timeout", "degraded") in set(
        OMI_FALLBACK_TOTAL._metrics
    )


# ---------------------------------------------------------------------------
# 6. Sibling fail-soft catches in the same module join the class
# ---------------------------------------------------------------------------


def test_langsmith_prompt_failure_logs_the_typed_line_and_returns_the_fallback_prompt(monkeypatch, caplog):
    """Designed behavior (inline prompt fallback) keeps working; the log line
    names the failing type even when the exception stringifies empty."""
    import utils.observability.langsmith_prompts as langsmith_prompts

    def broken():
        raise _connect_error("")

    monkeypatch.setattr(langsmith_prompts, "get_agentic_system_prompt_template", broken)
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        prompt = llm_chat._get_agentic_qa_prompt(uid="uid-meta-boundary")
    assert isinstance(prompt, str) and "<response_style>" in prompt
    message = _error_records(caplog)[0].getMessage()
    assert "using inline fallback: error=ConnectError" in message
    assert not any("omi_fallback_event" in record.getMessage() for record in caplog.records)


def test_memory_context_topics_failure_logs_the_typed_line(provider, caplog):
    """The memory-discard lane's 450+ prod lines carried only the message, none
    of the failing type; the typed token keeps the fail-soft return."""
    from models.transcript_segment import TranscriptSegment

    segment = TranscriptSegment(
        id="s1", text="Hey Omi add a task", speaker="SPEAKER_00", is_user=True, start=0.0, end=1.0
    )
    provider.outcomes = [ValueError("Invalid json output")]

    def broken_llm(feature, *args, **kwargs):
        return provider(feature, *args, **kwargs)

    original = llm_chat.get_llm
    llm_chat.get_llm = broken_llm
    try:
        with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
            topics = llm_chat.retrieve_memory_context_params("uid-meta-boundary", [segment], [])
    finally:
        llm_chat.get_llm = original
    assert topics == []
    message = _error_records(caplog)[0].getMessage()
    assert "Error determining memory discard: error=ValueError: Invalid json output" in message
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 7. Controls: the tests bite on the unmodified source
# ---------------------------------------------------------------------------


def test_the_typed_arm_is_wired_into_both_metadata_boundaries():
    source = (BACKEND_DIR / "utils" / "llm" / "chat.py").read_text()
    assert source.count("_record_extraction_fallback(outcome='degraded'") == 2
    assert "from utils.observability.fallback import record_fallback" in source


def test_retry_helper_is_wired_into_both_metadata_boundaries():
    source = (BACKEND_DIR / "utils" / "llm" / "chat.py").read_text()
    assert source.count("_invoke_with_bounded_retry(_invoke)") == 2


def test_signature_line_distinguishes_the_message_lane_from_the_transcript_lane(provider, caplog):
    provider.outcomes = [ValueError("bad shape")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _message_call() == _EMPTY
        assert _transcript_call() == _EMPTY
    paths = [record.getMessage() for record in _error_records(caplog)]
    assert any("path=message" in message for message in paths)
    assert any("path=transcript" in message for message in paths)


# ---------------------------------------------------------------------------
# 8. Per-lane deterministic failures and the structured alias
# ---------------------------------------------------------------------------


def test_message_path_deterministic_rejection_logs_typed_line(provider, caplog):
    provider.outcomes = [ValueError("model returned people as a string, not a list")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _message_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "path=message" in message
    assert "ValueError: model returned people as a string, not a list" in message


def test_text_path_deterministic_rejection_logs_typed_line(provider, caplog):
    provider.outcomes = [ValueError("bad shape")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert _text_call() == _EMPTY
    message = _error_records(caplog)[0].getMessage()
    assert "path=text" in message
    assert "ValueError: bad shape" in message


def test_structured_alias_terminal_exhaustion_returns_empty_and_degrades(provider, caplog):
    class _Structured:
        title = "Morning run"
        overview = "Ran with David in Boston."

    provider.outcomes = [_api_timeout(), _api_timeout()]
    before = _fallback_child_value("timeout")
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        metadata = llm_chat.retrieve_metadata_fields_from_structured(
            "uid-meta-boundary", datetime(2026, 10, 21, 12, 0, 0), _Structured(), "UTC"
        )
    assert metadata == _EMPTY
    assert _fallback_child_value("timeout") == before + 1.0
    assert len(_error_records(caplog)) == 1


def test_structured_alias_recovered_retry_records_no_degrade(provider, caplog):
    class _Structured:
        title = "Morning run"
        overview = "Ran with David in Boston."

    provider.outcomes = [_api_timeout(), _Extraction()]
    before = _fallback_child_value("timeout")
    assert llm_chat.retrieve_metadata_fields_from_structured(
        "uid-meta-boundary", datetime(2026, 10, 21, 12, 0, 0), _Structured(), "UTC"
    )["people"] == ["david"]
    assert _fallback_child_value("timeout") == before
    assert not any("omi_fallback_event" in record.getMessage() for record in caplog.records)


def test_retry_warning_precedes_the_terminal_error(provider, caplog):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call() == _EMPTY
    interesting = [
        record
        for record in caplog.records
        if "llm extraction retryable failure" in record.getMessage()
        or "metadata extraction failed" in record.getMessage()
    ]
    assert [record.levelno for record in interesting] == [logging.WARNING, logging.ERROR]


def test_retry_warning_carries_the_attempt_fraction(provider, caplog):
    provider.outcomes = [_api_timeout(), _Extraction()]
    with caplog.at_level(logging.INFO, logger="utils.llm.chat"):
        assert _transcript_call()["people"] == ["david"]
    warnings = [record for record in caplog.records if "llm extraction retryable failure" in record.getMessage()]
    assert any("attempt=1/2" in record.getMessage() for record in warnings)


def test_consecutive_degradations_increment_the_counter_by_two(provider):
    provider.outcomes = [_api_timeout(), _api_timeout()]
    before = _fallback_child_value("timeout")
    assert _transcript_call() == _EMPTY
    provider.outcomes = [_api_timeout(), _api_timeout()]
    assert _message_call() == _EMPTY
    assert _fallback_child_value("timeout") == before + 2.0


def test_connect_errors_classify_as_other_not_timeout(provider):
    """A connect failure is not a timeout: it lands in the catch-all bucket."""
    provider.outcomes = [_connect_error(""), _connect_error("")]
    before_other = _fallback_child_value("other")
    before_timeout = _fallback_child_value("timeout")
    assert _transcript_call() == _EMPTY
    assert _fallback_child_value("other") == before_other + 1.0
    assert _fallback_child_value("timeout") == before_timeout


def test_source_path_defaults_to_text_for_direct_callers(provider, caplog):
    """_process_extracted_metadata keeps its three-arg signature working."""
    provider.outcomes = [ValueError("bad shape")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert llm_chat._process_extracted_metadata("uid-meta-boundary", "ignored", "2026-10-21") == _EMPTY
    assert "path=text" in _error_records(caplog)[0].getMessage()


def test_usage_tracked_once_across_message_and_text_retries(provider):
    provider.outcomes = [_api_timeout(), _Extraction()]
    with _counted_usage_tracking() as usage_calls:
        assert _message_call()["people"] == ["david"]
    assert len(usage_calls) == 1

    provider.outcomes = [_api_connection_error(), _Extraction()]
    with _counted_usage_tracking() as usage_calls:
        assert _text_call()["people"] == ["david"]
    assert len(usage_calls) == 1


def test_message_and_text_lanes_never_seed_filters_on_failure(provider):
    provider.outcomes = [ValueError("bad shape")]
    with _captured_filter_writes() as writes:
        assert _message_call() == _EMPTY
        assert _text_call() == _EMPTY
    assert writes == []


# ---------------------------------------------------------------------------
# 9. Sibling lanes: success paths untouched, empty-stringify named
# ---------------------------------------------------------------------------


def test_memory_context_lane_success_still_returns_topics(provider, caplog):
    from types import SimpleNamespace

    from models.transcript_segment import TranscriptSegment

    segment = TranscriptSegment(
        id="s1", text="Hey Omi add a task", speaker="SPEAKER_00", is_user=True, start=0.0, end=1.0
    )
    provider.outcomes = [SimpleNamespace(topics=["budget", "planning"])]
    topics = llm_chat.retrieve_memory_context_params("uid-meta-boundary", [segment], [])
    assert topics == ["budget", "planning"]
    assert not any("Error determining memory discard" in record.getMessage() for record in caplog.records)


def test_memory_context_lane_names_empty_stringify_exceptions(provider, caplog):
    from models.transcript_segment import TranscriptSegment

    segment = TranscriptSegment(
        id="s1", text="Hey Omi add a task", speaker="SPEAKER_00", is_user=True, start=0.0, end=1.0
    )
    provider.outcomes = [_connect_error("")]
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        assert llm_chat.retrieve_memory_context_params("uid-meta-boundary", [segment], []) == []
    message = _error_records(caplog)[0].getMessage()
    assert message == "Error determining memory discard: error=ConnectError"


def test_langsmith_failure_message_is_flattened_to_one_line(monkeypatch, caplog):
    import utils.observability.langsmith_prompts as langsmith_prompts

    def broken():
        raise ValueError("line one\nline two")

    monkeypatch.setattr(langsmith_prompts, "get_agentic_system_prompt_template", broken)
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        llm_chat._get_agentic_qa_prompt(uid="uid-meta-boundary")
    message = _error_records(caplog)[0].getMessage()
    assert "\n" not in message
    assert "error=ValueError: line one line two" in message


def test_langsmith_failure_carries_the_message_token(monkeypatch, caplog):
    import utils.observability.langsmith_prompts as langsmith_prompts

    def broken():
        raise ValueError("quota exhausted")

    monkeypatch.setattr(langsmith_prompts, "get_agentic_system_prompt_template", broken)
    with caplog.at_level(logging.ERROR, logger="utils.llm.chat"):
        llm_chat._get_agentic_qa_prompt(uid="uid-meta-boundary")
    message = _error_records(caplog)[0].getMessage()
    assert "error=ValueError: quota exhausted" in message
