import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

for mod_name in ['deepgram', 'deepgram.clients', 'deepgram.clients.live', 'deepgram.clients.live.v1']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock
sys.modules.setdefault('database._client', types.SimpleNamespace(db=MagicMock()))

os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')

from utils.stt import provider_service  # noqa: E402
from utils.stt.providers import STTProviderName, STTWorkload, get_prerecorded_provider_name  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_assemblyai_routing(monkeypatch):
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync,background,postprocess')


def test_env_selects_assemblyai_for_sync():
    assert get_prerecorded_provider_name(STTWorkload.sync) == STTProviderName.assemblyai


@patch('utils.stt.provider_service.get_byok_key')
def test_resolve_uses_deepgram_byok_when_no_assembly_header(mock_get_key):
    mock_get_key.side_effect = lambda provider: {'deepgram': 'dg-user-key'}.get(provider)
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.deepgram


@patch('utils.stt.provider_service.get_byok_key')
def test_resolve_uses_deepgram_byok_for_background_when_no_assembly_header(mock_get_key):
    mock_get_key.side_effect = lambda provider: {'deepgram': 'dg-user-key'}.get(provider)
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.background) == STTProviderName.deepgram


@patch('utils.stt.provider_service.get_byok_key')
def test_resolve_uses_assemblyai_when_byok_assembly_header_present(mock_get_key):
    keys = {'assemblyai': 'aa-user-key', 'deepgram': 'dg-user-key'}

    def _lookup(provider):
        return keys.get(provider)

    mock_get_key.side_effect = _lookup
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.assemblyai


@patch('utils.stt.provider_service.get_byok_key')
def test_resolve_uses_assemblyai_for_background_when_byok_assembly_header_present(mock_get_key):
    keys = {'assemblyai': 'aa-user-key', 'deepgram': 'dg-user-key'}

    def _lookup(provider):
        return keys.get(provider)

    mock_get_key.side_effect = _lookup
    assert (
        provider_service.resolve_prerecorded_provider_for_request(STTWorkload.background) == STTProviderName.assemblyai
    )


@patch('utils.stt.provider_service.get_byok_key', return_value=None)
def test_resolve_uses_server_assembly_when_no_byok_headers(_mock_get_key):
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.assemblyai


@patch('utils.stt.provider_service.get_byok_key')
def test_assemblyai_provider_passes_byok_api_key(mock_get_key):
    mock_get_key.return_value = 'aa-user-key'
    with patch('utils.stt.provider_service.AssemblyAIAsyncTranscriptionProvider') as mock_cls:
        provider_service._assemblyai_prerecorded_provider()
        mock_cls.assert_called_once_with(api_key='aa-user-key')


# Activation endpoint tests live in test_byok_security.py::TestBYOKActivationValidation
