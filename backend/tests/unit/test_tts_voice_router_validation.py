"""PATCH /v1/users/voice maps the codec's invalid-uid ValueError to 400."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.tts as tts_router
from models.tts import AssistantVoicePreferenceUpdate


def test_update_user_voice_maps_invalid_uid_to_400():
    request = AssistantVoicePreferenceUpdate(voice_id='ash')
    with patch.object(tts_router.voice_preferences, 'set_assistant_voice', side_effect=ValueError('invalid_uid')):
        with pytest.raises(HTTPException) as exc:
            tts_router.update_user_voice(request, uid='   ')
    assert exc.value.status_code == 400
    assert exc.value.detail == 'invalid_uid'
