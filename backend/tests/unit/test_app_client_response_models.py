from typing import Optional

from pydantic import TypeAdapter

from routers.apps import UnapprovedPublicAppResponse
from routers.mcp import McpScreenActivitySummaryResponse
from routers.users import AIUserProfileResponse, AssistantSettingsResponse


def test_ai_profile_response_preserves_missing_profile_null():
    adapter = TypeAdapter(Optional[AIUserProfileResponse])

    assert adapter.validate_python(None) is None


def test_assistant_settings_response_keeps_forward_compatible_sections():
    response = AssistantSettingsResponse.model_validate(
        {
            'focus': {'enabled': True},
            'update_channel': 'beta',
            'future_section': {'enabled': False, 'threshold': 3},
        }
    )

    assert response.model_dump()['future_section'] == {'enabled': False, 'threshold': 3}


def test_unapproved_public_app_response_tolerates_legacy_partial_docs():
    response = UnapprovedPublicAppResponse.model_validate(
        {
            'id': 'legacy-app',
            'approved': False,
            'private': False,
            'unexpected_admin_note': 'needs cleanup',
        }
    )

    assert response.id == 'legacy-app'
    assert response.capabilities == []
    assert response.model_dump()['unexpected_admin_note'] == 'needs cleanup'


def test_mcp_screen_activity_summary_response_models_known_shape():
    response = McpScreenActivitySummaryResponse.model_validate(
        {
            'apps': {
                'Omi': {
                    'count': 2,
                    'first_seen': '2026-07-03T10:00:00Z',
                    'last_seen': '2026-07-03T10:05:00Z',
                    'window_titles': ['Main'],
                }
            },
            'total_screenshots': 2,
        }
    )

    assert response.apps['Omi'].count == 2
    assert response.apps['Omi'].window_titles == ['Main']
    assert response.total_screenshots == 2
