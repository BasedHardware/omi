"""Hermetic Cloud Tasks lifecycle coverage for durable account deletion."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from secrets import token_hex
import time
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from google.api_core.exceptions import NotFound
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore, tasks_v2

_PROJECT = "test-e2e-project"
_LOCATION = "us-central1"
_QUEUE = "account-deletion"
_HANDLER_URL = "http://127.0.0.1:8765/v1/users/account-deletion-wipes/run"
_INVOKER_SERVICE_ACCOUNT = "account-deletion-worker@example.invalid"
_LOCAL_TASK_TOKEN = "local-account-deletion-cloud-task"


class _LoopbackFirestore(firestore.Client):
    # The e2e harness subsequently patches firestore.Client's constructor.
    __init__ = firestore.Client.__init__


@pytest.mark.parametrize(
    'method,path,body',
    [
        ('POST', '/v1/users/private-cloud-sync?value=true', None),
        ('PATCH', '/v1/users/voice-profile-settings', {'save_other_voice_profiles': False}),
        ('POST', '/v1/users/migration/requests', {'target_level': 'enhanced'}),
    ],
)
def test_erased_account_privacy_mutations_return_gone(
    client, fake_firestore, monkeypatch, account_deletion_identity, method, path, body
):
    from database.batch_pipeline_privacy import privacy_owner_key

    uid, headers = account_deletion_identity
    monkeypatch.setenv('BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED', 'true')
    user = fake_firestore.collection('users').document(uid)
    user.delete()
    owner = fake_firestore.collection('batch_pipeline_privacy').document(privacy_owner_key(uid))
    owner.set({'generation': 1, 'blocked': True})
    try:
        response = client.request(method, path, headers=headers, json=body)
        assert response.status_code == 410
        assert response.json() == {'detail': 'Account has been erased.'}
        assert not user.get().exists
    finally:
        owner.delete()


class _CapturedCloudTasksClient:
    """Strict local substitute for the Cloud Tasks client used by this workflow."""

    def __init__(self) -> None:
        self.create_calls: list[tuple[str, Any]] = []
        self.queue_path_calls: list[tuple[str, str, str]] = []
        self.task_path_calls: list[tuple[str, str, str, str]] = []
        self._assert_pending_marker: Callable[[str], None] | None = None
        self.create_error: Exception | None = None
        self.verification_token: str | None = None

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
        expected_keys = {"job_id"}
        if self.verification_token:
            from database.speaker_evidence_verification import TASK_FIELD

            expected_keys.add(TASK_FIELD)
            assert payload[TASK_FIELD] == self.verification_token
        assert set(payload) == expected_keys
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
    monkeypatch.setenv("GO_QUEUE_ERASE_REQUIRED", "false")
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
    from database import user_data_deletion

    monkeypatch.setattr(account_deletion.auth, "delete_account", lambda _uid: None)
    monkeypatch.setattr(account_deletion.firebase_auth, "revoke_refresh_tokens", lambda _uid: None)
    monkeypatch.setattr(account_deletion.users_db, "get_user_subscription", lambda _uid: None)
    monkeypatch.setattr(account_deletion.stripe_utils, "find_billable_app_subscription_ids", lambda _uid: [])
    # The harness disables Typesense globally. The account-deletion service
    # requires a verified owner purge before completion, so keep this external
    # boundary hermetic just like Stripe, Firebase, and storage.
    monkeypatch.setattr(account_deletion, "purge_user_conversation_index", lambda _uid: None)
    # This E2E focuses on the durable wipe lifecycle, not marketplace query
    # semantics; creator-app erasure is covered by the focused unit test.
    monkeypatch.setattr(user_data_deletion, "search_apps_db", lambda _uid, my_apps: [])
    monkeypatch.setattr(account_deletion, "delete_user_caller_ids", lambda _uid: None)
    monkeypatch.setattr(account_deletion, "delete_agent_vm_for_account", lambda _uid: None)
    monkeypatch.setattr(account_deletion, "delete_account_credentials", lambda _uid: None)


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

    def observe_claim(uid: str, *, expected_job_id: str | None = None) -> str:
        assert uid == test_uid
        assert expected_job_id is None
        outcome = production_claim(uid)
        if outcome == "claimed":
            claimed_markers.append(_read_marker(fake_firestore, uid))
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
    wipe_failures: list[dict[str, Any]] = []
    monkeypatch.setattr(
        account_deletion,
        "_emit_deletion_telemetry",
        lambda _uid, event, properties: wipe_failures.append({"event": event, **properties}),
    )

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

    admitted = client.request("DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True})
    assert admitted.status_code == 200, admitted.text
    assert admitted.json() == {
        "status": "ok",
        "message": "Account deletion started",
        "pending_deletion": False,
        "wipe_at": None,
    }

    pending_marker = _read_marker(fake_firestore, test_uid)
    assert pending_marker["wipe_status"] == "pending"
    assert "wipe_due_at" not in pending_marker
    wipe_job_id = pending_marker["wipe_job_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", wipe_job_id)
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    unauthenticated = client.post("/v1/users/account-deletion-wipes/run", json=payload)
    assert unauthenticated.status_code == 403, unauthenticated.text

    completed = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert completed.status_code == 200, f"{completed.text}; wipe_failures={wipe_failures!r}"
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

    admitted = client.request("DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True})
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

    accepted = client.request("DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True})

    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {
        "status": "ok",
        "message": "Account deletion started",
        "pending_deletion": False,
        "wipe_at": None,
    }
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


def test_repeated_delete_request_is_fenced_without_requeueing(
    client,
    fake_firestore,
    monkeypatch,
    account_deletion_identity,
    cloud_tasks_client,
):
    """A repeat request is fenced without moving the wipe backwards or creating another task."""
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

    first = client.request("DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True})
    assert first.status_code == 200, first.text
    marker = _read_marker(fake_firestore, test_uid)
    assert marker["wipe_status"] == "pending"
    assert len(cloud_tasks_client.create_calls) == 1

    repeated_pending = client.request(
        "DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True}
    )
    assert repeated_pending.status_code == 403, repeated_pending.text
    assert repeated_pending.json() == {
        "detail": {
            "code": "account_deletion_in_progress",
            "status": "pending",
            "retryable": False,
        }
    }
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "pending"
    assert len(cloud_tasks_client.create_calls) == 1

    assert account_deletion.users_db.claim_deletion_wipe_for_task(test_uid) == "claimed"
    account_deletion.users_db.mark_user_deletion_wipe_running(test_uid)
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "running"

    repeated_running = client.request(
        "DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True}
    )
    assert repeated_running.status_code == 403, repeated_running.text
    assert repeated_running.json() == {
        "detail": {
            "code": "account_deletion_in_progress",
            "status": "running",
            "retryable": False,
        }
    }
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

    admitted = client.request("DELETE", "/v1/users/delete-account", headers=auth_headers, json={"erase_now": True})
    assert admitted.status_code == 200, admitted.text
    wipe_job_id = _read_marker(fake_firestore, test_uid)["wipe_job_id"]
    payload = _assert_enqueued_task_schema(cloud_tasks_client, wipe_job_id)

    completed = client.post(
        "/v1/users/account-deletion-wipes/run", json=payload, headers=_worker_headers(retry_count=0)
    )
    assert completed.status_code == 200, completed.text
    assert _read_marker(fake_firestore, test_uid)["wipe_status"] == "completed"
    assert not orphan_child.get().exists


@pytest.fixture
def verification_emulator(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required')
    from database import _client, user_data_deletion, users
    from database import speaker_evidence_verification as verification

    plane = _LoopbackFirestore(project=f'demo-evidence-{token_hex(6)}', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: plane)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: plane)
    monkeypatch.setattr(users, 'db', plane)
    monkeypatch.setattr(users, 'account_authority_writer_enabled', lambda: False)
    monkeypatch.setattr(user_data_deletion, 'account_authority_writer_enabled', lambda: False)
    monkeypatch.setenv('K_SERVICE', 'backend-sync')
    metrics = verification.metrics
    monkeypatch.setattr(metrics, '_REVISION', 'worker-sync-rehearsal')
    monkeypatch.setattr(
        metrics,
        '_VERIFICATION_OUTCOMES',
        {name: metrics._VERIFICATION.labels('worker-sync-rehearsal', name) for name in metrics._VERIFICATION_OUTCOMES},
    )
    yield plane
    plane.close()


def _arm_verification(monkeypatch, plane, uid, *, duration=120):
    from database import speaker_evidence_verification as verification

    token = token_hex(32)
    ref = plane.collection(verification.COLLECTION).document(hashlib.sha256(token.encode()).hexdigest())
    ref.create(
        {
            'account_hash': hashlib.sha256(uid.encode()).hexdigest(),
            'expires_at': datetime.now(timezone.utc) + timedelta(seconds=duration),
        }
    )
    monkeypatch.setenv('SPEAKER_EVIDENCE_VERIFY_UID_SHA256', hashlib.sha256(uid.encode()).hexdigest())
    monkeypatch.setenv('SPEAKER_EVIDENCE_VERIFY_TOKEN', token)
    return token, ref


def _verification_counts():
    from utils.observability import speaker_evidence_erasure as metrics

    return {name: counter._value.get() for name, counter in metrics._VERIFICATION_OUTCOMES.items()}


def _wait_for_writer(ref):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if (ref.get(retry=None, timeout=1).to_dict() or {}).get('writer') == 'waiting':
            return
        time.sleep(0.025)
    pytest.fail('sampled writer did not claim the rendezvous')


@pytest.mark.parametrize('delivery', ['exact', 'wrong_queue', 'wrong_task', 'unrelated', 'unchecked_sweep'])
def test_synthetic_speaker_evidence_verification(
    client, verification_emulator, monkeypatch, account_deletion_identity, cloud_tasks_client, delivery
):
    from database import batch_pipeline_purge, speaker_evidence, speaker_evidence_verification, user_data_deletion
    from database.conversation_revisions import firestore_revision_datetime
    from models.speaker_evidence import SpeakerEvidence
    from routers import users as users_router
    from services.users import account_deletion
    from utils.observability import speaker_evidence_erasure as metrics
    from utils.other import endpoints as auth
    from utils.speakers import processing

    plane = verification_emulator
    uid, auth_headers = account_deletion_identity
    _configure_durable_account_deletion(monkeypatch)
    _stub_external_deletion_boundaries(monkeypatch)
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda _uid: None)
    monkeypatch.setattr(account_deletion, '_emit_deletion_telemetry', lambda *a: None)
    monkeypatch.setattr(processing, '_roster', lambda *_: [])
    # Force one transient provider failure on the exact task before the real sweep.
    failures = iter([delivery == 'exact', False])

    def purge_derived(_uid):
        failure = [{'operation': 'synthetic_provider'}] if next(failures) else []
        return {'required_failures': failure, 'best_effort_failures': []}

    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', purge_derived)
    root = plane.document(f'users/{uid}')
    root.set({'uid': uid})
    parent = root.collection('conversations').document('fixture')
    revision = firestore_revision_datetime(parent.set({'status': 'completed'}).update_time)
    evidence = SpeakerEvidence(status='unavailable', policy_version='synthetic')
    speaker_evidence.store_evidence(uid, parent.id, evidence, expected_updated_at=revision, firestore_client=plane)
    child = parent.collection('speaker_evidence').document('current')
    assert child.get().exists
    expected_child = child.get().update_time
    foreign = plane.document('users/unrelated/conversations/fixture/speaker_evidence/current')
    foreign.set({'version': 1})
    token, control = _arm_verification(monkeypatch, plane, uid)
    cloud_tasks_client.verification_token = token
    cloud_tasks_client.expect_pending_marker(plane, uid)
    before = _verification_counts()
    checked_before = metrics.SWEEP_CHECKED._value.get()
    remaining_before = metrics.REMAINING._value.get()
    committed_before = metrics.COMMITTED_MARKER_PRESENT._value.get()
    refused_before = metrics.REFUSED_MARKER_PRESENT._value.get()
    conversation = SimpleNamespace(id=parent.id, updated_at=revision, transcript_segments=[])

    def writer():
        auth.enforce_account_deletion_http_access(uid, allow_grace_erase_now=False)
        processing.finish(processing.begin(conversation), uid, conversation, receipt=None)

    # An enabled rendezvous must never admit an unsampled writer.
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'shadow')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '0')
    writer()
    assert 'writer' not in control.get().to_dict()
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '100')
    with ThreadPoolExecutor(max_workers=1) as writer_pool:
        writing = writer_pool.submit(writer)
        _wait_for_writer(control)
        admitted = client.request('DELETE', '/v1/users/delete-account', headers=auth_headers, json={'erase_now': True})
        assert admitted.status_code == 200, admitted.text
        writing.result(timeout=20)
    assert control.get().get('writer') == 'refused_marker_present'
    assert child.get().update_time == expected_child

    ((queue_path, task),) = cloud_tasks_client.create_calls
    assert queue_path.endswith('/queues/account-deletion')
    path = '/v1/users/account-deletion-wipes/run'
    payload = json.loads(task.http_request.body)
    headers = _worker_headers(retry_count=0)
    headers['X-CloudTasks-QueueName'] = _QUEUE
    headers['X-CloudTasks-TaskName'] = task.name.rsplit('/', 1)[-1]
    assert client.post(path, json=payload).status_code == 403
    with monkeypatch.context() as unavailable_job:
        # Deliver the exact task and headers through OIDC, but simulate its
        # durable job becoming non-actionable before the route can claim it.
        unavailable_job.setattr(users_router, 'resolve_deletion_wipe_job_id', lambda _job: {'outcome': 'missing'})
        dropped = client.post(path, json=payload, headers=headers)
        assert dropped.json() == {'status': 'dropped', 'reason': 'missing'}
    assert control.get().get('dispatch') == 'enqueued'
    assert _verification_counts()['task_admitted'] == before['task_admitted']

    # Seed a child under a missing conversation and user immediately before the
    # second sweep, after the ordinary deletion traversal has already finished.
    late_child = plane.document(f'users/{uid}/conversations/late/speaker_evidence/current')
    real_sweep = user_data_deletion._sweep_speaker_evidence

    def sweep(owner, firestore_client, delete_collection):
        assert not root.get().exists
        late_child.set({'version': 1})
        real_sweep(owner, firestore_client, delete_collection)
        assert not late_child.get().exists

    monkeypatch.setattr(user_data_deletion, '_sweep_speaker_evidence', sweep)
    if delivery == 'wrong_queue':
        headers['X-CloudTasks-QueueName'] = 'wrong'
    if delivery == 'wrong_task':
        headers['X-CloudTasks-TaskName'] = 'wrong'
    if delivery == 'unrelated':
        payload.pop(speaker_evidence_verification.TASK_FIELD)
    if delivery == 'unchecked_sweep':
        monkeypatch.setenv(user_data_deletion.SPEAKER_EVIDENCE_ERASURE_CHECK_ENV, 'off')
    if delivery == 'exact':
        retry = client.post(path, json=payload, headers=headers)
        assert retry.status_code == 500 and retry.json() == {'status': 'retry'}
        assert control.get().get('dispatch') == 'enqueued'
        assert (
            _verification_counts()['task_completed_checked_zero_remaining']
            == before['task_completed_checked_zero_remaining']
        )
        headers['X-CloudTasks-TaskRetryCount'] = '1'
    completed = client.post(path, json=payload, headers=headers)
    assert completed.json() == {'status': 'done'}, completed.text
    duplicate = client.post(path, json=payload, headers=headers)
    assert duplicate.json() == {'status': 'dropped', 'reason': 'completed'}
    assert not child.get().exists and not late_child.get().exists and foreign.get().exists
    assert metrics.REFUSED_MARKER_PRESENT._value.get() - refused_before == 1
    assert metrics.COMMITTED_MARKER_PRESENT._value.get() - committed_before == 0
    assert metrics.SWEEP_CHECKED._value.get() - checked_before == int(delivery != 'unchecked_sweep')
    assert metrics.REMAINING._value.get() - remaining_before == 0
    after = _verification_counts()
    deltas = {name: after[name] - before[name] for name in before}
    expected = dict.fromkeys(before, 0)
    for key in ('writer_waiting', 'writer_released', 'writer_refused_marker_present', 'task_enqueued'):
        expected[key] = 1
    if delivery == 'exact':
        expected.update(
            task_admitted=2,
            task_admitted_retry=1,
            task_completed_checked_zero_remaining=1,
            task_completed_after_writer_refusal=1,
        )
        completed_receipt = control.get().to_dict()
        assert completed_receipt['executor_revision'] == 'worker-sync-rehearsal'
        assert completed_receipt['dispatch'] == 'completed'
        assert not {'job', 'task', 'marker_job', 'confirm_until', 'wait_until'}.intersection(completed_receipt)
    elif delivery == 'unchecked_sweep':
        expected['task_admitted'] = 1
    assert deltas == expected
    control.delete()
    foreign.delete()
    plane.document(f'account_deletions/{uid}').delete()


def test_synthetic_speaker_evidence_writer_is_single_use_and_times_out(
    client, verification_emulator, monkeypatch, fresh_uid
):
    from database import speaker_evidence, speaker_evidence_verification as verification
    from models.speaker_evidence import SpeakerEvidence

    plane = verification_emulator
    parent = plane.document(f'users/{fresh_uid}/conversations/fixture')
    parent.set({})
    _, control = _arm_verification(monkeypatch, plane, fresh_uid)
    monkeypatch.setattr(verification, 'WRITER_WAIT_SECONDS', 0.3)
    evidence = SpeakerEvidence(status='unavailable', policy_version='synthetic')
    before = _verification_counts()
    with pytest.raises(TimeoutError, match='verification writer timed out'):
        speaker_evidence.store_evidence(fresh_uid, parent.id, evidence, firestore_client=plane)
    assert control.get().get('writer') == 'timed_out'
    child = parent.collection('speaker_evidence').document('current')
    assert not child.get().exists
    speaker_evidence.store_evidence(fresh_uid, parent.id, evidence, firestore_client=plane)
    assert child.get().exists
    after = _verification_counts()
    deltas = {name: after[name] - before[name] for name in before}
    assert {name: value for name, value in deltas.items() if value} == {'writer_waiting': 1, 'writer_timed_out': 1}
    child.delete()
    parent.delete()
    control.delete()


def test_synthetic_speaker_evidence_pending_receipt_and_expiry(client, verification_emulator, monkeypatch, fresh_uid):
    from database import speaker_evidence_verification as verification

    _configure_durable_account_deletion(monkeypatch)
    token, control = _arm_verification(monkeypatch, verification_emulator, fresh_uid)
    queue_path = tasks_v2.CloudTasksClient.queue_path(_PROJECT, _LOCATION, _QUEUE)
    task = verification.reserve_task(fresh_uid, 'job', queue_path, 'task')
    assert task is not None
    before = _verification_counts()
    assert verification.admit_task(fresh_uid, 'job', token, queue_path, _QUEUE, 'task', 0) == (True, None)
    assert verification.admit_task(fresh_uid, 'job', token, queue_path, _QUEUE, 'wrong', 0) == (False, None)

    control.update({'confirm_until': datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert verification.admit_task(fresh_uid, 'job', token, queue_path, _QUEUE, 'task', 1) == (False, None)
    assert _verification_counts()['task_enqueued'] == before['task_enqueued']

    control.update({'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    verification.confirm_enqueue(task)
    assert verification.wait_for_deletion_marker(fresh_uid, verification_emulator) is None
    assert verification.reserve_task(fresh_uid, 'job', queue_path, 'second') is None
    assert verification.admit_task(fresh_uid, 'job', token, queue_path, _QUEUE, 'task', 1) == (False, None)
    after = _verification_counts()
    assert {name: after[name] - before[name] for name in before if after[name] != before[name]} == {'task_deferred': 1}
    control.delete()
