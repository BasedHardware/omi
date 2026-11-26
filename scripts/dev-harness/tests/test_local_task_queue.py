from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dev-harness"))

tasks_v2 = pytest.importorskip("google.cloud.tasks_v2")
from google.api_core.exceptions import AlreadyExists, InvalidArgument, NotFound  # noqa: E402
from google.protobuf import duration_pb2, timestamp_pb2  # noqa: E402

from dev_harness import local_task_queue  # noqa: E402
from dev_harness.local_task_queue import LocalTaskQueue, QueueSettings  # noqa: E402

FRESH_QUEUE = "sync-jobs-fresh"
BACKFILL_QUEUE = "sync-backfill-fresh"

HANDLER = "http://127.0.0.1:8000/v2/sync-jobs/run"
INVOKER = "local-tasks-invoker@demo-omi-local.iam.gserviceaccount.com"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class Worker:
    """Scripted worker: one (status, retry_after) per delivery, then 200."""

    def __init__(self, *answers: tuple[int, str | None] | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def __call__(self, url: str, body: bytes, headers: dict[str, str], timeout: float):
        self.calls.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        answer = self.answers.pop(0) if self.answers else (200, None)
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_queue(tmp_path: Path, worker: Worker, clock: Clock, **overrides) -> LocalTaskQueue:
    queues = {
        FRESH_QUEUE: QueueSettings(5, 60.0, 300.0, 4, 0.0),
        BACKFILL_QUEUE: QueueSettings(overrides.get("backfill_attempts", 5), 5.0, 60.0, 4, 0.0),
    }
    return LocalTaskQueue(tmp_path / "tasks.sqlite", queues, transport=worker, clock=clock, log=lambda _line: None)


def make_task(queue: LocalTaskQueue, name: str, *, lane_queue: str = BACKFILL_QUEUE, url: str = HANDLER, at=None):
    parent = queue.queue_path("demo-omi-local", "local", lane_queue)
    task = tasks_v2.Task(
        name=queue.task_path("demo-omi-local", "local", lane_queue, name),
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=url,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"job_id": name}).encode(),
            oidc_token=tasks_v2.OidcToken(service_account_email=INVOKER, audience=HANDLER),
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=1500),
        schedule_time=timestamp_pb2.Timestamp(seconds=int(at)) if at is not None else None,
    )
    return parent, task


def state(queue: LocalTaskQueue, lane_queue: str = BACKFILL_QUEUE) -> dict[str, int]:
    return queue.counts().get(lane_queue, {})


def test_delivers_with_cloud_tasks_headers_and_a_token_only_this_queue_minted(tmp_path):
    worker, clock = Worker(), Clock()
    queue = make_queue(tmp_path, worker, clock)
    queue.create_task(**dict(zip(("parent", "task"), make_task(queue, "job-1"))))

    assert queue.dispatch_due() == 1
    call = worker.calls[0]
    assert call["url"] == HANDLER and call["timeout"] == 1500.0
    assert json.loads(call["body"]) == {"job_id": "job-1"}
    headers = call["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["X-CloudTasks-QueueName"] == BACKFILL_QUEUE
    assert headers["X-CloudTasks-TaskName"] == "job-1"
    assert headers["X-CloudTasks-TaskRetryCount"] == "0"
    token = headers["Authorization"].removeprefix("Bearer ")
    assert queue.verify_token(token, HANDLER) == {"aud": HANDLER, "email": INVOKER, "email_verified": True}
    with pytest.raises(ValueError):
        queue.verify_token(token, "http://127.0.0.1:8000/v1/other")
    other = make_queue(tmp_path / "other", Worker(), clock)
    with pytest.raises(ValueError):
        other.verify_token(token, HANDLER)
    assert state(queue) == {"done": 1}


def test_named_task_is_deduplicated_while_live_and_for_the_tombstone_window(tmp_path):
    worker, clock = Worker(), Clock()
    queue = make_queue(tmp_path, worker, clock)
    parent, task = make_task(queue, "job-1")
    queue.create_task(parent=parent, task=task)
    with pytest.raises(AlreadyExists):
        queue.create_task(parent=parent, task=task)
    assert queue.get_task(name=task.name).name == task.name

    queue.dispatch_due()
    with pytest.raises(NotFound):
        queue.get_task(name=task.name)
    with pytest.raises(AlreadyExists):
        queue.create_task(parent=parent, task=task)

    clock.now += local_task_queue.NAME_TOMBSTONE_SECONDS + 1
    queue.create_task(parent=parent, task=task)
    assert state(queue) == {"pending": 1}


def test_failed_delivery_retries_with_queue_backoff_then_drops_at_max_attempts(tmp_path):
    worker, clock = Worker((409, None), (500, None), ConnectionError("refused"), (503, None), (500, None)), Clock()
    queue = make_queue(tmp_path, worker, clock)
    queue.create_task(**dict(zip(("parent", "task"), make_task(queue, "job-1"))))

    delays = []
    for attempt in range(5):
        assert queue.dispatch_due() == 1, attempt
        assert worker.calls[-1]["headers"]["X-CloudTasks-TaskRetryCount"] == str(attempt)
        if attempt < 4:
            assert queue.dispatch_due() == 0  # not due again until its backoff passes
            delay = [5.0, 10.0, 20.0, 40.0][attempt]
            delays.append(delay)
            clock.now += delay
    assert state(queue) == {"dropped": 1}
    assert queue.dispatch_due() == 0
    # The transport failure reached no handler, so it is not an execution.
    assert [call["headers"]["X-CloudTasks-TaskExecutionCount"] for call in worker.calls] == ["0", "1", "2", "2", "3"]


def test_a_closed_listener_is_not_a_delivery_and_spends_no_attempt(tmp_path):
    worker, clock = Worker(local_task_queue.WorkerUnreachable("refused"), (200, None)), Clock()
    queue = make_queue(tmp_path, worker, clock)
    queue.create_task(**dict(zip(("parent", "task"), make_task(queue, "job-1"))))

    assert queue.dispatch_due() == 1
    assert state(queue) == {"pending": 1}
    assert queue.dispatch_due() == 0  # a short pause while the service restarts
    clock.now += local_task_queue.UNREACHABLE_RETRY_SECONDS
    assert queue.dispatch_due() == 1
    assert worker.calls[1]["headers"]["X-CloudTasks-TaskRetryCount"] == "0"
    assert state(queue) == {"done": 1}


def test_fresh_queue_uses_its_own_backoff_and_honors_a_longer_retry_after(tmp_path):
    worker, clock = Worker((503, "900"), (200, None)), Clock()
    queue = make_queue(tmp_path, worker, clock)
    queue.create_task(**dict(zip(("parent", "task"), make_task(queue, "job-1", lane_queue=FRESH_QUEUE))))

    queue.dispatch_due()
    clock.now += 60
    assert queue.dispatch_due() == 0
    clock.now += 840
    assert queue.dispatch_due() == 1
    assert state(queue, FRESH_QUEUE) == {"done": 1}


def test_scheduled_task_waits_for_its_time(tmp_path):
    worker, clock = Worker(), Clock()
    queue = make_queue(tmp_path, worker, clock)
    queue.create_task(**dict(zip(("parent", "task"), make_task(queue, "job-1", at=clock.now + 120))))

    assert queue.dispatch_due() == 0
    clock.now += 121
    assert queue.dispatch_due() == 1


def test_refuses_unknown_queues_and_non_loopback_targets(tmp_path):
    queue = make_queue(tmp_path, Worker(), Clock())
    parent, task = make_task(queue, "job-1", url="https://api.omi.me/v2/sync-jobs/run")
    with pytest.raises(InvalidArgument):
        queue.create_task(parent=parent, task=task)
    parent, task = make_task(queue, "job-2", lane_queue="not-provisioned")
    with pytest.raises(NotFound):
        queue.create_task(parent=parent, task=task)
    assert queue.counts() == {}


def test_pending_work_survives_a_restart_and_an_interrupted_delivery_is_retried(tmp_path):
    clock = Clock()

    class Hang(Worker):
        def __call__(self, *args, **kwargs):
            raise KeyboardInterrupt  # the process dies mid-delivery

    first = make_queue(tmp_path, Hang(), clock)
    first.create_task(**dict(zip(("parent", "task"), make_task(first, "job-1"))))
    first.create_task(**dict(zip(("parent", "task"), make_task(first, "job-2", at=clock.now + 600))))
    with pytest.raises(KeyboardInterrupt):
        first.dispatch_due()
    assert state(first) == {"running": 1, "pending": 1}

    worker = Worker()
    second = make_queue(tmp_path, worker, clock)
    assert state(second) == {"pending": 2}
    assert second.dispatch_due() == 0
    clock.now += 5
    assert second.dispatch_due() == 1
    assert worker.calls[0]["headers"]["X-CloudTasks-TaskRetryCount"] == "1"


def test_service_processes_share_one_queue_and_one_dispatcher(tmp_path):
    """Any service creates a task; only the dispatcher delivers it; every service accepts its token."""
    worker, clock = Worker(), Clock()
    settings = local_task_queue.encode_settings({BACKFILL_QUEUE: QueueSettings(5, 5.0, 60.0, 4, 0.0)})
    env = {
        local_task_queue.DB_ENV: str(tmp_path / "tasks.sqlite"),
        local_task_queue.SECRET_ENV: "stack-secret",
        local_task_queue.SETTINGS_ENV: settings,
    }
    service = local_task_queue._shared_queue(env, owns_dispatch=False)
    dispatcher = local_task_queue._shared_queue(env, owns_dispatch=True)
    dispatcher._transport, dispatcher._clock, service._clock = worker, clock, clock
    service.create_task(**dict(zip(("parent", "task"), make_task(service, "job-1"))))

    assert dispatcher.dispatch_due() == 1
    token = worker.calls[0]["headers"]["Authorization"].removeprefix("Bearer ")
    assert service.verify_token(token, HANDLER)["email"] == INVOKER
    with pytest.raises(RuntimeError):
        local_task_queue._shared_queue({local_task_queue.DB_ENV: env[local_task_queue.DB_ENV]}, owns_dispatch=False)
