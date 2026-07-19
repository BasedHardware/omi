from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import check_app_client_openapi_compatibility as checker_module

ROOT = Path(__file__).resolve().parents[3]


def load_checker():
    return checker_module


def contract() -> dict:
    return {
        'openapi': '3.1.0',
        'paths': {
            '/v1/goals': {
                'post': {
                    'parameters': [
                        {
                            'name': 'dry_run',
                            'in': 'query',
                            'required': False,
                            'schema': {'type': 'boolean'},
                        }
                    ],
                    'requestBody': {
                        'required': True,
                        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/GoalCreate'}}},
                    },
                    'responses': {
                        '200': {
                            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/GoalResponse'}}}
                        }
                    },
                }
            },
            '/v3/memories/{memory_id}': {
                'patch': {
                    'parameters': [
                        {
                            'name': 'memory_id',
                            'in': 'path',
                            'required': True,
                            'schema': {'type': 'string'},
                        },
                        {
                            'name': 'value',
                            'in': 'query',
                            'required': True,
                            'schema': {'type': 'string'},
                        },
                    ],
                    'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object'}}}}},
                }
            },
        },
        'components': {
            'schemas': {
                'GoalCreate': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'title': {'type': 'string'},
                        'description': {'type': 'string'},
                        'source': {
                            'type': 'string',
                            'enum': ['user', 'ai', 'onboarding_typed'],
                        },
                    },
                    'required': ['title'],
                },
                'GoalResponse': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'id': {'type': 'string'},
                        'status': {'type': 'string', 'enum': ['active', 'done']},
                        'note': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                    },
                    'required': ['id', 'status'],
                },
            }
        },
    }


def messages(checker, base: dict, head: dict) -> list[str]:
    return [str(issue) for issue in checker.compare_specs(base, head)]


def test_identical_contract_is_compatible():
    checker = load_checker()
    base = contract()

    assert checker.compare_specs(base, copy.deepcopy(base)) == []


def test_additive_endpoint_optional_request_property_and_response_property_are_compatible():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    head['paths']['/v1/new'] = {'get': {'responses': {'200': {'description': 'ok'}}}}
    head['components']['schemas']['GoalCreate']['properties']['client_note'] = {'type': 'string'}
    head['components']['schemas']['GoalCreate']['properties']['source']['enum'].append('imported')
    head['components']['schemas']['GoalResponse']['properties']['future_field'] = {'type': 'string'}
    head['components']['schemas']['GoalResponse']['properties']['status']['enum'] = ['active']

    assert checker.compare_specs(base, head) == []


def test_released_query_parameter_cannot_move_to_body():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    operation = head['paths']['/v3/memories/{memory_id}']['patch']
    operation['parameters'] = [parameter for parameter in operation['parameters'] if parameter['name'] != 'value']
    operation['requestBody'] = {
        'required': True,
        'content': {'application/json': {'schema': {'type': 'object', 'properties': {'value': {'type': 'string'}}}}},
    }

    failures = messages(checker, base, head)

    assert any('parameters.query.value: released request parameter was removed or moved' in item for item in failures)


def test_released_goal_properties_and_enum_values_cannot_disappear():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    goal = head['components']['schemas']['GoalCreate']
    del goal['properties']['description']
    goal['properties']['source']['enum'] = ['user']

    failures = messages(checker, base, head)

    assert any('properties.description: released request property was removed' in item for item in failures)
    assert any(
        "properties.source.enum: value(s) ['ai', 'onboarding_typed'] are no longer accepted" in item
        for item in failures
    )


def test_new_required_request_property_is_breaking_but_optional_is_not():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    goal = head['components']['schemas']['GoalCreate']
    goal['properties']['tenant'] = {'type': 'string'}
    assert checker.compare_specs(base, head) == []

    goal['required'].append('tenant')
    assert any('properties.tenant: new required request property' in item for item in messages(checker, base, head))


def test_nullable_request_broadening_is_compatible_but_nullable_response_is_not():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    head['components']['schemas']['GoalCreate']['properties']['title'] = {
        'anyOf': [{'type': 'string'}, {'type': 'null'}]
    }
    assert checker.compare_specs(base, head) == []

    head['components']['schemas']['GoalResponse']['properties']['id'] = {
        'anyOf': [{'type': 'string'}, {'type': 'null'}]
    }
    assert any(
        'new response union branch has no compatible counterpart' in item for item in messages(checker, base, head)
    )


def test_response_required_property_and_new_enum_value_are_breaking():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    response = head['components']['schemas']['GoalResponse']
    response['required'].remove('id')
    response['properties']['status']['enum'].append('paused')

    failures = messages(checker, base, head)

    assert any(
        'properties.id: required released response property is no longer guaranteed' in item for item in failures
    )
    assert any("properties.status.enum: value(s) ['paused'] are not decodable" in item for item in failures)


def test_new_success_status_requires_released_wildcard_or_default_coverage():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    head['paths']['/v1/goals']['post']['responses']['201'] = copy.deepcopy(
        head['paths']['/v1/goals']['post']['responses']['200']
    )

    assert any(
        'responses.201: new success response status is not modeled' in item for item in messages(checker, base, head)
    )

    wildcard_base = copy.deepcopy(base)
    responses = wildcard_base['paths']['/v1/goals']['post']['responses']
    responses['2XX'] = responses.pop('200')
    assert checker.compare_specs(wildcard_base, head) == []

    default_base = copy.deepcopy(base)
    responses = default_base['paths']['/v1/goals']['post']['responses']
    responses['default'] = copy.deepcopy(responses['200'])
    assert checker.compare_specs(default_base, head) == []


def test_removing_success_status_is_response_narrowing_and_compatible():
    checker = load_checker()
    base = contract()
    base['paths']['/v1/goals']['post']['responses']['201'] = copy.deepcopy(
        base['paths']['/v1/goals']['post']['responses']['200']
    )
    head = copy.deepcopy(base)
    del head['paths']['/v1/goals']['post']['responses']['201']

    assert checker.compare_specs(base, head) == []


def test_response_media_types_follow_response_direction():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    del head['paths']['/v1/goals']['post']['responses']['200']['content']['application/json']
    assert checker.compare_specs(base, head) == []

    head = copy.deepcopy(base)
    head['paths']['/v1/goals']['post']['responses']['200']['content']['text/plain'] = {'schema': {'type': 'string'}}
    assert any('new success response media type is not modeled' in item for item in messages(checker, base, head))


def test_oauth_scope_removal_is_compatible_but_added_scope_is_breaking():
    checker = load_checker()
    base = contract()
    base['paths']['/v1/goals']['post']['security'] = [{'oauth': ['goals:read', 'goals:write']}]
    head = copy.deepcopy(base)
    head['paths']['/v1/goals']['post']['security'] = [{'oauth': ['goals:read']}]

    assert checker.compare_specs(base, head) == []

    head['paths']['/v1/goals']['post']['security'] = [{'oauth': ['goals:read', 'goals:write', 'goals:admin']}]
    assert any('authentication alternative is no longer accepted' in item for item in messages(checker, base, head))


def test_public_security_cannot_become_authenticated_but_auth_can_be_removed():
    checker = load_checker()
    public_base = contract()
    public_base['paths']['/v1/goals']['post']['security'] = []
    authenticated_head = copy.deepcopy(public_base)
    authenticated_head['paths']['/v1/goals']['post']['security'] = [{'firebaseBearer': []}]

    assert any(
        'authentication alternative is no longer accepted' in item
        for item in messages(checker, public_base, authenticated_head)
    )

    authenticated_base = copy.deepcopy(authenticated_head)
    public_head = copy.deepcopy(authenticated_base)
    public_head['paths']['/v1/goals']['post']['security'] = []
    assert checker.compare_specs(authenticated_base, public_head) == []


def test_new_default_response_is_breaking_and_existing_default_is_compared():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    head['paths']['/v1/goals']['post']['responses']['default'] = copy.deepcopy(
        head['paths']['/v1/goals']['post']['responses']['200']
    )
    assert any(
        'responses.default: new default response is not modeled' in item for item in messages(checker, base, head)
    )

    base_with_default = copy.deepcopy(head)
    incompatible_head = copy.deepcopy(head)
    incompatible_head['components']['schemas']['GoalResponse']['properties']['id'] = {'type': 'integer'}
    assert any(
        'responses.default' in item and '.type:' in item
        for item in messages(checker, base_with_default, incompatible_head)
    )


def test_additional_properties_schema_transitions_are_directional():
    checker = load_checker()
    base = contract()
    base['components']['schemas']['GoalCreate']['additionalProperties'] = True
    head = copy.deepcopy(base)
    head['components']['schemas']['GoalCreate']['additionalProperties'] = {'type': 'string'}
    assert any('request additional properties became constrained' in item for item in messages(checker, base, head))

    typed_request_base = copy.deepcopy(head)
    unconstrained_request_head = copy.deepcopy(typed_request_base)
    unconstrained_request_head['components']['schemas']['GoalCreate']['additionalProperties'] = True
    assert checker.compare_specs(typed_request_base, unconstrained_request_head) == []

    typed_response_base = contract()
    typed_response_base['components']['schemas']['GoalResponse']['additionalProperties'] = {'type': 'string'}
    unconstrained_response_head = copy.deepcopy(typed_response_base)
    unconstrained_response_head['components']['schemas']['GoalResponse']['additionalProperties'] = True
    assert any(
        'response additional-property values became unconstrained' in item
        for item in messages(checker, typed_response_base, unconstrained_response_head)
    )

    unconstrained_response_base = contract()
    unconstrained_response_base['components']['schemas']['GoalResponse']['additionalProperties'] = True
    typed_response_head = copy.deepcopy(unconstrained_response_base)
    typed_response_head['components']['schemas']['GoalResponse']['additionalProperties'] = {'type': 'string'}
    assert checker.compare_specs(unconstrained_response_base, typed_response_head) == []


def test_array_item_schema_transitions_are_directional():
    checker = load_checker()
    typed_request_base = contract()
    typed_request_base['components']['schemas']['GoalCreate']['properties']['tags'] = {
        'type': 'array',
        'items': {'type': 'string'},
    }
    unconstrained_request_head = copy.deepcopy(typed_request_base)
    del unconstrained_request_head['components']['schemas']['GoalCreate']['properties']['tags']['items']
    assert checker.compare_specs(typed_request_base, unconstrained_request_head) == []

    unconstrained_request_base = copy.deepcopy(unconstrained_request_head)
    typed_request_head = copy.deepcopy(typed_request_base)
    assert any(
        'request array items became constrained' in item
        for item in messages(checker, unconstrained_request_base, typed_request_head)
    )

    unconstrained_response_base = contract()
    unconstrained_response_base['components']['schemas']['GoalResponse']['properties']['tags'] = {'type': 'array'}
    typed_response_head = copy.deepcopy(unconstrained_response_base)
    typed_response_head['components']['schemas']['GoalResponse']['properties']['tags']['items'] = {'type': 'string'}
    assert checker.compare_specs(unconstrained_response_base, typed_response_head) == []

    typed_response_base = copy.deepcopy(typed_response_head)
    unconstrained_response_head = copy.deepcopy(unconstrained_response_base)
    assert any(
        'response array items became unconstrained' in item
        for item in messages(checker, typed_response_base, unconstrained_response_head)
    )


def test_request_body_media_type_and_operation_cannot_be_removed():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    del head['paths']['/v1/goals']['post']['requestBody']['content']['application/json']
    del head['paths']['/v3/memories/{memory_id}']['patch']

    failures = messages(checker, base, head)

    assert any(
        'requestBody.content.application/json: released request media type was removed' in item for item in failures
    )
    assert any('/v3/memories/{memory_id}.patch: released operation was removed' in item for item in failures)


def test_changed_composed_schema_fails_conservatively_instead_of_being_ignored():
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    old_note = base['components']['schemas']['GoalResponse']['properties']['note']['anyOf']
    head['components']['schemas']['GoalResponse']['properties']['note']['anyOf'] = [old_note[0]]

    # Removing null from a response is compatible. Adding a new response branch is not.
    assert checker.compare_specs(base, head) == []
    head['components']['schemas']['GoalResponse']['properties']['note']['anyOf'].append({'type': 'integer'})
    assert any(
        'new response union branch has no compatible counterpart' in item for item in messages(checker, base, head)
    )


def test_cli_reports_precise_breaking_paths(tmp_path, capsys):
    checker = load_checker()
    base = contract()
    head = copy.deepcopy(base)
    del head['components']['schemas']['GoalCreate']['properties']['description']
    base_path = tmp_path / 'base.json'
    head_path = tmp_path / 'head.json'
    base_path.write_text(json.dumps(base), encoding='utf-8')
    head_path.write_text(json.dumps(head), encoding='utf-8')

    result = checker.main(['--base-spec', str(base_path), '--head-spec', str(head_path)])

    assert result == 1
    stderr = capsys.readouterr().err
    assert 'paths./v1/goals.post.requestBody.content.application/json.schema.properties.description' in stderr
    assert 'GoalCreate' not in stderr  # Report the affected HTTP surface, not an orphan component.


def test_compatibility_check_is_wired_in_ci_and_pre_push():
    workflow = (ROOT / '.github/workflows/openapi-contract.yml').read_text(encoding='utf-8')
    pre_push = (ROOT / 'scripts/pre-push').read_text(encoding='utf-8')

    assert 'fetch-depth: 0' in workflow
    assert 'check_app_client_openapi_compatibility.py --base-ref FETCH_HEAD' in workflow
    assert 'backend/scripts/check_app_client_openapi_compatibility.py' in pre_push
    assert '--base-ref "$BASE_REMOTE_REF"' in pre_push

    backend_unit_start = pre_push.index('check_backend_unit_tests_if_needed()')
    backend_unit_end = pre_push.index('\n}\n', backend_unit_start)
    openapi_start = pre_push.index('check_openapi_contract_if_needed()')
    openapi_end = pre_push.index('\n}\n', openapi_start)
    backend_unit_body = pre_push[backend_unit_start:backend_unit_end]
    openapi_body = pre_push[openapi_start:openapi_end]

    assert 'check_app_client_openapi_compatibility.py' not in backend_unit_body
    assert 'check_app_client_openapi_compatibility.py' in openapi_body
    assert openapi_body.index('PRE_PUSH_SKIP_OPENAPI_CONTRACT') < openapi_body.index(
        'check_app_client_openapi_compatibility.py'
    )
