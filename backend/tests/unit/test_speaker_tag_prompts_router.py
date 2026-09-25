import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.speaker_tag_prompts import SpeakerTagPromptQualityOutcome, SpeakerTagPromptsResponse
from routers import speaker_tag_prompts as router_module


def _client(monkeypatch):
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: 'u'
    for route in router_module.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.call is not router_module.auth.get_current_user_uid and dependency.name == 'uid':
                app.dependency_overrides[dependency.call] = lambda: 'u'
    return TestClient(app)


def _answer_body(**extra):
    body = {
        'prompt_id': 'pid',
        'kind': 'identify',
        'origin': 'unnamed',
        'conversation_id': 'c1',
        'speaker_id': 1,
        'segment_ids': ['s1'],
        'answer': 'person',
        'person_id': 'p1',
    }
    body.update(extra)
    return body


def test_list_returns_service_payload(monkeypatch):
    monkeypatch.setattr(router_module.service, 'get_prompts', lambda uid: SpeakerTagPromptsResponse(status='cooldown'))
    response = _client(monkeypatch).get('/v1/speaker-tag-prompts')
    assert response.status_code == 200 and response.json()['status'] == 'cooldown'


def test_answer_maps_entitlement_and_validation_errors(monkeypatch):
    client = _client(monkeypatch)

    def forbidden(*args, **kwargs):
        raise router_module.service.TagPromptForbidden('paid')

    monkeypatch.setattr(router_module.service, 'apply_answer', forbidden)
    assert client.post('/v1/speaker-tag-prompts/answer', json=_answer_body()).status_code == 402

    def missing(*args, **kwargs):
        raise LookupError('Person not found')

    monkeypatch.setattr(router_module.service, 'apply_answer', missing)
    assert client.post('/v1/speaker-tag-prompts/answer', json=_answer_body()).status_code == 404
    assert client.post('/v1/speaker-tag-prompts/answer', json=_answer_body(extra='x')).status_code == 422


def test_answer_success(monkeypatch):
    seen = {}

    def apply(uid, data, schedule=None):
        seen['uid'] = uid
        return {'status': 'ok', 'quality_outcome': SpeakerTagPromptQualityOutcome.person_missed_known}

    monkeypatch.setattr(router_module.service, 'apply_answer', apply)
    response = _client(monkeypatch).post('/v1/speaker-tag-prompts/answer', json=_answer_body())
    assert response.status_code == 200 and response.json()['quality_outcome'] == 'person_missed_known'
    assert seen['uid'] == 'u'


def test_clip_rejects_long_windows_and_missing_audio(monkeypatch):
    client = _client(monkeypatch)
    assert (
        client.get('/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 0, 'end': 30}).status_code
        == 400
    )
    monkeypatch.setattr(router_module.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *a: None)
    assert (
        client.get('/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 0, 'end': 5}).status_code
        == 404
    )
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *a: b'\x00\x00' * 160)
    response = client.get('/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 0, 'end': 5})
    assert response.status_code == 200
    body = response.json()
    assert body['content_type'] == 'audio/wav' and body['duration_seconds'] == 0.01
    assert base64.b64decode(body['audio_base64'])[:4] == b'RIFF'


def test_clip_rejects_deleted_and_locked_before_storage(monkeypatch):
    client = _client(monkeypatch)
    seen = []
    clips = []

    def get_conversation(uid, cid):
        seen.append((uid, cid))
        return {'id': cid, 'deleted': cid == 'deleted-c', 'is_locked': cid == 'locked-c'}

    monkeypatch.setattr(router_module.conversations_db, 'get_conversation', get_conversation)
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *a: clips.append(a) or b'')
    assert (
        client.get(
            '/v1/speaker-tag-prompts/clip', params={'conversation_id': 'deleted-c', 'start': 0, 'end': 5}
        ).status_code
        == 404
    )
    assert (
        client.get(
            '/v1/speaker-tag-prompts/clip', params={'conversation_id': 'locked-c', 'start': 0, 'end': 5}
        ).status_code
        == 402
    )
    assert seen == [('u', 'deleted-c'), ('u', 'locked-c')]
    assert clips == []


def test_settings_patch_passes_source_and_drops_it_from_updates(monkeypatch):
    seen = {}

    def update(uid, updates, source):
        seen.update(updates=updates, source=source)
        return {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': False}

    monkeypatch.setattr(router_module.service, 'update_settings', update)
    response = _client(monkeypatch).patch(
        '/v1/users/voice-profile-settings', json={'save_other_voice_profiles': False, 'source': 'first_prompt'}
    )
    assert response.status_code == 200 and response.json()['save_other_voice_profiles'] is False
    assert seen == {'updates': {'save_other_voice_profiles': False}, 'source': 'first_prompt'}
    bad = _client(monkeypatch).patch('/v1/users/voice-profile-settings', json={'source': 'push'})
    assert bad.status_code == 422
