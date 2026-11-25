from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from config.translation import TranslationProvider
from routers import conversations as conversation_routes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.translation_test_support import DictTranslationStore, build_service
from utils.llm.model_config import LUNA_MODEL
from utils.conversations import onopen_translation
from utils.translation_core.engine import TranslationOutcome, TranslationStatus
from utils.translation_core.providers import LunaTranslationProvider, LunaViewedTranslationBatch
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
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_DAILY_CHARS', '100000')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '1000000')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'a' * 32)
    monkeypatch.setattr(onopen_translation.users_db, 'get_user_language_preference', lambda uid, **kwargs: 'en')
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
    detail, status, cursor = onopen_translation.translate_open_page(
        'u', conversation(), gui_signal=True, service=service
    )
    assert status == 'partial' and cursor
    assert len(service.calls) == 1 and len(service.calls[0][1]) == 1
    assert detail['transcript_segments'][0]['text'].startswith('Yến')
    _, status, final_cursor = onopen_translation.translate_open_page(
        'u', detail, cursor, gui_signal=True, service=service
    )
    assert status == 'complete' and final_cursor is None
    with pytest.raises(ValueError):
        onopen_translation.translate_open_page('another-user', conversation(), cursor, gui_signal=True, service=service)
    with pytest.raises(ValueError):
        onopen_translation.translate_open_page(
            'u', conversation(), ('A' if cursor[0] != 'A' else 'B') + cursor[1:], gui_signal=True, service=service
        )


def test_oversized_segment_is_deferred_without_truncation(monkeypatch):
    configure(monkeypatch)
    detail = conversation(1)
    detail['transcript_segments'][0]['text'] = 'Y' * 12001
    service = FakeService()
    _, status, cursor = onopen_translation.translate_open_page('u', detail, gui_signal=True, service=service)
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
    _, status, cursor = onopen_translation.translate_open_page('u', detail, gui_signal=True, service=service)
    assert status == 'partial' and cursor
    guard = 0
    while cursor is not None:
        detail, status, cursor = onopen_translation.translate_open_page(
            'u', detail, cursor, gui_signal=True, service=service
        )
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
    _, status, cursor = onopen_translation.translate_open_page('u', detail, gui_signal=True, service=service)
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
    monkeypatch.setattr(
        conversation_routes,
        'translate_open_page',
        lambda uid, current, cursor, *, gui_signal: (current, 'partial', 'signed-next-page'),
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

    def unavailable(*args, **kwargs):
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
    _, status, cursor = onopen_translation.translate_open_page('u', conversation(1), gui_signal=True, service=service)
    assert status == 'deferred' and cursor
    assert service.calls == []


def test_http_translation_requires_exact_open_on_every_page(monkeypatch):
    db = conversation_routes.conversations_db
    monkeypatch.setenv('TRANSLATION_ONOPEN_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_DAILY_CHARS', '100000')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '1000000')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_MAX_SEGMENTS', '1')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_DEADLINE_SECONDS', '30')
    monkeypatch.setattr(onopen_translation, 'classify_translation_need', lambda *a, **k: TranslationNeed.TRANSLATE)

    uid = 'u'
    cid = 'canonical'
    path = ('users', uid, 'conversations', cid)
    detail = {
        **conversation(401),
        'created_at': datetime.now(timezone.utc),
        'started_at': None,
        'finished_at': None,
        'structured': {'title': 'Test', 'overview': 'Summary'},
        'data_protection_level': 'standard',
        'has_photos': False,
    }
    for index, segment in enumerate(detail['transcript_segments']):
        segment.update(is_user=False, start=float(index), end=float(index + 1))
    stored_translation = {'lang': 'en', 'text': 'Previously saved.'}
    detail['transcript_segments'][1]['translations'] = [stored_translation]
    detail['transcript_segments'][-1]['translations'] = [stored_translation]
    store = StrictFirestore(
        {
            path: db.encode_conversation_for_write(uid, detail, 'standard'),
            ('users', uid): {'language': 'en'},
        }
    )
    get_cached_language = Mock(side_effect=lambda policy, key, fetch: fetch())
    monkeypatch.setattr(onopen_translation.users_db, 'db', store)
    monkeypatch.setattr(onopen_translation.users_db, 'get_or_fetch', get_cached_language)
    snapshot = deepcopy(store.rows[path])
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)

    reservation = object()
    reserve = Mock(return_value=(reservation, 'admitted'))
    release = Mock()
    materialize = Mock(wraps=db.materialize_translation)
    monkeypatch.setattr(onopen_translation, 'reserve_translation', reserve)
    monkeypatch.setattr(onopen_translation, 'release_translation', release)
    monkeypatch.setattr(onopen_translation, 'reservation_is_current', lambda value: value is reservation)
    monkeypatch.setattr(db, 'reservation_is_current', lambda value: value is reservation)
    monkeypatch.setattr(db, 'materialize_translation', materialize)
    first_open = Mock()
    monkeypatch.setattr(conversation_routes, '_enrich_deferred_conversation', first_open)
    open_recording = Mock()
    monkeypatch.setattr(conversation_routes, 'open_recording', open_recording)

    provider_client = Mock(spec=['with_structured_output'])
    provider_call = provider_client.with_structured_output.return_value.invoke
    translated_text = 'Yến spoke with the elder in 2025.'
    provider_call.return_value = LunaViewedTranslationBatch(
        translations=[{'ordinal': 0, 'text': translated_text, 'detected_language': 'vi'}]
    )
    monkeypatch.setattr('utils.translation_core.providers.get_model', lambda feature: LUNA_MODEL)
    cache_store = DictTranslationStore()
    service, _ = build_service(
        {TranslationProvider.luna: LunaTranslationProvider(lambda: provider_client)}, store=cache_store
    )
    monkeypatch.setattr(onopen_translation, 'TranslationService', lambda: service)

    app = FastAPI()
    app.include_router(conversation_routes.router)
    app.dependency_overrides[conversation_routes.auth.get_current_user_uid] = lambda: uid
    client = TestClient(app)
    url = f'/v1/conversations/{cid}'
    opt_in = {'include_translations': 'true'}
    gui = {'X-Omi-Recording-Detail': '1'}

    def read(headers=None, cursor=None):
        params = opt_in if cursor is None else {**opt_in, 'translation_cursor': cursor}
        result = client.get(url, params=params, headers=headers)
        assert result.status_code == 200, result.text
        segments = result.json()['transcript_segments']
        assert [segment['text'] for segment in segments] == [
            segment['text'] for segment in detail['transcript_segments']
        ]
        assert segments[-1]['translations'] == [stored_translation]
        return result

    paid_events = ('reservation_attempted', 'provider_called', 'materialization_committed')

    def counts(signal, events):
        return [
            REGISTRY.get_sample_value('omi_detail_translation_total', {'event': event, 'gui_signal': signal})
            for event in events
        ]

    absent_before = counts('absent', (*paid_events, 'detail_returned'))
    present_before = counts('present', paid_events)
    for headers in (None, {'X-Omi-Recording-Detail': 'true'}):
        page = read(headers)
        assert page.headers['x-translation-status'] == 'partial'
        assert page.json()['transcript_segments'][1]['translations'] == [stored_translation]
        tail = read(headers, page.headers['x-translation-cursor'])
        assert tail.headers['x-translation-status'] == 'deferred'
        assert 'x-translation-cursor' not in tail.headers
    assert counts('absent', (*paid_events, 'detail_returned')) == [*absent_before[:3], absent_before[3] + 4]
    for call in (reserve, release, provider_call, materialize, open_recording, first_open, get_cached_language):
        call.assert_not_called()
    assert store.rows[path] == snapshot
    assert not cache_store.puts and not cache_store.negative

    assert client.get(url, headers=gui).status_code == 200
    reserve.assert_not_called()
    positive = read(gui)
    reserve.assert_called_once()
    provider_call.assert_called_once()
    materialize.assert_called_once()
    release.assert_called_once()
    assert positive.headers['x-translation-status'] == 'partial'
    assert positive.json()['transcript_segments'][0]['translations'] == [{'lang': 'en', 'text': translated_text}]
    assert materialize.call_args.args[:4] == (uid, cid, 's0', detail['transcript_segments'][0]['text'])
    assert materialize.call_args.kwargs['reservation'] is reservation
    assert counts('present', paid_events) == [value + 1 for value in present_before]
    after_open = deepcopy(store.rows[path])
    assert after_open != snapshot
    cache_puts_after_open = list(cache_store.puts)

    gui_cursor = positive.headers['x-translation-cursor']
    stored_page = read(cursor=gui_cursor)
    assert stored_page.headers['x-translation-status'] == 'partial'
    assert stored_page.json()['transcript_segments'][0]['translations'] == [{'lang': 'en', 'text': translated_text}]
    assert read(cursor=stored_page.headers['x-translation-cursor']).headers['x-translation-status'] == 'deferred'
    assert read({'X-Omi-Recording-Detail': 'true'}, cursor=gui_cursor).headers['x-translation-status'] == 'partial'
    assert client.get(url, params={**opt_in, 'translation_cursor': 'invalid'}).status_code == 400
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '0')
    assert read().headers['x-translation-status'] == 'partial'
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '1000000')
    monkeypatch.setenv('TRANSLATION_ONOPEN_ENABLED', 'false')
    assert read(gui, cursor=gui_cursor).headers['x-translation-status'] == 'partial'
    assert read().headers['x-translation-status'] == 'partial'
    assert store.rows[path] == after_open
    assert cache_store.puts == cache_puts_after_open and not cache_store.negative
    assert counts('absent', paid_events) == absent_before[:3]
    assert counts('present', paid_events) == [value + 1 for value in present_before]
    for call in (reserve, release, provider_call, materialize, get_cached_language):
        call.assert_called_once()
    first_open.assert_not_called()
