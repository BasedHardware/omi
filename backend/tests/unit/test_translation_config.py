from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.translation import TranslationProvider, _positive_float, resolve_translation_profile


@pytest.fixture(autouse=True)
def _fast_safe_yaml_for_chart_and_manifest_fixtures(monkeypatch):
    # Keep the same safe YAML schema and every assertion, without spending
    # the call-phase CPU budget on Python tokenization of large manifests
    # (runtime_env.yaml alone cost ~1s CPU under SafeLoader; run
    # 41468678725 tripped the 1.00s fast-unit guard on it).
    monkeypatch.setattr(yaml, 'safe_load', lambda stream: yaml.load(stream, Loader=yaml.CSafeLoader))


@pytest.mark.parametrize('raw', ['nan', 'inf', '+inf', '-inf', 'NaN'])
def test_positive_float_rejects_non_finite_values(raw: str) -> None:
    with pytest.raises(ValueError, match='finite'):
        _positive_float(raw, 'TRANSLATION_NLLB_TIMEOUT_SECONDS')


@pytest.mark.parametrize('raw', ['0', '-1', 'not-a-number'])
def test_positive_float_rejects_non_positive_or_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        _positive_float(raw, 'TRANSLATION_NLLB_TIMEOUT_SECONDS')


def test_translation_profile_preserves_finite_timeout() -> None:
    profile = resolve_translation_profile({'TRANSLATION_NLLB_TIMEOUT_SECONDS': '2.5'})
    assert profile.nllb_timeout_seconds == 2.5


ROOT = Path(__file__).resolve().parents[3]


def _chart_env(path: Path) -> dict[str, str]:
    values = yaml.safe_load(path.read_text(encoding='utf-8'))
    return {entry['name']: str(entry['value']) for entry in values.get('env', []) if 'value' in entry}


@pytest.mark.parametrize('values_file', sorted((ROOT / 'backend/charts').glob('*/*_values.yaml')), ids=lambda p: p.name)
def test_no_deployed_chart_routes_translation_to_nllb(values_file: Path) -> None:
    env = _chart_env(values_file)
    if 'TRANSLATION_SERVICE_MODELS' not in env and 'HOSTED_TRANSLATION_API_URL' not in env:
        return
    resolved = resolve_translation_profile(env)
    assert resolved.providers == (TranslationProvider.luna,), values_file
    assert TranslationProvider.nllb not in resolved.configured_providers, values_file
    assert resolved.deprecated_tokens == (), values_file


def test_prod_binds_no_nllb_translation_endpoint() -> None:
    prod_listen = _chart_env(ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml')
    assert 'HOSTED_TRANSLATION_API_URL' not in prod_listen
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(encoding='utf-8'))
    prod = manifest['environments']['prod']
    services = [*prod['cloud_run']['services'].values(), *prod['gke'].values()]
    assert not any('HOSTED_TRANSLATION_API_URL' in service.get('env', {}) for service in services)


def test_nllb_workflow_cannot_target_prod() -> None:
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_nllb_translation.yml').read_text(encoding='utf-8'))
    # PyYAML reads the bare `on:` key as True.
    inputs = workflow[True]['workflow_dispatch']['inputs']
    assert inputs['environment']['options'] == ['development']
