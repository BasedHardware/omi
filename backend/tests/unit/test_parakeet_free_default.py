"""get_stt_service_for_language(prefer_parakeet=...) — the free-plan Parakeet default.

prefer_parakeet routes to the self-hosted Parakeet engine for supported languages and
falls back to the normal provider selection otherwise (or when Parakeet isn't configured).
"""

import pytest

from utils.stt.streaming import STTService, get_stt_service_for_language


@pytest.fixture
def parakeet_available(monkeypatch):
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.internal/v3/stream')


def test_prefers_parakeet_for_supported_language(parakeet_available):
    svc, _lang, model = get_stt_service_for_language('en', prefer_parakeet=True)
    assert svc == STTService.parakeet
    assert model == 'parakeet'


def test_falls_back_for_unsupported_language(parakeet_available):
    # Japanese isn't in parakeet_languages -> normal provider selection.
    svc, _lang, _model = get_stt_service_for_language('ja', prefer_parakeet=True)
    assert svc != STTService.parakeet


def test_no_prefer_keeps_default(parakeet_available):
    svc, _lang, _model = get_stt_service_for_language('en', prefer_parakeet=False)
    assert svc != STTService.parakeet


def test_prefer_ignored_when_service_unconfigured(monkeypatch):
    monkeypatch.delenv('HOSTED_PARAKEET_API_URL', raising=False)
    svc, _lang, _model = get_stt_service_for_language('en', prefer_parakeet=True)
    assert svc != STTService.parakeet
