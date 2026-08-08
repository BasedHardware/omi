from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from scripts.render_gke_backend_config import config_map_entries

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_config_map_entries_reads_manifest_metadata(tmp_path: Path) -> None:
    manifest = {
        'environments': {
            'dev': {
                'gke': {
                    'config_map': {
                        'name': 'custom-backend-config',
                        'entries': {
                            'REDIS_DB_HOST': {'source': 'environment'},
                        },
                    }
                }
            }
        }
    }
    manifest_path = tmp_path / 'runtime_env.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    os.environ['REDIS_DB_HOST'] = '10.0.0.1'

    name, entries = config_map_entries('dev', manifest_path)

    assert name == 'custom-backend-config'
    assert entries == {'REDIS_DB_HOST': '10.0.0.1'}


def test_config_map_entries_falls_back_to_legacy_manifest_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = {
        'environments': {
            'dev': {
                'gke': {
                    'region': 'us-central1',
                }
            }
        }
    }
    manifest_path = tmp_path / 'runtime_env.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    for key in (
        'CONVERSATION_SUMMARIZED_APP_IDS',
        'GOOGLE_CLIENT_ID',
        'MCP_AUTHORIZATION_SERVER_URL',
        'MCP_OAUTH_CHATGPT_CLIENT_ID',
        'MCP_OAUTH_CHATGPT_REDIRECT_URIS',
        'MCP_OAUTH_PUBLIC_CLIENT_ID',
        'MCP_OAUTH_PUBLIC_REDIRECT_URIS',
        'MCP_RESOURCE_URL',
        'RAPID_API_HOST',
        'REDIS_DB_HOST',
        'STT_PRERECORDED_MODEL',
        'STT_SERVICE_MODELS',
        'TYPESENSE_HOST',
        'TWILIO_ACCOUNT_SID',
        'TWILIO_API_KEY_SID',
        'TWILIO_TWIML_APP_SID',
        'X_OAUTH_CLIENT_ID',
        'X_OAUTH_REDIRECT_URI',
    ):
        monkeypatch.setenv(key, f'value-for-{key}')

    name, entries = config_map_entries('dev', manifest_path)

    assert name == 'dev-omi-backend-config'
    assert entries['REDIS_DB_HOST'] == 'value-for-REDIS_DB_HOST'
    assert entries['GOOGLE_CLIENT_ID'] == 'value-for-GOOGLE_CLIENT_ID'
