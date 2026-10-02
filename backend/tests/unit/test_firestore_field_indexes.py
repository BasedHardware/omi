import copy

import pytest

from database.firestore_index_registry import FIELD_INDEX_REQUIREMENTS, firebase_index_manifest
from database.firestore_query_types import FieldIndexRequirement
from scripts import firestore_field_indexes as fields

PROJECT = 'dev-project'
DATABASE = '(default)'

_STATUS = FieldIndexRequirement('req', 'conversations', 'status', ('ASCENDING',))
_BOTH = FieldIndexRequirement('req', 'events', 'ref', ('ASCENDING', 'DESCENDING'))
_TAGS = FieldIndexRequirement('req', 'memories', 'tags', ('CONTAINS',))


def _field_url(requirement):
    return fields.field_resource_url(
        project=PROJECT,
        database=DATABASE,
        collection_group=requirement.collection_group,
        field_path=requirement.field_path,
    )


def _field_name(requirement):
    return fields.field_resource_name(
        project=PROJECT,
        database=DATABASE,
        collection_group=requirement.collection_group,
        field_path=requirement.field_path,
    )


def _index(scope, field_path, mode, *, state='READY', **extra):
    field = {'fieldPath': field_path}
    if mode == 'CONTAINS':
        field['arrayConfig'] = 'CONTAINS'
    else:
        field['order'] = mode
    return {'queryScope': scope, 'fields': [field], 'state': state, **extra}


def _collection_defaults(field_path, *, state='READY'):
    return [
        _index('COLLECTION', field_path, 'ASCENDING', state=state),
        _index('COLLECTION', field_path, 'DESCENDING', state=state),
        _index('COLLECTION', field_path, 'CONTAINS', state=state),
    ]


def _request(payload):
    calls = []

    def request(method, url, body):
        calls.append((method, url, body))
        return payload(method, url, body) if callable(payload) else payload

    request.calls = calls
    return request


def test_expected_field_requirements_parses_only_additive_overrides():
    manifest = firebase_index_manifest()
    requirements = fields.expected_field_requirements(manifest)

    assert [
        (requirement.collection_group, requirement.field_path, requirement.collection_group_modes)
        for requirement in requirements
    ] == [
        (requirement.collection_group, requirement.field_path, requirement.collection_group_modes)
        for requirement in FIELD_INDEX_REQUIREMENTS
    ]
    assert len(requirements) == 16
    assert sum(len(requirement.collection_group_modes) for requirement in requirements) == 18
    assert all(
        requirement.collection_group_modes
        and all(mode in {'ASCENDING', 'DESCENDING', 'CONTAINS'} for mode in requirement.collection_group_modes)
        for requirement in requirements
    )


def test_expected_field_requirements_skips_empty_exemptions():
    manifest = {
        'fieldOverrides': [
            {'collectionGroup': 'a', 'fieldPath': 'b', 'ttl': False, 'indexes': []},
            {
                'collectionGroup': 'c',
                'fieldPath': 'd',
                'ttl': False,
                'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': 'ASCENDING'}],
            },
        ]
    }
    requirements = fields.expected_field_requirements(manifest)
    assert [(r.collection_group, r.field_path) for r in requirements] == [('c', 'd')]


@pytest.mark.parametrize(
    'override',
    [
        'not-an-object',
        {'fieldPath': 'b', 'indexes': []},
        {'collectionGroup': 'a', 'indexes': []},
        {'collectionGroup': 'a', 'fieldPath': 'b/c', 'indexes': []},
        {'collectionGroup': 'a', 'fieldPath': 'b', 'indexes': 'x'},
        {'collectionGroup': 'a', 'fieldPath': 'b', 'indexes': [], 'ttl': True},
        {
            'collectionGroup': 'a',
            'fieldPath': 'b',
            'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': 'SIDEWAYS'}],
        },
        {'collectionGroup': 'a', 'fieldPath': 'b', 'indexes': [{'queryScope': 'COLLECTION', 'order': 'ASCENDING'}]},
    ],
)
def test_expected_field_requirements_fails_closed_on_malformed_overrides(override):
    with pytest.raises(fields.FieldIndexError):
        fields.expected_field_requirements({'fieldOverrides': [override]})


def test_expected_field_requirements_rejects_missing_list_and_duplicates():
    with pytest.raises(fields.FieldIndexError):
        fields.expected_field_requirements({})
    override = {
        'collectionGroup': 'a',
        'fieldPath': 'b',
        'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': 'ASCENDING'}],
    }
    with pytest.raises(fields.FieldIndexError, match='duplicates'):
        fields.expected_field_requirements({'fieldOverrides': [override, dict(override)]})


def _state(requirement, payload):
    return fields.field_requirement_state(
        project=PROJECT, database=DATABASE, requirement=requirement, request=_request(payload)
    )


def test_ready_when_required_group_modes_are_ready_and_no_write_needed():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': False,
            'indexes': [*_collection_defaults('status'), _index('COLLECTION_GROUP', 'status', 'ASCENDING')],
        },
    }
    request = _request(payload)

    state, patch = fields.field_requirement_state(
        project=PROJECT, database=DATABASE, requirement=_STATUS, request=request
    )

    assert (state, patch) == ('READY', None)


def test_missing_patch_unions_live_modes_with_declared_scalar_modes():
    live = _collection_defaults('ref') + [_index('COLLECTION_GROUP', 'ref', 'CONTAINS')]
    payload = {'name': _field_name(_BOTH), 'indexConfig': {'usesAncestorConfig': False, 'indexes': live}}

    state, patch = _state(_BOTH, payload)

    assert state == 'MISSING'
    modes = {
        (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
        for index in patch['indexConfig']['indexes']
    }
    assert modes == {
        ('COLLECTION', 'ASCENDING'),
        ('COLLECTION', 'DESCENDING'),
        ('COLLECTION', 'CONTAINS'),
        ('COLLECTION_GROUP', 'CONTAINS'),
        ('COLLECTION_GROUP', 'ASCENDING'),
        ('COLLECTION_GROUP', 'DESCENDING'),
    }
    assert 'ttlConfig' not in patch
    assert all('state' not in index and 'name' not in index for index in patch['indexConfig']['indexes'])


def test_missing_patch_creates_contains_mode_with_array_config():
    payload = {
        'name': _field_name(_TAGS),
        'indexConfig': {'usesAncestorConfig': False, 'indexes': _collection_defaults('tags')},
    }

    state, patch = _state(_TAGS, payload)

    assert state == 'MISSING'
    assert {
        'queryScope': 'COLLECTION_GROUP',
        'fields': [{'fieldPath': 'tags', 'arrayConfig': 'CONTAINS'}],
    } in patch[
        'indexConfig'
    ]['indexes']


def test_missing_field_with_explicit_empty_config_gets_full_defaults():
    payload = {'name': _field_name(_STATUS), 'indexConfig': {'usesAncestorConfig': False}}

    state, patch = _state(_STATUS, payload)

    assert state == 'MISSING'
    modes = {
        (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
        for index in patch['indexConfig']['indexes']
    }
    assert modes == {
        ('COLLECTION', 'ASCENDING'),
        ('COLLECTION', 'DESCENDING'),
        ('COLLECTION', 'CONTAINS'),
        ('COLLECTION_GROUP', 'ASCENDING'),
    }


def test_missing_index_config_fails_closed():
    payload = {'name': _field_name(_STATUS)}
    with pytest.raises(fields.FieldIndexError, match='indexConfig'):
        _state(_STATUS, payload)


def test_reverting_config_fails_closed():
    payload = {'name': _field_name(_STATUS), 'indexConfig': {'reverting': True, 'indexes': []}}
    with pytest.raises(fields.FieldIndexError, match='reverting'):
        _state(_STATUS, payload)


def test_resource_identity_mismatch_fails_closed():
    payload = {
        'name': 'projects/other-project/databases/(default)/collectionGroups/conversations/fields/status',
        'indexConfig': {'usesAncestorConfig': False, 'indexes': []},
    }
    with pytest.raises(fields.FieldIndexError, match='identity'):
        _state(_STATUS, payload)


def test_inherited_ancestor_chain_is_resolved_and_constrained():
    ancestor_name = f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*'
    calls = []

    def request(method, url, payload):
        calls.append(url)
        if url.endswith('/fields/status'):
            return {
                'name': _field_name(_STATUS),
                'indexConfig': {'usesAncestorConfig': True, 'ancestorField': ancestor_name},
            }
        return {
            'name': ancestor_name,
            'indexConfig': {'usesAncestorConfig': False, 'indexes': _collection_defaults('*', state='READY')},
        }

    state, patch = fields.field_requirement_state(
        project=PROJECT, database=DATABASE, requirement=_STATUS, request=request
    )

    assert state == 'MISSING'
    field_paths = {field['fieldPath'] for index in patch['indexConfig']['indexes'] for field in index['fields']}
    assert field_paths == {'status'}


def test_ancestor_outside_the_database_fails_closed():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': True,
            'ancestorField': 'projects/other/databases/(default)/collectionGroups/__default__/fields/*',
        },
    }
    with pytest.raises(fields.FieldIndexError, match='identity'):
        _state(_STATUS, payload)


def test_cyclic_ancestor_fails_closed():
    self_name = _field_name(_STATUS)
    payload = {
        'name': self_name,
        'indexConfig': {'usesAncestorConfig': True, 'ancestorField': self_name},
    }
    with pytest.raises(fields.FieldIndexError, match='cyclic'):
        _state(_STATUS, payload)


def test_creating_index_waits_without_patch():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': False,
            'indexes': [
                *_collection_defaults('status'),
                _index('COLLECTION_GROUP', 'status', 'ASCENDING', state='CREATING'),
            ],
        },
    }
    assert _state(_STATUS, payload) == ('CREATING', None)


def test_needs_repair_fails_even_when_required_mode_is_ready():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': False,
            'indexes': [
                *_collection_defaults('status'),
                _index('COLLECTION_GROUP', 'status', 'ASCENDING'),
                _index('COLLECTION_GROUP', 'status', 'DESCENDING', state='NEEDS_REPAIR'),
            ],
        },
    }
    with pytest.raises(fields.FieldIndexError, match='needs repair'):
        _state(_STATUS, payload)


def test_ready_fails_closed_on_an_index_for_a_different_field():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': False,
            'indexes': [*_collection_defaults('status'), _index('COLLECTION_GROUP', 'other', 'ASCENDING')],
        },
    }
    with pytest.raises(fields.FieldIndexError, match='different field'):
        _state(_STATUS, payload)


def test_duplicate_semantic_modes_fail_closed():
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {
            'usesAncestorConfig': False,
            'indexes': [
                *_collection_defaults('status'),
                _index('COLLECTION_GROUP', 'status', 'ASCENDING'),
                _index('COLLECTION_GROUP', 'status', 'ASCENDING'),
            ],
        },
    }
    with pytest.raises(fields.FieldIndexError, match='duplicate'):
        _state(_STATUS, payload)


def test_field_entry_with_both_modes_fails_closed():
    index = {
        'queryScope': 'COLLECTION_GROUP',
        'fields': [{'fieldPath': 'status', 'order': 'ASCENDING', 'arrayConfig': 'CONTAINS'}],
        'state': 'READY',
    }
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {'usesAncestorConfig': False, 'indexes': [*_collection_defaults('status'), index]},
    }
    with pytest.raises(fields.FieldIndexError, match='exactly one mode'):
        _state(_STATUS, payload)


def test_index_with_multiple_named_fields_fails_closed():
    index = {
        'queryScope': 'COLLECTION_GROUP',
        'fields': [
            {'fieldPath': 'status', 'order': 'ASCENDING'},
            {'fieldPath': 'status', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }
    payload = {
        'name': _field_name(_STATUS),
        'indexConfig': {'usesAncestorConfig': False, 'indexes': [*_collection_defaults('status'), index]},
    }
    with pytest.raises(fields.FieldIndexError, match='exactly one field'):
        _state(_STATUS, payload)


def test_missing_field_resource_name_fails_closed():
    payload = {'indexConfig': {'usesAncestorConfig': False, 'indexes': []}}
    with pytest.raises(fields.FieldIndexError, match='identity'):
        _state(_STATUS, payload)


def test_ancestor_response_identity_mismatch_fails_closed():
    ancestor_name = f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*'

    def request(method, url, body):
        if url.endswith('/fields/status'):
            return {
                'name': _field_name(_STATUS),
                'indexConfig': {'usesAncestorConfig': True, 'ancestorField': ancestor_name},
            }
        return {
            'name': ancestor_name.replace('/fields/*', '/fields/other'),
            'indexConfig': {'usesAncestorConfig': False, 'indexes': []},
        }

    with pytest.raises(fields.FieldIndexError, match='mismatched resource name'):
        fields.field_requirement_state(project=PROJECT, database=DATABASE, requirement=_STATUS, request=request)


def test_operation_outside_the_database_fails_closed():
    with pytest.raises(fields.FieldIndexError, match='identity'):
        fields.wait_field_operation(
            'projects/other/databases/(default)/operations/op',
            project=PROJECT,
            database=DATABASE,
            request=_request({'done': True}),
            timeout_seconds=1,
            poll_interval_seconds=1,
            sleep=lambda _seconds: None,
            monotonic=lambda: 0,
        )


def test_apply_requirement_patches_once_and_waits():
    applied = []

    def payload(method, url, body):
        if 'operations/' in url:
            return {'done': True}
        if method == 'PATCH':
            applied.append(body)
            return {'name': f'projects/{PROJECT}/databases/{DATABASE}/operations/op'}
        indexes = _collection_defaults('status')
        if applied:
            indexes.append(_index('COLLECTION_GROUP', 'status', 'ASCENDING'))
        return {
            'name': _field_name(_STATUS),
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    request = _request(payload)
    changed = fields.apply_field_requirement(
        project=PROJECT,
        database=DATABASE,
        requirement=_STATUS,
        request=request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is True
    assert len(applied) == 1


def test_apply_requirement_is_a_noop_when_ready():
    def payload(_method, _url, _body):
        return {
            'name': _field_name(_STATUS),
            'indexConfig': {
                'usesAncestorConfig': False,
                'indexes': [*_collection_defaults('status'), _index('COLLECTION_GROUP', 'status', 'ASCENDING')],
            },
        }

    request = _request(payload)
    changed = fields.apply_field_requirement(
        project=PROJECT,
        database=DATABASE,
        requirement=_STATUS,
        request=request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is False
    assert all(method == 'GET' for method, _url, _body in request.calls)


def test_provision_issues_all_patches_before_the_final_wait():
    events = []
    applied = set()
    by_field = {_STATUS.field_path: _STATUS, _TAGS.field_path: _TAGS}

    def payload(method, url, body):
        if 'operations/' in url:
            assert len(applied) == 2
            return {'done': True}
        field_path = url.split('?')[0].rsplit('/fields/', 1)[-1]
        if method == 'PATCH':
            events.append(('PATCH', field_path))
            applied.add(field_path)
            return {'name': f'projects/{PROJECT}/databases/{DATABASE}/operations/op-{field_path}'}
        events.append(('GET', field_path))
        requirement = by_field[field_path]
        indexes = _collection_defaults(field_path)
        if field_path in applied:
            indexes += [_index('COLLECTION_GROUP', field_path, mode) for mode in requirement.collection_group_modes]
        return {
            'name': f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{requirement.collection_group}/fields/{field_path}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    request = _request(payload)
    patched = fields.provision_field_requirements(
        requirements=(_STATUS, _TAGS),
        project=PROJECT,
        database=DATABASE,
        request=request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert patched == {('conversations', 'status'), ('memories', 'tags')}
    patch_positions = [position for position, (kind, _field) in enumerate(events) if kind == 'PATCH']
    assert len(patch_positions) == 2
    assert all(position < len(events) - 2 for position in patch_positions)
    assert [kind for kind, _field in events[-2:]] == ['GET', 'GET']


def test_creating_transition_then_still_missing_plans_one_union_patch():
    gets = 0
    applied = []
    stored = {}

    def payload(method, url, body):
        nonlocal gets
        if 'operations/' in url:
            return {'done': True}
        if method == 'PATCH':
            applied.append(body)
            stored['indexes'] = [dict(index, state='READY') for index in body['indexConfig']['indexes']]
            return {'name': f'projects/{PROJECT}/databases/{DATABASE}/operations/op'}
        gets += 1
        if 'indexes' in stored:
            indexes = stored['indexes']
        elif gets == 1:
            indexes = [
                *_collection_defaults('status'),
                _index('COLLECTION_GROUP', 'status', 'DESCENDING', state='CREATING'),
            ]
        else:
            indexes = [
                *_collection_defaults('status'),
                _index('COLLECTION_GROUP', 'status', 'DESCENDING'),
            ]
        return {
            'name': _field_name(_STATUS),
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    patched = fields.provision_field_requirements(
        requirements=(_STATUS,),
        project=PROJECT,
        database=DATABASE,
        request=_request(payload),
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert patched == {('conversations', 'status')}
    assert len(applied) == 1
    modes = {
        (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
        for index in applied[0]['indexConfig']['indexes']
    }
    assert {('COLLECTION_GROUP', 'ASCENDING'), ('COLLECTION_GROUP', 'DESCENDING')} <= modes


_ORIGINAL_REQUIREMENTS = tuple(
    requirement
    for requirement in FIELD_INDEX_REQUIREMENTS
    if requirement.identifier
    not in {
        'chat_first_dead_letters_created_at_group_ascending',
        'chat_first_proactive_intents_created_at_group_ascending',
    }
)


def test_frozen_inventory_fake_patches_exactly_the_five_missing_fields():
    production_project = 'based-hardware'
    production_database = '(default)'
    missing_groups = {
        'candidate_integration_outbox',
        'chat_first_proactive_intents',
        'memory_outbox',
        'projection_repairs',
        'task_recurrence_inbox',
    }
    narrow_collection_modes = {
        ('conversations', 'source'): ('ASCENDING',),
        ('fcm_tokens', 'app_version'): ('ASCENDING', 'DESCENDING'),
    }
    ancestor_name = (
        f'projects/{production_project}/databases/{production_database}' '/collectionGroups/__default__/fields/*'
    )
    live = {
        ancestor_name: {
            'name': ancestor_name,
            'indexConfig': {'usesAncestorConfig': False, 'indexes': _collection_defaults('*')},
        }
    }
    for requirement in _ORIGINAL_REQUIREMENTS:
        name = fields.field_resource_name(
            project=production_project,
            database=production_database,
            collection_group=requirement.collection_group,
            field_path=requirement.field_path,
        )
        if requirement.collection_group in missing_groups:
            live[name] = {
                'name': name,
                'indexConfig': {'usesAncestorConfig': True, 'ancestorField': ancestor_name},
            }
        else:
            collection_modes = narrow_collection_modes.get(
                (requirement.collection_group, requirement.field_path),
                ('ASCENDING', 'DESCENDING', 'CONTAINS'),
            )
            live[name] = {
                'name': name,
                'indexConfig': {
                    'usesAncestorConfig': False,
                    'indexes': [
                        *(_index('COLLECTION', requirement.field_path, mode) for mode in collection_modes),
                        *(
                            _index('COLLECTION_GROUP', requirement.field_path, mode)
                            for mode in requirement.collection_group_modes
                        ),
                    ],
                },
            }

    applied = {}

    def payload(method, url, body):
        if 'operations/' in url:
            return {'done': True}
        name = url.split('?')[0].split('/v1/', 1)[-1]
        if method == 'PATCH':
            applied[name] = body
            live[name] = {
                'name': name,
                'indexConfig': {
                    'usesAncestorConfig': False,
                    'indexes': [dict(index, state='READY') for index in body['indexConfig']['indexes']],
                },
            }
            return {
                'name': f'projects/{production_project}/databases/{production_database}/operations/op{len(applied)}'
            }
        return live[name]

    before = {name: copy.deepcopy(config) for name, config in live.items()}
    patched = fields.provision_field_requirements(
        requirements=_ORIGINAL_REQUIREMENTS,
        project=production_project,
        database=production_database,
        request=_request(payload),
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert patched == {
        (requirement.collection_group, requirement.field_path)
        for requirement in _ORIGINAL_REQUIREMENTS
        if requirement.collection_group in missing_groups
    }
    assert len(applied) == 5
    for name, config in before.items():
        if name not in applied:
            assert live[name] == config
    for name, body in applied.items():
        key = tuple(name.split('collectionGroups/')[1].split('/fields/'))
        assert key[0] in missing_groups
        indexes = body['indexConfig']['indexes']
        modes = {
            (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
            for index in indexes
        }
        assert {
            ('COLLECTION', 'ASCENDING'),
            ('COLLECTION', 'DESCENDING'),
            ('COLLECTION', 'CONTAINS'),
            ('COLLECTION_GROUP', 'ASCENDING'),
        } <= modes
        assert all('state' not in index and 'name' not in index for index in indexes)


def test_provision_stops_patching_once_the_budget_expires():
    clock = iter((0.0, 0.5, 5.0)).__next__
    patched_urls = []
    by_field = {_STATUS.field_path: _STATUS, _TAGS.field_path: _TAGS}

    def payload(method, url, body):
        if 'operations/' in url:
            return {'done': True}
        field_path = url.split('?')[0].rsplit('/fields/', 1)[-1]
        if method == 'PATCH':
            patched_urls.append(field_path)
            return {'name': f'projects/{PROJECT}/databases/{DATABASE}/operations/op{len(patched_urls)}'}
        requirement = by_field[field_path]
        return {
            'name': f'projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{requirement.collection_group}/fields/{field_path}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': _collection_defaults(field_path)},
        }

    with pytest.raises(fields.FieldIndexError, match='timed out'):
        fields.provision_field_requirements(
            requirements=(_STATUS, _TAGS),
            project=PROJECT,
            database=DATABASE,
            request=_request(payload),
            timeout_seconds=1,
            poll_interval_seconds=1,
            sleep=lambda _seconds: None,
            monotonic=clock,
        )
    assert patched_urls == ['status']


def test_lro_done_but_mode_still_creating_polls_with_sleep_until_ready():
    gets = 0
    sleeps = []
    patched = []

    def payload(method, url, body):
        nonlocal gets
        if 'operations/' in url:
            return {'done': True}
        if method == 'PATCH':
            patched.append(body)
            return {'name': f'projects/{PROJECT}/databases/{DATABASE}/operations/op'}
        gets += 1
        indexes = _collection_defaults('status')
        if gets >= 2:
            indexes.append(_index('COLLECTION_GROUP', 'status', 'ASCENDING', state='CREATING' if gets < 4 else 'READY'))
        return {
            'name': _field_name(_STATUS),
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    changed = fields.provision_field_requirements(
        requirements=(_STATUS,),
        project=PROJECT,
        database=DATABASE,
        request=_request(payload),
        timeout_seconds=30,
        poll_interval_seconds=1,
        sleep=sleeps.append,
        monotonic=lambda: 0,
    )

    assert changed == {('conversations', 'status')}
    assert len(patched) == 1
    assert sleeps
