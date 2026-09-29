from fastapi import Response
import pytest

from routers import conversations as conversation_routes
from utils.conversations import onopen_translation
from utils.translation_core.engine import TranslationOutcome, TranslationStatus
from utils.translation_language import TranslationNeed


class FakeService:
    def __init__(self):
        self.calls = []

    def translate_outcomes(self, target, units, *, mode, profile):
        self.calls.append((target, units, mode, profile))
        return [
            TranslationOutcome(index, segment_id, text, f'Translated {text}', 'vi', TranslationStatus.translated)
            for index, (segment_id, text) in enumerate(units)
        ]


def conversation(count=2):
    return {
        'id': 'canonical',
        'transcript_segments': [
            {'id': f's{index}', 'text': f'Yến nói với bác năm {2025 + index}.', 'translations': []}
            for index in range(count)
        ],
    }


def configure(monkeypatch):
    monkeypatch.setenv('TRANSLATION_ONOPEN_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_ALLOWLIST', 'u,another-user')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GEMINI_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_DAILY_CHARS', '100000')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '1000000')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'a' * 32)
    monkeypatch.setattr(onopen_translation.users_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(
        onopen_translation, 'classify_translation_need', lambda *args, **kwargs: TranslationNeed.TRANSLATE
    )
    monkeypatch.setattr(
        onopen_translation.conversations_db, 'translation_materialization_is_current', lambda *args, **kwargs: False
    )
    monkeypatch.setattr(onopen_translation, 'reserve_translation', lambda *args, **kwargs: (object(), 'admitted'))
    monkeypatch.setattr(onopen_translation, 'reservation_is_current', lambda *args, **kwargs: True)
    monkeypatch.setattr(onopen_translation, 'release_translation', lambda *args, **kwargs: True)
    monkeypatch.setattr(onopen_translation, 'should_persist_translation', lambda *args, **kwargs: True)
    monkeypatch.setattr(
        onopen_translation.conversations_db,
        'materialize_translation',
        lambda _uid, _cid, sid, source, target, translated, **kwargs: {
            'id': sid,
            'text': source,
            'translations': [{'lang': target, 'text': translated}],
        },
    )


def test_opt_in_page_is_bounded_and_cursor_is_uid_bound(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv('TRANSLATION_ONDEMAND_MAX_SEGMENTS', '1')
    service = FakeService()
    detail, status, cursor = onopen_translation.translate_open_page('u', conversation(), service=service)
    assert status == 'partial' and cursor
    assert len(service.calls) == 1 and len(service.calls[0][1]) == 1
    assert detail['transcript_segments'][0]['text'].startswith('Yến')
    _, status, final_cursor = onopen_translation.translate_open_page('u', conversation(), cursor, service=service)
    assert status == 'complete' and final_cursor is None
    with pytest.raises(ValueError):
        onopen_translation.translate_open_page('another-user', conversation(), cursor, service=service)
    with pytest.raises(ValueError):
        onopen_translation.translate_open_page(
            'u', conversation(), ('A' if cursor[0] != 'A' else 'B') + cursor[1:], service=service
        )


def test_oversized_segment_is_deferred_without_truncation(monkeypatch):
    configure(monkeypatch)
    detail = conversation(1)
    detail['transcript_segments'][0]['text'] = 'Y' * 12001
    service = FakeService()
    _, status, cursor = onopen_translation.translate_open_page('u', detail, service=service)
    assert status == 'deferred' and cursor and not service.calls


def test_default_detail_route_has_no_translation_side_effect(monkeypatch):
    detail = conversation(1)
    monkeypatch.setattr(conversation_routes, '_get_valid_conversation_by_id', lambda *args, **kwargs: detail)
    monkeypatch.setattr(conversation_routes, '_dispatch_first_open_work', lambda *args, **kwargs: None)
    called = []
    monkeypatch.setattr(conversation_routes, 'translate_open_page', lambda *args, **kwargs: called.append(True))
    response = Response()
    assert (
        conversation_routes.get_conversation_by_id(
            'canonical',
            source=None,
            include_discarded=True,
            uid='u',
            include_translations=False,
            translation_cursor=None,
            response=response,
        )
        == detail
    )
    assert not called and 'X-Translation-Status' not in response.headers
