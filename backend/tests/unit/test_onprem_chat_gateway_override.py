"""On-prem LLM gateway route-override guard (D32, ADR-0035).

The on-prem chat path pins every gateway feature to the single local model the operator's
OpenAI-compatible endpoint serves (deploy/onprem/helm/omi-oss/files/generated_route_overrides.yaml, mounted
over the image's cloud config). If upstream adds a feature to the cloud override and the on-prem file
is not updated, that feature would fall back to a cloud model name the local endpoint cannot serve —
a silent on-prem breakage. These hermetic checks fail closed on that drift.
"""

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLOUD_OVERRIDES = _REPO_ROOT / 'backend' / 'llm_gateway' / 'config' / 'generated_route_overrides.yaml'
_ONPREM_OVERRIDES = _REPO_ROOT / 'deploy' / 'onprem' / 'helm' / 'omi-oss' / 'files' / 'generated_route_overrides.yaml'


def _overrides(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding='utf-8'))['generated_route_overrides']


def _features(path: Path) -> set[str]:
    return {item['feature'] for item in _overrides(path)}


def test_onprem_override_covers_every_cloud_feature():
    """Every feature upstream overrides, we override too — as a SUPERSET, not as equality.

    Equality was the wrong invariant, and it was the reassuring kind of wrong: it reported "37 of 37
    covered" while eight lanes were open. Upstream does not need an override entry to route a feature —
    its QoS table already points at a provider it owns — so its file is a subset of the configured
    features, not the list of what needs pinning. Measured 2026-08-21 on the correct base: 45 configured
    features, 8 with no on-prem entry (translation among them, and it carries transcript text).

    The full-coverage rule now lives in .github/scripts/check_oss_llm_gateway_route_coverage.py, which
    measures against get_all_configured_features() and ratchets (ADR-0067). What stays here is the
    direction upstream can still break: it adds an override, we must have one too.
    """
    missing = _features(_CLOUD_OVERRIDES) - _features(_ONPREM_OVERRIDES)
    assert missing == set(), f'upstream overrides these and we do not: {sorted(missing)}'


def test_onprem_override_pins_one_openai_compatible_model():
    items = _overrides(_ONPREM_OVERRIDES)
    providers = {item['primary']['provider'] for item in items}
    models = {item['primary']['model'] for item in items}
    # One operator endpoint (Ollama/vLLM) over the OpenAI-compatible wire => provider 'openai',
    # and a single model name for every feature.
    assert providers == {'openai'}
    assert len(models) == 1, f'expected one local model for all features, got {sorted(models)}'
