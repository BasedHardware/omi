"""Historic jobs aliases qualify only under the existing strict resource/state gate."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.firestore_index_registry import firebase_index_manifest
from scripts import reconcile_firestore_indexes as gate

PROJECT = 'test-project'
DATABASE = '(default)'
COLLECTIONS = ('batch_pipeline_dev_jobs', 'batch_pipeline_prod_jobs')


def signature(collection):
    return (collection, 'COLLECTION', (('state', 'ASCENDING'), ('enqueued_at', 'ASCENDING')))


def live(collection, *, state='READY', suffix='one'):
    expected = signature(collection)
    return gate.LiveIndex(
        f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{collection}/indexes/{suffix}',
        (collection, 'COLLECTION', expected[2] + (('__name__', 'ASCENDING'),)),
        state,
    )


def states(expected, inventory):
    return gate.expected_index_states(expected={expected}, live_indexes=inventory, project=PROJECT, database=DATABASE)


@pytest.mark.parametrize('collection', COLLECTIONS)
@pytest.mark.parametrize('state', ['READY', 'CREATING', 'NEEDS_REPAIR', 'DELETING', 'STATE_UNSPECIFIED'])
def test_historic_alias_preserves_actual_state(collection, state):
    expected = signature(collection)
    assert states(expected, [live(collection, state=state)]) == {expected: state}
    assert states(expected, []) == {expected: 'MISSING'}


@pytest.mark.parametrize('collection', COLLECTIONS)
@pytest.mark.parametrize(
    'invalid',
    [
        'direction',
        'query_scope',
        'api_scope',
        'project',
        'database',
        'collection_resource',
        'empty_id',
        'nested_id',
        'new_field',
        'array',
    ],
)
def test_alias_cannot_change_scope_identity_or_shape(collection, invalid):
    from dataclasses import replace

    expected = signature(collection)
    item = live(collection)
    fields = item.signature[2]
    changes = {
        'direction': dict(signature=(collection, 'COLLECTION', fields[:-1] + (('__name__', 'DESCENDING'),))),
        'query_scope': dict(signature=(collection, 'COLLECTION_GROUP', fields)),
        'api_scope': dict(api_scope='DATASTORE_MODE_API'),
        'project': dict(resource_name=item.resource_name.replace(PROJECT, 'other-project')),
        'database': dict(resource_name=item.resource_name.replace(DATABASE, 'other-database')),
        'collection_resource': dict(resource_name=item.resource_name.replace(collection, 'other-collection')),
        'empty_id': dict(resource_name=item.resource_name.rsplit('/', 1)[0] + '/'),
        'nested_id': dict(resource_name=item.resource_name + '/nested'),
        'new_field': dict(signature=(collection, 'COLLECTION', fields[:-1] + (('new', 'ASCENDING'), fields[-1]))),
        'array': dict(signature=(collection, 'COLLECTION', (fields[0], ('enqueued_at', 'CONTAINS'), fields[-1]))),
    }
    assert states(expected, [replace(item, **changes[invalid])]) == {expected: 'MISSING'}


@pytest.mark.parametrize('collection', COLLECTIONS)
def test_exact_and_alias_or_two_alias_resources_remain_ambiguous(collection):
    from dataclasses import replace

    expected = signature(collection)
    alias = live(collection)
    exact = replace(alias, signature=expected, resource_name=alias.resource_name + '-exact')
    for inventory in ([alias, exact], [alias, live(collection, suffix='two')], [alias, alias]):
        assert states(expected, inventory) == {expected: 'AMBIGUOUS'}
    assert states(expected, [exact]) == {expected: 'READY'}


@pytest.mark.parametrize(
    'expected',
    [
        ('new_jobs', 'COLLECTION', (('state', 'ASCENDING'), ('enqueued_at', 'ASCENDING'))),
        (COLLECTIONS[0], 'COLLECTION_GROUP', (('state', 'ASCENDING'), ('enqueued_at', 'ASCENDING'))),
        (COLLECTIONS[1], 'COLLECTION', (('state', 'ASCENDING'), ('enqueued_at', 'DESCENDING'))),
    ],
)
def test_unrelated_or_new_signatures_keep_exact_matching(expected):
    item = gate.LiveIndex(
        f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{expected[0]}/indexes/id',
        (expected[0], expected[1], expected[2] + (('__name__', expected[2][-1][1]),)),
        'READY',
    )
    assert states(expected, [item]) == {expected: 'MISSING'}


def inventory_runner(items):
    payload = [
        {
            'name': item.resource_name,
            'queryScope': item.signature[1],
            'fields': [{'fieldPath': f, 'order': direction} for f, direction in item.signature[2]],
            'apiScope': item.api_scope,
            'state': item.state,
        }
        for item in items
    ]

    def runner(command, **_kwargs):
        assert command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'list']
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    return runner


@pytest.mark.parametrize('state', ['READY', 'CREATING', 'MISSING'])
def test_canonical_wait_and_missing_checks_preserve_nonready_refusals(state):
    expected = {signature(c) for c in COLLECTIONS}
    inventory = [live(c, state=state) for c in COLLECTIONS] if state != 'MISSING' else []
    runner = inventory_runner(inventory)
    missing = gate.missing_index_signatures(
        expected=expected, live_indexes=inventory, project=PROJECT, database=DATABASE
    )
    assert missing == (expected if state == 'MISSING' else set())
    kwargs = dict(
        expected=expected,
        project=PROJECT,
        database=DATABASE,
        timeout_seconds=1,
        poll_interval_seconds=1,
        runner=runner,
        sleep=lambda _: None,
        monotonic=iter((0, 2)).__next__,
    )
    if state == 'READY':
        gate.wait_for_indexes(**kwargs)
        assert (
            gate.provision_missing_indexes(expected=expected, project=PROJECT, database=DATABASE, runner=runner)
            == set()
        )
    else:
        with pytest.raises(RuntimeError, match=state):
            gate.wait_for_indexes(**kwargs)


@pytest.mark.parametrize('pending', [False, True])
def test_full_manifest_canonical_check_only_uses_compatibility_without_overriding_others(
    tmp_path, monkeypatch, pending
):
    manifest = firebase_index_manifest()
    expected = gate.expected_index_signatures(manifest)
    assert set(gate.HISTORIC_IMPLICIT_DOCUMENT_ID_SIGNATURES) == {signature(c) for c in COLLECTIONS}
    assert gate.HISTORIC_IMPLICIT_DOCUMENT_ID_SIGNATURES <= expected
    inventory = []
    other = next(s for s in sorted(expected) if s not in gate.HISTORIC_IMPLICIT_DOCUMENT_ID_SIGNATURES)
    for i, shape in enumerate(sorted(expected)):
        if gate._implicit_terminal_document_id_alias(shape) in gate.HISTORIC_IMPLICIT_DOCUMENT_ID_SIGNATURES:
            # Its historic declaration below contributes this same physical shape.
            continue
        if shape in gate.HISTORIC_IMPLICIT_DOCUMENT_ID_SIGNATURES:
            inventory.append(live(shape[0]))
        else:
            inventory.append(
                gate.LiveIndex(
                    f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{shape[0]}/indexes/{i}',
                    shape,
                    'CREATING' if pending and shape == other else 'READY',
                )
            )
    # This regression isolates the composite contract; existing field-state tests
    # cover the unchanged field path. The real manifest/registry verification runs.
    monkeypatch.setattr(gate, 'expected_field_requirements', lambda _: ())
    proposal = tmp_path / 'proposal.json'
    kwargs = dict(
        project=PROJECT,
        database=DATABASE,
        manifest_path=Path(gate.ROOT) / 'firestore.indexes.json',
        timeout_seconds=1,
        poll_interval_seconds=1,
        check_only=True,
        proposal_output=proposal,
        source_commit='a' * 40,
        runner=inventory_runner(inventory),
    )
    if pending:
        with pytest.raises(RuntimeError, match='CREATING'):
            gate.reconcile(**kwargs)
        assert proposal.is_file()
    else:
        gate.reconcile(**kwargs)
        assert not proposal.exists()
