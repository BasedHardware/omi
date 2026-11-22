from copy import deepcopy
from pathlib import Path

import pytest

from scripts.sync_backfill_routing import compose_rendered_routing, read_routing


@pytest.fixture
def routing_file(tmp_path):
    path = tmp_path / 'routing.env'
    path.write_text(
        'SYNC_BACKFILL_TASKS_QUEUE=control-current\n'
        'SYNC_BACKFILL_TASKS_HANDLER_URL=https://backfill.example.invalid/v2/sync-jobs/run\n'
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE=https://backfill.example.invalid/v2/sync-jobs/run\n'
    )
    return path


def test_routing_composition_preserves_every_other_binding_and_service(routing_file):
    state = {
        'services': {
            'backend-sync': {
                'env': [
                    {'name': 'SYNC_BACKFILL_TASKS_QUEUE', 'value': 'manifest-retired'},
                    {'name': 'PRIVATE_SECRET_REF', 'valueFrom': {'secretKeyRef': {'name': 'synthetic'}}},
                ]
            },
            'backend': {'env': [{'name': 'UNCHANGED', 'value': 'original'}]},
        },
        'jobs': {'independent': {'env': []}},
    }
    original = deepcopy(state)
    updated = compose_rendered_routing(state, read_routing(routing_file))
    assert state == original
    assert updated['services']['backend'] == state['services']['backend']
    assert updated['jobs'] == state['jobs']
    values = {entry['name']: entry for entry in updated['services']['backend-sync']['env']}
    assert values['SYNC_BACKFILL_TASKS_QUEUE']['value'] == 'control-current'
    assert values['PRIVATE_SECRET_REF'] == state['services']['backend-sync']['env'][1]


@pytest.mark.parametrize(
    'invalid',
    [
        'EXTRA_GATE=true\n',
        'SYNC_BACKFILL_TASKS_QUEUE=duplicate\n',
    ],
)
def test_overlay_cannot_add_arbitrary_config_or_duplicate_keys(routing_file, invalid):
    routing_file.write_text(routing_file.read_text() + invalid)
    with pytest.raises(ValueError):
        read_routing(routing_file)


def test_overlay_rejects_mismatched_audience(routing_file):
    text = routing_file.read_text().replace('OIDC_AUDIENCE=https://backfill.', 'OIDC_AUDIENCE=https://other.')
    routing_file.write_text(text)
    with pytest.raises(ValueError):
        read_routing(routing_file)
