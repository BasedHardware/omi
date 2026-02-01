"""
Unit tests for voice message language resolution.
"""

import sys
import types
from unittest.mock import MagicMock

sys.modules["database._client"] = MagicMock()
sys.modules["stripe"] = MagicMock()
sys.modules["database.chat"] = MagicMock()
sys.modules["database.notifications"] = MagicMock()
sys.modules["database.apps"] = MagicMock()
sys.modules["models.chat"] = MagicMock()
sys.modules["models.conversation"] = MagicMock()
sys.modules["models.notification_message"] = MagicMock()
sys.modules["models.app"] = MagicMock()
sys.modules["models.transcript_segment"] = MagicMock()
sys.modules["utils.notifications"] = MagicMock()
sys.modules["utils.other.storage"] = MagicMock()
sys.modules["utils.retrieval.graph"] = MagicMock()
sys.modules["utils.stt.pre_recorded"] = MagicMock()


class NotFound(Exception):
    pass


_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_exceptions_module = types.ModuleType("google.cloud.exceptions")
_google_exceptions_module.NotFound = NotFound
sys.modules.setdefault("google.cloud.exceptions", _google_exceptions_module)
_google_firestore_module = types.ModuleType("google.cloud.firestore")
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
_google_firestore_v1_module = types.ModuleType("google.cloud.firestore_v1")
_google_firestore_v1_module.FieldFilter = MagicMock()
_google_firestore_v1_module.transactional = lambda func: func
sys.modules.setdefault("google.cloud.firestore_v1", _google_firestore_v1_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "exceptions", _google_exceptions_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)

import database.users as user_db
from utils.chat import resolve_voice_message_language


def test_request_language_auto_overrides_preferences(monkeypatch):
    def fake_get_user_language_preference(uid: str) -> str:
        return "es"

    def fake_get_user_transcription_preferences(uid: str) -> dict:
        return {"single_language_mode": True, "vocabulary": []}

    monkeypatch.setattr(user_db, "get_user_language_preference", fake_get_user_language_preference)
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", fake_get_user_transcription_preferences)

    language = resolve_voice_message_language("uid", " auto ")
    assert language == "multi"


def test_request_language_multi(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "ru")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = resolve_voice_message_language("uid", "multi")
    assert language == "multi"


def test_request_language_specific(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = resolve_voice_message_language("uid", "ru")
    assert language == "ru"


def test_request_language_blank_uses_user_preferences(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "vi")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = resolve_voice_message_language("uid", "   ")
    assert language == "vi"


def test_user_preference_single_language(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "vi")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language = resolve_voice_message_language("uid", None)
    assert language == "vi"


def test_user_preference_multi_language_mode(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "fr")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = resolve_voice_message_language("uid", None)
    assert language == "multi"


def test_no_preference_detect_language(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language = resolve_voice_message_language("uid", None)
    assert language == "multi"
