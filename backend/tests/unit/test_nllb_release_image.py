"""An image rollback must replay the recorded artifact even after failed startup."""

import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.nllb_release_image import PREVIOUS_DIGEST, release_values

REPOSITORY = 'gcr.io/example/nllb-translation'
OLD = 'sha256:' + 'a' * 64
NEW = 'sha256:' + 'b' * 64
NEXT = 'sha256:' + 'c' * 64
TAG = '1234567'


def serving():
    image = REPOSITORY + ':' + TAG
    deployment = {
        'metadata': {'generation': 3},
        'spec': {
            'replicas': 1,
            'selector': {'matchLabels': {'app': 'nllb'}},
            'template': {
                'metadata': {'annotations': {PREVIOUS_DIGEST: OLD}},
                'spec': {'containers': [{'name': 'nllb-translation', 'image': image}]},
            },
        },
        'status': {'observedGeneration': 3, 'readyReplicas': 1, 'updatedReplicas': 1},
    }
    pods = {
        'items': [
            {
                'metadata': {'labels': {'app': 'nllb'}},
                'spec': {'containers': [{'name': 'nllb-translation', 'image': image}]},
                'status': {
                    'containerStatuses': [
                        {
                            'name': 'nllb-translation',
                            'ready': True,
                            'image': image,
                            'imageID': REPOSITORY + '@' + NEW,
                        }
                    ]
                },
            }
        ]
    }
    return deployment, pods


def test_normal_deploy_records_observed_image_not_source_tag():
    deployment, pods = serving()
    result = release_values(deployment, pods, REPOSITORY, TAG, candidate_digest=NEXT)
    assert result == {'image': {'tag': TAG, 'digest': NEXT}, 'podAnnotations': {PREVIOUS_DIGEST: NEW}}


def test_rollback_uses_recorded_digest_even_if_current_rollout_never_became_ready():
    deployment, _ = serving()
    deployment['status']['readyReplicas'] = 0
    result = release_values(deployment, {'items': []}, REPOSITORY, TAG, OLD)
    assert result['image']['digest'] == OLD


@pytest.mark.parametrize('rollback', [NEW, 'latest', 'sha256:bad', 'sha256:' + 'A' * 64])
def test_rollback_cannot_select_an_unrecorded_or_malformed_image(rollback):
    deployment, pods = serving()
    with pytest.raises(ValueError):
        release_values(deployment, pods, REPOSITORY, TAG, rollback)


@pytest.mark.parametrize('fault', ['unready', 'mixed', 'missing', 'wrong_repo', 'stale_generation'])
def test_normal_deploy_requires_one_ready_observed_image(fault):
    deployment, pods = serving()
    container = pods['items'][0]['status']['containerStatuses'][0]
    if fault == 'unready':
        container['ready'] = False
    elif fault == 'mixed':
        deployment['spec']['replicas'] = 2
        deployment['status'].update(readyReplicas=2, updatedReplicas=2)
        other = deepcopy(pods['items'][0])
        other['status']['containerStatuses'][0]['imageID'] = REPOSITORY + '@' + OLD
        pods['items'].append(other)
    elif fault == 'missing':
        pods['items'].clear()
    elif fault == 'wrong_repo':
        container['imageID'] = 'gcr.io/other/image@' + NEW
    else:
        deployment['status']['observedGeneration'] = 2
    with pytest.raises(ValueError):
        release_values(deployment, pods, REPOSITORY, TAG, candidate_digest=NEXT)


def test_first_deployment_has_no_rollback_target():
    assert release_values({}, {'items': []}, REPOSITORY, TAG, candidate_digest=NEXT) == {
        'image': {'tag': TAG, 'digest': NEXT}
    }
    with pytest.raises(ValueError):
        release_values({}, {'items': []}, REPOSITORY, TAG, OLD)


def test_workflow_rollback_skips_rebuild_but_retains_receipt_and_rollout_gates():
    root = Path(__file__).resolve().parents[3]
    source = (root / '.github/workflows/gcp_nllb_translation.yml').read_text()
    assert "if: github.event.inputs.rollback_digest == ''" in source
    assert "github.event.inputs.rollback_digest != '' && 'main'" in source
    assert source.index('Record serving image and validate rollback receipt') < source.index(
        'Deploy NLLB Translation to GKE cluster using Helm'
    )
    assert 'gcloud container images describe' in source
    assert '-f /tmp/nllb-release-values.json' in source
    assert '--set-string "image.tag=${{ steps.vars.outputs.short_sha }}"' in source
    assert 'rollout status' in source
    assert 'runtime_image_contracts.py smoke' in source


def test_prod_rollout_strategy_and_wait_cover_startup_probe_budget():
    root = Path(__file__).resolve().parents[3]
    values_path = root / 'backend/charts/nllb-translation/prod_omi_nllb_translation_values.yaml'
    values = yaml.safe_load(values_path.read_text())
    startup_probe = values['startupProbe']
    startup_budget = startup_probe['failureThreshold'] * startup_probe['periodSeconds']
    rollout_workflow = (root / '.github/workflows/gcp_nllb_translation.yml').read_text()
    timeout = re.search(r'rollout status[^\n]*--timeout=(\d+)s', rollout_workflow)

    assert values['livenessProbe']['httpGet']['path'] == '/live'
    assert values['readinessProbe']['httpGet']['path'] == '/ready'
    assert values['strategy']['rollingUpdate'] == {'maxSurge': 0, 'maxUnavailable': 1}
    assert timeout is not None
    assert int(timeout.group(1)) > startup_budget


def test_retry_preserves_original_rollback_receipt_for_same_candidate():
    deployment, pods = serving()
    result = release_values(deployment, pods, REPOSITORY, TAG, candidate_digest=NEW)
    assert result['podAnnotations'][PREVIOUS_DIGEST] == OLD
    assert result['image']['digest'] == NEW


def test_status_image_alias_does_not_hide_immutable_image_identity():
    deployment, pods = serving()
    pods['items'][0]['status']['containerStatuses'][0]['image'] = NEW
    assert release_values(deployment, pods, REPOSITORY, TAG, candidate_digest=NEXT)['image']['digest'] == NEXT


def test_normal_release_rejects_missing_candidate_digest():
    deployment, pods = serving()
    with pytest.raises(ValueError, match='candidate digest'):
        release_values(deployment, pods, REPOSITORY, TAG)
