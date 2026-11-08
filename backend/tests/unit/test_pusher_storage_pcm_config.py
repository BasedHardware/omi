"""Default-zero custody admission stays registered and deployment-validated."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.runtime_env_validation.manifest import _validate_manifest_shape

ROOT = Path(__file__).resolve().parents[3]
KEY = 'PUSHER_STORAGE_PCM_BUDGET_MB'


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('value', ['0', '27', '512', '1', '26', '-1', 'bad', '0.5', None])
def test_pusher_byte_limit_manifest_requires_progress_capable_integer(environment, value):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    config = copy.deepcopy(manifest['environments'][environment])
    env = config['gke']['pusher']['env']
    if value is None:
        env.pop(KEY)
    else:
        env[KEY] = {'value': value, 'category': 'ops_kill'}
    errors = _validate_manifest_shape(config, environment)
    relevant = [error for error in errors if KEY in str(error)]
    assert bool(relevant) is (value not in ('0', '27', '512'))


# Prod stays off; dev carries the 512 MiB canary (lead2 2afa3e, 2026-11-08). Any other
# value, or any prod change, is a deliberate policy change that must update this contract.
EXPECTED_DECLARED_VALUES = {'dev': '512', 'prod': '0'}


def test_all_deployment_declarations_remain_off_and_classified():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for environment in ('dev', 'prod'):
        expected = EXPECTED_DECLARED_VALUES[environment]
        assert manifest['environments'][environment]['gke']['pusher']['env'][KEY]['value'] == expected
        chart = yaml.load(
            (ROOT / f'backend/charts/pusher/{environment}_omi_pusher_values.yaml').read_text(), Loader=yaml.CSafeLoader
        )
        assert next(entry for entry in chart['env'] if entry['name'] == KEY)['value'] == expected
    policy = json.loads((ROOT / 'config/deployment-setting-classification.json').read_text())
    assert KEY in policy['kinds']['config']
    flags = yaml.load((ROOT / 'config/feature-flags.yaml').read_text(), Loader=yaml.CSafeLoader)
    flag = next(entry for entry in flags['flags'] if entry['key'] == KEY)
    assert flag['fail'] == 'open' and flag['decision'] == 'keep'
