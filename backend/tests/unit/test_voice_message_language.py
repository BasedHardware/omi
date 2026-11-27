"""
Unit tests for voice message language resolution.
"""

import asyncio
import os
from pathlib import Path
import threading
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _build_google_stubs() -> dict[str, ModuleType]:
    """Build the google.cloud.* stub subpackages (NotFound / FieldFilter / transactional)."""
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    class NotFound(Exception):
        pass

    google_exceptions = ModuleType("google.cloud.exceptions")
    google_exceptions.NotFound = NotFound  # type: ignore[attr-defined]
    google_firestore = ModuleType("google.cloud.firestore")
    google_firestore_v1 = ModuleType("google.cloud.firestore_v1")
    google_firestore_v1.FieldFilter = MagicMock()  # type: ignore[attr-defined]
    google_firestore_v1.transactional = lambda func: func  # type: ignore[attr-defined]

    google_pkg.cloud = google_cloud_pkg  # type: ignore[attr-defined]
    google_cloud_pkg.exceptions = google_exceptions  # type: ignore[attr-defined]
    google_cloud_pkg.firestore = google_firestore  # type: ignore[attr-defined]

    return {
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.exceptions": google_exceptions,
        "google.cloud.firestore": google_firestore,
        "google.cloud.firestore_v1": google_firestore_v1,
    }


@pytest.fixture(scope="module")
def chat():
    """Load utils.chat fresh against a stubbed db/llm/models chain.

    utils.chat pulls a heavy import chain at import time (typesense clients, llm
    clients, etc.) that cannot run in a hermetic unit process. The fakes below
    short-circuit that chain so only the pure ``resolve_voice_message_language``
    logic is exercised. The fake must precede the import — see
    ``backend/docs/test_isolation.md`` and ``testing/import_isolation``.
    """
    redis_db = MagicMock()
    redis_db.try_acquire_user_platform_write_lock = MagicMock()
    subscription = MagicMock()
    subscription.get_default_basic_subscription = MagicMock()
    usage_tracker = MagicMock()
    usage_tracker.track_usage = MagicMock()
    usage_tracker.set_usage_context = MagicMock()
    usage_tracker.reset_usage_context = MagicMock()

    users = MagicMock()
    users.get_user_language_preference = MagicMock(return_value='')
    users.get_user_transcription_preferences = MagicMock(return_value={})
    fakes: dict[str, object] = {
        "database._client": MagicMock(),
        "stripe": MagicMock(),
        "database.chat": MagicMock(),
        "database.notifications": MagicMock(),
        "database.apps": MagicMock(),
        "database.auth": MagicMock(),
        "database.users": users,
        "utils.apps": MagicMock(),
        "utils.llm.chat": MagicMock(),
        "utils.llm.persona": MagicMock(),
        "database.redis_db": redis_db,
        "models.chat": MagicMock(),
        "models.conversation": MagicMock(),
        "models.notification_message": MagicMock(),
        "models.app": MagicMock(),
        "models.transcript_segment": MagicMock(),
        "utils.subscription": subscription,
        "utils.llm.usage_tracker": usage_tracker,
        "utils.notifications": MagicMock(),
        "utils.other.storage": MagicMock(),
        "utils.retrieval.graph": MagicMock(),
        "utils.stt.pre_recorded": MagicMock(),
    }
    fakes.update(_build_google_stubs())

    with stub_modules(fakes):  # type: ignore[arg-type]
        module = load_module_fresh("utils.chat", os.path.join(str(_BACKEND), "utils", "chat.py"))
        yield module


def test_request_language_auto_overrides_preferences(chat, monkeypatch):
    def fake_get_user_language_preference(uid: str) -> str:
        return "es"

    def fake_get_user_transcription_preferences(uid: str) -> dict:
        return {"single_language_mode": True, "vocabulary": []}

    monkeypatch.setattr(chat.user_db, "get_user_language_preference", fake_get_user_language_preference)
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", fake_get_user_transcription_preferences)

    language = chat.resolve_voice_message_language("uid", " auto ")
    assert language == "multi"


def test_request_language_multi(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "ru")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = chat.resolve_voice_message_language("uid", "multi")
    assert language == "multi"


def test_request_language_specific(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = chat.resolve_voice_message_language("uid", "ru")
    assert language == "ru"


def test_request_language_blank_uses_user_preferences(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "vi")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = chat.resolve_voice_message_language("uid", "   ")
    assert language == "vi"


def test_user_preference_single_language(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "vi")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = chat.resolve_voice_message_language("uid", None)
    assert language == "vi"


def test_user_preference_multi_language_mode(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "fr")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = chat.resolve_voice_message_language("uid", None)
    assert language == "multi"


def test_no_preference_detect_language(chat, monkeypatch):
    monkeypatch.setattr(chat.user_db, "get_user_language_preference", lambda uid: "")
    monkeypatch.setattr(chat.user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = chat.resolve_voice_message_language("uid", None)
    assert language == "multi"


def test_prepare_voice_message_url_signs_without_starting_cleanup(chat, monkeypatch):
    signed_url = "https://signed.test/audio"
    receipt = object()
    sign = MagicMock(return_value=(signed_url, receipt))
    schedule_cleanup = MagicMock()
    monkeypatch.setattr(chat, "get_syncing_file_temporal_signed_url_with_receipt", sign)
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)

    assert chat._prepare_voice_message_url("audio.wav", "uid") == (signed_url, receipt)
    sign.assert_called_once_with("audio.wav", "uid")
    schedule_cleanup.assert_not_called()


def _prepare_consumer(chat, monkeypatch, receipt, schedule_cleanup):
    monkeypatch.setattr(chat, "_prepare_voice_message_url", lambda path, uid: ("https://signed.test/audio", receipt))
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)
    monkeypatch.setattr(chat, "get_prerecorded_service", lambda language: ("modulate", language, "velma-2"))


def test_delayed_consumption_keeps_only_input_until_worker_finishes(chat, monkeypatch):
    receipt = object()
    schedule_cleanup = MagicMock()
    events = []
    _prepare_consumer(chat, monkeypatch, receipt, schedule_cleanup)
    monkeypatch.setattr(chat, "_validated_wav_is_silent", lambda path, provider: False)

    def consume(*args, **kwargs):
        events.append("consumer_started")
        schedule_cleanup.assert_not_called()
        events.append("consumer_finished")
        return "transcript", "en"

    monkeypatch.setattr(chat, "_transcribe_voice_message_url", consume)

    assert chat.transcribe_voice_message_segment("audio.wav", "uid", "en") == ("transcript", "en")
    assert events == ["consumer_started", "consumer_finished"]
    schedule_cleanup.assert_called_once_with(receipt)


def test_failed_consumption_schedules_cleanup_only_at_terminal_failure(chat, monkeypatch):
    receipt = object()
    schedule_cleanup = MagicMock()
    _prepare_consumer(chat, monkeypatch, receipt, schedule_cleanup)
    monkeypatch.setattr(chat, "_validated_wav_is_silent", lambda path, provider: False)

    def fail(*args, **kwargs):
        schedule_cleanup.assert_not_called()
        raise RuntimeError("provider exhausted retries")

    monkeypatch.setattr(chat, "_transcribe_voice_message_url", fail)

    with pytest.raises(RuntimeError, match="exhausted retries"):
        chat.transcribe_voice_message_segment("audio.wav", "uid", "en")
    schedule_cleanup.assert_called_once_with(receipt)


def test_silent_voice_message_schedules_temporary_audio_cleanup(chat, monkeypatch):
    """Silence is terminal, but it must not leave uploaded audio retained."""
    receipt = object()
    schedule_cleanup = MagicMock()
    _prepare_consumer(chat, monkeypatch, receipt, schedule_cleanup)
    monkeypatch.setattr(chat, "_validated_wav_is_silent", lambda path, provider: True)

    assert chat.transcribe_voice_message_segment("audio.wav", "uid", "en") == (None, "en")
    schedule_cleanup.assert_called_once_with(receipt)


@pytest.mark.asyncio
async def test_stream_uses_one_cancellation_safe_consumer_worker(chat, monkeypatch):
    calls = []

    async def fake_run_blocking(executor, func, *args, **kwargs):
        calls.append((executor, func, args, kwargs))
        if func is chat.transcribe_voice_message_segment:
            return None, "en"
        raise AssertionError(f"unexpected blocking call: {func.__name__}")

    monkeypatch.setattr(chat, "run_blocking", fake_run_blocking)

    chunks = [
        chunk
        async for chunk in chat.process_voice_message_segment_stream(
            "audio.wav", "uid", "en", register_answer=lambda *_: None
        )
    ]

    assert chunks == []
    assert [(executor, func) for executor, func, _, _ in calls] == [
        (chat.sync_executor, chat.transcribe_voice_message_segment)
    ]
    assert calls[0][2] == ("audio.wav", "uid", "en")


@pytest.mark.asyncio
async def test_silent_stream_schedules_temporary_audio_cleanup(chat, monkeypatch):
    """The streamed and non-streamed paths share the same terminal lifecycle."""
    receipt = object()
    schedule_cleanup = MagicMock()
    _prepare_consumer(chat, monkeypatch, receipt, schedule_cleanup)
    monkeypatch.setattr(chat, "_validated_wav_is_silent", lambda path, provider: True)

    async def fake_run_blocking(executor, func, *args, **kwargs):
        assert executor is chat.sync_executor
        return func(*args, **kwargs)

    monkeypatch.setattr(chat, "run_blocking", fake_run_blocking)

    chunks = [
        chunk
        async for chunk in chat.process_voice_message_segment_stream(
            "audio.wav", "uid", "en", register_answer=lambda *_: None
        )
    ]

    assert chunks == []
    schedule_cleanup.assert_called_once_with(receipt)


@pytest.mark.asyncio
async def test_stream_cancellation_does_not_cleanup_until_worker_exit(chat, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    worker_finished = threading.Event()
    schedule_cleanup = MagicMock()
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)

    def slow_consumer(*args, **kwargs):
        started.set()
        if not release.wait(timeout=2):
            raise RuntimeError("test worker was not released")
        schedule_cleanup("receipt")
        worker_finished.set()
        return None, "en"

    monkeypatch.setattr(chat, "transcribe_voice_message_segment", slow_consumer)

    async def consume():
        return [
            chunk
            async for chunk in chat.process_voice_message_segment_stream(
                "audio.wav", "uid", "en", register_answer=lambda *_: None
            )
        ]

    task = asyncio.create_task(consume())
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    schedule_cleanup.assert_not_called()

    release.set()
    assert await asyncio.to_thread(worker_finished.wait, 1)
    schedule_cleanup.assert_called_once_with("receipt")
