import copy
from pathlib import Path

import pytest

from scripts import jit_qa_firestore_index_operator as operator

_UNSET = object()


def _field_api_request(*, ready: bool = False, api_scope: object = _UNSET):
    indexes = [
        {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status/indexes/asc",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
            "state": "READY",
        },
        {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status/indexes/desc",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "status", "order": "DESCENDING"}],
            "state": "READY",
        },
    ]
    if ready:
        indexes.append(
            {
                "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status/indexes/group",
                "queryScope": "COLLECTION_GROUP",
                "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
                "state": "READY",
            }
        )
    if api_scope is not _UNSET:
        for index in indexes:
            index["apiScope"] = api_scope
    calls = []

    def request(method, url, payload):
        calls.append((method, url, payload))
        if method == "PATCH":
            indexes[:] = [{**index, "state": "READY"} for index in payload["indexConfig"]["indexes"]]
            return {"name": "projects/based-hardware-dev/databases/jit-qa/operations/field-update"}
        if url.endswith("/operations/field-update"):
            return {"done": True}
        return {
            "name": "projects/based-hardware-dev/databases/jit-qa/collectionGroups/conversations/fields/status",
            "indexConfig": {"usesAncestorConfig": False, "indexes": indexes},
        }

    request.calls = calls
    return request


def test_selected_manifest_is_canonical_and_contains_only_bounded_required_queries():
    manifest, signatures = operator.selected_manifest()

    assert len(manifest["indexes"]) == 11
    assert signatures == {requirement.signature for requirement in operator.TARGET_REQUIREMENTS}
    assert {
        (
            entry["collectionGroup"],
            entry["queryScope"],
            tuple((field["fieldPath"], field.get("order")) for field in entry["fields"]),
        )
        for entry in manifest["indexes"]
    } == signatures


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
    assert result["selected_index_count"] == 11
    assert result["selected_field_index_count"] == 1
    assert result["missing_count"] == 12
    assert {entry["state"] for entry in result["indexes"]} == {"MISSING"}
    assert {entry["identifier"] for entry in result["indexes"]} == {
        "memory_items_universal_list_scan",
        "conversations_entity_timeline_completed",
        "memories_universal_list_scan_updated_at",
        "memories_universal_list_scan_created_at",
        "daily_sweep_active_fact_subject",
        "daily_sweep_active_fact_slot",
        "daily_sweep_active_fact_entity",
        "daily_sweep_active_fact_entity_slot",
        "daily_sweep_active_fact_subject_content",
        "daily_sweep_active_fact_entity_content",
        "conversation_finalization_jobs_oldest_nonterminal",
    }
    assert result["field_indexes"] == [
        {
            "identifier": "conversations_status_collection_group_ascending",
            "collection_group": "conversations",
            "field_path": "status",
            "query_scope": "COLLECTION_GROUP",
            "order": "ASCENDING",
            "state": "MISSING",
        }
    ]


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
    )
    assert result["schema_version"] == "omi.jit.qa.firestore-index-apply.v1"
    assert result["created_index_count"] == 11
    assert result["created_field_index_count"] == 1
    assert calls[0][0] == "provision"
    assert calls[1][0] == "wait"
    assert calls[0][1]["project"] == operator.PROJECT
    assert calls[0][1]["database"] == operator.DATABASE
    assert len(calls[0][1]["expected"]) == 11
    assert calls[1][1]["expected"] == calls[0][1]["expected"]


def test_apply_cli_keeps_reconciler_progress_out_of_json_receipt(monkeypatch, capsys):
    import json

    signatures = operator._target_signatures()
    field_api = _field_api_request()
    monkeypatch.setattr(operator, "_field_api_request", field_api)
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
    assert receipt["created_index_count"] == 11
    assert receipt["created_field_index_count"] == 1
    assert "READY" in captured.err


def test_field_patch_preserves_collection_scope_defaults_and_adds_only_group_ascending():
    field_api = _field_api_request()
    changed = operator._apply_field_target(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
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
            "queryScope": "COLLECTION_GROUP",
            "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
        },
    ]


def test_field_patch_resolves_live_inherited_defaults_before_writing_group_index():
    field_api = _field_api_request()
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
    patched = False

    def inherited_request(method, url, payload):
        nonlocal patched
        if method == "PATCH":
            patched = True
            return field_api(method, url, payload)
        if method == "GET" and url.endswith("/fields/status") and not patched:
            return {
                "indexConfig": {
                    "usesAncestorConfig": True,
                    "ancestorField": ancestor,
                    "indexes": inherited_indexes,
                }
            }
        if method == "GET" and url.endswith("/collectionGroups/__default__/fields/*"):
            return {"indexConfig": {"usesAncestorConfig": False, "indexes": inherited_indexes}}
        return field_api(method, url, payload)

    changed = operator._apply_field_target(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
        field_api_request=inherited_request,
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


def test_field_target_is_idempotent_when_collection_group_index_is_present():
    field_api = _field_api_request(ready=True)
    changed = operator._apply_field_target(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
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

    changed = operator._apply_field_target(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
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
        operator._field_target_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            target=operator.TARGET_FIELD_INDEXES[0],
            field_api_request=field_api,
        )


@pytest.mark.parametrize("api_scope", ["UNKNOWN_SCOPE", None, 123])
def test_field_target_rejects_invalid_api_scope_on_preserved_index(api_scope):
    field_api = _field_api_request(api_scope=api_scope)

    with pytest.raises(operator.IndexOperatorError, match="apiScope must be ANY_API"):
        operator._field_target_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            target=operator.TARGET_FIELD_INDEXES[0],
            field_api_request=field_api,
        )


def test_field_target_waits_for_existing_creating_index_without_repatching():
    field_api = _field_api_request()
    creating = True

    def request(method, url, payload):
        nonlocal creating
        if method == "PATCH":
            raise AssertionError("existing CREATING index must not be patched again")
        if url.endswith("/operations/field-update"):
            return {"done": True}
        response = copy.deepcopy(field_api(method, url, payload))
        if url.endswith("/fields/status"):
            response["indexConfig"]["indexes"] = [
                index
                for index in response["indexConfig"]["indexes"]
                if not (
                    index.get("queryScope") == "COLLECTION_GROUP"
                    and index.get("fields") == [{"fieldPath": "status", "order": "ASCENDING"}]
                )
            ]
            response["indexConfig"]["indexes"].append(
                {
                    "queryScope": "COLLECTION_GROUP",
                    "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
                    "state": "CREATING" if creating else "READY",
                }
            )
            creating = False
        return response

    changed = operator._apply_field_target(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
        field_api_request=request,
        timeout_seconds=1,
        poll_interval_seconds=1,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
    )

    assert changed is False


def test_field_target_waits_for_preserved_creating_index_even_when_target_is_ready():
    field_api = _field_api_request(ready=True)

    def request(method, url, payload):
        response = copy.deepcopy(field_api(method, url, payload))
        if method == "GET" and url.endswith("/fields/status"):
            response["indexConfig"]["indexes"][0]["state"] = "CREATING"
        return response

    state, patch = operator._field_target_state(
        project=operator.PROJECT,
        database=operator.DATABASE,
        target=operator.TARGET_FIELD_INDEXES[0],
        field_api_request=request,
    )

    assert (state, patch) == ("CREATING", None)


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
        operator._field_target_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            target=operator.TARGET_FIELD_INDEXES[0],
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
        operator._field_target_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            target=operator.TARGET_FIELD_INDEXES[0],
            field_api_request=request,
        )


def test_field_target_fails_closed_when_inherited_defaults_are_not_exposed():
    def missing_ancestor(_method, _url, _payload):
        return {"indexConfig": {"usesAncestorConfig": True}}

    with pytest.raises(operator.IndexOperatorError, match="ancestorField"):
        operator._field_target_state(
            project=operator.PROJECT,
            database=operator.DATABASE,
            target=operator.TARGET_FIELD_INDEXES[0],
            field_api_request=missing_ancestor,
        )
