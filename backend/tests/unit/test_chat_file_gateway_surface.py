"""File chat is an acknowledged direct surface under gateway feature mode — uploads must not raise.

After prod flipped OMI_LLM_GATEWAY_FEATURE_MODE=gateway (PR #11281), every POST /v2/files 500'd:
FileChatTool.upload() called raise_if_gateway_feature_mode_blocks_direct_model_surface, which raised
GatewayDirectModelSurfaceBlocked because file chat runs directly on OpenAI Files/Assistants/vision and
has no gateway lane. The surface is now recorded via record_direct_exception_surface and never blocked.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from types import SimpleNamespace
from unittest.mock import patch

import utils.other.chat_file as cf  # noqa: E402
from utils.llm.gateway_client import LLM_GATEWAY_FEATURE_MODE_ENV_VAR  # noqa: E402


def _gateway_mode(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)


def test_upload_proceeds_and_records_surface_under_gateway_mode(monkeypatch, tmp_path):
    _gateway_mode(monkeypatch)
    file_path = tmp_path / 'note.txt'
    file_path.write_text('hello')

    fake_files = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(id='file-1', filename='note.txt'))
    with patch.object(cf.openai, 'files', fake_files), patch.object(cf, 'record_direct_exception_surface') as record:
        result = cf.FileChatTool.upload(file_path)

    assert result['file_id'] == 'file-1'
    record.assert_called_once_with(surface='file_chat.openai_files_assistants_vision')


def test_upload_proceeds_when_gateway_mode_is_misconfigured_in_prod(monkeypatch, tmp_path):
    # Prod runtime with gateway mode on but the allow-prod flag missing makes
    # should_route_features_through_gateway raise RuntimeError; upload must still work.
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.setenv('K_SERVICE', 'omi-backend')
    monkeypatch.delenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', raising=False)
    file_path = tmp_path / 'note.txt'
    file_path.write_text('hello')

    fake_files = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(id='file-1', filename='note.txt'))
    with patch.object(cf.openai, 'files', fake_files), patch.object(cf, 'record_direct_exception_surface') as record:
        result = cf.FileChatTool.upload(file_path)

    assert result['file_id'] == 'file-1'
    record.assert_called_once_with(surface='file_chat.openai_files_assistants_vision')


def test_upload_does_not_record_surface_outside_gateway_mode(monkeypatch, tmp_path):
    monkeypatch.delenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, raising=False)
    file_path = tmp_path / 'note.txt'
    file_path.write_text('hello')

    fake_files = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(id='file-1', filename='note.txt'))
    with patch.object(cf.openai, 'files', fake_files), patch.object(cf, 'record_direct_exception_surface') as record:
        result = cf.FileChatTool.upload(file_path)

    assert result['file_id'] == 'file-1'
    record.assert_not_called()
