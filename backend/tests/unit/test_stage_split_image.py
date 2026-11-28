from copy import deepcopy

import pytest

from scripts.integration_canary_metrics import Refused
from scripts.stage_split_image import STAMP, require_inherited_env, stage_body

BASE, SHADOW, CANDIDATE = 'backend-base', 'backend-shadow', 'backend-new'
SOURCE = 'a' * 40
IMAGE = 'gcr.io/based-hardware/backend:aaaaaaa'


@pytest.fixture
def split():
    plan = {'donor': SHADOW, 'inverse': {BASE: 90, SHADOW: 10}}
    traffic = [
        {'revisionName': BASE, 'percent': 90},
        {'revisionName': SHADOW, 'percent': 10, 'tag': 'shadow'},
    ]
    ready = [{'type': 'Ready', 'status': 'True'}]
    service = {
        'metadata': {
            'name': 'backend',
            'namespace': '123',
            'uid': 'service',
            'resourceVersion': 'version',
            'generation': 8,
            'annotations': {'run.googleapis.com/ingress': 'all'},
        },
        'spec': {'traffic': traffic, 'template': {'metadata': {'name': BASE}}},
        'status': {'traffic': deepcopy(traffic), 'observedGeneration': 8, 'conditions': ready},
    }
    donor = {
        'metadata': {
            'name': SHADOW,
            'namespace': '123',
            'uid': 'shadow-uid',
            'resourceVersion': 'immutable',
            'labels': {'serving.knative.dev/service': 'backend'},
            'annotations': {'autoscaling.knative.dev/maxScale': '100'},
        },
        'spec': {
            'containers': [
                {
                    'name': 'backend',
                    'ports': [{'containerPort': 8080}],
                    'image': 'old',
                    'env': [{'name': STAMP, 'value': 'b' * 40}, {'name': 'LEASE_MODE', 'value': 'shadow'}],
                },
                {'name': 'sidecar', 'image': 'collector@sha256:' + 'c' * 64},
            ],
            'serviceAccountName': 'backend-identity',
        },
        'status': {'conditions': ready},
    }
    return service, donor, plan


def test_split_clone_preserves_donor_config_and_traffic(split):
    service, donor, plan = split
    body = stage_body(service, donor, plan, CANDIDATE, IMAGE, SOURCE)

    assert 'status' not in body
    assert body['metadata']['resourceVersion'] == 'version'
    assert body['metadata']['annotations'] == service['metadata']['annotations']
    assert body['spec']['traffic'] == service['spec']['traffic']
    template = body['spec']['template']
    assert template['metadata']['name'] == CANDIDATE
    assert template['metadata']['annotations'] == donor['metadata']['annotations']
    expected = deepcopy(donor['spec'])
    expected['containers'][0]['image'] = IMAGE
    expected['containers'][0]['env'][0]['value'] = SOURCE
    assert template['spec'] == expected
    assert donor['spec']['containers'][0]['env'][0]['value'] == 'b' * 40


@pytest.mark.parametrize('mismatch', ['observed_generation', 'tag', 'percent', 'latest'])
def test_split_clone_refuses_changes_to_admitted_traffic(split, mismatch):
    service, donor, plan = split
    if mismatch == 'observed_generation':
        service['status']['observedGeneration'] = 7
    elif mismatch == 'tag':
        service['status']['traffic'][1]['tag'] = 'different'
    elif mismatch == 'latest':
        service['spec']['traffic'][0]['latestRevision'] = True
    else:
        service['status']['traffic'][0]['percent'] = 80
        service['status']['traffic'][1]['percent'] = 20
    with pytest.raises(Refused):
        stage_body(service, donor, plan, CANDIDATE, IMAGE, SOURCE)


def inherited_entries():
    return [
        {'name': STAMP, 'value': SOURCE},
        {'name': 'LEASE_MODE', 'value': 'shadow'},
        {'name': 'SERVICE_TOKEN', 'valueFrom': {'secretKeyRef': {'name': 'service-token', 'key': 'latest'}}},
    ]


def expected_state():
    return {
        'services': {
            'backend': {
                'env': [
                    {'name': 'LEASE_MODE', 'value': 'shadow'},
                    {
                        'name': 'SERVICE_TOKEN',
                        'valueFrom': {'secretKeyRef': {'name': 'service-token', 'key': 'latest'}},
                    },
                ]
            }
        }
    }


def test_image_only_split_plan_accepts_its_own_rendered_runtime_env():
    require_inherited_env(inherited_entries(), expected_state())


@pytest.mark.parametrize(
    'mutate,reason',
    [
        (lambda state: state['services']['backend']['env'][0].update(value='other'), '~LEASE_MODE'),
        (lambda state: state['services']['backend']['env'].pop(), '+SERVICE_TOKEN'),
        (lambda state: state['services']['backend']['env'].append({'name': 'NEW', 'value': '1'}), '-NEW'),
        (
            lambda state: state['services']['backend']['env'][1]['valueFrom']['secretKeyRef'].update(key='3'),
            '~SERVICE_TOKEN',
        ),
    ],
)
def test_env_changing_split_plan_is_refused_before_promotion(mutate, reason):
    state = expected_state()
    mutate(state)
    with pytest.raises(Refused) as refused:
        require_inherited_env(inherited_entries(), state)
    assert 'split_plan_changes_runtime_env' in str(refused.value)
    assert reason in str(refused.value)


def test_split_plan_without_a_rendered_state_is_refused():
    with pytest.raises(Refused, match='split_plan_expected_state_incomplete'):
        require_inherited_env(inherited_entries(), {'services': {}})
