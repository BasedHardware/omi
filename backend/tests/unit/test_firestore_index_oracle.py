from __future__ import annotations

import base64
import datetime
import json
import math
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from google.api_core.exceptions import FailedPrecondition, InvalidArgument, PermissionDenied
from google.cloud import firestore_admin_v1
from google.cloud.firestore_v1.base_query import FieldFilter

from scripts import firestore_index_oracle as oracle
from tests.support import firestore_index_rules as rules
from tests.support.firestore_query_driver_registry import DRIVERS
from tests.support.firestore_query_drivers import run_driver
from tests.support.firestore_shape_recorder import QueryFilter, QueryShape, _encode_value
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient

NAMESPACE = "index-oracle-fixture"
PROJECT = "based-hardware-dev"
DATABASE = "jit-qa"
PARENT = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/-"

PROD_DECODED_TOKEN = "ClRwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS9kYXRhYmFzZXMvKGRlZmF1bHQpL2NvbGxlY3Rpb25Hcm91cHMvY29udmVyc2F0aW9ucy9pbmRleGVzL18QARoNCglkaXNjYXJkZWQQARoOCgpjcmVhdGVkX2F0EAEaDAoIX19uYW1lX18QAQ"


def _asc(field):
    return firestore_admin_v1.Index.IndexField(field_path=field, order="ASCENDING")


def _desc(field):
    return firestore_admin_v1.Index.IndexField(field_path=field, order="DESCENDING")


def _contains(field):
    return firestore_admin_v1.Index.IndexField(field_path=field, array_config="CONTAINS")


def _token(
    fields,
    collection="conversations",
    scope="COLLECTION",
    project="based-hardware",
    database="(default)",
    state="READY",
):
    index = firestore_admin_v1.Index(
        name=f"projects/{project}/databases/{database}/collectionGroups/{collection}/indexes/_",
        query_scope=scope,
        state=state,
        fields=fields,
    )
    return base64.urlsafe_b64encode(firestore_admin_v1.Index.serialize(index)).decode()


def _message(token):
    return f"no matching index found; create it here: https://x/?create_composite={token}"


def _precondition(token=None):
    return FailedPrecondition(_message(token) if token else "no matching index found")


def _field_index(fields, collection="conversations", scope="COLLECTION", state="READY", api_scope="ANY_API"):
    return firestore_admin_v1.Index(
        name=f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{collection}/indexes/_",
        query_scope=scope,
        state=state,
        api_scope=api_scope,
        fields=fields,
    )


def _field(name, config=None):
    return firestore_admin_v1.Field(name=name, **({"index_config": config} if config is not None else {}))


def _index_config(indexes, uses_ancestor=False, ancestor=None, reverting=False):
    return firestore_admin_v1.Field.IndexConfig(
        indexes=indexes,
        uses_ancestor_config=uses_ancestor,
        ancestor_field=ancestor or "",
        reverting=reverting,
    )


def _manifest_index(fields, collection="conversations", scope="COLLECTION"):
    return {
        "collectionGroup": collection,
        "queryScope": scope,
        "fields": [
            {"fieldPath": field, "arrayConfig" if mode == "CONTAINS" else "order": mode} for field, mode in fields
        ],
    }


def _leaf(field, operator, value):
    return {"field": field, "operator": operator, "value": _encode(value)}


def _encode(value):
    return _encode_value(value)


def _encoded_shape(**overrides):
    shape = {
        "collection_group": "conversations",
        "scope": "COLLECTION",
        "collection_path": "users/original-uid/conversations",
        "filters": [_leaf("discarded", "==", False), _leaf("created_at", ">=", "2026-01-01T00:00:00")],
        "filter_tree": None,
        "orders": [{"field": "created_at", "direction": "ASCENDING"}],
        "aggregations": [],
        "cursors": [],
        "limit": 1,
        "limit_to_last": False,
        "offset": 0,
        "projection": None,
    }
    shape.update(overrides)
    return shape


def _entry(entry_id, shape=None, calling_function="database.a", driver_function="driver", parameter_combo=None):
    return {
        "id": entry_id,
        "shape": shape if shape is not None else _encoded_shape(),
        "calling_function": calling_function,
        "driver_function": driver_function,
        "parameter_combo": parameter_combo or {},
        "served": True,
    }


class FakeQuery:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def get(self, retry=None, timeout=None):
        self.calls.append({"retry": retry, "timeout": timeout})
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeBuilder(FakeQuery):
    def __init__(self, outcome):
        super().__init__(outcome)
        self.built = 0

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def select(self, *args, **kwargs):
        return self

    def start_at(self, *args, **kwargs):
        return self

    def start_after(self, *args, **kwargs):
        return self

    def end_at(self, *args, **kwargs):
        return self

    def end_before(self, *args, **kwargs):
        return self

    def count(self, *args, **kwargs):
        return self

    def sum(self, *args, **kwargs):
        return self

    def avg(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.built += 1
        return self

    def offset(self, count):
        return self


class FakeClient:
    def __init__(self, outcomes=None, default=None):
        self.outcomes = dict(outcomes or {})
        self.default = default if default is not None else []
        self.builders = {}
        self.document_calls = []

    def collection_group(self, group):
        builder = FakeBuilder(self.outcomes.get(group, self.default))
        self.builders[group] = builder
        return builder

    def collection(self, path):
        builder = FakeBuilder(self.outcomes.get(path, self.default))
        self.builders[path] = builder
        return builder

    def document(self, path):
        self.document_calls.append(path)
        raise AssertionError(f"unexpected document lookup: {path}")


class _PassLimiter:
    def __init__(self):
        self.waits = 0

    def wait(self, deadline):
        self.waits += 1
        return True


def _run_groups(entries, client, manifest=None, concurrency=4):
    groups = oracle.deduplicate(entries)
    return oracle.run_groups(
        groups,
        client,
        manifest or {"indexes": [], "fieldOverrides": []},
        NAMESPACE,
        concurrency,
        10.0,
        _PassLimiter(),
        time.monotonic() + 60,
    )


def test_decode_suggested_index_matches_known_prod_decoded_fixture():
    suggestion = oracle.decode_suggested_index(_message(PROD_DECODED_TOKEN))
    assert suggestion == {
        "collectionGroup": "conversations",
        "queryScope": "COLLECTION",
        "fields": [
            {"fieldPath": "discarded", "order": "ASCENDING"},
            {"fieldPath": "created_at", "order": "ASCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
        ],
    }


@pytest.mark.parametrize(
    "fields,scope,expected",
    [
        ([_asc("a"), _asc("__name__")], "COLLECTION_GROUP", {"a": "ASCENDING"}),
        ([_asc("a"), _desc("__name__")], "COLLECTION", {"__name__": "DESCENDING"}),
        ([_contains("tags"), _asc("__name__")], "COLLECTION", {"tags": "CONTAINS"}),
    ],
)
def test_decode_suggested_index_accepts_scope_order_and_array_variants(fields, scope, expected):
    suggestion = oracle.decode_suggested_index(_message(_token(fields, scope=scope)))
    assert suggestion["queryScope"] == scope
    modes = {field["fieldPath"]: field.get("order") or field.get("arrayConfig") for field in suggestion["fields"]}
    for field, mode in expected.items():
        assert modes[field] == mode


@pytest.mark.parametrize("transform", ["unpadded", "percent_encoded"])
def test_decode_suggested_index_accepts_unpadded_and_percent_encoded_tokens(transform):
    token = _token([_asc("a"), _asc("__name__")])
    if transform == "unpadded":
        token = token.rstrip("=")
    else:
        token = quote(token, safe="")
    suggestion = oracle.decode_suggested_index(_message(token))
    assert suggestion["collectionGroup"] == "conversations"


@pytest.mark.parametrize(
    "message",
    [
        "no suggestion at all",
        _message("%%%"),
        _message(base64.b64encode(b"\x08").decode()),
        _message(_token([firestore_admin_v1.Index.IndexField(field_path="a")])),
        _message(_token([_asc("a"), _asc("a")])),
        _message(_token([_asc("a"), _asc("__name__")])[:-8]),
    ],
)
def test_decode_suggested_index_rejects_malformed_suggestions(message):
    with pytest.raises(Exception):
        oracle.decode_suggested_index(message)


def test_decode_suggested_index_rejects_unsupported_query_scope():
    index = firestore_admin_v1.Index(
        name=f"projects/based-hardware/databases/(default)/collectionGroups/conversations/indexes/_",
        fields=[_asc("a"), _asc("__name__")],
    )
    token = base64.b64encode(firestore_admin_v1.Index.serialize(index)).decode()
    with pytest.raises(ValueError):
        oracle.decode_suggested_index(_message(token))


def test_execute_query_reports_served_rows_and_disables_retry():
    query = FakeQuery([])
    result = oracle.execute_query(query, 3.5)
    assert result == {"status": "served", "result_rows": 0}
    assert query.calls == [{"retry": oracle.NO_RETRY, "timeout": 3.5}]
    assert oracle.NO_RETRY._predicate(FailedPrecondition("x")) is False
    assert oracle.execute_query(FakeQuery([object()]), 1.0)["result_rows"] == 1


def test_execute_query_unserved_decodes_exact_suggestion():
    token = _token([_asc("discarded"), _asc("created_at"), _asc("__name__")])
    result = oracle.execute_query(FakeQuery(_precondition(token)), 1.0)
    assert result["status"] == "unserved"
    assert result["suggested_index"] == {
        "collectionGroup": "conversations",
        "queryScope": "COLLECTION",
        "fields": [
            {"fieldPath": "discarded", "order": "ASCENDING"},
            {"fieldPath": "created_at", "order": "ASCENDING"},
            {"fieldPath": "__name__", "order": "ASCENDING"},
        ],
    }


@pytest.mark.parametrize(
    "exc,error_type",
    [
        (_precondition(), "FailedPrecondition"),
        (PermissionDenied("denied"), "PermissionDenied"),
        (InvalidArgument("bad"), "InvalidArgument"),
        (RuntimeError("boom"), "RuntimeError"),
    ],
)
def test_execute_query_classifies_errors_without_suggestions(exc, error_type):
    result = oracle.execute_query(FakeQuery(exc), 1.0)
    assert result["status"] == "error"
    assert result["error_type"] == error_type
    assert "suggested_index" not in result


def test_execute_query_malformed_suggestion_is_decode_error_not_guess():
    result = oracle.execute_query(FakeQuery(_precondition("%%%")), 1.0)
    assert result["status"] == "error"
    assert result["error_type"] == "SuggestionDecodeError"


def _exemption_message(token):
    return f"index is exempted; create it here: https://x/?create_exemption={token}"


def _exemption_token(field, collection="conversations", scope="COLLECTION_GROUP", mode="ASCENDING", leaf=None):
    index = firestore_admin_v1.Index(
        name=f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/{collection}/fields/{leaf or field}",
        query_scope=scope,
        fields=[firestore_admin_v1.Index.IndexField(field_path=field, order=mode)],
    )
    return base64.urlsafe_b64encode(firestore_admin_v1.Index.serialize(index)).decode()


EXEMPTION_TOKENS = {
    "96bb4f6af065cbe3": (
        "candidate_integration_outbox",
        "status",
        "Cmhwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL2NhbmRpZGF0ZV9pbnRlZ3JhdGlvbl9vdXRib3gvZmllbGRzL3N0YXR1cxACGgoKBnN0YXR1cxAB",
    ),
    "1616723a69adb00c": (
        "chat_first_proactive_intents",
        "delivery_state",
        "CnBwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL2NoYXRfZmlyc3RfcHJvYWN0aXZlX2ludGVudHMvZmllbGRzL2RlbGl2ZXJ5X3N0YXRlEAIaEgoOZGVsaXZlcnlfc3RhdGUQAQ",
    ),
    "3999cbd3c1d1f287": (
        "fcm_tokens",
        "token",
        "ClVwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL2ZjbV90b2tlbnMvZmllbGRzL3Rva2VuEAIaCQoFdG9rZW4QAQ",
    ),
    "89fa7f36c3668de0": (
        "fcm_tokens",
        "token",
        "ClVwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL2ZjbV90b2tlbnMvZmllbGRzL3Rva2VuEAIaCQoFdG9rZW4QAQ",
    ),
    "26cf2251c7e5c9a5": (
        "llm_usage",
        "date",
        "ClNwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL2xsbV91c2FnZS9maWVsZHMvZGF0ZRACGggKBGRhdGUQAQ",
    ),
    "f9179fb85d7f9f79": (
        "memory_outbox",
        "status",
        "Cllwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL21lbW9yeV9vdXRib3gvZmllbGRzL3N0YXR1cxACGgoKBnN0YXR1cxAB",
    ),
    "822d5b56e5c6c5b5": (
        "projection_repairs",
        "status",
        "Cl5wcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL3Byb2plY3Rpb25fcmVwYWlycy9maWVsZHMvc3RhdHVzEAIaCgoGc3RhdHVzEAE",
    ),
    "ef5612c842c5106b": (
        "task_recurrence_inbox",
        "status",
        "CmFwcm9qZWN0cy9iYXNlZC1oYXJkd2FyZS1kZXYvZGF0YWJhc2VzL2ppdC1xYS9jb2xsZWN0aW9uR3JvdXBzL3Rhc2tfcmVjdXJyZW5jZV9pbmJveC9maWVsZHMvc3RhdHVzEAIaCgoGc3RhdHVzEAE",
    ),
}


@pytest.mark.parametrize("query_id", sorted(EXEMPTION_TOKENS))
def test_decode_suggested_index_decodes_real_create_exemption_tokens(query_id):
    collection, field, token = EXEMPTION_TOKENS[query_id]
    suggestion = oracle.decode_suggested_index(_exemption_message(token))
    assert suggestion == {
        "collectionGroup": collection,
        "queryScope": "COLLECTION_GROUP",
        "fields": [{"fieldPath": field, "order": "ASCENDING"}],
    }


@pytest.mark.parametrize("mode", ["ASCENDING", "DESCENDING"])
def test_decode_suggested_index_accepts_exemption_order_modes(mode):
    suggestion = oracle.decode_suggested_index(_exemption_message(_exemption_token("status", mode=mode)))
    assert suggestion["fields"] == [{"fieldPath": "status", "order": mode}]


def test_decode_suggested_index_accepts_exemption_array_mode():
    index = firestore_admin_v1.Index(
        name=f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/tags",
        query_scope="COLLECTION",
        fields=[_contains("tags")],
    )
    token = base64.urlsafe_b64encode(firestore_admin_v1.Index.serialize(index)).decode()
    suggestion = oracle.decode_suggested_index(_exemption_message(token))
    assert suggestion["fields"] == [{"fieldPath": "tags", "arrayConfig": "CONTAINS"}]


@pytest.mark.parametrize(
    "token",
    [
        "%%%",
        base64.b64encode(b"\x08").decode(),
        _exemption_token("other", leaf="status"),
        _exemption_token("status", leaf="fields/too/deep"),
    ],
)
def test_decode_suggested_index_rejects_malformed_exemptions(token):
    with pytest.raises(Exception):
        oracle.decode_suggested_index(_exemption_message(token))


def test_decode_suggested_index_rejects_multi_field_exemption():
    index = firestore_admin_v1.Index(
        name=f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/status",
        query_scope="COLLECTION_GROUP",
        fields=[_asc("status"), _asc("other")],
    )
    token = base64.urlsafe_b64encode(firestore_admin_v1.Index.serialize(index)).decode()
    with pytest.raises(ValueError):
        oracle.decode_suggested_index(_exemption_message(token))


def test_decode_suggested_index_rejects_exemption_kind_mismatch():
    suggestion_kind = _token([_asc("a"), _asc("__name__")])
    with pytest.raises(ValueError):
        oracle.decode_suggested_index(_exemption_message(suggestion_kind))
    exemption_kind = _exemption_token("status")
    with pytest.raises(ValueError):
        oracle.decode_suggested_index(_message(exemption_kind))


def test_execute_query_unserved_decodes_exemption_suggestion():
    token = _exemption_token("status", collection="memory_outbox")
    result = oracle.execute_query(FakeQuery(FailedPrecondition(_exemption_message(token))), 1.0)
    assert result["status"] == "unserved"
    assert result["suggested_index"] == {
        "collectionGroup": "memory_outbox",
        "queryScope": "COLLECTION_GROUP",
        "fields": [{"fieldPath": "status", "order": "ASCENDING"}],
    }


def test_execute_query_malformed_exemption_is_decode_error():
    result = oracle.execute_query(FakeQuery(FailedPrecondition(_exemption_message("%%%"))), 1.0)
    assert result["status"] == "error"
    assert result["error_type"] == "SuggestionDecodeError"


def test_registry_cursor_driver_exports_snapshot_cursor(sdk_client, monkeypatch):
    """The compatibility-page driver passes a real snapshot, not a scalar cursor."""
    result = run_driver(DRIVERS["database.candidates.list_candidates_compatibility_page"])
    assert not result.errors
    cursor_shapes = [shape for shape in result.shapes if shape.cursors]
    assert cursor_shapes
    encoded = cursor_shapes[0].to_dict()
    cursor = next(item for item in encoded["cursors"] if item["kind"] == "start_after")
    assert cursor["value"]["type"] == "snapshot"
    assert "created_at" in cursor["value"]["value"]
    shape = oracle.hydrate_shape(encoded, sdk_client, NAMESPACE)
    pb = oracle.build_query(shape, sdk_client)._to_protobuf()
    assert pb.start_at.values


def test_execute_query_real_sdk_query_propagates_iterator_failure_once(monkeypatch):
    client = OfflineFirestoreClient(project=PROJECT, database=DATABASE)
    query = (
        client.collection("users/u/conversations")
        .where(filter=FieldFilter("discarded", "==", False))
        .order_by("created_at")
        .limit(1)
    )
    calls = []

    def failing_iterator(transaction=None, retry=None, timeout=None, explain_options=None):
        calls.append(1)

        def generator():
            raise FailedPrecondition(_message(_token([_asc("discarded"), _asc("created_at"), _asc("__name__")])))
            yield

        return generator(), "unused-prefix"

    monkeypatch.setattr(query, "_get_stream_iterator", failing_iterator)
    result = oracle.execute_query(query, 5.0)
    assert result["status"] == "unserved"
    assert result["suggested_index"]["collectionGroup"] == "conversations"
    assert calls == [1]


def _candidate_shape():
    return QueryShape(
        collection_group="conversations",
        scope="COLLECTION",
        collection_path="users/u/conversations",
        filters=(QueryFilter("discarded", "==", False), QueryFilter("created_at", ">=", object())),
        orders=(("created_at", "ASCENDING"),),
    )


def _candidate_manifest():
    return {
        "indexes": [
            _manifest_index([("discarded", "ASCENDING"), ("created_at", "ASCENDING"), ("__name__", "ASCENDING")])
        ],
        "fieldOverrides": [],
    }


def _suggestion(fields, collection="conversations", scope="COLLECTION"):
    return {
        "collectionGroup": collection,
        "queryScope": scope,
        "fields": [
            {"fieldPath": field, "arrayConfig" if mode == "CONTAINS" else "order": mode} for field, mode in fields
        ],
    }


_MATCHING_SUGGESTION = _suggestion([("discarded", "ASCENDING"), ("created_at", "ASCENDING"), ("__name__", "ASCENDING")])


def test_compare_prediction_predicts_served_and_flags_unserved_observation():
    shape = _candidate_shape()
    comparison = oracle.compare_prediction(shape, _candidate_manifest(), {"status": "served", "result_rows": 0})
    assert comparison["predicted_served"] is True
    assert comparison["rule_bugs"] == []
    observed = {"status": "unserved", "suggested_index": _MATCHING_SUGGESTION}
    comparison = oracle.compare_prediction(shape, _candidate_manifest(), observed)
    assert comparison["rule_bugs"] == ["predicted_served_but_unserved"]


def test_compare_prediction_accepts_matching_suggestion_on_empty_manifest():
    observed = {"status": "unserved", "suggested_index": _MATCHING_SUGGESTION}
    comparison = oracle.compare_prediction(_candidate_shape(), {"indexes": [], "fieldOverrides": []}, observed)
    assert comparison["predicted_served"] is False
    assert comparison["rule_bugs"] == []


@pytest.mark.parametrize(
    "suggested",
    [
        _suggestion([("discarded", "ASCENDING"), ("created_at", "DESCENDING"), ("__name__", "DESCENDING")]),
        _suggestion([("discarded", "ASCENDING"), ("created_at", "ASCENDING"), ("__name__", "DESCENDING")]),
        _suggestion(
            [
                ("discarded", "ASCENDING"),
                ("created_at", "ASCENDING"),
                ("extra", "ASCENDING"),
                ("__name__", "ASCENDING"),
            ]
        ),
        _suggestion([("discarded", "ASCENDING"), ("__name__", "ASCENDING")]),
        _suggestion(
            [
                ("discarded", "ASCENDING"),
                ("discarded", "ASCENDING"),
                ("created_at", "ASCENDING"),
                ("__name__", "ASCENDING"),
            ]
        ),
        _suggestion(
            [("discarded", "ASCENDING"), ("created_at", "ASCENDING"), ("__name__", "ASCENDING")],
            collection="other",
        ),
        _suggestion(
            [("discarded", "ASCENDING"), ("created_at", "ASCENDING"), ("__name__", "ASCENDING")],
            scope="COLLECTION_GROUP",
        ),
    ],
)
def test_compare_prediction_rejects_mismatching_suggestions(suggested):
    observed = {"status": "unserved", "suggested_index": suggested}
    comparison = oracle.compare_prediction(_candidate_shape(), {"indexes": [], "fieldOverrides": []}, observed)
    assert "suggested_index_mismatch" in comparison["rule_bugs"]


def test_compare_prediction_reorders_equality_prefix_but_keeps_array_and_suffix():
    shape = QueryShape(
        collection_group="conversations",
        scope="COLLECTION",
        collection_path="users/u/conversations",
        filters=(
            QueryFilter("a", "==", 1),
            QueryFilter("b", "==", 2),
            QueryFilter("tags", "array_contains", "x"),
            QueryFilter("created_at", ">=", object()),
        ),
        orders=(("created_at", "ASCENDING"),),
    )
    manifest = {"indexes": [], "fieldOverrides": []}
    reordered = _suggestion(
        [
            ("b", "DESCENDING"),
            ("a", "ASCENDING"),
            ("tags", "CONTAINS"),
            ("created_at", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ]
    )
    comparison = oracle.compare_prediction(shape, manifest, {"status": "unserved", "suggested_index": reordered})
    assert comparison["rule_bugs"] == []
    array_as_equality = _suggestion(
        [
            ("b", "ASCENDING"),
            ("a", "ASCENDING"),
            ("tags", "ASCENDING"),
            ("created_at", "ASCENDING"),
            ("__name__", "ASCENDING"),
        ]
    )
    comparison = oracle.compare_prediction(
        shape, manifest, {"status": "unserved", "suggested_index": array_as_equality}
    )
    assert "suggested_index_mismatch" in comparison["rule_bugs"]
    moved_into_suffix = _suggestion(
        [
            ("b", "ASCENDING"),
            ("created_at", "ASCENDING"),
            ("a", "ASCENDING"),
            ("tags", "CONTAINS"),
            ("__name__", "ASCENDING"),
        ]
    )
    comparison = oracle.compare_prediction(
        shape, manifest, {"status": "unserved", "suggested_index": moved_into_suffix}
    )
    assert "suggested_index_mismatch" in comparison["rule_bugs"]


def test_compare_prediction_required_none_still_rejects_unserved_suggestion():
    shape = QueryShape(
        collection_group="conversations",
        scope="COLLECTION",
        collection_path="users/u/conversations",
        filters=(QueryFilter("discarded", "==", False),),
    )
    comparison = oracle.compare_prediction(
        shape,
        {"indexes": [], "fieldOverrides": []},
        {"status": "unserved", "suggested_index": _suggestion([("discarded", "ASCENDING"), ("__name__", "ASCENDING")])},
    )
    assert comparison["required_index"] is None
    assert "suggested_index_mismatch" in comparison["rule_bugs"]


def test_equivalent_suggestion_does_not_delegate_to_matches_index(monkeypatch):
    monkeypatch.setattr(rules, "matches_index", lambda *args, **kwargs: True)
    wrong = _suggestion([("discarded", "ASCENDING"), ("created_at", "DESCENDING"), ("__name__", "DESCENDING")])
    comparison = oracle.compare_prediction(
        _candidate_shape(),
        {"indexes": [], "fieldOverrides": []},
        {"status": "unserved", "suggested_index": wrong},
    )
    assert "suggested_index_mismatch" in comparison["rule_bugs"]


def _uncertain_shape():
    shape = QueryShape(
        collection_group="conversations",
        scope="COLLECTION_GROUP",
        collection_path="conversations",
        filters=(QueryFilter("a", "==", 1), QueryFilter("b", "==", 2)),
    )
    assert rules.candidate_index(shape).uncertain
    return shape


def _uncertain_manifest():
    return {
        "indexes": [
            _manifest_index(
                [("a", "ASCENDING"), ("b", "ASCENDING"), ("__name__", "ASCENDING")],
                scope="COLLECTION_GROUP",
            )
        ],
        "fieldOverrides": [],
    }


def test_uncertain_served_without_candidate_is_reviewed_and_resolved():
    comparison = oracle.compare_prediction(
        _uncertain_shape(), {"indexes": [], "fieldOverrides": []}, {"status": "served", "result_rows": 0}
    )
    assert comparison["uncertain"] is True
    assert comparison["predicted_served"] is False
    assert comparison["review_findings"] == ["predicted_unserved_but_served"]
    assert comparison["resolution"] == "observed_served_without_full_candidate"


def test_uncertain_served_with_exact_candidate_stays_unresolved():
    comparison = oracle.compare_prediction(
        _uncertain_shape(), _uncertain_manifest(), {"status": "served", "result_rows": 0}
    )
    assert comparison["predicted_served"] is True
    assert comparison["resolution"] is None


def test_uncertain_matching_unserved_confirms_required_index():
    suggestion = _suggestion(
        [("a", "ASCENDING"), ("b", "ASCENDING"), ("__name__", "ASCENDING")], scope="COLLECTION_GROUP"
    )
    comparison = oracle.compare_prediction(
        _uncertain_shape(),
        {"indexes": [], "fieldOverrides": []},
        {"status": "unserved", "suggested_index": suggestion},
    )
    assert comparison["resolution"] == "confirmed_required_index"


@pytest.mark.parametrize(
    "observed",
    [
        {"status": "error", "error_type": "RuntimeError", "error": "x"},
        {
            "status": "unserved",
            "suggested_index": _suggestion(
                [("a", "ASCENDING"), ("b", "DESCENDING"), ("__name__", "DESCENDING")],
                scope="COLLECTION_GROUP",
            ),
        },
    ],
)
def test_uncertain_error_or_mismatch_gives_no_resolution(observed):
    comparison = oracle.compare_prediction(_uncertain_shape(), {"indexes": [], "fieldOverrides": []}, observed)
    assert comparison["resolution"] is None


@pytest.fixture()
def sdk_client():
    return OfflineFirestoreClient(project=PROJECT, database=DATABASE)


def test_hydration_uses_synthetic_collection_path_and_group_keeps_id(sdk_client):
    shape = oracle.hydrate_shape(_encoded_shape(), sdk_client, NAMESPACE)
    assert shape.collection_path == f"users/{NAMESPACE}/conversations"
    query = oracle.build_query(shape, sdk_client)
    pb = query._to_protobuf()
    assert "/".join(query._parent._path) == f"users/{NAMESPACE}/conversations"
    assert pb.from_[0].collection_id == "conversations"
    assert pb.from_[0].all_descendants is False

    group = oracle.hydrate_shape(_encoded_shape(scope="COLLECTION_GROUP"), sdk_client, NAMESPACE)
    pb = oracle.build_query(group, sdk_client)._to_protobuf()
    assert pb.from_[0].collection_id == "conversations"
    assert pb.from_[0].all_descendants is True


def test_nested_boolean_tree_and_operator_translation_survive_to_wire(sdk_client):
    encoded = _encoded_shape(
        filter_tree={
            "op": "AND",
            "filters": [
                _leaf("tags", "array_contains", "x"),
                {
                    "op": "OR",
                    "filters": [
                        _leaf("flag", "not_in", [1, 2]),
                        _leaf("mode", "array_contains_any", ["a", "b"]),
                    ],
                },
            ],
        },
        orders=[],
    )
    pb = oracle.build_query(oracle.hydrate_shape(encoded, sdk_client, NAMESPACE), sdk_client)._to_protobuf()
    where = pb.where
    assert where.composite_filter.op.name == "AND"
    leaf_ops = {
        f.field_filter.op.name
        for f in where.composite_filter.filters
        if type(f).pb(f).WhichOneof("filter_type") == "field_filter"
    }
    assert leaf_ops == {"ARRAY_CONTAINS"}
    nested = [
        f for f in where.composite_filter.filters if type(f).pb(f).WhichOneof("filter_type") == "composite_filter"
    ]
    assert len(nested) == 1
    assert nested[0].composite_filter.op.name == "OR"
    nested_ops = {f.field_filter.op.name for f in nested[0].composite_filter.filters}
    assert nested_ops == {"NOT_IN", "ARRAY_CONTAINS_ANY"}


def test_decode_value_decodes_all_supported_kinds(sdk_client):
    path = f"users/{NAMESPACE}/conversations"
    assert oracle.decode_value({"type": "null", "value": None}, sdk_client, path) is None
    assert oracle.decode_value({"type": "bool", "value": True}, sdk_client, path) is True
    assert oracle.decode_value({"type": "int", "value": 7}, sdk_client, path) == 7
    assert oracle.decode_value({"type": "str", "value": "x"}, sdk_client, path) == "x"
    assert oracle.decode_value({"type": "float", "value": "NaN"}, sdk_client, path) != 0
    assert math.isnan(oracle.decode_value({"type": "float", "value": "NaN"}, sdk_client, path))
    assert oracle.decode_value({"type": "float", "value": "Infinity"}, sdk_client, path) == float("inf")
    assert oracle.decode_value({"type": "float", "value": "-Infinity"}, sdk_client, path) == float("-inf")
    stamp = oracle.decode_value({"type": "timestamp", "value": "2026-01-01T00:00:00"}, sdk_client, path)
    assert isinstance(stamp, datetime.datetime) and stamp.year == 2026
    assert oracle.decode_value({"type": "date", "value": "2026-01-02"}, sdk_client, path) == datetime.date(2026, 1, 2)
    assert oracle.decode_value({"type": "bytes", "value": base64.b64encode(b"ab").decode()}, sdk_client, path) == b"ab"
    assert oracle.decode_value({"type": "array", "value": [{"type": "int", "value": 1}]}, sdk_client, path) == [1]
    assert oracle.decode_value({"type": "map", "value": {"k": {"type": "int", "value": 2}}}, sdk_client, path) == {
        "k": 2
    }

    reference = oracle.decode_value(
        {"type": "reference", "value": "users/original-uid/conversations/original-doc"}, sdk_client, path
    )
    assert reference.path.startswith(f"users/{NAMESPACE}/conversations/oracle-")
    assert "original-uid" not in reference.path and "original-doc" not in reference.path

    snapshot = oracle.decode_value(
        {
            "type": "snapshot",
            "reference": "users/original-uid/conversations/original-doc",
            "value": {"created_at": {"type": "int", "value": 3}},
        },
        sdk_client,
        path,
    )
    assert snapshot.reference.path.startswith(f"users/{NAMESPACE}/conversations/oracle-")
    assert "original-uid" not in snapshot.reference.path
    assert snapshot.to_dict() == {"created_at": 3}
    assert snapshot.exists


def test_build_query_caps_limit_and_offset_and_preserves_projection(sdk_client):
    encoded = _encoded_shape(limit=50, offset=7, projection=["discarded"])
    shape = oracle.hydrate_shape(encoded, sdk_client, NAMESPACE)
    assert shape.limit == 1
    pb = oracle.build_query(shape, sdk_client)._to_protobuf()
    assert pb.limit == 1
    assert pb.offset == 0
    assert [field.field_path for field in pb.select.fields] == ["discarded"]


def test_limit_to_last_reverses_wire_orders(sdk_client):
    encoded = _encoded_shape(limit_to_last=True)
    pb = oracle.build_query(oracle.hydrate_shape(encoded, sdk_client, NAMESPACE), sdk_client)._to_protobuf()
    directions = {order.field.field_path: order.direction.name for order in pb.order_by}
    assert directions["created_at"] == "DESCENDING"


def test_snapshot_cursor_rewritten_and_wire_orders_cover_range_then_name(sdk_client):
    encoded = _encoded_shape(
        orders=[],
        cursors=[
            {
                "kind": "start_after",
                "value": {
                    "type": "snapshot",
                    "reference": "users/original-uid/conversations/original-doc",
                    "value": {"created_at": {"type": "int", "value": 1}},
                },
            }
        ],
    )
    shape = oracle.hydrate_shape(encoded, sdk_client, NAMESPACE)
    cursor = shape.cursors[0][1]
    assert cursor.reference.path.startswith(f"users/{NAMESPACE}/conversations/oracle-")
    assert "original-uid" not in cursor.reference.path
    pb = oracle.build_query(shape, sdk_client)._to_protobuf()
    orders = [(order.field.field_path, order.direction.name) for order in pb.order_by]
    assert orders == [("created_at", "ASCENDING"), ("__name__", "ASCENDING")]
    cursor_values = pb.start_at.values
    assert cursor_values and pb.start_at.before is False
    cursor_fields = [value.reference_value for value in cursor_values]
    assert cursor_fields and cursor_fields[-1].endswith(f"users/{NAMESPACE}/conversations/" + cursor.reference.id)


def test_aggregations_preserve_multiple_aliases(sdk_client):
    encoded = _encoded_shape(
        aggregations=[
            {"kind": "count", "field": None, "alias": "c"},
            {"kind": "sum", "field": "cost", "alias": "s"},
            {"kind": "avg", "field": "cost", "alias": "a"},
        ]
    )
    query = oracle.build_query(oracle.hydrate_shape(encoded, sdk_client, NAMESPACE), sdk_client)
    aliases = [aggregation.alias for aggregation in query._aggregations]
    assert aliases == ["c", "s", "a"]


@pytest.mark.parametrize(
    "shape_overrides",
    [
        {"filters": [{"field": "a", "operator": "==", "value": {"type": "unsupported", "value": 1}}]},
        {"filters": [_leaf("a", "~=", 1)]},
        {"scope": "BOGUS"},
        {"aggregations": [{"kind": "median", "field": "x", "alias": "m"}]},
        {"cursors": [{"kind": "jump_to", "value": _encode(1)}]},
        {
            "filter_tree": {
                "op": "XOR",
                "filters": [_leaf("a", "==", 1), _leaf("b", "==", 2)],
            },
            "filters": [],
        },
        {"orders": [{"field": "a", "direction": "SIDEWAYS"}]},
    ],
)
def test_run_groups_classifies_reconstruction_errors(sdk_client, shape_overrides):
    entries = [_entry("e1", _encoded_shape(**shape_overrides))]
    results = _run_groups(entries, sdk_client)
    assert len(results) == 1
    assert results[0]["observed"]["status"] == "error"
    assert results[0]["predictions"] == []


def test_run_groups_scalar_cursor_classifies_error_without_rpc(sdk_client, monkeypatch):
    monkeypatch.setattr(
        type(sdk_client),
        "_firestore_api",
        property(lambda self: pytest.fail("unexpected Firestore RPC")),
    )
    entry = _entry(
        "cursor-shape",
        _encoded_shape(cursors=[{"kind": "start_after", "value": _encode("cursor-1")}]),
    )
    results = _run_groups([entry], sdk_client)
    assert results[0]["observed"]["status"] == "error"


def test_deduplicate_groups_shape_variants_and_runs_one_query(sdk_client, monkeypatch):
    built = []
    monkeypatch.setattr(oracle, "build_query", lambda shape, client: built.append(FakeQuery([object()])) or built[-1])
    base = _encoded_shape()
    entries = [
        _entry("one", base, calling_function="database.a", driver_function="d1", parameter_combo={"p": 1}),
        _entry(
            "two",
            _encoded_shape(
                collection_path="users/other-uid/conversations",
                filters=[_leaf("discarded", "==", True), _leaf("created_at", ">=", "2026-02-02T00:00:00")],
                limit=25,
                offset=9,
                projection=["discarded"],
                aggregations=[],
            ),
            calling_function="database.b",
            driver_function="d2",
        ),
        _entry("one", base),
    ]
    entries[1]["shape"]["aggregations"] = [{"kind": "count", "field": None, "alias": "other-alias"}]
    entries[0]["shape"]["aggregations"] = [{"kind": "count", "field": None, "alias": "first-alias"}]
    groups = oracle.deduplicate(entries)
    assert len(groups) == 1
    results = _run_groups(entries, sdk_client)
    assert len(results) == 1
    assert len(built) == 1
    assert sorted(results[0]["shape_ids"]) == ["one", "two"]
    assert sorted(prediction["id"] for prediction in results[0]["predictions"]) == ["one", "two"]
    assert results[0]["calling_functions"] == ["database.a", "database.b"]


@pytest.mark.parametrize(
    "mutations",
    [
        {"collection_group": "other"},
        {"scope": "COLLECTION_GROUP"},
        {"filters": [_leaf("other_field", "==", False), _leaf("created_at", ">=", "2026-01-01T00:00:00")]},
        {"filters": [_leaf("discarded", "!=", False), _leaf("created_at", ">=", "2026-01-01T00:00:00")]},
        {"orders": [{"field": "created_at", "direction": "DESCENDING"}]},
        {"aggregations": [{"kind": "sum", "field": "cost", "alias": "c"}]},
        {"aggregations": [{"kind": "count", "field": None, "alias": "c"}]},
        {
            "filter_tree": {
                "op": "OR",
                "filters": [_leaf("discarded", "==", False), _leaf("created_at", ">=", "2026-01-01T00:00:00")],
            },
            "filters": [],
        },
        {"filters": [_leaf("discarded", "==", None), _leaf("created_at", ">=", "2026-01-01T00:00:00")]},
        {"filters": [_leaf("discarded", "in", [1, 2, 3]), _leaf("created_at", ">=", "2026-01-01T00:00:00")]},
        {"cursors": [{"kind": "start_at", "value": _encode(1)}]},
    ],
)
def test_deduplicate_separates_distinct_signatures(mutations):
    base = _encoded_shape()
    if "aggregations" in mutations and mutations["aggregations"] == [{"kind": "count", "field": None, "alias": "c"}]:
        base["aggregations"] = [{"kind": "count", "field": "cost", "alias": "c"}]
    groups = oracle.deduplicate([_entry("a", base), _entry("b", _encoded_shape(**mutations))])
    assert len(groups) == 2, mutations


def test_run_groups_bounds_concurrency(sdk_client, monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    class SlowQuery:
        def get(self, retry=None, timeout=None):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return []

    monkeypatch.setattr(oracle, "build_query", lambda shape, client: SlowQuery())
    entries = [_entry(f"e{i}", _encoded_shape(filters=[_leaf(f"f{i}", "==", i)])) for i in range(6)]
    results = _run_groups(entries, sdk_client, concurrency=2)
    assert len(results) == 6
    assert 1 < peak <= 2


def test_signature_separates_membership_cardinality_and_unary_values():
    pairs = [
        (
            _encoded_shape(filters=[_leaf("x", "in", [1, 2])]),
            _encoded_shape(filters=[_leaf("x", "in", [1, 2, 3])]),
        ),
        (
            _encoded_shape(filters=[_leaf("x", "==", None)]),
            _encoded_shape(filters=[_leaf("x", "==", 5)]),
        ),
    ]
    for first, second in pairs:
        assert len(oracle.deduplicate([_entry("a", first), _entry("b", second)])) == 2


def test_rate_limiter_spaces_starts_and_honours_deadline(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(oracle.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(oracle.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    limiter = oracle.RateLimiter(10)
    assert limiter.wait(1.0) is True
    assert clock["now"] == 0.0
    assert limiter.wait(1.0) is True
    assert clock["now"] == pytest.approx(0.1)
    clock["now"] = 2.0
    assert limiter.wait(1.0) is False
    assert clock["now"] == 2.0


def test_run_groups_elapsed_deadline_errors_without_get(sdk_client, monkeypatch):
    queries = []

    def fake_build(shape, client):
        query = FakeQuery([])
        queries.append(query)
        return query

    monkeypatch.setattr(oracle, "build_query", fake_build)

    class ExpiredLimiter:
        def wait(self, deadline):
            return False

    entries = [_entry("a", _encoded_shape())]
    groups = oracle.deduplicate(entries)
    results = oracle.run_groups(
        groups,
        sdk_client,
        {"indexes": [], "fieldOverrides": []},
        NAMESPACE,
        2,
        10.0,
        ExpiredLimiter(),
        time.monotonic() - 1,
    )
    assert results[0]["observed"]["status"] == "error"
    assert all(not query.calls for query in queries)


class FakeAdmin:
    def __init__(self, indexes=None, fields=None, named_fields=None):
        self.indexes = indexes if indexes is not None else []
        self.fields = fields if fields is not None else []
        self.named_fields = dict(named_fields or {})
        self.requests = []
        self.get_field_calls = []

    def list_indexes(self, request, retry=None, timeout=None):
        self.requests.append(("list_indexes", dict(request)))
        return iter(self.indexes)

    def list_fields(self, request, retry=None, timeout=None):
        self.requests.append(("list_fields", dict(request)))
        return iter(self.fields)

    def get_field(self, name, retry=None, timeout=None):
        self.get_field_calls.append(name)
        return self.named_fields[name]


class _Paged:
    def __init__(self, pages):
        self.pages = pages
        self.consumed_pages = 0

    def __iter__(self):
        for page in self.pages:
            self.consumed_pages += 1
            yield from page


def _default_field(indexes=None):
    return _field(
        f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*",
        _index_config(
            indexes
            if indexes is not None
            else [
                _field_index([_asc("x"), _asc("__name__")], collection="__default__"),
                _field_index([_contains("x"), _asc("__name__")], collection="__default__", scope="COLLECTION_GROUP"),
            ]
        ),
    )


def test_read_live_manifest_requests_and_default_scope():
    ready = _field_index([_asc("a"), _asc("__name__")])
    index_pages = _Paged(
        [
            [
                ready,
                _field_index([_asc("b"), _asc("__name__")], state="CREATING"),
            ],
            [
                _field_index([_asc("c"), _asc("__name__")], state="NEEDS_REPAIR"),
                _field_index([_asc("d"), _asc("__name__")], api_scope="DATASTORE_MODE_API"),
                firestore_admin_v1.Index(
                    name=f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/indexes/vector",
                    query_scope="COLLECTION",
                    state="READY",
                    fields=[
                        firestore_admin_v1.Index.IndexField(
                            field_path="embedding",
                            vector_config=firestore_admin_v1.Index.IndexField.VectorConfig(
                                dimension=3, flat=firestore_admin_v1.Index.IndexField.VectorConfig.FlatIndex()
                            ),
                        )
                    ],
                ),
            ],
        ]
    )
    default = _default_field(
        [
            _field_index([_asc("x"), _asc("__name__")], collection="__default__"),
            _field_index([_contains("x"), _asc("__name__")], collection="__default__", scope="COLLECTION_GROUP"),
            _field_index(
                [_asc("datastore_only"), _asc("__name__")],
                collection="__default__",
                api_scope="DATASTORE_MODE_API",
            ),
        ]
    )
    default_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*"
    override = _field(
        f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/flagged",
        _index_config([_field_index([_desc("flagged"), _asc("__name__")])]),
    )
    field_pages = _Paged([[], [override]])
    admin = FakeAdmin(
        indexes=index_pages,
        fields=field_pages,
        named_fields={default_name: default},
    )
    inventory = oracle.read_live_manifest(admin, PROJECT, DATABASE, {"conversations"}, 10.0)
    kinds = {kind for kind, _ in admin.requests}
    assert kinds == {"list_indexes", "list_fields"}
    for kind, request in admin.requests:
        assert request["parent"] == PARENT
    fields_request = dict(admin.requests)["list_fields"]
    assert fields_request["filter"] == "indexConfig.usesAncestorConfig:false"
    assert admin.get_field_calls == [default_name]
    assert index_pages.consumed_pages == 2 and field_pages.consumed_pages == 2
    assert inventory["manifest"]["indexes"] == [
        {
            "collectionGroup": "conversations",
            "queryScope": "COLLECTION",
            "fields": [{"fieldPath": "a", "order": "ASCENDING"}, {"fieldPath": "__name__", "order": "ASCENDING"}],
        }
    ]
    assert len(inventory["raw_indexes"]) == 5
    overrides = {(o["collectionGroup"], o["fieldPath"]): o["indexes"] for o in inventory["manifest"]["fieldOverrides"]}
    assert overrides[("conversations", "flagged")] == [{"queryScope": "COLLECTION", "order": "DESCENDING"}]
    wildcard = overrides[("conversations", "*")]
    modes = {(i.get("queryScope"), i.get("order") or i.get("arrayConfig")) for i in wildcard}
    assert modes == {("COLLECTION", "ASCENDING"), ("COLLECTION_GROUP", "CONTAINS")}
    assert not hasattr(admin, "create_index") and not hasattr(admin, "delete_index")


def test_read_live_manifest_field_overrides_and_ancestor_resolution():
    default_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*"
    disabled = _field(
        f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/discarded",
        _index_config([]),
    )
    ancestor = _field(
        f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/meta",
        _index_config([_field_index([_desc("meta"), _asc("__name__")])]),
    )
    child = _field(
        f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/meta.score",
        _index_config([], uses_ancestor=True, ancestor=ancestor.name),
    )
    admin = FakeAdmin(
        indexes=[],
        fields=[disabled, child],
        named_fields={default_name: _default_field(), ancestor.name: ancestor},
    )
    inventory = oracle.read_live_manifest(admin, PROJECT, DATABASE, {"conversations"}, 10.0)
    overrides = {(o["collectionGroup"], o["fieldPath"]): o["indexes"] for o in inventory["manifest"]["fieldOverrides"]}
    assert overrides[("conversations", "discarded")] == []
    assert overrides[("conversations", "meta.score")] == [{"queryScope": "COLLECTION", "order": "DESCENDING"}]
    assert admin.get_field_calls == [default_name, ancestor.name]


def test_read_live_manifest_rejects_cycles_reverting_and_foreign_resources():
    default_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*"
    a_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/a"
    b_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/conversations/fields/b"
    cyclic_admin = FakeAdmin(
        fields=[_field(a_name, _index_config([], uses_ancestor=True, ancestor=b_name))],
        named_fields={
            default_name: _default_field(),
            b_name: _field(b_name, _index_config([], uses_ancestor=True, ancestor=a_name)),
        },
    )
    with pytest.raises(ValueError):
        oracle.read_live_manifest(cyclic_admin, PROJECT, DATABASE, {"conversations"}, 10.0)
    reverting_admin = FakeAdmin(
        fields=[_field(a_name, _index_config([], reverting=True))],
        named_fields={default_name: _default_field()},
    )
    with pytest.raises(ValueError):
        oracle.read_live_manifest(reverting_admin, PROJECT, DATABASE, {"conversations"}, 10.0)
    foreign = FakeAdmin(
        indexes=[
            firestore_admin_v1.Index(
                name="projects/other/databases/d/collectionGroups/conversations/indexes/_",
                query_scope="COLLECTION",
                state="READY",
                fields=[_asc("a"), _asc("__name__")],
            )
        ],
        named_fields={default_name: _default_field()},
    )
    with pytest.raises(ValueError):
        oracle.read_live_manifest(foreign, PROJECT, DATABASE, {"conversations"}, 10.0)


def _probe_client(baseline, indexed_outcome, tracking):
    client = FakeClient()

    def collection_group(group):
        calls = tracking.setdefault(group, [])
        calls.append("group")
        return _ProbeBuilder(group, baseline, indexed_outcome, tracking)

    client.collection_group = collection_group
    return client


class _ProbeBuilder(FakeBuilder):
    def __init__(self, group, baseline, indexed_outcome, tracking):
        super().__init__(None)
        self.group = group
        self.baseline = baseline
        self.indexed_outcome = indexed_outcome
        self.tracking = tracking
        self.filtered = False

    def where(self, *args, **kwargs):
        self.tracking.setdefault(self.group, []).append("where")
        self.filtered = True
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.outcome = self.indexed_outcome if self.filtered else self.baseline
        self.built += 1
        return self


def test_empty_group_probe_verifies_fresh_indexed_group():
    tracking = {}
    collection = f"oracle_probe_{NAMESPACE}"
    token = _token(
        [_asc("oracle_equality"), _asc("oracle_range"), _asc("__name__")],
        collection=collection,
        scope="COLLECTION_GROUP",
        project=PROJECT,
        database=DATABASE,
    )
    client = _probe_client([], _precondition(token), tracking)
    result = oracle.empty_group_probe(client, NAMESPACE, 10.0, _PassLimiter(), time.monotonic() + 60)
    assert result["verified"] is True
    assert result["collection"] == collection


@pytest.mark.parametrize("baseline", [[object()], PermissionDenied("denied")])
def test_empty_group_probe_stops_when_baseline_is_not_empty(baseline):
    tracking = {}
    client = _probe_client(baseline, _precondition(_token([_asc("x")])), tracking)
    result = oracle.empty_group_probe(client, NAMESPACE, 10.0, _PassLimiter(), time.monotonic() + 60)
    assert result["verified"] is False
    assert "where" not in tracking[f"oracle_probe_{NAMESPACE}"]


def test_empty_group_probe_rejects_served_or_mistargeted_indexed_scan():
    collection = f"oracle_probe_{NAMESPACE}"
    tracking = {}
    client = _probe_client([], [], tracking)
    assert oracle.empty_group_probe(client, NAMESPACE, 10.0, _PassLimiter(), time.monotonic() + 60)["verified"] is False
    wrong = _token([_asc("x")], collection="other", scope="COLLECTION")
    client = _probe_client([], _precondition(wrong), tracking)
    assert oracle.empty_group_probe(client, NAMESPACE, 10.0, _PassLimiter(), time.monotonic() + 60)["verified"] is False


def _write_export(tmp_path, entries, drivers=None):
    export_path = tmp_path / "export.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps({"schema_version": 1, "drivers": drivers or [], "shapes": entries}))
    return export_path


def _argv(tmp_path, export_path, extra=()):
    return [
        "--export",
        str(export_path),
        "--project",
        PROJECT,
        "--database",
        DATABASE,
        "--output-dir",
        str(tmp_path / "out"),
        *extra,
    ]


def _install_factories(monkeypatch, tracked, admin, query_outcome):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    def client_factory(**kwargs):
        tracked["client_project"] = kwargs.get("project")
        tracked["client_database"] = kwargs.get("database")
        fake = FakeClient()

        def collection_group(group):
            token = _token(
                [_asc("oracle_equality"), _asc("oracle_range"), _asc("__name__")],
                collection=group,
                scope="COLLECTION_GROUP",
                project=kwargs.get("project", PROJECT),
                database=DATABASE,
            )
            return _ProbeBuilder(group, [], _precondition(token), tracked)

        def collection(path):
            tracked.setdefault("collections", []).append(path)
            return FakeBuilder(query_outcome)

        fake.collection_group = collection_group
        fake.collection = collection
        return fake

    monkeypatch.setattr(oracle, "Client", client_factory)
    monkeypatch.setattr(oracle.firestore_admin_v1, "FirestoreAdminClient", lambda: admin)


def _matching_main_setup(tmp_path, monkeypatch, tracked, query_outcome):
    admin = FakeAdmin(
        indexes=[_field_index([_asc("discarded"), _asc("created_at"), _asc("__name__")])],
        named_fields={
            f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*": _default_field()
        },
    )
    _install_factories(monkeypatch, tracked, admin, query_outcome)
    entry = _entry("s1", _encoded_shape())
    entry["served"] = True
    export_path = _write_export(tmp_path, [entry])
    return export_path, admin


def test_main_writes_reports_and_exits_zero_on_consistent_run(tmp_path, monkeypatch):
    tracked = {}
    export_path, _ = _matching_main_setup(tmp_path, monkeypatch, tracked, [])
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 0
    out = tmp_path / "out"
    report = json.loads((out / "report.json").read_text())
    assert (out / "report.md").exists()
    resolved = json.loads((out / "resolved-uncertain.json").read_text())
    assert resolved["resolutions"] == []
    assert report["project"] == PROJECT and report["database"] == DATABASE
    assert report["exit_code"] == 0
    assert report["counts"]["exported_shapes"] == 1
    assert report["counts"]["served"] == 1
    assert report["counts"]["rule_bugs"] == 0
    assert tracked["client_project"] == PROJECT
    assert tracked["client_database"] == DATABASE
    assert report["counts"]["evaluated_signatures"] == 1
    assert report["comparisons_valid"] is True
    assert tracked["collections"] == [f"users/{report['namespace']}/conversations"]
    assert report["results"][0]["predictions"][0]["predicted_served"] is True


def test_main_uses_default_dev_target_when_flags_omitted(tmp_path, monkeypatch):
    tracked = {}
    export_path, _ = _matching_main_setup(tmp_path, monkeypatch, tracked, [])
    code = oracle.main(["--export", str(export_path), "--output-dir", str(tmp_path / "out")])
    assert code == 0
    assert tracked["client_project"] == "based-hardware-dev"
    assert tracked["client_database"] == "jit-qa"
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["project"] == "based-hardware-dev" and report["database"] == "jit-qa"


def test_main_count_aggregation_uses_live_manifest_not_export_flag(tmp_path, monkeypatch):
    tracked = {}
    admin = FakeAdmin(
        indexes=[],
        named_fields={
            f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*": _default_field()
        },
    )
    _install_factories(
        monkeypatch,
        tracked,
        admin,
        _precondition(
            _token(
                [_asc("discarded"), _asc("created_at"), _asc("__name__")],
                project=PROJECT,
                database=DATABASE,
            )
        ),
    )
    entry = _entry(
        "agg1",
        _encoded_shape(
            aggregations=[{"kind": "count", "field": None, "alias": "c"}],
        ),
    )
    entry["served"] = True
    export_path = _write_export(tmp_path, [entry])
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["counts"]["unserved"] == 1
    prediction = report["results"][0]["predictions"][0]
    assert prediction["predicted_served"] is False


def test_main_exit_one_on_rule_bug_and_two_on_errors(tmp_path, monkeypatch):
    tracked = {}
    export_path, _ = _matching_main_setup(
        tmp_path,
        monkeypatch,
        tracked,
        _precondition(
            _token(
                [_asc("discarded"), _asc("created_at"), _asc("__name__")],
                project=PROJECT,
                database=DATABASE,
            )
        ),
    )
    assert oracle.main(_argv(tmp_path, export_path)) == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["counts"]["rule_bugs"] >= 1

    export_path2 = _write_export(tmp_path / "second", [_entry("s1", _encoded_shape())])
    _install_factories(
        monkeypatch,
        {},
        FakeAdmin(
            indexes=[],
            named_fields={
                f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*": _default_field()
            },
        ),
        RuntimeError("boom"),
    )
    code = oracle.main(
        [
            "--export",
            str(export_path2),
            "--project",
            PROJECT,
            "--database",
            DATABASE,
            "--output-dir",
            str(tmp_path / "out2"),
        ]
    )
    assert code == 2


def test_main_aborts_all_queries_when_probe_unverified(tmp_path, monkeypatch):
    tracked = {}
    admin = FakeAdmin(
        indexes=[],
        named_fields={
            f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*": _default_field()
        },
    )
    _install_factories(monkeypatch, tracked, admin, [])

    def client_factory(**kwargs):
        fake = FakeClient()

        def collection_group(group):
            return _ProbeBuilder(group, [object()], [], tracked)

        def collection(path):
            tracked.setdefault("collections", []).append(path)
            return FakeBuilder([])

        fake.collection_group = collection_group
        fake.collection = collection
        return fake

    monkeypatch.setattr(oracle, "Client", client_factory)
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 2
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["results"] == []
    assert report["errors"]
    assert tracked.get("collections") is None


def test_main_detects_inventory_change_and_invalidates_resolutions(tmp_path, monkeypatch):
    tracked = {}
    default_name = f"projects/{PROJECT}/databases/{DATABASE}/collectionGroups/__default__/fields/*"

    class ChangingAdmin(FakeAdmin):
        def __init__(self):
            super().__init__(named_fields={default_name: _default_field()})
            self.calls = 0

        def list_indexes(self, request, retry=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return iter([_field_index([_asc("a"), _asc("__name__")])])
            return iter([_field_index([_asc("other"), _asc("__name__")])])

    admin = ChangingAdmin()
    _install_factories(monkeypatch, tracked, admin, [])
    uncertain = _encoded_shape(
        filters=[_leaf("a", "==", 1), _leaf("b", "==", 2)],
        orders=[{"field": "__name__", "direction": "DESCENDING"}],
    )
    export_path = _write_export(tmp_path, [_entry("s1", uncertain)])
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 2
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["comparisons_valid"] is False
    assert report["resolved_uncertain"] == []
    assert report["counts"]["resolved_uncertain"] == 0
    assert report["results"][0]["predictions"][0]["uncertain"] is True
    resolved = json.loads((tmp_path / "out" / "resolved-uncertain.json").read_text())
    assert resolved["comparisons_valid"] is False
    assert resolved["resolutions"] == []
    assert "INCONCLUSIVE" in (tmp_path / "out" / "report.md").read_text()


def test_main_inventory_failure_still_writes_reports(tmp_path, monkeypatch):
    tracked = {}

    class FailingAdmin(FakeAdmin):
        def list_indexes(self, request, retry=None, timeout=None):
            raise PermissionDenied("denied")

    _install_factories(monkeypatch, tracked, FailingAdmin(), [])
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 2
    out = tmp_path / "out"
    assert (out / "report.json").exists() and (out / "resolved-uncertain.json").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--concurrency", "0"],
        ["--concurrency", "33"],
        ["--queries-per-second", "0"],
        ["--queries-per-second", "51"],
        ["--query-timeout", "0"],
        ["--query-timeout", "61"],
        ["--max-runtime", "0"],
        ["--max-runtime", "601"],
    ],
)
def test_main_rejects_invalid_bounds_before_clients(tmp_path, monkeypatch, extra):
    built = []
    monkeypatch.setattr(oracle, "Client", lambda **kw: built.append(1))
    monkeypatch.setattr(oracle.firestore_admin_v1, "FirestoreAdminClient", lambda: built.append(1))
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    with pytest.raises(SystemExit) as error:
        oracle.main(_argv(tmp_path, export_path, extra=extra))
    assert error.value.code == 2
    assert built == []


def test_main_refuses_prod_without_flag_before_clients(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(oracle, "Client", lambda **kw: built.append(1))
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    with pytest.raises(SystemExit):
        oracle.main(_argv(tmp_path, export_path, extra=("--project", "based-hardware")))
    assert built == []


def test_main_refuses_numeric_alias_and_emulator_before_clients(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(oracle, "Client", lambda **kw: built.append(1))
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    for project in ("123456", "based_hardware"):
        with pytest.raises(SystemExit):
            oracle.main(
                [
                    "--export",
                    str(export_path),
                    "--project",
                    project,
                    "--database",
                    DATABASE,
                    "--output-dir",
                    str(tmp_path / "out"),
                ]
            )
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    with pytest.raises(SystemExit):
        oracle.main(_argv(tmp_path, export_path))
    assert built == []


def test_main_allows_explicit_prod_flag_with_fake_factories(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    tracked = {}
    default_name = "projects/based-hardware/databases/jit-qa/collectionGroups/__default__/fields/*"

    admin = FakeAdmin(
        indexes=[
            firestore_admin_v1.Index(
                name="projects/based-hardware/databases/jit-qa/collectionGroups/conversations/indexes/i",
                query_scope="COLLECTION",
                state="READY",
                fields=[_asc("discarded"), _asc("created_at"), _asc("__name__")],
            )
        ],
        named_fields={
            default_name: _field(
                default_name,
                _index_config(
                    [
                        firestore_admin_v1.Index(
                            name="projects/based-hardware/databases/jit-qa/collectionGroups/__default__/indexes/_",
                            query_scope="COLLECTION",
                            fields=[_asc("x"), _asc("__name__")],
                        )
                    ]
                ),
            )
        },
    )

    def client_factory(**kwargs):
        tracked["client_project"] = kwargs.get("project")
        fake = FakeClient()

        def collection_group(group):
            token = _token(
                [_asc("oracle_equality"), _asc("oracle_range"), _asc("__name__")],
                collection=group,
                scope="COLLECTION_GROUP",
                project="based-hardware",
                database=DATABASE,
            )
            return _ProbeBuilder(group, [], _precondition(token), tracked)

        def collection(path):
            return FakeBuilder([])

        fake.collection_group = collection_group
        fake.collection = collection
        return fake

    monkeypatch.setattr(oracle, "Client", client_factory)
    monkeypatch.setattr(oracle.firestore_admin_v1, "FirestoreAdminClient", lambda: admin)
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape())])
    code = oracle.main(
        [
            "--export",
            str(export_path),
            "--project",
            "based-hardware",
            "--database",
            DATABASE,
            "--output-dir",
            str(tmp_path / "out"),
            "--allow-prod-read-only",
        ]
    )
    assert code == 0
    assert tracked["client_project"] == "based-hardware"


def test_hydration_preserves_root_collection_path(sdk_client):
    shape = oracle.hydrate_shape(_encoded_shape(collection_path="conversations"), sdk_client, NAMESPACE)
    assert shape.collection_path == "conversations"
    pb = oracle.build_query(shape, sdk_client)._to_protobuf()
    assert pb.from_[0].collection_id == "conversations"
    assert pb.from_[0].all_descendants is False


@pytest.mark.parametrize(
    "collection_path",
    [
        None,
        "",
        "users/uid",
        "users//conversations",
        "users/uid/other",
        "/conversations",
        "conversations/",
    ],
)
def test_hydration_fails_closed_on_malformed_collection_paths(sdk_client, collection_path):
    with pytest.raises((ValueError, KeyError)):
        oracle.hydrate_shape(
            (
                _encoded_shape(collection_path=collection_path)
                if collection_path is not None
                else {key: value for key, value in _encoded_shape().items() if key != "collection_path"}
            ),
            sdk_client,
            NAMESPACE,
        )


def test_deduplicate_separates_root_and_nested_same_group():
    root = _entry("root", _encoded_shape(collection_path="conversations"))
    nested = _entry("nested", _encoded_shape(collection_path="users/uid/conversations"))
    groups = oracle.deduplicate([root, nested])
    assert len(groups) == 2


def test_deduplicate_merges_nested_paths_with_different_uids():
    one = _entry("one", _encoded_shape(collection_path="users/uid-a/conversations"))
    two = _entry("two", _encoded_shape(collection_path="users/uid-b/conversations"))
    groups = oracle.deduplicate([one, two])
    assert len(groups) == 1


def test_main_refuses_production_root_probe_even_with_prod_flag(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(oracle, "Client", lambda **kw: built.append(1))
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape(collection_path="conversations"))])
    for extra in ((), ("--allow-prod-read-only",)):
        with pytest.raises(SystemExit):
            oracle.main(
                _argv(tmp_path, export_path, extra=("--project", "based-hardware", "--database", "(default)", *extra))
            )
    assert built == []


def test_main_refuses_root_probe_on_other_dev_databases(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(oracle, "Client", lambda **kw: built.append(1))
    export_path = _write_export(tmp_path, [_entry("s1", _encoded_shape(collection_path="conversations"))])
    with pytest.raises(SystemExit):
        oracle.main(_argv(tmp_path, export_path, extra=("--project", "based-hardware-dev", "--database", "other-db")))
    assert built == []


def test_main_root_probe_allowed_on_dev_jit_qa(tmp_path, monkeypatch):
    tracked = {}
    export_path, _admin = _matching_main_setup(tmp_path, monkeypatch, tracked, [])
    export = json.loads(export_path.read_text())
    export["shapes"][0]["shape"]["collection_path"] = "conversations"
    export_path.write_text(json.dumps(export))
    code = oracle.main(_argv(tmp_path, export_path))
    assert code == 0
    assert tracked["collections"] == ["conversations"]


def test_hydration_preserves_feedback_reports_root_collection_path(sdk_client):
    shape = oracle.hydrate_shape(
        _encoded_shape(collection_group="feedback_reports", collection_path="feedback_reports"),
        sdk_client,
        NAMESPACE,
    )
    assert shape.collection_path == "feedback_reports"
    pb = oracle.build_query(shape, sdk_client)._to_protobuf()
    assert pb.from_[0].collection_id == "feedback_reports"
    assert pb.from_[0].all_descendants is False


def test_signature_rejects_a_stale_path_template_that_conflates_root_and_nested():
    nested = _encoded_shape(collection_path="users/uid/conversations")
    nested["document_path_template"] = "conversations/{document_id}"
    with pytest.raises(ValueError, match="document_path_template"):
        oracle.query_signature(nested)


def test_deduplicate_serving_entry_wins_group_metadata():
    serving = _entry("serving", _encoded_shape())
    nonserving = _entry("nonserving", {**_encoded_shape(), "serving": False})
    groups = oracle.deduplicate([nonserving, serving])
    assert len(groups) == 1
    assert groups[0]["serving"] is True
    assert sorted(groups[0]["entries"]) == ["nonserving", "serving"]


def _result(result_id, serving, status, rule_bugs=()):
    return {
        "id": result_id,
        "signature": f"sig-{result_id}",
        "serving": serving,
        "shape_ids": [result_id],
        "calling_functions": ["database.a"],
        "observed": {"status": status},
        "predictions": [{"id": result_id, "rule_bugs": list(rule_bugs), "review_findings": [], "resolution": None}],
    }


def test_report_splits_serving_and_nonserving_outcomes():
    export = {
        "shapes": [
            _entry("a", {**_encoded_shape(), "serving": True}),
            _entry("b", {**_encoded_shape(), "serving": False}),
        ]
    }
    results = [
        _result("serving-unserved", True, "unserved", rule_bugs=("predicted_served_but_unserved",)),
        _result("nonserving-unserved", False, "unserved"),
        _result("serving-served", True, "served"),
    ]
    report = oracle.build_report(
        "p",
        "d",
        NAMESPACE,
        export,
        {"manifest": {}},
        {"verified": True},
        results,
        [],
    )
    counts = report["counts"]
    assert counts["unserved"] == 2 and counts["served"] == 1
    assert counts["serving_counts"] == {"served": 1, "unserved": 1, "error": 0, "rule_bugs": 1}
    assert counts["nonserving_counts"] == {"served": 0, "unserved": 1, "error": 0, "rule_bugs": 0}
    assert counts["serving_shapes"] == 1 and counts["nonserving_shapes"] == 1
    markdown = oracle.markdown_report(report)
    assert "nonserving_counts" in markdown and "serving_counts" in markdown


def test_serving_origin_wins_when_signature_is_shared():
    serving = _entry("serving", _encoded_shape())
    nonserving = _entry("nonserving", {**_encoded_shape(), "serving": False})
    groups = oracle.deduplicate([nonserving, serving])
    result = _result("shared", groups[0]["serving"], "unserved")
    report = oracle.build_report(
        "p",
        "d",
        NAMESPACE,
        {"shapes": [serving, nonserving]},
        {"manifest": {}},
        {"verified": True},
        [result],
        [],
    )
    assert report["counts"]["serving_counts"]["unserved"] == 1
    assert report["counts"]["nonserving_counts"]["unserved"] == 0
