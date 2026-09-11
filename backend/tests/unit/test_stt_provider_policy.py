"""Regression coverage for the single source of truth governing STT serving."""

from pathlib import Path

import pytest
import yaml

from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_PROVIDER,
    PARAKEET_TDT_V3_MODEL,
    PARAKEET_TDT_V3_SUPPORTED_LANGUAGES,
    STTServingSurface,
    canonical_model_config,
    deepgram_provider_for_runtime,
    model_is_enabled,
    modulate_supports_language,
    parakeet_supports_language,
    provider_for_model_token,
    provider_is_enabled,
    supports_live_multilingual_mode,
)

ROOT = Path(__file__).resolve().parents[3]
PARAKEET_VALUES_FILES = (
    ROOT / 'backend/charts/parakeet/dev_omi_parakeet_values.yaml',
    ROOT / 'backend/charts/parakeet/prod_omi_parakeet_values.yaml',
)


def _chart_env_value(values_path: Path, name: str) -> str | None:
    values = yaml.safe_load(values_path.read_text(encoding='utf-8'))
    for entry in values.get('env', []) if isinstance(values, dict) else []:
        if isinstance(entry, dict) and entry.get('name') == name:
            return str(entry.get('value')) if 'value' in entry else None
    return None


def test_hosted_deepgram_serves_streaming_only():
    assert provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING)
    # PTT dispatches only Parakeet and Modulate and raises on anything else;
    # batch is carried by Parakeet/Velma.
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PTT)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PRERECORDED)


def test_self_hosted_deepgram_is_explicitly_limited_to_streaming():
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_policy_owns_the_safe_model_order_for_every_serving_surface():
    expected = {
        STTServingSurface.STREAMING: 'parakeet,modulate-velma-2,dg-nova-3',
        STTServingSurface.PRERECORDED: 'parakeet,modulate-velma-2',
        STTServingSurface.PTT: 'parakeet,modulate-velma-2',
    }
    for surface, model_order in expected.items():
        assert canonical_model_config(surface) == model_order
        assert provider_is_enabled(PARAKEET_PROVIDER, surface)
        assert provider_is_enabled(MODULATE_PROVIDER, surface)


def test_deepgram_model_tokens_report_the_hosted_deployment_by_default():
    assert provider_for_model_token('dg-nova-3') == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(False) == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(True) == DEEPGRAM_SELF_HOSTED_PROVIDER


def test_deepgram_token_is_admissible_while_either_deployment_serves_the_surface():
    assert model_is_enabled('dg-nova-3', STTServingSurface.STREAMING)
    assert not model_is_enabled('dg-nova-3', STTServingSurface.PRERECORDED)


def test_parakeet_capability_tracks_the_model_selected_for_each_surface():
    assert len(PARAKEET_TDT_V3_SUPPORTED_LANGUAGES) == 25
    assert all(model == PARAKEET_TDT_V3_MODEL for model in PARAKEET_MODEL_BY_SURFACE.values())
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'fr')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'es-419')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'multi')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'zh')
    assert parakeet_supports_language(STTServingSurface.PTT, 'en')
    assert parakeet_supports_language(STTServingSurface.PTT, 'fr')
    assert parakeet_supports_language(STTServingSurface.PTT, 'multi')
    assert not parakeet_supports_language(STTServingSurface.PTT, 'zh')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'es')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'multi')


@pytest.mark.parametrize('values_path', PARAKEET_VALUES_FILES)
def test_parakeet_chart_models_match_the_capability_policy(values_path: Path):
    """A model deployment swap must update the policy before routing can change (#10009)."""
    assert _chart_env_value(values_path, 'PARAKEET_MODEL') == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]
    assert (
        _chart_env_value(values_path, 'PARAKEET_STREAM_MODEL') == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.STREAMING]
    )
    assert PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PTT] == PARAKEET_MODEL_BY_SURFACE[STTServingSurface.STREAMING]


def test_live_multilingual_policy_normalizes_supported_locales_and_rejects_unknown_languages():
    assert supports_live_multilingual_mode('zh-TW')
    assert supports_live_multilingual_mode('ar')
    assert modulate_supports_language('es-419')
    assert not supports_live_multilingual_mode('xx-unsupported')


def test_stream_and_ptt_routes_keep_parakeet_primary_with_model_capabilities():
    """The default order changes only for surfaces that can connect to Parakeet.

    Parakeet's TDTv3 streaming model supports the same 25 languages as batch.
    The selector must still skip it for an explicit language outside that set,
    including when live auto-detection is enabled. PTT has no Deepgram
    connector, so its policy intentionally contains no Deepgram token.
    """
    assert canonical_model_config(STTServingSurface.STREAMING) == 'parakeet,modulate-velma-2,dg-nova-3'
    assert canonical_model_config(STTServingSurface.PTT) == 'parakeet,modulate-velma-2'
    assert not model_is_enabled('dg-nova-3', STTServingSurface.PTT)
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'fr')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'es')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'zh')


@pytest.mark.parametrize(
    'values_path',
    (
        ROOT / 'backend/charts/backend-listen/dev_omi_backend_listen_values.yaml',
        ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
    ),
)
def test_backend_listen_values_split_batch_and_stream_parakeet_endpoints(values_path: Path):
    """Batch keeps its legacy endpoint while live listener uses stream DNS."""
    assert _chart_env_value(values_path, 'HOSTED_PARAKEET_API_URL') in {
        'http://parakeet.omiapi.com',
        'http://parakeet.omi.me',
    }
    stream_url = _chart_env_value(values_path, 'HOSTED_PARAKEET_STREAM_API_URL')
    assert stream_url is not None
    assert '-omi-backend.svc.cluster.local:8080' in stream_url
    assert '-omi-parakeet-stream.' in stream_url


# ---------------------------------------------------------------------------
# #10022: user language preference gate must follow the live policy
# ---------------------------------------------------------------------------


def test_user_language_route_gates_multilingual_mode_by_live_policy():
    """Static tripwire (source order, not behavior): the PATCH /v1/users/language
    preference gate derives single_language_mode from the live STT capability
    policy, and the retired Deepgram Nova-3 multi-language list no longer
    appears in the route module (#10022)."""
    users_py = (Path(__file__).resolve().parents[2] / 'routers' / 'users.py').read_text(encoding='utf-8')
    assert 'single_language_mode = not supports_live_multilingual_mode(language)' in users_py
    assert 'deepgram_nova3_multi_languages' not in users_py


@pytest.mark.parametrize('language', ['vi', 'vi-VN', 'ko', 'tr', 'ar', 'th', 'pt-BR', 'en'])
def test_live_policy_admits_languages_beyond_the_retired_deepgram_list(language):
    """vi/ko/tr/ar/th were wrongly locked into single-language mode by the old
    19-locale Deepgram list; en/pt-BR keep their existing eligibility."""
    assert supports_live_multilingual_mode(language) is True


@pytest.mark.parametrize('language', ['my', 'am', 'lo'])
def test_live_policy_rejects_languages_outside_modulate_auto_detection(language):
    assert supports_live_multilingual_mode(language) is False
