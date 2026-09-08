from datetime import datetime, timedelta, timezone

import pytest

from testing.memory.v3_f6.readonly_contracts import (
    AuditLogEvent,
    AuditQuery,
    EvidenceClientConfig,
    FakeAuditLogClient,
    FakeIdentityIamSource,
    FakeReadEvidenceTransport,
    IdentityIamTarget,
    ReadEvidenceRequest,
    RunRecord,
    ReadOnlyEvidenceClient,
    assess_audit_correlation,
    verify_identity_iam,
)

READ_PERMISSIONS = frozenset(
    {
        "datastore.databases.get",
        "datastore.entities.get",
        "datastore.entities.list",
        "datastore.indexes.list",
        "iam.serviceAccounts.get",
        "resourcemanager.projects.getIamPolicy",
        "secretmanager.secrets.get",
        "logging.logEntries.list",
    }
)


def test_f6c_verifier_accepts_exact_identity_read_permissions_and_metadata_only_secret_access():
    target = IdentityIamTarget(
        project_id="omi-nonprod", principal="serviceAccount:memory-reader@omi-nonprod.iam.gserviceaccount.com"
    )
    run = RunRecord(run_id="run-f6", project_id="omi-nonprod", principal=target.principal)
    source = FakeIdentityIamSource(
        project_id="omi-nonprod",
        principal=target.principal,
        permissions=READ_PERMISSIONS,
        roles={"roles/omi.MemoryEvidenceReader"},
        secret_payload_access_attempted=False,
    )

    result = verify_identity_iam(target, run, source)

    assert result.status == "PASS"
    assert result.effective_project_id == "omi-nonprod"
    assert result.effective_principal == target.principal
    assert result.missing_read_permissions == frozenset()
    assert result.forbidden_roles_present == frozenset()
    assert result.forbidden_write_permissions_present == frozenset()
    assert result.secret_payload_access_rejected is True
    assert result.failures == ()


@pytest.mark.parametrize(
    "source_kwargs,run_kwargs,expected_failure",
    [
        ({"project_id": "wrong-project"}, {}, "effective_project_mismatch"),
        ({"principal": "serviceAccount:wrong@omi-nonprod.iam.gserviceaccount.com"}, {}, "effective_principal_mismatch"),
        ({}, {"principal": "serviceAccount:other@omi-nonprod.iam.gserviceaccount.com"}, "run_principal_mismatch"),
        ({"permissions": READ_PERMISSIONS - {"datastore.entities.list"}}, {}, "missing_read_permissions"),
        ({"roles": {"roles/owner"}}, {}, "forbidden_broad_roles"),
        ({"permissions": READ_PERMISSIONS | {"datastore.entities.create"}}, {}, "forbidden_write_permissions"),
        ({"secret_payload_access_attempted": True}, {}, "secret_payload_access_not_rejected"),
    ],
)
def test_f6c_verifier_fails_closed_on_mismatch_broad_roles_write_permissions_and_payload_access(
    source_kwargs, run_kwargs, expected_failure
):
    target = IdentityIamTarget(
        project_id="omi-nonprod", principal="serviceAccount:memory-reader@omi-nonprod.iam.gserviceaccount.com"
    )
    base_source = {
        "project_id": "omi-nonprod",
        "principal": target.principal,
        "permissions": READ_PERMISSIONS,
        "roles": {"roles/omi.MemoryEvidenceReader"},
        "secret_payload_access_attempted": False,
    }
    base_source.update(source_kwargs)
    base_run = {"run_id": "run-f6", "project_id": "omi-nonprod", "principal": target.principal}
    base_run.update(run_kwargs)

    result = verify_identity_iam(target, RunRecord(**base_run), FakeIdentityIamSource(**base_source))

    assert result.status == "FAIL"
    assert expected_failure in result.failures


def test_f6d_evidence_client_only_allows_configured_read_methods_and_enforces_limits():
    transport = FakeReadEvidenceTransport(
        responses={
            "get_control_metadata": [{"generation": 7}],
            "list_projection_metadata": [{"id": "m1"}, {"id": "m2"}],
        }
    )
    client = ReadOnlyEvidenceClient(
        transport=transport,
        config=EvidenceClientConfig(
            allowed_methods=frozenset({"get_control_metadata", "list_projection_metadata"}),
            per_rpc_timeout_seconds=3,
            max_attempts=2,
            max_items=2,
        ),
    )

    assert client.call("get_control_metadata", ReadEvidenceRequest(run_id="run-f6")) == [{"generation": 7}]
    assert client.call("list_projection_metadata", ReadEvidenceRequest(run_id="run-f6", limit=2)) == [
        {"id": "m1"},
        {"id": "m2"},
    ]
    assert transport.calls == [
        ("get_control_metadata", "run-f6", 2, 3, 2),
        ("list_projection_metadata", "run-f6", 2, 3, 2),
    ]


@pytest.mark.parametrize(
    "method",
    [
        "unknown_read",
        "create_memory_item",
        "update_projection",
        "delete_cursor",
        "commit",
        "batch_write",
        "request",
        "send",
        "raw_transport",
    ],
)
def test_f6d_evidence_client_fails_closed_for_unknown_generic_raw_and_mutating_methods(method):
    client = ReadOnlyEvidenceClient(
        transport=FakeReadEvidenceTransport(responses={method: [{"should": "not run"}]}),
        config=EvidenceClientConfig(allowed_methods=frozenset({"get_control_metadata"})),
    )

    with pytest.raises(PermissionError):
        client.call(method, ReadEvidenceRequest(run_id="run-f6"))


def test_f6d_evidence_client_rejects_invalid_timeout_retry_and_item_limits_locally():
    with pytest.raises(ValueError):
        EvidenceClientConfig(allowed_methods=frozenset({"get_control_metadata"}), per_rpc_timeout_seconds=0)
    with pytest.raises(ValueError):
        EvidenceClientConfig(allowed_methods=frozenset({"get_control_metadata"}), max_attempts=0)
    with pytest.raises(ValueError):
        EvidenceClientConfig(allowed_methods=frozenset({"get_control_metadata"}), max_items=0)

    client = ReadOnlyEvidenceClient(
        transport=FakeReadEvidenceTransport(responses={"list_projection_metadata": [{"id": "m1"}, {"id": "m2"}]}),
        config=EvidenceClientConfig(allowed_methods=frozenset({"list_projection_metadata"}), max_items=1),
    )
    with pytest.raises(ValueError, match="item_limit_exceeded"):
        client.call("list_projection_metadata", ReadEvidenceRequest(run_id="run-f6", limit=2))


def _event(
    method,
    seconds=0,
    principal="serviceAccount:memory-reader@omi-nonprod.iam.gserviceaccount.com",
    project_id="omi-nonprod",
):
    return AuditLogEvent(
        timestamp=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        run_id="run-f6",
        project_id=project_id,
        principal=principal,
        service="firestore.googleapis.com",
        method=method,
    )


def test_f6e_audit_correlation_passes_when_run_window_identity_and_method_families_match():
    query = AuditQuery(
        run_id="run-f6",
        project_id="omi-nonprod",
        principal="serviceAccount:memory-reader@omi-nonprod.iam.gserviceaccount.com",
        started_at=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 20, 12, 5, tzinfo=timezone.utc),
        expected_method_families=frozenset({"firestore.read", "secretmanager.metadata", "logging.read"}),
    )
    client = FakeAuditLogClient(
        events=[
            _event("google.firestore.v1.Firestore.GetDocument", 1),
            AuditLogEvent(
                timestamp=datetime(2026, 6, 20, 12, 1, tzinfo=timezone.utc),
                run_id="run-f6",
                project_id="omi-nonprod",
                principal=query.principal,
                service="secretmanager.googleapis.com",
                method="google.cloud.secretmanager.v1.SecretManagerService.GetSecret",
            ),
            AuditLogEvent(
                timestamp=datetime(2026, 6, 20, 12, 2, tzinfo=timezone.utc),
                run_id="run-f6",
                project_id="omi-nonprod",
                principal=query.principal,
                service="logging.googleapis.com",
                method="google.logging.v2.LoggingServiceV2.ListLogEntries",
            ),
        ]
    )

    result = assess_audit_correlation(client, query)

    assert result.status == "PASS"
    assert result.covered_method_families == query.expected_method_families
    assert result.unexpected_write_methods == ()
    assert result.failures == ()


@pytest.mark.parametrize(
    "events,expected_status,expected_failure",
    [
        ([], "INCONCLUSIVE", "missing_audit_logs"),
        ([_event("google.firestore.v1.Firestore.GetDocument", seconds=600)], "INCONCLUSIVE", "missing_audit_logs"),
        (
            [_event("google.firestore.v1.Firestore.GetDocument", seconds=1)],
            "INCONCLUSIVE",
            "incomplete_method_family_coverage",
        ),
        ([_event("google.firestore.v1.Firestore.Commit", seconds=1)], "FAIL", "unexpected_write_methods"),
    ],
)
def test_f6e_audit_correlation_inconclusive_for_missing_delayed_incomplete_and_fails_on_writes(
    events, expected_status, expected_failure
):
    query = AuditQuery(
        run_id="run-f6",
        project_id="omi-nonprod",
        principal="serviceAccount:memory-reader@omi-nonprod.iam.gserviceaccount.com",
        started_at=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 20, 12, 5, tzinfo=timezone.utc),
        expected_method_families=frozenset({"firestore.read", "logging.read"}),
    )

    result = assess_audit_correlation(FakeAuditLogClient(events=events), query)

    assert result.status == expected_status
    assert expected_failure in result.failures
