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
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_ENABLED', 'true')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_WORKLOADS', 'sync,background,postprocess')
    monkeypatch.setenv('ASSEMBLYAI_API_KEY', 'aa-server-key')


def test_env_selects_assemblyai_for_sync():
    assert get_prerecorded_provider_name(STTWorkload.sync) == STTProviderName.assemblyai


def test_resolve_uses_deepgram_byok_when_no_assembly_header(monkeypatch):
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda provider: {'deepgram': 'dg-user-key'}.get(provider))
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.deepgram


def test_resolve_uses_deepgram_byok_for_background_when_no_assembly_header(monkeypatch):
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda provider: {'deepgram': 'dg-user-key'}.get(provider))
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.background) == STTProviderName.deepgram


def test_resolve_uses_assemblyai_when_byok_assembly_header_present(monkeypatch):
    keys = {'assemblyai': 'aa-user-key', 'deepgram': 'dg-user-key'}

    def _lookup(provider):
        return keys.get(provider)

    monkeypatch.setattr(provider_service, 'get_byok_key', _lookup)
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.assemblyai


def test_resolve_uses_assemblyai_for_background_when_byok_assembly_header_present(monkeypatch):
    keys = {'assemblyai': 'aa-user-key', 'deepgram': 'dg-user-key'}

    def _lookup(provider):
        return keys.get(provider)

    monkeypatch.setattr(provider_service, 'get_byok_key', _lookup)
    assert (
        provider_service.resolve_prerecorded_provider_for_request(STTWorkload.background) == STTProviderName.assemblyai
    )


def test_resolve_uses_server_assembly_when_no_byok_headers(monkeypatch):
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda _provider: None)
    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.assemblyai


def test_resolve_uses_server_deepgram_when_server_assembly_missing_and_fallback_enabled(monkeypatch):
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-server-key')
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda _provider: None)

    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.deepgram


def test_resolve_keeps_assemblyai_selected_when_server_assembly_missing_and_fallback_disabled(
    monkeypatch,
):
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-server-key')
    monkeypatch.setenv('ASSEMBLYAI_PRERECORDED_STT_FALLBACK_ENABLED', 'false')
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda _provider: None)

    assert provider_service.resolve_prerecorded_provider_for_request(STTWorkload.sync) == STTProviderName.assemblyai


def test_assemblyai_provider_passes_byok_api_key(monkeypatch):
    monkeypatch.setattr(provider_service, 'get_byok_key', lambda _provider: 'aa-user-key')
    with patch.object(provider_service, 'AssemblyAIAsyncTranscriptionProvider') as mock_cls:
        provider_service._assemblyai_prerecorded_provider()
        mock_cls.assert_called_once_with(api_key='aa-user-key')


# Activation endpoint tests live in test_byok_security.py::TestBYOKActivationValidation
