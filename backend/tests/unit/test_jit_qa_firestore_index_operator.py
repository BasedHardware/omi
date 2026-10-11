import copy
import re
from pathlib import Path

import pytest

from database import firestore_index_registry as registry
from scripts import jit_qa_firestore_index_operator as operator

# Every registry composite is selected; the count follows the registry so a new
# production query requirement is provisioned on the isolated QA database too.
_REGISTRY_COUNT = len(registry.INDEX_REQUIREMENTS)
_FIELD_COUNT = len(registry.FIELD_INDEX_REQUIREMENTS)

_UNSET = object()

_FIELD_REQUIREMENTS = {
    (requirement.collection_group, requirement.field_path): requirement
    for requirement in registry.FIELD_INDEX_REQUIREMENTS
}


def _default_indexes(field_path):
    return [
        {
            'queryScope': 'COLLECTION',
            'fields': [{'fieldPath': field_path, 'order': 'ASCENDING'}],
            'state': 'READY',
        },
        {
            'queryScope': 'COLLECTION',
            'fields': [{'fieldPath': field_path, 'order': 'DESCENDING'}],
            'state': 'READY',
        },
        {
            'queryScope': 'COLLECTION',
            'fields': [{'fieldPath': field_path, 'arrayConfig': 'CONTAINS'}],
            'state': 'READY',
        },
    ]


def _required_index(requirement, mode, *, state='READY'):
    field = {'fieldPath': requirement.field_path}
    if mode == 'CONTAINS':
        field['arrayConfig'] = 'CONTAINS'
    else:
        field['order'] = mode
    return {'queryScope': 'COLLECTION_GROUP', 'fields': [field], 'state': state}


def _field_api_request(*, ready: bool = False, api_scope: object = _UNSET):
    """Fake the Admin REST field endpoints for every declared requirement."""

    calls = []
    applied = set()

    def request(method, url, payload):
        calls.append((method, url, payload))
        if 'operations/' in url:
            return {'done': True}
        match = re.search(r'collectionGroups/([^/]+)/fields/([^/?]+)', url)
        assert match, url
        key = (match.group(1), match.group(2))
        requirement = _FIELD_REQUIREMENTS[key]
        if method == 'PATCH':
            applied.add(key)
            return {'name': 'projects/based-hardware-dev/databases/jit-qa/operations/field-update'}
        indexes = _default_indexes(requirement.field_path)
        if ready or key in applied:
            indexes += [_required_index(requirement, mode) for mode in requirement.collection_group_modes]
        if api_scope is not _UNSET:
            for index in indexes:
                index['apiScope'] = api_scope
        return {
            'name': f'projects/based-hardware-dev/databases/jit-qa/collectionGroups/{key[0]}/fields/{key[1]}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    request.calls = calls
    return request


def _status_requirement():
    return next(
        requirement
        for requirement in operator.TARGET_FIELD_REQUIREMENTS
        if (requirement.collection_group, requirement.field_path) == ('conversations', 'status')
    )


def test_selected_manifest_is_canonical_and_contains_every_registry_composite():
    manifest, signatures = operator.selected_manifest()

    assert _REGISTRY_COUNT >= 78
    assert len(manifest["indexes"]) == _REGISTRY_COUNT
    assert operator.TARGET_REQUIREMENTS is registry.INDEX_REQUIREMENTS
    assert signatures == {requirement.signature for requirement in operator.TARGET_REQUIREMENTS}
    assert {
        (
            entry["collectionGroup"],
            entry["queryScope"],
            tuple((field["fieldPath"], field.get("order") or field.get("arrayConfig")) for field in entry["fields"]),
        )
        for entry in manifest["indexes"]
    } == signatures


def test_field_targets_are_the_registry_field_requirements():
    assert operator.TARGET_FIELD_REQUIREMENTS is registry.FIELD_INDEX_REQUIREMENTS
    assert _FIELD_COUNT == 16


def test_plan_reads_only_fixed_named_database_and_reports_all_required_indexes(monkeypatch):
    calls = []

    def list_live_indexes(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(operator.reconciler, "list_live_indexes", list_live_indexes)
    field_api = _field_api_request()
    result = operator.build_plan(
        project=operator.PROJECT,
        database=operator.DATABASE,
        field_api_request=field_api,
    )

    assert calls == [
        {"project": "based-hardware-dev", "database": "jit-qa", "runner": operator.reconciler.subprocess.run}
    ]
    assert result["manifest_validated"] is True
    assert result["selected_index_count"] == _REGISTRY_COUNT
    assert result["selected_field_index_count"] == _FIELD_COUNT
    assert result["missing_count"] == _REGISTRY_COUNT + _FIELD_COUNT
    assert {entry["state"] for entry in result["indexes"]} == {"MISSING"}
    assert {entry["identifier"] for entry in result["indexes"]} == {
        requirement.identifier for requirement in registry.INDEX_REQUIREMENTS
    }
    assert {
        "chat_first_deferrals_due",
        "action_items_completed_created_newest_first",
        "memory_items_canonical_atlas_read",
    } <= {entry["identifier"] for entry in result["indexes"]}
    assert {entry["identifier"] for entry in result["field_indexes"]} == {
        requirement.identifier for requirement in registry.FIELD_INDEX_REQUIREMENTS
    }
    assert {entry["state"] for entry in result["field_indexes"]} == {"MISSING"}


def test_plan_rejects_non_qa_targets():
    with pytest.raises(operator.IndexOperatorError, match="project is fixed"):
        operator.build_plan(project="based-hardware", database=operator.DATABASE)
    with pytest.raises(operator.IndexOperatorError, match="database is fixed"):
        operator.build_plan(project=operator.PROJECT, database="(default)")


def test_apply_requires_confirmation_and_delegates_only_selected_signatures(monkeypatch):
    calls = []
    monkeypatch.setattr(operator.reconciler, "list_live_indexes", lambda **kwargs: [])
    field_api = _field_api_request()

    def provision_missing_indexes(**kwargs):
        calls.append(("provision", kwargs))
        return set(kwargs["expected"])

    def wait_for_indexes(**kwargs):
        calls.append(("wait", kwargs))

    monkeypatch.setattr(operator.reconciler, "provision_missing_indexes", provision_missing_indexes)
    monkeypatch.setattr(operator.reconciler, "wait_for_indexes", wait_for_indexes)

    with pytest.raises(operator.IndexOperatorError, match="requires APPLY_JIT_QA_INDEXES"):
        operator.apply_plan(
            project=operator.PROJECT,
            database=operator.DATABASE,
            manifest_path=Path(operator.MANIFEST_PATH),
            confirmation="",
            timeout_seconds=1,
            poll_interval_seconds=1,
            field_api_request=field_api,
        )

    result = operator.apply_plan(
        project=operator.PROJECT,
        database=operator.DATABASE,
        confirmation=operator.APPLY_CONFIRMATION,
        timeout_seconds=1,
        poll_interval_seconds=1,
        field_api_request=field_api,
        sleep=lambda _seconds: None,
    )
    assert result["schema_version"] == "omi.jit.qa.firestore-index-apply.v1"
    assert result["created_index_count"] == _REGISTRY_COUNT
    assert result["created_field_index_count"] == _FIELD_COUNT
    assert calls[0][0] == "provision"
    assert calls[1][0] == "wait"
    assert calls[0][1]["project"] == operator.PROJECT
    assert calls[0][1]["database"] == operator.DATABASE
    assert len(calls[0][1]["expected"]) == _REGISTRY_COUNT
    assert calls[1][1]["expected"] == calls[0][1]["expected"]


def test_apply_cli_keeps_reconciler_progress_out_of_json_receipt(monkeypatch, capsys):
    import json

    signatures = operator._target_signatures()
    field_api = _field_api_request(ready=True)
    monkeypatch.setattr(operator.field_indexes, "field_api_request", field_api)
    monkeypatch.setattr(operator.reconciler, "provision_missing_indexes", lambda **kwargs: signatures)
    # Exercise the actual wait function and its READY progress print.
    monkeypatch.setattr(operator.reconciler, "list_live_indexes", lambda **kwargs: [])
    monkeypatch.setattr(
        operator.reconciler,
        "expected_index_states",
        lambda **kwargs: {signature: "READY" for signature in signatures},
    )
    assert (
        operator.main(
            [
                "--project",
                operator.PROJECT,
                "--database",
                operator.DATABASE,
                "apply",
                "--confirmation",
                operator.APPLY_CONFIRMATION,
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt["missing_count"] == 0
    assert receipt["created_index_count"] == _REGISTRY_COUNT
    assert receipt["created_field_index_count"] == 0
    assert "READY" in captured.err


def test_field_patch_preserves_collection_scope_defaults_and_adds_only_group_ascending():
    field_api = _field_api_request()
    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=field_api,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is True
    patch = next(payload for method, _url, payload in field_api.calls if method == "PATCH")
    assert patch["indexConfig"]["indexes"] == [
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
        },
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "DESCENDING"}],
        },
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "arrayConfig": "CONTAINS"}],
        },
        {
            "queryScope": "COLLECTION_GROUP",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
        },
    ]


def test_field_patch_batches_both_declared_modes_for_one_field():
    requirement = next(
        item
        for item in operator.TARGET_FIELD_REQUIREMENTS
        if (item.collection_group, item.field_path) == ('fair_use_events', 'case_ref')
    )
    field_api = _field_api_request()

    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=requirement,
        field_api_request=field_api,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is True
    patches = [payload for method, _url, payload in field_api.calls if method == "PATCH"]
    assert len(patches) == 1
    modes = {
        (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
        for index in patches[0]['indexConfig']['indexes']
    }
    assert {('COLLECTION_GROUP', 'ASCENDING'), ('COLLECTION_GROUP', 'DESCENDING')} <= modes


def test_field_patch_supports_array_contains_mode():
    requirement = next(item for item in operator.TARGET_FIELD_REQUIREMENTS if item.collection_group == 'memories')
    field_api = _field_api_request()

    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=requirement,
        field_api_request=field_api,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is True
    patch = next(payload for method, _url, payload in field_api.calls if method == "PATCH")
    assert {
        'queryScope': 'COLLECTION_GROUP',
        'fields': [{'fieldPath': 'tags', 'arrayConfig': 'CONTAINS'}],
    } in patch[
        'indexConfig'
    ]['indexes']


def test_field_patch_resolves_live_inherited_defaults_before_writing_group_index():
    inherited_indexes = [
        {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/__default__/fields/*",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "*", "order": "ASCENDING"}],
            "state": "READY",
        },
        {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/__default__/fields/*",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "*", "order": "DESCENDING"}],
            "state": "READY",
        },
        {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/__default__/fields/*",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "*", "arrayConfig": "CONTAINS"}],
            "state": "READY",
        },
    ]
    ancestor = "projects/based-hardware-dev/databases/jit-qa/" "collectionGroups/__default__/fields/*"
    patched = None

    def inherited_request(method, url, payload):
        nonlocal patched
        if method == "PATCH":
            patched = payload
            return {"name": "projects/based-hardware-dev/databases/jit-qa/operations/field-update"}
        if 'operations/' in url:
            return {"done": True}
        if method == "GET" and url.endswith("/fields/status"):
            if patched is not None:
                indexes = [{**index, "state": "READY"} for index in patched["indexConfig"]["indexes"]]
                return {
                    "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status",
                    "indexConfig": {"usesAncestorConfig": False, "indexes": indexes},
                }
            return {
                "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status",
                "indexConfig": {
                    "usesAncestorConfig": True,
                    "ancestorField": ancestor,
                    "indexes": inherited_indexes,
                },
            }
        if method == "GET" and url.endswith("/collectionGroups/__default__/fields/*"):
            return {"name": ancestor, "indexConfig": {"usesAncestorConfig": False, "indexes": inherited_indexes}}
        raise AssertionError(f"unexpected request {method} {url}")

    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=inherited_request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is True
    assert patched["indexConfig"]["indexes"] == [
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
        },
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "DESCENDING"}],
        },
        {
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "arrayConfig": "CONTAINS"}],
        },
        {
            "queryScope": "COLLECTION_GROUP",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
        },
    ]


def test_field_target_is_idempotent_when_collection_group_index_is_present():
    field_api = _field_api_request(ready=True)
    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=field_api,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is False
    assert all(method == "GET" for method, _url, _payload in field_api.calls)


def test_field_target_accepts_explicit_any_api_scope():
    field_api = _field_api_request(ready=True, api_scope="ANY_API")

    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=field_api,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is False


def test_field_target_rejects_non_any_api_scope_on_target():
    field_api = _field_api_request(ready=True, api_scope="DATASTORE_MODE_API")

    with pytest.raises(operator.IndexOperatorError, match="apiScope must be ANY_API"):
        operator._field_requirement_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            requirement=_status_requirement(),
            field_api_request=field_api,
        )


@pytest.mark.parametrize("api_scope", ["UNKNOWN_SCOPE", None, 123])
def test_field_target_rejects_invalid_api_scope_on_preserved_index(api_scope):
    field_api = _field_api_request(api_scope=api_scope)

    with pytest.raises(operator.IndexOperatorError, match="apiScope must be ANY_API"):
        operator._field_requirement_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            requirement=_status_requirement(),
            field_api_request=field_api,
        )


def test_field_target_waits_for_existing_creating_index_without_repatching():
    field_api = _field_api_request()
    creating = True

    def request(method, url, payload):
        nonlocal creating
        if method == "PATCH":
            raise AssertionError("existing CREATING index must not be patched again")
        if 'operations/' in url:
            return {"done": True}
        response = copy.deepcopy(field_api(method, url, payload))
        if url.endswith("/fields/status"):
            response["indexConfig"]["indexes"].append(
                {
                    "queryScope": "COLLECTION_GROUP",
                    "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
                    "state": "CREATING" if creating else "READY",
                }
            )
            creating = False
        return response

    changed = operator._apply_field_requirement(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is False


def test_field_target_reports_ready_when_only_an_unrelated_index_is_creating():
    field_api = _field_api_request(ready=True)

    def request(method, url, payload):
        response = copy.deepcopy(field_api(method, url, payload))
        if method == "GET" and url.endswith("/fields/status"):
            response["indexConfig"]["indexes"][0]["state"] = "CREATING"
        return response

    state, patch = operator._field_requirement_state(
        project=operator.PROJECT,
        database=operator.DATABASE,
        requirement=_status_requirement(),
        field_api_request=request,
    )

    assert (state, patch) == ("READY", None)


@pytest.mark.parametrize("replacement", ["NEEDS_REPAIR", None])
def test_field_target_fails_closed_for_preserved_nonready_or_missing_state(replacement):
    field_api = _field_api_request(ready=True)

    def request(method, url, payload):
        response = copy.deepcopy(field_api(method, url, payload))
        if method == "GET" and url.endswith("/fields/status"):
            if replacement is None:
                response["indexConfig"]["indexes"][0].pop("state")
            else:
                response["indexConfig"]["indexes"][0]["state"] = replacement
        return response

    with pytest.raises(operator.IndexOperatorError, match="needs repair|state is missing"):
        operator._field_requirement_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            requirement=_status_requirement(),
            field_api_request=request,
        )


def test_field_target_rejects_needs_repair_state():
    field_api = _field_api_request()
    original = field_api

    def request(method, url, payload):
        response = original(method, url, payload)
        if method == "GET" and url.endswith("/fields/status"):
            response["indexConfig"]["indexes"].append(
                {
                    "queryScope": "COLLECTION_GROUP",
                    "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
                    "state": "NEEDS_REPAIR",
                }
            )
        return response

    with pytest.raises(operator.IndexOperatorError, match="needs repair"):
        operator._field_requirement_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            requirement=_status_requirement(),
            field_api_request=request,
        )


def test_field_target_fails_closed_when_inherited_defaults_are_not_exposed():
    def missing_ancestor(_method, _url, _payload):
        return {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status",
            "indexConfig": {"usesAncestorConfig": True},
        }

    with pytest.raises(operator.IndexOperatorError, match="ancestorField"):
        operator._field_requirement_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            requirement=_status_requirement(),
            field_api_request=missing_ancestor,
        )
