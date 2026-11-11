from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CALLERS = ['backend', 'omi-web', 'omi-admin-dashboard']


def _allowed_callers(environment: str) -> list[str]:
    values_path = BACKEND_ROOT / 'charts' / 'llm-gateway' / f'{environment}_omi_llm_gateway_values.yaml'
    values = yaml.safe_load(values_path.read_text(encoding='utf-8'))
    return next(entry['value'].split(',') for entry in values['env'] if entry['name'] == 'LLM_GATEWAY_ALLOWED_CALLERS')


def test_llm_gateway_allows_personas_from_dev_and_prod_charts():
    for environment in ('dev', 'prod'):
        assert _allowed_callers(environment) == EXPECTED_CALLERS
