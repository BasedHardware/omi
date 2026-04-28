from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException

from models.app import App
from routers import apps as apps_router
from routers.sync import (
    AmbientFallbackSegmentsRequest,
    AmbientFallbackSegmentIn,
    AmbientTelemetryEventIn,
    get_timestamp_from_path,
    ingest_ambient_capture_telemetry,
    ingest_ambient_fallback_segments,
)


def _controller_app(capability=True):
    return {
        'id': 'controller-app',
        'name': 'Ambient Controller',
        'private': False,
        'approved': True,
        'status': 'approved',
        'category': 'utilities-and-tools',
        'author': 'Omi',
        'description': 'Controls ambient capture policy',
        'image': '',
        'capabilities': ['ambient_capture_controller'] if capability else ['chat'],
        'rating_count': 0,
        'enabled': True,
        'is_paid': False,
        'is_user_paid': False,
        'external_integration': {
            'capture_policy_url': 'https://controller.example/policy',
            'capture_controller_public_key': 'public-key',
            'capture_controller_key_id': 'kid-1',
        },
    }


def test_app_model_accepts_ambient_capture_controller_fields():
    app = App(**_controller_app())
    assert 'ambient_capture_controller' in app.capabilities
    assert app.external_integration.capture_policy_url == 'https://controller.example/policy'
    assert app.external_integration.capture_controller_key_id == 'kid-1'


def test_only_capable_enabled_app_can_be_selected(monkeypatch):
    saved = {}
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda app_id, uid: _controller_app())
    monkeypatch.setattr(apps_router, 'is_app_enabled', lambda uid, app_id: True)
    monkeypatch.setattr(
        apps_router.users_db,
        'set_active_ambient_capture_controller',
        lambda uid, device_id, app_id, key_fingerprint=None: saved.update(
            {'uid': uid, 'device_id': device_id, 'app_id': app_id, 'key_fingerprint': key_fingerprint}
        ),
    )

    result = apps_router.select_ambient_capture_controller('controller-app', 'device-1', uid='user-1')

    assert result['status'] == 'ok'
    assert saved['app_id'] == 'controller-app'
    assert saved['device_id'] == 'device-1'


def test_unauthorized_plugin_cannot_control_policy(monkeypatch):
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda app_id, uid: _controller_app(capability=False))

    with pytest.raises(HTTPException) as exc:
        apps_router.select_ambient_capture_controller('controller-app', 'device-1', uid='user-1')

    assert exc.value.status_code == 422


def test_fallback_segment_route_creates_conversation(monkeypatch):
    stored = {}
    monkeypatch.setattr('routers.sync.conversations_db.get_conversation', lambda uid, conversation_id: None)
    monkeypatch.setattr(
        'routers.sync.conversations_db.upsert_conversation',
        lambda uid, conversation: stored.update({'uid': uid, 'conversation': conversation}),
    )
    monkeypatch.setattr(
        'routers.sync._reprocess_conversation_after_update',
        lambda uid, conversation_id, language: None,
    )

    now = datetime.now(timezone.utc)
    request = AmbientFallbackSegmentsRequest(
        device_id='android-ambient-phone-mic',
        segments=[
            AmbientFallbackSegmentIn(
                text='Caption text',
                source='accessibility_caption',
                start=now,
                end=now + timedelta(seconds=1),
                health_state='TEXT_ONLY_FALLBACK',
            )
        ],
    )

    result = ingest_ambient_fallback_segments(request, uid='user-1')

    assert result['segments'] == 1
    assert stored['uid'] == 'user-1'
    assert stored['conversation']['external_data']['ambient_capture']['fallback_only'] is True
    assert (
        stored['conversation']['external_data']['ambient_capture']['fallback_segments'][0]['source']
        == 'accessibility_caption'
    )
    assert stored['conversation']['transcript_segments'][0]['stt_provider'] == 'ambient_fallback:accessibility_caption'


def test_ambient_spool_timestamp_parser_uses_session_start():
    assert get_timestamp_from_path('ambient_android_pcm16_16000_1_1767225600_0000.bin') == 1767225600
    assert get_timestamp_from_path('/tmp/audio_pcm16_16000_1_1767225600000.bin') == 1767225600


def test_ambient_telemetry_rejects_transcript_payload():
    event = AmbientTelemetryEventIn(
        type='policy_rejected',
        timestamp=datetime.now(timezone.utc),
        metadata={'transcript': 'should-not-be-here'},
    )

    with pytest.raises(HTTPException) as exc:
        ingest_ambient_capture_telemetry(event, uid='user-1')

    assert exc.value.status_code == 422
