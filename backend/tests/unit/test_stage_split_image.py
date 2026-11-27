from copy import deepcopy

import pytest

from scripts.integration_canary_metrics import Refused
from scripts.stage_split_image import STAMP, stage_body

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
