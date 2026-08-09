"""On-prem LLM gateway route-override guard (D32, ADR-0035).

The on-prem chat path pins every gateway feature to the single local model the operator's
OpenAI-compatible endpoint serves (deploy/onprem/llm_gateway/generated_route_overrides.yaml, mounted
over the image's cloud config). If upstream adds a feature to the cloud override and the on-prem file
is not updated, that feature would fall back to a cloud model name the local endpoint cannot serve —
a silent on-prem breakage. These hermetic checks fail closed on that drift.
"""

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLOUD_OVERRIDES = _REPO_ROOT / 'backend' / 'llm_gateway' / 'config' / 'generated_route_overrides.yaml'
_ONPREM_OVERRIDES = _REPO_ROOT / 'deploy' / 'onprem' / 'llm_gateway' / 'generated_route_overrides.yaml'


def _overrides(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding='utf-8'))['generated_route_overrides']


def _features(path: Path) -> set[str]:
    return {item['feature'] for item in _overrides(path)}


def test_onprem_override_covers_every_cloud_feature():
    # Parity: no feature is left un-pinned on-prem (which would resolve to a cloud model and fail).
    assert _features(_ONPREM_OVERRIDES) == _features(_CLOUD_OVERRIDES)


def test_onprem_override_pins_one_openai_compatible_model():
    items = _overrides(_ONPREM_OVERRIDES)
    providers = {item['primary']['provider'] for item in items}
    models = {item['primary']['model'] for item in items}
    # One operator endpoint (Ollama/vLLM) over the OpenAI-compatible wire => provider 'openai',
    # and a single model name for every feature.
    assert providers == {'openai'}
    assert len(models) == 1, f'expected one local model for all features, got {sorted(models)}'
