import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.routers import speech_profile as sp


client = TestClient(sp.router)


@patch('backend.routers.speech_profile.get_profile_audio_if_exists')
@patch('backend.routers.speech_profile.add_shared_person_to_user')
@patch('backend.routers.speech_profile.redis_db')
def test_share_endpoint_calls_add_and_publishes(mock_redis, mock_add_shared, mock_get_profile):
    mock_get_profile.return_value = 'http://example.com/profile.wav'
    mock_redis.r = MagicMock()

    # Simulate auth dependency by passing uid param via query
    response = client.post('/v3/speech-profile/share?target_uid=target&name=Bob&uid=caller')
    assert response.status_code == 200
    mock_add_shared.assert_called()
    mock_redis.r.publish.assert_called()


@patch('backend.routers.speech_profile.remove_shared_person_from_user')
@patch('backend.routers.speech_profile.redis_db')
def test_revoke_endpoint_calls_remove_and_publishes(mock_redis, mock_remove):
    mock_remove.return_value = True
    mock_redis.r = MagicMock()
    response = client.post('/v3/speech-profile/revoke?target_uid=target&uid=caller')
    assert response.status_code == 200
    mock_remove.assert_called()
    mock_redis.r.publish.assert_called()
