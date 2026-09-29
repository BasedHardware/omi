import base64
from datetime import datetime, timezone

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
    res_forbidden = client.post('/v1/speaker-tag-prompts/answer', json=_answer_body())
    assert res_forbidden.status_code == 402
    assert res_forbidden.json()['detail'] == 'A paid plan is required to perform this action.'

    def missing(*args, **kwargs):
        raise LookupError('Person not found')

    monkeypatch.setattr(router_module.service, 'apply_answer', missing)
    res_missing = client.post('/v1/speaker-tag-prompts/answer', json=_answer_body())
    assert res_missing.status_code == 404
    assert res_missing.json()['detail'] == 'Person or conversation not found'
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
    started = datetime(2026, 9, 26, tzinfo=timezone.utc)
    row = {
        'id': 'c1',
        'started_at': started,
        'audio_files': [{'chunk_timestamps': [started.timestamp()], 'duration': 10.0}],
        'transcript_segments': [{'start': 0, 'end': 5, 'speaker_id': 0, 'text': 'one two three four five'}],
    }
    monkeypatch.setattr(router_module.conversations_db, 'get_conversation', lambda uid, cid: row)
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *a: None)
    assert (
        client.get('/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 0, 'end': 5}).status_code
        == 404
    )
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *a: b'\x00\x00' * (5 * 16000))
    monkeypatch.setattr(router_module.service, 'verified_clip_pcm', lambda uid, row, start, end, text, pcm: pcm)
    response = client.get('/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 0, 'end': 5})
    assert response.status_code == 200
    body = response.json()
    assert body['content_type'] == 'audio/wav' and body['duration_seconds'] == 5.0
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


def test_clip_endpoint_rejects_uncovered_legacy_window_without_download(monkeypatch):
    started = datetime(2026, 9, 25, 7, 33, 17, tzinfo=timezone.utc)
    row = {
        'id': 'c1',
        'started_at': started,
        'audio_files': [{'chunk_timestamps': [started.timestamp() + 2692], 'duration': 60.0}],
    }
    monkeypatch.setattr(router_module.conversations_db, 'get_conversation', lambda uid, cid: row)
    downloads = []
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *args: downloads.append(1) or b'pcm')
    response = _client(monkeypatch).get(
        '/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 45.61, 'end': 55.61}
    )
    assert response.status_code == 404 and downloads == []


def test_clip_endpoint_rejects_unmatched_audio(monkeypatch):
    started = datetime(2026, 9, 26, tzinfo=timezone.utc)
    row = {
        'id': 'c1',
        'started_at': started,
        'audio_files': [{'chunk_timestamps': [started.timestamp()], 'duration': 92.3}],
        'transcript_segments': [
            {'start': 10.28, 'end': 20.28, 'speaker_id': 0, 'text': 'The expected conversation words'}
        ],
        'sync_merged_from': ['donor'],
    }
    monkeypatch.setattr(router_module.conversations_db, 'get_conversation', lambda uid, cid: row)
    monkeypatch.setattr(router_module, 'conversation_clip_pcm', lambda *args: b'\x00\x00' * 160000)
    monkeypatch.setattr(router_module.service, 'verified_clip_pcm', lambda *args: None)
    response = _client(monkeypatch).get(
        '/v1/speaker-tag-prompts/clip', params={'conversation_id': 'c1', 'start': 10.28, 'end': 20.28}
    )
    assert response.status_code == 404


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


def test_answer_sanitizes_pii_and_tokens_in_error(monkeypatch):
    client = _client(monkeypatch)

    def invalid_with_token(*args, **kwargs):
        raise router_module.service.TagPromptInvalid(
            'Invalid prompt auth=tok_secret123456789 and user=alice@example.com'
        )

    monkeypatch.setattr(router_module.service, 'apply_answer', invalid_with_token)
    res = client.post('/v1/speaker-tag-prompts/answer', json=_answer_body())
    assert res.status_code == 400
    assert res.json()['detail'] == 'Invalid speaker tag prompt answer'


def test_answer_unhandled_exception_masks_internal_error(monkeypatch):
    client = _client(monkeypatch)

    def crash(*args, **kwargs):
        raise RuntimeError('Raw internal database crash secret_db_key_999')

    monkeypatch.setattr(router_module.service, 'apply_answer', crash)
    res = client.post('/v1/speaker-tag-prompts/answer', json=_answer_body())
    assert res.status_code == 500
    assert res.json()['detail'] == 'Internal server error'
    assert 'secret_db_key_999' not in res.text


def test_router_endpoints_mask_unexpected_exceptions(monkeypatch):
    client = _client(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError('Service failure')

    monkeypatch.setattr(router_module.service, 'get_prompts', fail)
    res = client.get('/v1/speaker-tag-prompts')
    assert res.status_code == 500
    assert res.json()['detail'] == 'Failed to retrieve speaker tag prompts'

    monkeypatch.setattr(router_module.service, 'mark_shown', fail)
    res = client.post('/v1/speaker-tag-prompts/shown', json={'prompt_ids': ['p1']})
    assert res.status_code == 500
    assert res.json()['detail'] == 'Failed to mark speaker tag prompts shown'

    monkeypatch.setattr(router_module.service, 'mark_dismissed', fail)
    res = client.post('/v1/speaker-tag-prompts/dismiss')
    assert res.status_code == 500
    assert res.json()['detail'] == 'Failed to dismiss speaker tag prompts'

    monkeypatch.setattr(router_module.voice_profiles_db, 'get_voice_profile_settings', fail)
    res = client.get('/v1/users/voice-profile-settings')
    assert res.status_code == 500
    assert res.json()['detail'] == 'Failed to fetch voice profile settings'

    monkeypatch.setattr(router_module.service, 'update_settings', fail)
    res = client.patch('/v1/users/voice-profile-settings', json={'speaker_tag_prompts_enabled': False})
    assert res.status_code == 500
    assert res.json()['detail'] == 'Failed to update voice profile settings'
