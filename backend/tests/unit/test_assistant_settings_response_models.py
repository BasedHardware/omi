import json
from pathlib import Path

from routers.users import AssistantSettingsResponse

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'


def test_assistant_settings_response_keeps_forward_compatible_sections():
    response = AssistantSettingsResponse.model_validate(
        {
            'focus': {'enabled': True},
            'update_channel': 'beta',
            'future_section': {'enabled': False, 'threshold': 3},
        }
    )

    assert response.model_dump()['future_section'] == {'enabled': False, 'threshold': 3}


def test_assistant_settings_model_schema_exposes_known_fields_and_allows_future_sections():
    schema = AssistantSettingsResponse.model_json_schema()

    assert schema['title'] == 'AssistantSettingsResponse'
    assert schema.get('additionalProperties') is True
    assert {'shared', 'focus', 'task', 'advice', 'memory', 'floating_bar', 'update_channel'} <= set(
        schema['properties']
    )


def test_app_client_openapi_assistant_settings_response_exposes_known_fields_and_allows_future_sections():
    spec = json.loads(SPEC_PATH.read_text())
    schema = spec['components']['schemas']['AssistantSettingsResponse']

    assert schema['title'] == 'AssistantSettingsResponse'
    assert schema.get('additionalProperties') is True
    assert {'shared', 'focus', 'task', 'advice', 'memory', 'floating_bar', 'update_channel'} <= set(
        schema['properties']
    )
