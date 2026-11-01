"""A retirement rollout must never leave the batch language gate closed."""

from copy import deepcopy

import pytest

from scripts.rollout.legacy_env import EXCLUSION, retirement_env_sets


@pytest.mark.parametrize('mode', ['draining', 'dark'])
@pytest.mark.parametrize('percent', range(101))
def test_every_retirement_set_opens_language_admission(mode, percent):
    services = {
        'cloud_run/' + service: {'BATCH_PIPELINE_PERCENT': str(percent), EXCLUSION: 'true'}
        for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
    }
    sets = {'retirement': services, 'rollback': {'cloud_run/backend-sync': {'BATCH_PIPELINE_PERCENT': '0'}}}
    before = deepcopy(sets)
    generated = retirement_env_sets(sets, {'retirement': mode})
    assert all(env[EXCLUSION] == 'false' for env in generated['retirement'].values())
    assert generated['rollback'] == sets['rollback']
    assert sets == before


@pytest.mark.parametrize('modes', [{'missing': 'dark'}, {'retirement': 'off'}])
def test_unknown_retirement_set_or_mode_is_rejected(modes):
    with pytest.raises(ValueError):
        retirement_env_sets({'retirement': {}}, modes)
