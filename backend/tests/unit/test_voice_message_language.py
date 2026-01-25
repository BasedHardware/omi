"""
Unit tests for voice message language resolution.
"""

import database.users as user_db
from utils.chat import resolve_voice_message_language


def test_request_language_auto_overrides_preferences(monkeypatch):
    def fake_get_user_language_preference(uid: str) -> str:
        return "es"

    def fake_get_user_transcription_preferences(uid: str) -> dict:
        return {"single_language_mode": True, "vocabulary": []}

    monkeypatch.setattr(user_db, "get_user_language_preference", fake_get_user_language_preference)
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", fake_get_user_transcription_preferences)

    language, detect_language = resolve_voice_message_language("uid", " auto ")
    assert language is None
    assert detect_language is True


def test_request_language_multi(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "ru")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language, detect_language = resolve_voice_message_language("uid", "multi")
    assert language is None
    assert detect_language is True


def test_request_language_specific(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language, detect_language = resolve_voice_message_language("uid", "ru")
    assert language == "ru"
    assert detect_language is False


def test_user_preference_single_language(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "vi")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": True})

    language, detect_language = resolve_voice_message_language("uid", None)
    assert language == "vi"
    assert detect_language is False


def test_user_preference_multi_language_mode(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "fr")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language, detect_language = resolve_voice_message_language("uid", None)
    assert language is None
    assert detect_language is True


def test_no_preference_detect_language(monkeypatch):
    monkeypatch.setattr(user_db, "get_user_language_preference", lambda uid: "")
    monkeypatch.setattr(user_db, "get_user_transcription_preferences", lambda uid: {"single_language_mode": False})

    language, detect_language = resolve_voice_message_language("uid", None)
    assert language is None
    assert detect_language is True
