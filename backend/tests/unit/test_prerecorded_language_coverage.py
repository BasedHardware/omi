"""Pre-recorded STT selection must cover every language a client can store."""

import pytest

from config.prerecorded_stt import TranscriptionOutcome
from utils.stt.outcomes import TranscriptionFailure, failure_from_exception
from utils.stt.pre_recorded import PrerecordedSTTService, get_prerecorded_service

# Every base language the mobile picker offers (app/lib/providers/home_provider.dart).
CLIENT_OFFERED_LANGUAGES = (
    'ar',
    'be',
    'bg',
    'bn',
    'bs',
    'ca',
    'cs',
    'da',
    'de',
    'el',
    'en',
    'es',
    'et',
    'fa',
    'fi',
    'fr',
    'he',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'ko',
    'lt',
    'lv',
    'mk',
    'mr',
    'ms',
    'nl',
    'no',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sl',
    'sr',
    'sv',
    'ta',
    'te',
    'th',
    'tl',
    'tr',
    'uk',
    'vi',
    'zh',
)

# Must keep their exact provider: widening Velma's gate would pull these — including
# 'multi', the default for most users — off self-hosted Parakeet onto metered Velma.
ALREADY_ROUTED = {
    'multi': PrerecordedSTTService.PARAKEET,
    'ru': PrerecordedSTTService.PARAKEET,
    'pl': PrerecordedSTTService.PARAKEET,
    'uk': PrerecordedSTTService.PARAKEET,
    'cs': PrerecordedSTTService.PARAKEET,
    'sv': PrerecordedSTTService.PARAKEET,
    'en': PrerecordedSTTService.MODULATE,
    'ja': PrerecordedSTTService.MODULATE,
    'ko': PrerecordedSTTService.MODULATE,
    'zh': PrerecordedSTTService.MODULATE,
}

# In neither capability map.
PREVIOUSLY_UNROUTABLE = (
    'ar',
    'be',
    'bn',
    'bs',
    'ca',
    'fa',
    'he',
    'hi',
    'id',
    'kn',
    'mk',
    'mr',
    'ms',
    'no',
    'sr',
    'ta',
    'te',
    'th',
    'tl',
    'tr',
    'ur',
    'vi',
)


@pytest.fixture(autouse=True)
def _prod_model_preference(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'modulate-velma-2,parakeet')


@pytest.mark.parametrize('language', CLIENT_OFFERED_LANGUAGES)
def test_every_client_offered_language_resolves_to_a_provider(language):
    service, _resolved_language, model = get_prerecorded_service(language)

    assert service in {PrerecordedSTTService.MODULATE, PrerecordedSTTService.PARAKEET}
    assert model in {'velma-2', 'parakeet'}


@pytest.mark.parametrize('language,expected_service', sorted(ALREADY_ROUTED.items()))
def test_a_language_a_capability_map_claims_keeps_its_provider(language, expected_service):
    service, resolved_language, _model = get_prerecorded_service(language)

    assert service == expected_service
    assert resolved_language == language


@pytest.mark.parametrize('language', PREVIOUSLY_UNROUTABLE)
def test_an_uncovered_language_reaches_velma_by_detection(language):
    service, resolved_language, model = get_prerecorded_service(language)

    assert service == PrerecordedSTTService.MODULATE
    assert resolved_language == 'multi'
    assert model == 'velma-2'


@pytest.mark.parametrize('stored_language', ['japanese', 'russian', 'português', 'not-a-language'])
def test_a_stored_language_name_falls_back_to_provider_detection(stored_language):
    """Desktop onboarding saved language names before they were normalized to codes."""
    service, resolved_language, model = get_prerecorded_service(stored_language)

    assert service == PrerecordedSTTService.MODULATE
    assert resolved_language == 'multi'
    assert model == 'velma-2'


def test_region_qualified_codes_resolve_on_their_base_language():
    assert get_prerecorded_service('pt-BR') == (PrerecordedSTTService.MODULATE, 'pt', 'velma-2')
    assert get_prerecorded_service('zh_Hans') == (PrerecordedSTTService.MODULATE, 'zh', 'velma-2')


def test_parakeet_only_deployment_still_reaches_velma_for_a_language_it_cannot_serve(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')

    assert get_prerecorded_service('ru') == (PrerecordedSTTService.PARAKEET, 'ru', 'parakeet')

    service, resolved_language, _model = get_prerecorded_service('hi')
    assert service == PrerecordedSTTService.MODULATE
    assert resolved_language == 'multi'


def test_no_enabled_provider_raises_a_non_retryable_config_failure(monkeypatch):
    monkeypatch.setattr('utils.stt.pre_recorded.provider_is_enabled', lambda *_args, **_kwargs: False)
    monkeypatch.setattr('utils.stt.pre_recorded.default_models_for_surface', lambda *_args, **_kwargs: ())

    with pytest.raises(TranscriptionFailure) as raised:
        get_prerecorded_service('en')

    assert raised.value.outcome == TranscriptionOutcome.CONFIG_ERROR
    assert raised.value.retryable is False


def test_a_selection_failure_stays_non_retryable_through_the_public_mapping():
    failure = failure_from_exception(
        TranscriptionFailure(TranscriptionOutcome.CONFIG_ERROR, retryable=False),
        provider='unknown',
    )

    assert failure.outcome == TranscriptionOutcome.CONFIG_ERROR
    assert failure.retryable is False
