"""Regression coverage for the single source of truth governing STT serving."""

from pathlib import Path

import pytest
import yaml

from config.stt_provider_policy import (
    APPROVED_STREAMING_PARAKEET_MODELS,
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_PROVIDER,
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
        STTServingSurface.STREAMING: 'modulate-velma-2,dg-nova-3,parakeet',
        STTServingSurface.PRERECORDED: 'parakeet,modulate-velma-2',
        STTServingSurface.PTT: 'modulate-velma-2,parakeet',
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


def test_parakeet_capability_tracks_the_model_selected_for_each_surface(monkeypatch):
    # Default (no deployment override): the real-time model is English-only.
    monkeypatch.delenv('PARAKEET_STREAM_MODEL', raising=False)
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'es')
    assert parakeet_supports_language(STTServingSurface.PTT, 'en')
    assert not parakeet_supports_language(STTServingSurface.PTT, 'multi')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'es')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'multi')


def test_streaming_multilingual_model_enables_its_locales(monkeypatch):
    """On-prem deploying the multilingual NIM model makes real-time STT serve its languages."""
    monkeypatch.setenv('PARAKEET_STREAM_MODEL', 'nvidia/parakeet-1-1b-rnnt-multilingual')
    for lang in ('en', 'es', 'it', 'fr', 'de', 'pt', 'ja', 'multi'):
        assert parakeet_supports_language(STTServingSurface.STREAMING, lang), lang
        assert parakeet_supports_language(STTServingSurface.PTT, lang), lang
    # A language outside the 25-language set is still rejected.
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'zu')
    # Prerecorded is unaffected by the streaming override (own model).
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'es')


def test_unknown_stream_model_falls_back_to_english_only_default(monkeypatch):
    """A typo/unapproved value must not silently disable or widen the surface."""
    monkeypatch.setenv('PARAKEET_STREAM_MODEL', 'nvidia/not-a-real-model')
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'es')


def test_parakeet_serving_pod_stream_model_allow_list_matches_policy():
    """Static drift guard: the isolated Parakeet image carries a mirror of the code-owned
    streaming allow-list (it cannot import ``config``). The routing policy falls back silently
    for an unrecognized value, so the pod fails fast on the same set to avoid serving a model
    routing does not expect. Keep the two definitions identical."""
    transcribe_py = (Path(__file__).resolve().parents[2] / 'parakeet' / 'transcribe.py').read_text(encoding='utf-8')
    for model in APPROVED_STREAMING_PARAKEET_MODELS:
        assert model in transcribe_py, f'{model} missing from parakeet/transcribe.py APPROVED_STREAM_MODELS'
    # The mirror must not list a model the policy does not approve.
    assert "APPROVED_STREAM_MODELS" in transcribe_py


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


def test_parakeet_pod_stream_allowlist_matches_the_policy_source_of_truth():
    """The isolated GPU pod mirror in ``backend/parakeet/transcribe.py`` cannot import this policy
    (only ``backend/parakeet/`` is copied into that image), so it hardcodes ``APPROVED_STREAM_MODELS``.
    Parse it statically and assert EXACT, bidirectional set equality with the code-owned source of
    truth here, so adding/removing/typo'ing a model on either side fails this guard — the drift the
    pod's comment promises (a substring or one-directional check would miss an extra pod-only value)."""
    import ast

    pod_source = Path(__file__).resolve().parents[2] / 'parakeet' / 'transcribe.py'
    tree = ast.parse(pod_source.read_text(encoding='utf-8'), filename=str(pod_source))
    pod_models = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
            value = node.value
        else:
            continue
        if 'APPROVED_STREAM_MODELS' in names and value is not None:
            pod_models = {n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            break

    assert pod_models is not None, 'APPROVED_STREAM_MODELS not found in backend/parakeet/transcribe.py'
    assert pod_models == set(APPROVED_STREAMING_PARAKEET_MODELS)
