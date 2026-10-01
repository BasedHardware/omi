from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from datetime import datetime, timezone
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
    _, status, final_cursor = onopen_translation.translate_open_page('u', detail, cursor, service=service)
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


def test_scan_cap_exhaustion_never_reports_complete(monkeypatch):
    """Luna R2-2 regression: a transcript longer than the selection scan window
    must not return `complete` when the scanned window itself needs no work —
    untranslated segments remain beyond the cap and the cursor continues."""
    configure(monkeypatch)
    monkeypatch.setenv('TRANSLATION_ONDEMAND_MAX_SEGMENTS', '50')
    count = 500  # > default scan cap (400)
    detail = conversation(count)
    service = FakeService()
    # All segments need translation, but the page bound stops after 50; the
    # important part is the cursor chain never claims complete before the end.
    _, status, cursor = onopen_translation.translate_open_page('u', detail, service=service)
    assert status == 'partial' and cursor
    guard = 0
    while cursor is not None:
        detail, status, cursor = onopen_translation.translate_open_page('u', detail, cursor, service=service)
        guard += 1
        if status == 'complete':
            break
        assert guard < 20, 'cursor chain did not terminate'
    assert status == 'complete'


def test_clean_scan_cap_exhaustion_returns_partial_cursor_not_complete(monkeypatch):
    """Luna R2-2 exact defect: materializations current for the scanned window,
    but untranslated segments exist beyond the scan cap. Must return partial +
    cursor (never complete)."""
    configure(monkeypatch)
    monkeypatch.setenv('TRANSLATION_ONDEMAND_MAX_SEGMENTS', '50')
    count = 500
    detail = conversation(count)

    def current_only_within_cap(*args):
        segment = args[2]
        # Within the first 400 (scan cap) segments pretend materializations are
        # current; beyond that pretend stale — selection never scans there, so
        # the old bug reported complete while segment 450 stayed untranslated.
        try:
            index = int(str(segment['id'])[1:])
        except (ValueError, TypeError, KeyError):
            return False
        return index < 400

    monkeypatch.setattr(
        onopen_translation.conversations_db,
        'translation_materialization_is_current',
        current_only_within_cap,
    )
    service = FakeService()
    _, status, cursor = onopen_translation.translate_open_page('u', detail, service=service)
    assert status == 'partial' and cursor is not None
    import base64
    import json as _json

    padded = cursor + '=' * (-len(cursor) % 4)
    signed = base64.urlsafe_b64decode(padded)
    payload = _json.loads(signed[:-32])
    assert payload['index'] == 400, 'cursor must continue at the scan bound, not the transcript end'


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


def test_authenticated_detail_http_opt_in_returns_status_without_shape_change(monkeypatch):
    detail = {
        'id': 'canonical',
        'created_at': datetime.now(timezone.utc),
        'started_at': None,
        'finished_at': None,
        'structured': {'title': 'Test', 'overview': 'Summary'},
        'transcript_segments': [],
    }
    monkeypatch.setattr(conversation_routes, '_get_valid_conversation_by_id', lambda *args, **kwargs: detail)
    monkeypatch.setattr(conversation_routes, '_dispatch_first_open_work', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        conversation_routes,
        'translate_open_page',
        lambda uid, current, cursor: (current, 'partial', 'signed-next-page'),
    )
    app = FastAPI()
    app.include_router(conversation_routes.router)
    app.dependency_overrides[conversation_routes.auth.get_current_user_uid] = lambda: 'u'
    client = TestClient(app)
    ordinary = client.get('/v1/conversations/canonical')
    opted = client.get('/v1/conversations/canonical?include_translations=true')
    assert ordinary.status_code == opted.status_code == 200
    assert ordinary.json() == opted.json()
    assert 'x-translation-status' not in ordinary.headers
    assert opted.headers['x-translation-status'] == 'partial'
    assert opted.headers['x-translation-cursor'] == 'signed-next-page'


def test_detail_route_serves_raw_when_translation_service_fails(monkeypatch):
    detail = conversation(1)
    monkeypatch.setattr(conversation_routes, '_get_valid_conversation_by_id', lambda *args, **kwargs: detail)
    monkeypatch.setattr(conversation_routes, '_dispatch_first_open_work', lambda *args, **kwargs: None)

    def unavailable(*args):
        raise ConnectionError('translation unavailable')

    monkeypatch.setattr(conversation_routes, 'translate_open_page', unavailable)
    response = Response()
    returned = conversation_routes.get_conversation_by_id(
        'canonical',
        source=None,
        include_discarded=True,
        uid='u',
        include_translations=True,
        translation_cursor=None,
        response=response,
    )
    assert returned == detail
    assert response.headers['X-Translation-Status'] == 'unavailable'


def test_rest_capacity_defers_provider_without_dispatch(monkeypatch):
    configure(monkeypatch)

    class Busy:
        def acquire(self, **kwargs):
            return False

        def release(self):
            raise AssertionError('unacquired slot released')

    monkeypatch.setattr(onopen_translation, 'VIEWED_REST_CAPACITY', Busy())
    service = FakeService()
    _, status, cursor = onopen_translation.translate_open_page('u', conversation(1), service=service)
    assert status == 'deferred' and cursor
    assert service.calls == []
