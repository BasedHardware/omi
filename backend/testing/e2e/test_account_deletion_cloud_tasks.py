"""Hermetic Cloud Tasks lifecycle coverage for durable account deletion."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

import pytest
from google.api_core.exceptions import NotFound
from google.cloud import tasks_v2

_PROJECT = "test-e2e-project"
_LOCATION = "us-central1"
_QUEUE = "account-deletion"
_HANDLER_URL = "http://127.0.0.1:8765/v1/users/account-deletion-wipes/run"
_INVOKER_SERVICE_ACCOUNT = "account-deletion-worker@example.invalid"
_LOCAL_TASK_TOKEN = "local-account-deletion-cloud-task"


class _CapturedCloudTasksClient:
    """Strict local substitute for the Cloud Tasks client used by this workflow."""

    def __init__(self) -> None:
        self.create_calls: list[tuple[str, Any]] = []
        self.queue_path_calls: list[tuple[str, str, str]] = []
        self.task_path_calls: list[tuple[str, str, str, str]] = []
        self._assert_pending_marker: Callable[[str], None] | None = None
        self.create_error: Exception | None = None

    def queue_path(self, project: str, location: str, queue: str) -> str:
        assert (project, location, queue) == (_PROJECT, _LOCATION, _QUEUE)
        self.queue_path_calls.append((project, location, queue))
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def task_path(self, project: str, location: str, queue: str, task_id: str) -> str:
        assert (project, location, queue) == (_PROJECT, _LOCATION, _QUEUE)
        self.task_path_calls.append((project, location, queue, task_id))
        return f"projects/{project}/locations/{location}/queues/{queue}/tasks/{task_id}"

    def create_task(self, *, parent: str, task: Any) -> None:
        from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS

        if self.create_error is not None:
            raise self.create_error
        assert parent == f"projects/{_PROJECT}/locations/{_LOCATION}/queues/{_QUEUE}"
        assert isinstance(task, tasks_v2.Task)
        assert task.http_request.http_method == tasks_v2.HttpMethod.POST
        assert task.http_request.url == _HANDLER_URL
        assert task.http_request.headers == {"Content-Type": "application/json"}
        assert task.http_request.oidc_token.service_account_email == _INVOKER_SERVICE_ACCOUNT
        assert task.http_request.oidc_token.audience == _HANDLER_URL
        assert task.dispatch_deadline.seconds == DISPATCH_DEADLINE_SECONDS
        payload = json.loads(task.http_request.body)
        assert set(payload) == {"job_id"}
        wipe_job_id = payload["job_id"]
        assert isinstance(wipe_job_id, str) and re.fullmatch(r"[0-9a-f]{32}", wipe_job_id)
        job_hash = hashlib.sha256(wipe_job_id.encode("utf-8")).hexdigest()[:32]
        expected_name = (
            rf"projects/{_PROJECT}/locations/{_LOCATION}/queues/{_QUEUE}/tasks/account-delete-{job_hash}-[0-9a-f]{{32}}"
        )
        assert re.fullmatch(expected_name, task.name)
        if self._assert_pending_marker is not None:
            self._assert_pending_marker(wipe_job_id)
        self.create_calls.append((parent, task))

    def expect_pending_marker(self, fake_firestore: Any, uid: str) -> None:
        """Require durable pending state before the production task handoff returns."""

        def assert_pending_marker(wipe_job_id: str) -> None:
            snapshot = fake_firestore.collection("account_deletions").document(uid).get()
            assert snapshot.exists
            marker = snapshot.to_dict()
            assert marker["wipe_status"] == "pending"
            assert marker["wipe_job_id"] == wipe_job_id

        self._assert_pending_marker = assert_pending_marker


@pytest.fixture()
def account_deletion_identity(monkeypatch, fake_firestore, fresh_uid):
    """Authenticate as an isolated user and clean its durable deletion record."""

    from fakes.firestore import clear_user_data

    admin_key = "account-deletion-e2e-admin:"
    marker = fake_firestore.collection("account_deletions").document(fresh_uid)

    def clear_marker() -> None:
        if marker.get().exists:
            marker.delete()

    monkeypatch.setenv("ADMIN_KEY", admin_key)
    clear_marker()
    try:
        yield fresh_uid, {"Authorization": f"Bearer {admin_key}{fresh_uid}"}
    finally:
        clear_user_data(fresh_uid)
        clear_marker()


@pytest.fixture()
def cloud_tasks_client(monkeypatch):
    """Route production task construction to a strict in-memory client."""

    from utils import cloud_tasks

    client = _CapturedCloudTasksClient()
    monkeypatch.setattr(cloud_tasks, "_get_tasks_client", lambda: client)
    return client


def _configure_durable_account_deletion(monkeypatch) -> None:
    """Enable the production Cloud Tasks path with only local configuration."""

    monkeypatch.setenv("ACCOUNT_DELETION_DISPATCH_MODE", "cloud_tasks")
    monkeypatch.setenv("SYNC_TASKS_PROJECT", _PROJECT)
    monkeypatch.setenv("SYNC_TASKS_LOCATION", _LOCATION)
    monkeypatch.setenv("SYNC_TASKS_INVOKER_SA", _INVOKER_SERVICE_ACCOUNT)
    monkeypatch.setenv("ACCOUNT_DELETION_TASKS_QUEUE", _QUEUE)
    monkeypatch.setenv("ACCOUNT_DELETION_HANDLER_URL", _HANDLER_URL)
    monkeypatch.setenv("ACCOUNT_DELETION_TASKS_OIDC_AUDIENCE", _HANDLER_URL)
    monkeypatch.setenv("ACCOUNT_DELETION_TASKS_MAX_ATTEMPTS", "2")

    from utils import cloud_tasks

    def verify_local_task_token(token: str, _request: Any, audience: str) -> dict[str, Any]:
        assert token == _LOCAL_TASK_TOKEN
        assert audience == _HANDLER_URL
        return {"email": _INVOKER_SERVICE_ACCOUNT, "email_verified": True}

    monkeypatch.setattr(cloud_tasks.id_token, "verify_oauth2_token", verify_local_task_token)


def _worker_headers(retry_count: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_LOCAL_TASK_TOKEN}",
        "X-CloudTasks-TaskRetryCount": str(retry_count),
    }


def _seed_deletable_user(fake_firestore, test_uid: str) -> None:
    user = fake_firestore.collection("users").document(test_uid)
    user.set({"uid": test_uid, "name": "Hermetic deletion user"})
    user.collection("memories").document("deletion-memory").set({"id": "deletion-memory", "uid": test_uid})


def _assert_user_data_deleted(fake_firestore, test_uid: str) -> None:
    user = fake_firestore.collection("users").document(test_uid)
    assert not user.get().exists
    assert not user.collection("memories").document("deletion-memory").get().exists


def _stub_external_deletion_boundaries(monkeypatch) -> None:
    """Keep Firebase, Twilio, billing, and vector service calls inside the harness."""

    from services.users import account_deletion

    monkeypatch.setattr(account_deletion.auth, "delete_account", lambda _uid: None)
    monkeypatch.setattr(account_deletion.users_db, "get_user_subscription", lambda _uid: None)
    monkeypatch.setattr(account_deletion, "delete_user_caller_ids", lambda _uid: None)


def _assert_enqueued_task_schema(tasks_client: _CapturedCloudTasksClient, wipe_job_id: str) -> dict[str, str]:
    """Prove the production queue request is durable, scoped, and opaque."""

    assert tasks_client.queue_path_calls == [(_PROJECT, _LOCATION, _QUEUE)]
    assert len(tasks_client.task_path_calls) == 1
    project, location, queue, task_id = tasks_client.task_path_calls[0]
    assert (project, location, queue) == (_PROJECT, _LOCATION, _QUEUE)
    job_hash = hashlib.sha256(wipe_job_id.encode("utf-8")).hexdigest()[:32]
    assert re.fullmatch(rf"account-delete-{job_hash}-[0-9a-f]{{32}}", task_id)

    assert len(tasks_client.create_calls) == 1
    parent, task = tasks_client.create_calls[0]
    assert parent == f"projects/{_PROJECT}/locations/{_LOCATION}/queues/{_QUEUE}"
    assert task.name.endswith(f"/tasks/{task_id}")

    payload = json.loads(task.http_request.body)
    assert payload == {"job_id": wipe_job_id}
    return payload


def _read_marker(fake_firestore, test_uid: str) -> dict[str, Any]:
    snapshot = fake_firestore.collection("account_deletions").document(test_uid).get()
    assert snapshot.exists
    return snapshot.to_dict()


def _observe_claim_transitions(monkeypatch, fake_firestore, test_uid: str) -> list[dict[str, Any]]:
    """Observe the real transaction's durable claim state without replacing it."""

    import routers.users as users_router

    production_claim = users_router.claim_deletion_wipe_for_task
    claimed_markers: list[dict[str, Any]] = []

    def observe_claim(uid: str) -> str:
        outcome = production_claim(uid)
        if outcome == "claimed":
            claimed_markers.append(_read_marker(fake_firestore, test_uid))
        return outcome

    monkeypatch.setattr(users_router, "claim_deletion_wipe_for_task", observe_claim)
    return claimed_markers


def test_account_deletion_cloud_task_completes_once_and_redelivery_is_acked(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """Admission -> opaque task -> worker claim -> completed redelivery is one real lifecycle."""

    from services.users import account_deletion

    test_uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    purge_calls: list[str] = []

    def successful_purge(uid: str) -> dict[str, list[dict[str, str]]]:
        purge_calls.append(uid)
        return {"required_failures": [], "best_effort_failures": []}

    monkeypatch.setattr(
        account_deletion,
        "purge_derived_user_data",
        successful_purge,
    )
    _seed_deletable_user(fake_firestore, test_uid)
    cloud_tasks_client.expect_pending_marker(fake_firestore, test_uid)
    claimed_markers = _observe_claim_transitions(monkeypatch, fake_firestore, test_uid)

    admitted = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert admitted.status_code == 200, admitted.text
    assert admitted.json() == {"status": "ok", "message": "Account deletion started"}

    pending_marker = _read_marker(fake_firestore, test_uid)
    assert pending_marker["wipe_status"] == "pending"
    wipe_job_id = pending_marker["wipe_job_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", wipe_job_id)
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    unauthenticated = client.post("/v1/users/account-deletion-wipes/run", json=payload)
    assert unauthenticated.status_code == 403, unauthenticated.text

    completed = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert completed.status_code == 200, completed.text
    assert completed.json() == {"status": "done"}
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    _assert_user_data_deleted(fake_firestore, test_uid)
    assert len(claimed_markers) == 1
    assert claimed_markers[0]["wipe_status"] == "retrying"
    assert "wipe_claimed_at" in claimed_markers[0]
    assert purge_calls == [test_uid]

    redelivery = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=1)
    )
    assert redelivery.status_code == 200, redelivery.text
    assert redelivery.json() == {"status": "dropped", "reason": "completed"}
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    assert len(claimed_markers) == 1
    assert purge_calls == [test_uid]


def test_account_deletion_cloud_task_retries_required_purge_failure_without_losing_the_job(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """A required purge failure returns retry, preserves data, and later completes the same job."""

    from services.users import account_deletion

    test_uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    purge_calls: list[str] = []
    purge_results = iter(
        [
            {
                "required_failures": [{"operation": "conversation_vectors", "error": "fake unavailable"}],
                "best_effort_failures": [],
            },
            {"required_failures": [], "best_effort_failures": []},
        ]
    )

    def controlled_purge(uid: str) -> dict[str, list[dict[str, str]]]:
        purge_calls.append(uid)
        return next(purge_results)

    monkeypatch.setattr(account_deletion, "purge_derived_user_data", controlled_purge)
    _seed_deletable_user(fake_firestore, test_uid)
    cloud_tasks_client.expect_pending_marker(fake_firestore, test_uid)
    claimed_markers = _observe_claim_transitions(monkeypatch, fake_firestore, test_uid)

    admitted = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert admitted.status_code == 200, admitted.text
    wipe_job_id = _read_marker(fake_firestore, test_uid)["wipe_job_id"]
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    failed_delivery = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert failed_delivery.status_code == 500, failed_delivery.text
    assert failed_delivery.json() == {"status": "retry"}
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "failed"
    user = fake_firestore.collection("users").document(test_uid)
    assert user.get().exists
    assert user.collection("memories").document("deletion-memory").get().exists
    assert len(claimed_markers) == 1
    assert claimed_markers[0]["wipe_status"] == "retrying"
    assert "wipe_claimed_at" in claimed_markers[0]
    assert purge_calls == [test_uid]

    retried_delivery = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=1)
    )
    assert retried_delivery.status_code == 200, retried_delivery.text
    assert retried_delivery.json() == {"status": "done"}
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    _assert_user_data_deleted(fake_firestore, test_uid)
    assert len(claimed_markers) == 2
    assert all(marker["wipe_status"] == "retrying" and "wipe_claimed_at" in marker for marker in claimed_markers)
    assert purge_calls == [test_uid, test_uid]

    redelivery = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=2)
    )
    assert redelivery.status_code == 200, redelivery.text
    assert redelivery.json() == {"status": "dropped", "reason": "completed"}
    assert len(claimed_markers) == 2
    assert purge_calls == [test_uid, test_uid]


def test_queue_not_found_preserves_auth_and_reconciles_from_the_marker(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """A real route request proves queue failure cannot strand an auth-less user."""
    from services.users import account_deletion

    test_uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    _seed_deletable_user(fake_firestore, test_uid)
    auth_deletions: list[str] = []
    monkeypatch.setattr(account_deletion.auth, "delete_account", lambda uid: auth_deletions.append(uid))
    monkeypatch.setattr(
        account_deletion,
        "purge_derived_user_data",
        lambda _uid: {"required_failures": [], "best_effort_failures": []},
    )
    cloud_tasks_client.create_error = NotFound("account-deletion queue is absent")

    accepted = client.delete("/v1/users/delete-account", headers=auth_headers)

    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"status": "ok", "message": "Account deletion started"}
    assert auth_deletions == []
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "failed"
    assert fake_firestore.collection("users").document(test_uid).get().exists

    cloud_tasks_client.create_error = None
    cloud_tasks_client.queue_path_calls.clear()
    cloud_tasks_client.task_path_calls.clear()
    cloud_tasks_client.create_calls.clear()
    recovered = account_deletion.reconcile_pending_deletion_wipes()
    assert recovered == {"requeued": 1, "skipped": 0}
    assert auth_deletions == []
    wipe_job_id = _read_marker(fake_firestore, test_uid)["wipe_job_id"]
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    completed = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert completed.status_code == 200, completed.text
    assert auth_deletions == [test_uid]
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    _assert_user_data_deleted(fake_firestore, test_uid)


def test_repeated_delete_request_joins_running_wipe_without_requeueing(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """A repeat request cannot move a claimed wipe backwards or create another task."""
    from services.users import account_deletion

    test_uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    _seed_deletable_user(fake_firestore, test_uid)
    monkeypatch.setattr(
        account_deletion,
        "purge_derived_user_data",
        lambda _uid: {"required_failures": [], "best_effort_failures": []},
    )

    first = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert first.status_code == 200, first.text
    marker = _read_marker(fake_firestore, test_uid)
    assert marker["wipe_status"] == "pending"
    assert len(cloud_tasks_client.create_calls) == 1

    repeated_pending = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert repeated_pending.status_code == 200, repeated_pending.text
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "pending"
    assert len(cloud_tasks_client.create_calls) == 1

    assert account_deletion.users_db.claim_deletion_wipe_for_task(test_uid) == "claimed"
    account_deletion.users_db.mark_user_deletion_wipe_running(test_uid)
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "running"

    repeated_running = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert repeated_running.status_code == 200, repeated_running.text
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "running"
    assert len(cloud_tasks_client.create_calls) == 1


def test_missing_root_document_does_not_hide_immediate_child_data(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """The production worker must delete children even when their root is absent."""
    from services.users import account_deletion

    test_uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    orphan_child = fake_firestore.collection("users").document(test_uid).collection("memories").document("orphan")
    orphan_child.set({"id": "orphan", "uid": test_uid})
    assert not fake_firestore.collection("users").document(test_uid).get().exists
    monkeypatch.setattr(
        account_deletion,
        "purge_derived_user_data",
        lambda _uid: {"required_failures": [], "best_effort_failures": []},
    )

    admitted = client.delete("/v1/users/delete-account", headers=auth_headers)
    assert admitted.status_code == 200, admitted.text
    wipe_job_id = _read_marker(fake_firestore, test_uid)["wipe_job_id"]
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    completed = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert completed.status_code == 200, completed.text
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    assert not orphan_child.get().exists
