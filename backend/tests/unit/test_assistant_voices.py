import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from config.assistant_voices import (
    ASSISTANT_VOICES,
    DEFAULT_ASSISTANT_VOICE,
    normalize_assistant_voice,
)
from database import voice_preferences
from models.tts import DEFAULT_VOICE_ID, TtsSynthesizeRequest
from routers import desktop_tts_updates as desktop_router
from routers import tts as tts_router
from utils import tts as tts_utils

EXPECTED_VOICES = (
    'Zephyr',
    'Puck',
    'Charon',
    'Kore',
    'Fenrir',
    'Leda',
    'Orus',
    'Aoede',
    'Callirrhoe',
    'Autonoe',
    'Enceladus',
    'Iapetus',
    'Umbriel',
    'Algieba',
    'Despina',
    'Erinome',
    'Algenib',
    'Rasalgethi',
    'Laomedeia',
    'Achernar',
    'Alnilam',
    'Schedar',
    'Gacrux',
    'Pulcherrima',
    'Achird',
    'Zubenelgenubi',
    'Vindemiatrix',
    'Sadachbia',
    'Sadaltager',
    'Sulafat',
)


def test_catalog_is_the_curated_thirty_gemini_voices():
    assert ASSISTANT_VOICES == EXPECTED_VOICES
    assert len(set(ASSISTANT_VOICES)) == 30
    assert DEFAULT_ASSISTANT_VOICE == 'Charon'


@pytest.mark.parametrize('voice', EXPECTED_VOICES)
def test_normalize_accepts_every_catalog_voice(voice):
    assert normalize_assistant_voice(voice) == voice


@pytest.mark.parametrize('client', ['mobile', 'desktop'])
@pytest.mark.parametrize('voice', EXPECTED_VOICES)
def test_gemini_voice_map_accepts_every_catalog_voice(client, voice):
    assert tts_utils.map_gemini_voice(voice, client) == voice


@pytest.mark.parametrize(
    'value', [None, '', '  ', 'kore', 'KORE', 'Nova', 'Sloane', '../history', 'BAMYoBHLZM7lJgJAmFz0']
)
def test_normalize_rejects_empty_unknown_and_legacy_ids(value):
    assert normalize_assistant_voice(value) == 'Charon'


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocument:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self):
        return _FakeSnapshot(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        if merge:
            self._store.docs.setdefault(self._path, {}).update(data)
        else:
            self._store.docs[self._path] = dict(data)


class _FakeCollection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id):
        return _FakeDocument(self._store, f'{self._name}/{doc_id}')


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def collection(self, name):
        return _FakeCollection(self, name)


def test_missing_document_and_field_fall_back_to_default():
    db = _FakeDb()
    assert voice_preferences.get_assistant_voice('u1', firestore_client=db) == 'Charon'
    db = _FakeDb({'users/u1': {'display_name': 'x'}})
    assert voice_preferences.get_assistant_voice('u1', firestore_client=db) == 'Charon'


def test_invalid_stored_voice_falls_back_to_default():
    db = _FakeDb({'users/u1': {'assistant_voice_id': 'not-a-voice'}})
    assert voice_preferences.get_assistant_voice('u1', firestore_client=db) == 'Charon'


def test_set_merges_without_clobbering_siblings_and_roundtrips():
    db = _FakeDb({'users/u1': {'display_name': 'Ada', 'assistant_voice_id': 'Charon'}})
    assert voice_preferences.set_assistant_voice('u1', 'Kore', firestore_client=db) == 'Kore'
    assert db.docs['users/u1'] == {'display_name': 'Ada', 'assistant_voice_id': 'Kore'}
    assert voice_preferences.get_assistant_voice('u1', firestore_client=db) == 'Kore'


def test_set_normalizes_unknown_before_persisting():
    db = _FakeDb()
    assert voice_preferences.set_assistant_voice('u1', 'NotARealVoice', firestore_client=db) == 'Charon'
    assert db.docs['users/u1']['assistant_voice_id'] == 'Charon'


def test_preferences_are_scoped_per_user():
    db = _FakeDb()
    voice_preferences.set_assistant_voice('u1', 'Puck', firestore_client=db)
    voice_preferences.set_assistant_voice('u2', 'Kore', firestore_client=db)
    assert voice_preferences.get_assistant_voice('u1', firestore_client=db) == 'Puck'
    assert voice_preferences.get_assistant_voice('u2', firestore_client=db) == 'Kore'
    assert voice_preferences.get_assistant_voice('u3', firestore_client=db) == 'Charon'


def _voice_client(monkeypatch, uid='test-uid'):
    db = _FakeDb()
    monkeypatch.setattr(voice_preferences, 'get_data_plane_firestore_client', lambda: db)
    app = FastAPI()
    app.include_router(tts_router.router)
    app.dependency_overrides[tts_router.auth.get_current_user_uid] = lambda: uid
    return TestClient(app), db


def test_voices_catalog_route_lists_every_voice_with_default(monkeypatch):
    client, _db = _voice_client(monkeypatch)
    response = client.get('/v1/tts/voices')
    assert response.status_code == 200
    data = response.json()
    assert [v['id'] for v in data['voices']] == list(EXPECTED_VOICES)
    assert all(v['name'] == v['id'] for v in data['voices'])
    assert data['default_voice_id'] == 'Charon'


def test_user_voice_get_normalizes_and_patch_persists(monkeypatch):
    client, db = _voice_client(monkeypatch)
    assert client.get('/v1/users/voice').json() == {'voice_id': 'Charon'}
    assert client.patch('/v1/users/voice', json={'voice_id': 'Kore'}).json() == {'voice_id': 'Kore'}
    assert db.docs['users/test-uid']['assistant_voice_id'] == 'Kore'
    assert client.get('/v1/users/voice').json() == {'voice_id': 'Kore'}


def test_user_voice_patch_normalizes_unknown_to_default(monkeypatch):
    client, db = _voice_client(monkeypatch)
    response = client.patch('/v1/users/voice', json={'voice_id': 'totally-made-up'})
    assert response.json() == {'voice_id': 'Charon'}
    assert db.docs['users/test-uid']['assistant_voice_id'] == 'Charon'


def test_default_resolver_uses_data_plane_not_compute_client(monkeypatch):
    data_plane = _FakeDb({'users/u1': {'assistant_voice_id': 'Kore'}})
    monkeypatch.setattr(voice_preferences, 'get_data_plane_firestore_client', lambda: data_plane)

    def compute_client():
        raise AssertionError('compute-plane get_firestore_client must not resolve user voice preferences')

    monkeypatch.setattr(voice_preferences, 'get_firestore_client', compute_client, raising=False)
    assert voice_preferences.get_assistant_voice('u1') == 'Kore'
    assert voice_preferences.set_assistant_voice('u1', 'Puck') == 'Puck'
    assert data_plane.docs['users/u1']['assistant_voice_id'] == 'Puck'


def test_user_voice_routes_do_not_leak_between_users(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(voice_preferences, 'get_data_plane_firestore_client', lambda: db)
    app = FastAPI()
    app.include_router(tts_router.router)
    current_uid = {'value': 'u1'}
    app.dependency_overrides[tts_router.auth.get_current_user_uid] = lambda: current_uid['value']
    client = TestClient(app)

    client.patch('/v1/users/voice', json={'voice_id': 'Puck'})
    current_uid['value'] = 'u2'
    assert client.get('/v1/users/voice').json() == {'voice_id': 'Charon'}
    client.patch('/v1/users/voice', json={'voice_id': 'Kore'})
    current_uid['value'] = 'u1'
    assert client.get('/v1/users/voice').json() == {'voice_id': 'Puck'}


def test_gemini_voice_map_keeps_legacy_alias_and_unknown_defaults():
    assert tts_utils.map_gemini_voice('BAMYoBHLZM7lJgJAmFz0', 'mobile') == 'Charon'
    assert tts_utils.map_gemini_voice('shimmer', 'desktop') == 'Aoede'
    assert tts_utils.map_gemini_voice('UnknownVoice1', 'mobile') == 'Charon'
    assert tts_utils.map_gemini_voice('kore', 'desktop') == 'Charon'


async def _audio_chunks():
    yield b'mp3'


async def _allow_all_blocking(_executor, function, *_args, **_kwargs):
    if function is voice_preferences.get_assistant_voice:
        return 'Puck'
    return 0, None


@pytest.mark.asyncio
async def test_mobile_omitted_voice_resolves_stored_preference(monkeypatch):
    calls = []

    async def open_stream(**kwargs):
        calls.append(kwargs)
        return _audio_chunks()

    monkeypatch.setattr(tts_router, 'run_blocking', _allow_all_blocking)
    monkeypatch.setattr(tts_router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(tts_router, 'open_gemini_mp3_stream', open_stream)

    await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')

    assert calls == [{'text': 'hello', 'voice_id': 'Puck', 'client': 'mobile'}]


@pytest.mark.asyncio
async def test_mobile_explicit_voice_does_not_read_preference(monkeypatch):
    calls = []

    async def open_stream(**kwargs):
        calls.append(kwargs)
        return _audio_chunks()

    read_calls = []

    async def run_blocking(_executor, function, *_args, **_kwargs):
        read_calls.append(function)
        return 0, None

    monkeypatch.setattr(tts_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(tts_router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(tts_router, 'open_gemini_mp3_stream', open_stream)

    await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello', voice_id='Kore'), uid='u')

    assert calls == [{'text': 'hello', 'voice_id': 'Kore', 'client': 'mobile'}]
    assert voice_preferences.get_assistant_voice not in read_calls


class _LegacyUpstreamResponse:
    status_code = 400

    async def aread(self):
        return b'err'


class _LegacyStreamContext:
    async def __aenter__(self):
        return _LegacyUpstreamResponse()

    async def __aexit__(self, *_args):
        return None


def _legacy_client(captured):
    class _FakeClient:
        def stream(self, method, url, **kwargs):
            captured['url'] = url
            return _LegacyStreamContext()

    return _FakeClient()


def _monkeypatch_mobile_legacy(monkeypatch, captured):
    monkeypatch.setattr(tts_router, 'run_blocking', _allow_all_blocking)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'el-key')
    monkeypatch.setattr(tts_router, 'get_tts_client', lambda: _legacy_client(captured))
    monkeypatch.setattr(tts_router, 'get_tts_semaphore', lambda: __import__('asyncio').Semaphore(1))


@pytest.mark.asyncio
async def test_mobile_legacy_maps_gemini_voice_to_released_default(monkeypatch):
    captured = {}
    _monkeypatch_mobile_legacy(monkeypatch, captured)

    with pytest.raises(HTTPException) as exc_info:
        await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello', voice_id='Kore'), uid='u')

    assert exc_info.value.status_code == 400
    assert captured['url'] == f'https://api.elevenlabs.io/v1/text-to-speech/{DEFAULT_VOICE_ID}'


@pytest.mark.asyncio
async def test_mobile_legacy_maps_unknown_voice_to_released_default(monkeypatch):
    captured = {}
    _monkeypatch_mobile_legacy(monkeypatch, captured)

    with pytest.raises(HTTPException):
        await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello', voice_id='elevenLabsVoice9'), uid='u')

    assert captured['url'] == f'https://api.elevenlabs.io/v1/text-to-speech/{DEFAULT_VOICE_ID}'


@pytest.mark.asyncio
async def test_desktop_omitted_voice_resolves_stored_preference(monkeypatch):
    calls = []

    async def open_stream(**kwargs):
        calls.append(kwargs)
        return _audio_chunks()

    async def run_blocking(_executor, function, *_args, **_kwargs):
        if function is desktop_router.get_assistant_voice:
            return 'Kore'
        if function is desktop_router.is_desktop_trial_paywalled:
            return False
        return 0, None

    monkeypatch.setattr(desktop_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_router, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(desktop_router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(desktop_router, 'open_gemini_mp3_stream', open_stream)

    await desktop_router.tts_synthesize(desktop_router.TtsSynthesizeRequest(text='hello'), uid='u')

    assert calls == [{'text': 'hello', 'voice_id': 'Kore', 'client': 'desktop', 'style': None}]


def _desktop_legacy_mocks(monkeypatch, payloads):
    class _FakeUpstream:
        is_error = False
        status_code = 200
        content = b'mp3'

    async def fake_openai(payload, _api_key):
        payloads.append(payload)
        return _FakeUpstream()

    async def run_blocking(_executor, function, *_args, **_kwargs):
        if function is desktop_router.is_desktop_trial_paywalled:
            return False
        return 0, None

    monkeypatch.setattr(desktop_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_router, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(desktop_router, '_openai_tts', fake_openai)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')


@pytest.mark.asyncio
async def test_desktop_legacy_maps_gemini_voice_to_fixed_openai_default(monkeypatch):
    payloads = []
    _desktop_legacy_mocks(monkeypatch, payloads)

    response = await desktop_router.tts_synthesize(
        desktop_router.TtsSynthesizeRequest(text='hello', voice_id='Kore'), uid='u'
    )

    assert response.status_code == 200
    assert payloads[0]['voice'] == 'cedar'


@pytest.mark.asyncio
async def test_desktop_legacy_keeps_allowed_openai_voice(monkeypatch):
    payloads = []
    _desktop_legacy_mocks(monkeypatch, payloads)

    await desktop_router.tts_synthesize(desktop_router.TtsSynthesizeRequest(text='hello', voice_id='nova'), uid='u')

    assert payloads[0]['voice'] == 'nova'


@pytest.mark.asyncio
async def test_desktop_rejects_invalid_voice_name_on_both_providers(monkeypatch):
    for provider in ('gemini', 'legacy'):
        monkeypatch.setenv('TTS_PROVIDER', provider)
        with pytest.raises(HTTPException) as exc_info:
            await desktop_router.tts_synthesize(
                desktop_router.TtsSynthesizeRequest(text='hello', voice_id='../bad path'), uid='u'
            )
        assert exc_info.value.status_code == 400
