"""
Unit tests for voice message language resolution.
"""

import os
from pathlib import Path
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

    fakes: dict[str, object] = {
        "database._client": MagicMock(),
        "stripe": MagicMock(),
        "database.chat": MagicMock(),
        "database.notifications": MagicMock(),
        "database.apps": MagicMock(),
        "database.auth": MagicMock(),
        "database.users": MagicMock(),
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


def test_prepare_voice_message_url_signs_and_schedules_same_path(chat, monkeypatch):
    signed_url = "https://signed.test/audio"
    sign = MagicMock(return_value=signed_url)
    schedule_cleanup = MagicMock()
    monkeypatch.setattr(chat, "get_syncing_file_temporal_signed_url", sign)
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)

    assert chat._prepare_voice_message_url("audio.wav") == signed_url
    sign.assert_called_once_with("audio.wav")
    schedule_cleanup.assert_called_once_with("audio.wav")


def test_silent_voice_message_still_schedules_temporary_audio_cleanup(chat, monkeypatch):
    """Silence is terminal, but it must not leave uploaded audio retained."""
    sign = MagicMock(return_value="https://signed.test/audio")
    schedule_cleanup = MagicMock()
    monkeypatch.setattr(chat, "get_syncing_file_temporal_signed_url", sign)
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)
    monkeypatch.setattr(chat, "get_prerecorded_service", lambda language: ("deepgram", "en", "nova-3"))
    monkeypatch.setattr(chat, "_validated_wav_is_silent", lambda path, provider: True)

    assert chat.transcribe_voice_message_segment("audio.wav", "uid", "en") == (None, "en")
    sign.assert_called_once_with("audio.wav")
    schedule_cleanup.assert_called_once_with("audio.wav")


@pytest.mark.asyncio
async def test_stream_routes_storage_and_transcription_to_owned_executors(chat, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "get_prerecorded_service", lambda language: ("deepgram", language, "nova-3"))

    async def fake_run_blocking(executor, func, *args, **kwargs):
        calls.append((executor, func, args, kwargs))
        if func is chat._validated_wav_is_silent:
            return False
        if func is chat._prepare_voice_message_url:
            return "https://signed.test/audio"
        if func is chat._transcribe_voice_message_url:
            return None, "en"
        raise AssertionError(f"unexpected blocking call: {func.__name__}")

    monkeypatch.setattr(chat, "run_blocking", fake_run_blocking)

    chunks = [chunk async for chunk in chat.process_voice_message_segment_stream("audio.wav", "uid", "en")]

    assert chunks == []
    assert [(executor, func) for executor, func, _, _ in calls] == [
        (chat.storage_executor, chat._prepare_voice_message_url),
        (chat.sync_executor, chat._validated_wav_is_silent),
        (chat.sync_executor, chat._transcribe_voice_message_url),
    ]
    assert calls[0][2] == ("audio.wav",)
    assert calls[1][2] == ("audio.wav",)
    assert calls[1][3] == {"provider": "deepgram"}
    assert calls[2][2] == ("https://signed.test/audio", "audio.wav", "en", False)


@pytest.mark.asyncio
async def test_silent_stream_still_schedules_temporary_audio_cleanup(chat, monkeypatch):
    """The streamed VAD gate must preserve the same deletion lifecycle."""
    sign = MagicMock(return_value="https://signed.test/audio")
    schedule_cleanup = MagicMock()
    monkeypatch.setattr(chat, "get_syncing_file_temporal_signed_url", sign)
    monkeypatch.setattr(chat, "schedule_syncing_temporal_file_deletion", schedule_cleanup)
    monkeypatch.setattr(chat, "get_prerecorded_service", lambda language: ("deepgram", "en", "nova-3"))

    async def fake_run_blocking(executor, func, *args, **kwargs):
        if func is chat._prepare_voice_message_url:
            assert executor is chat.storage_executor
            return func(*args, **kwargs)
        if func is chat._validated_wav_is_silent:
            assert executor is chat.sync_executor
            return True
        raise AssertionError(f"unexpected blocking call: {func.__name__}")

    monkeypatch.setattr(chat, "run_blocking", fake_run_blocking)

    chunks = [chunk async for chunk in chat.process_voice_message_segment_stream("audio.wav", "uid", "en")]

    assert chunks == []
    sign.assert_called_once_with("audio.wav")
    schedule_cleanup.assert_called_once_with("audio.wav")
