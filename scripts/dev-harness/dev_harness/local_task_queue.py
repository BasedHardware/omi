"""Local stand-in for Cloud Tasks in a prod-parity stack.

Deployed services hand work to Cloud Tasks: an upload is staged, a named task
is created, and Cloud Tasks delivers it to a worker route (sync jobs,
conversation finalization, enrichment, audio merge, account deletion). A local
stack has no queue. This module keeps the production code path and replaces
only the provider:

* ``utils.cloud_tasks`` still builds the real ``tasks_v2.Task``; each service
  process gets this module as the client it hands the task to
  (``install_client``).
* Tasks are stored in SQLite under the harness state root, so they survive a
  service restart the way a queued Cloud Task survives a worker restart.
* One dispatcher process (``python -m dev_harness.local_task_queue``) delivers
  each task over loopback HTTP to the URL the task names, with the Cloud Tasks
  headers, and retries a non-2xx answer with the queue's backoff until its
  attempts run out.
* The worker route keeps its production dependency (bearer header, audience,
  invoker identity, retry count). Only Google's signature check is replaced,
  by a token built from a secret that never leaves this machine. The secret
  matters: the stack's public port may be bound on the LAN for a phone.

Queue names, attempts, backoff and rate follow production: the running queues
when a production snapshot is configured, else ``backend/deploy/ops/prod.yaml``.
Each queue delivers one task at a time unless
``OMI_HARNESS_TASK_QUEUE_CONCURRENCY`` raises it.

One backend guard is lifted, in ``_accept_backfill_deliveries``: non-prod stages
acknowledge backfill tasks unprocessed because a dev deployment could receive
production's; this stack owns its queue and state.

Not reproduced: Cloud Tasks IAM, Google-signed tokens, system throttling after
bursts of errors, and at-least-once duplicate delivery.

The repository's other Cloud Tasks stand-ins (``backend/testing/fakes/cloud_tasks_queue.py``
and the loopback clients of the hermetic stacks under ``backend/testing``) are
in-process or one-shot test doubles; none persists tasks or delivers them
between separately running services.
"""

from __future__ import annotations

import ipaddress
import json
import os
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from dev_harness import log_timestamps

DB_ENV = "OMI_HARNESS_TASK_QUEUE_DB"
CA_BUNDLE_ENV = "OMI_HARNESS_CA_BUNDLE"
CONCURRENCY_ENV = "OMI_HARNESS_TASK_QUEUE_CONCURRENCY"

# Deliveries in flight per queue: production's own limit, capped for one machine
# (production's limits are far higher, spread over many accounts and instances). A harness
# stack serves a single account whose work all lands in the same few documents,
# so a high cap mostly produces Firestore-emulator lock contention.
DEFAULT_CONCURRENCY = 4
# Cloud Tasks refuses a finished task's name for about an hour.
NAME_TOMBSTONE_SECONDS = 3600.0
MAX_DOUBLINGS = 16
UNREACHABLE_RETRY_SECONDS = 2.0
TOKEN_PREFIX = "local-task-oidc"

Transport = Callable[[str, bytes, dict[str, str], float], "tuple[int, str | None]"]


@dataclass(frozen=True)
class QueueSettings:
    """Retry and rate settings of one queue (``gcloud tasks queues describe``)."""

    max_attempts: int  # total deliveries; -1 is unlimited
    min_backoff: float
    max_backoff: float
    max_concurrent: int
    max_per_second: float

    def retry_delay(self, failed_attempts: int) -> float:
        doublings = min(max(failed_attempts - 1, 0), MAX_DOUBLINGS)
        return min(self.max_backoff, self.min_backoff * (2**doublings))


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class WorkerUnreachable(Exception):
    """Nothing is listening at the worker's address."""


def _http_post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, str | None]:
    import httpx

    # The stack's trust file when its services speak TLS (dev_harness.local_tls).
    verify: Any = os.environ.get(CA_BUNDLE_ENV, "").strip() or True
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), trust_env=False, verify=verify) as client:
        try:
            response = client.post(url, content=body, headers=headers)
        except httpx.ConnectError as error:
            raise WorkerUnreachable(str(error)) from error
        return response.status_code, response.headers.get("retry-after")


class LocalTaskQueue:
    """The ``tasks_v2.CloudTasksClient`` surface Sync uses, backed by SQLite."""

    def __init__(
        self,
        db_path: Path,
        queues: Mapping[str, QueueSettings],
        *,
        transport: Transport = _http_post,
        clock: Callable[[], float] = time.time,
        log: Callable[[str], None] | None = None,
        secret: str | None = None,
        owns_dispatch: bool = True,
    ):
        """Several processes use one queue: every service creates tasks and checks
        tokens with the shared ``secret``, one dispatcher (``owns_dispatch``) delivers."""
        self._queues = dict(queues)
        self._transport = transport
        self._clock = clock
        self._log = log or (lambda line: print(log_timestamps.line(line), flush=True))
        self._secret = secret or secrets.token_urlsafe(24)
        self._lock = threading.RLock()
        self._next_allowed: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool: ThreadPoolExecutor | None = None
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS task("
            " name TEXT PRIMARY KEY, queue TEXT NOT NULL, url TEXT NOT NULL, body BLOB NOT NULL,"
            " headers TEXT NOT NULL, audience TEXT NOT NULL, invoker TEXT NOT NULL, deadline REAL NOT NULL,"
            " eta REAL NOT NULL, created REAL NOT NULL, state TEXT NOT NULL, dispatches INTEGER NOT NULL DEFAULT 0,"
            " responses INTEGER NOT NULL DEFAULT 0, last_status TEXT, finished REAL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS due ON task(state, queue, eta)")
        if owns_dispatch:
            self._recover_interrupted()

    # ---- client surface -------------------------------------------------

    @staticmethod
    def queue_path(project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    @staticmethod
    def task_path(project: str, location: str, queue: str, task: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}/tasks/{task}"

    def _queue_of(self, parent: str) -> str:
        from google.api_core.exceptions import NotFound

        queue = parent.rsplit("/", 1)[-1]
        if "/queues/" not in parent or queue not in self._queues:
            raise NotFound(f"Queue does not exist: {parent}")
        return queue

    def get_queue(self, *, name: str, **_kwargs: Any) -> Any:
        from google.cloud import tasks_v2

        self._queue_of(name)
        return tasks_v2.Queue(name=name)

    def create_task(self, *, parent: str, task: Any, **_kwargs: Any) -> Any:
        from google.api_core.exceptions import AlreadyExists, InvalidArgument
        from google.cloud import tasks_v2

        if not isinstance(task, tasks_v2.Task):
            raise TypeError(f"expected tasks_v2.Task, got {type(task).__name__}")
        queue = self._queue_of(parent)
        raw = tasks_v2.Task.pb(task)
        request = raw.http_request
        parsed = urlparse(request.url)
        if (
            parsed.scheme not in ("http", "https")
            or not _is_loopback(parsed.hostname)
            or parsed.username
            or parsed.password
        ):
            # Local task bodies carry local user data; they are only ever
            # delivered to this machine.
            raise InvalidArgument("local task queue delivers to loopback targets only")
        if request.http_method != tasks_v2.HttpMethod.POST:
            raise InvalidArgument("local task queue delivers POST tasks only")
        if not request.oidc_token.audience or not request.oidc_token.service_account_email:
            raise InvalidArgument("local task queue requires an OIDC audience and service account")
        now = self._clock()
        name = raw.name or f"{parent}/tasks/{secrets.token_hex(16)}"
        if not name.startswith(f"{parent}/tasks/"):
            raise InvalidArgument("task name is outside its queue")
        eta = now
        if raw.HasField("schedule_time"):
            eta = max(now, raw.schedule_time.seconds + raw.schedule_time.nanos / 1e9)
        deadline = float(raw.dispatch_deadline.seconds) if raw.HasField("dispatch_deadline") else 600.0
        with self._lock:
            row = self._db.execute("SELECT state, finished FROM task WHERE name=?", (name,)).fetchone()
            if row is not None:
                live = row[0] in ("pending", "running")
                if live or now - float(row[1] or 0) < NAME_TOMBSTONE_SECONDS:
                    self._emit("deduplicated", queue, name)
                    raise AlreadyExists(f"task {name.rsplit('/', 1)[-1]} already exists")
                self._db.execute("DELETE FROM task WHERE name=?", (name,))
            try:
                self._db.execute(
                    "INSERT INTO task(name, queue, url, body, headers, audience, invoker, deadline, eta, created,"
                    " state) VALUES(?,?,?,?,?,?,?,?,?,?,'pending')",
                    (
                        name,
                        queue,
                        request.url,
                        bytes(request.body),
                        json.dumps(dict(request.headers)),
                        request.oidc_token.audience,
                        request.oidc_token.service_account_email,
                        deadline,
                        eta,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                # Another service process created the same name between the read and the insert.
                raise AlreadyExists(f"task {name.rsplit('/', 1)[-1]} already exists") from error
        self._emit("created", queue, name, eta_in=f"{max(0.0, eta - now):.0f}")
        return task

    def get_task(self, request: Any = None, *, name: str | None = None, **_kwargs: Any) -> Any:
        from google.api_core.exceptions import NotFound
        from google.cloud import tasks_v2

        task_name = name or getattr(request, "name", None) or (request or {}).get("name")
        with self._lock:
            row = self._db.execute("SELECT state FROM task WHERE name=?", (task_name,)).fetchone()
        if row is None or row[0] not in ("pending", "running"):
            raise NotFound(f"Task does not exist: {task_name}")
        return tasks_v2.Task(name=task_name)

    # ---- local identity -------------------------------------------------

    def token_for(self, audience: str, invoker: str) -> str:
        return f"{TOKEN_PREFIX}:{self._secret}:{audience}:{invoker}"

    def is_local_token(self, token: str) -> bool:
        return token.startswith(f"{TOKEN_PREFIX}:")

    def verify_token(self, token: str, audience: str | Iterable[str] | None) -> dict[str, Any]:
        """Claims for a token this process minted for one of ``audience``."""
        audiences = [audience] if isinstance(audience, str) else list(audience or [])
        for expected in audiences:
            prefix = f"{TOKEN_PREFIX}:{self._secret}:{expected}:"
            if expected and token.startswith(prefix) and len(token) > len(prefix):
                return {"aud": expected, "email": token[len(prefix) :], "email_verified": True}
        raise ValueError("local task queue token rejected")

    # ---- dispatch -------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        workers = sum(settings.max_concurrent for settings in self._queues.values())
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="local-task")
        self._thread = threading.Thread(target=self._run, name="local-task-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pool is not None:
            self._pool.shutdown(wait=False)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.dispatch_due()
            except Exception as error:  # noqa: BLE001 - the dispatcher must outlive one bad pass
                self._log(f"harness_task_queue event=dispatcher_error exception_type={type(error).__name__}")
            self._stop.wait(0.25)

    def dispatch_due(self) -> int:
        """Start every task that is due and within its queue's limits."""
        started = 0
        now = self._clock()
        for queue, settings in self._queues.items():
            interval = 1.0 / settings.max_per_second if settings.max_per_second > 0 else 0.0
            with self._lock:
                running = self._db.execute(
                    "SELECT COUNT(*) FROM task WHERE queue=? AND state='running'", (queue,)
                ).fetchone()[0]
                free = settings.max_concurrent - running
                if free <= 0:
                    continue
                rows = self._db.execute(
                    "SELECT name, url, body, headers, audience, invoker, deadline, eta, dispatches, responses"
                    " FROM task WHERE queue=? AND state='pending' AND eta<=? ORDER BY eta LIMIT ?",
                    (queue, now, free),
                ).fetchall()
                claimed = []
                for row in rows:
                    # Token bucket holding at most one second of dispatches.
                    allowed_at = max(self._next_allowed.get(queue, 0.0), now - 1.0)
                    if allowed_at > now:
                        break
                    self._next_allowed[queue] = allowed_at + interval
                    self._db.execute("UPDATE task SET state='running', dispatches=dispatches+1 WHERE name=?", (row[0],))
                    claimed.append(row)
            for row in claimed:
                started += 1
                if self._pool is not None:
                    self._pool.submit(self._deliver, queue, settings, row)
                else:
                    self._deliver(queue, settings, row)
        return started

    def _deliver(self, queue: str, settings: QueueSettings, row: tuple) -> None:
        name, url, body, headers_json, audience, invoker, deadline, eta, dispatches, responses = row
        headers = {
            **json.loads(headers_json),
            "Authorization": f"Bearer {self.token_for(audience, invoker)}",
            "User-Agent": "Google-Cloud-Tasks",
            "X-CloudTasks-QueueName": queue,
            "X-CloudTasks-TaskName": name.rsplit("/", 1)[-1],
            "X-CloudTasks-TaskRetryCount": str(dispatches),
            "X-CloudTasks-TaskExecutionCount": str(responses),
            "X-CloudTasks-TaskETA": f"{eta:.6f}",
        }
        started = time.monotonic()
        status: int | None = None
        retry_after: str | None = None
        outcome = "no_response"
        try:
            status, retry_after = self._transport(url, bytes(body), headers, float(deadline))
            outcome = str(status)
        except WorkerUnreachable:
            # Not a delivery: the task keeps its attempts and waits for the listener
            # (a service that is restarting). Other workers' tasks are unaffected.
            with self._lock:
                self._db.execute(
                    "UPDATE task SET state='pending', dispatches=dispatches-1, last_status='worker_unreachable',"
                    " eta=? WHERE name=?",
                    (self._clock() + UNREACHABLE_RETRY_SECONDS, name),
                )
            self._emit("worker_unreachable", queue, name)
            return
        except Exception as error:  # noqa: BLE001 - any transport failure is a failed delivery
            outcome = f"exception:{type(error).__name__}"
        elapsed_ms = int((time.monotonic() - started) * 1000)
        attempts = dispatches + 1
        now = self._clock()
        with self._lock:
            if status is not None and 200 <= status < 300:
                self._db.execute(
                    "UPDATE task SET state='done', responses=responses+1, last_status=?, finished=? WHERE name=?",
                    (outcome, now, name),
                )
                verdict = "delivered"
            elif settings.max_attempts != -1 and attempts >= settings.max_attempts:
                self._db.execute(
                    "UPDATE task SET state='dropped', responses=responses+?, last_status=?, finished=? WHERE name=?",
                    (0 if status is None else 1, outcome, now, name),
                )
                verdict = "attempts_exhausted"
            else:
                delay = settings.retry_delay(attempts)
                try:
                    delay = max(delay, float(retry_after)) if retry_after else delay
                except ValueError:
                    pass
                self._db.execute(
                    "UPDATE task SET state='pending', responses=responses+?, last_status=?, eta=? WHERE name=?",
                    (0 if status is None else 1, outcome, now + delay, name),
                )
                verdict = f"retry_in_{delay:.0f}s"
        self._emit(verdict, queue, name, status=outcome, attempt=str(attempts), ms=str(elapsed_ms))

    def _recover_interrupted(self) -> None:
        """A delivery cut off by a restart failed; it is retried like any other failure."""
        now = self._clock()
        with self._lock:
            rows = self._db.execute("SELECT name, queue, dispatches FROM task WHERE state='running'").fetchall()
            for name, queue, dispatches in rows:
                settings = self._queues.get(queue)
                if settings is None or (settings.max_attempts != -1 and dispatches >= settings.max_attempts):
                    self._db.execute(
                        "UPDATE task SET state='dropped', last_status='interrupted', finished=? WHERE name=?",
                        (now, name),
                    )
                    continue
                self._db.execute(
                    "UPDATE task SET state='pending', last_status='interrupted', eta=? WHERE name=?",
                    (now + settings.retry_delay(dispatches), name),
                )

    def counts(self) -> dict[str, dict[str, int]]:
        with self._lock:
            rows = self._db.execute("SELECT queue, state, COUNT(*) FROM task GROUP BY queue, state").fetchall()
        result: dict[str, dict[str, int]] = {}
        for queue, state, count in rows:
            result.setdefault(queue, {})[state] = count
        return result

    def _emit(self, event: str, queue: str, name: str, **fields: str) -> None:
        extra = "".join(f" {key}={value}" for key, value in fields.items())
        self._log(f"harness_task_queue event={event} queue={queue} task={name.rsplit('/', 1)[-1]}{extra}")


class _LocalFirstIdToken:
    """``google.oauth2.id_token`` for ``utils.cloud_tasks`` with the local token accepted first."""

    def __init__(self, google_id_token: Any, queue: LocalTaskQueue):
        self._google = google_id_token
        self._queue = queue

    def verify_oauth2_token(self, token: str, request: Any, audience: Any = None, **kwargs: Any) -> Any:
        if self._queue.is_local_token(token):
            return self._queue.verify_token(token, audience)
        return self._google.verify_oauth2_token(token, request, audience=audience, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._google, name)


def _accept_backfill_deliveries(env: Mapping[str, str]) -> None:
    """Let this stack's worker run the backfill tasks its own queue delivers.

    Outside the ``prod`` stage the worker acknowledges every backfill-lane task
    without running it (``uid_sequencer.foreign_delivery``): a dev deployment
    used to share queue and sequencer state with production, and a task from
    the other environment must not touch it. Here the queue, Redis and
    Firestore emulator all belong to this harness instance, so no delivery can
    be foreign, and leaving the guard on would admit an old upload (202) and
    then never process it. Refused unless Firestore is the emulator.
    """
    if not env.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise RuntimeError("the local task queue is for emulator-backed stacks only (FIRESTORE_EMULATOR_HOST is unset)")
    if env.get("OMI_ENV_STAGE", "").strip().lower() == "prod":
        return  # the production stage runs backfill deliveries itself; nothing to lift
    from utils.sync import uid_sequencer

    uid_sequencer.foreign_delivery = lambda _payload: False


# ---- one queue shared by every service of a prod-parity stack ----------

SECRET_ENV = "OMI_HARNESS_TASK_QUEUE_SECRET"
SETTINGS_ENV = "OMI_HARNESS_TASK_QUEUE_SETTINGS"
# Queues production creates outside backend/deploy/ops/prod.yaml; settings from
# backend/deploy/staging/create_queues.sh (name: concurrent, per-second, attempts, min, max backoff).
_QUEUES_OUTSIDE_OPS = {
    "conversation-finalization": (16, 10.0, 5, 5.0, 60.0),
    "audio-merge": (16, 10.0, 5, 5.0, 60.0),
    "account-deletion": (4, 4.0, 5, 5.0, 300.0),
    "conversation-erasure": (20, 5.0, 5, 5.0, 300.0),
}


def _seconds(value: object) -> float:
    return float(str(value).rstrip("s"))


def live_queue_settings(live: Mapping[str, Mapping[str, Any]], concurrency_cap: int) -> dict[str, QueueSettings]:
    """Queue settings read from the running Cloud Tasks queues (a production snapshot)."""
    queues: dict[str, QueueSettings] = {}
    for name, spec in live.items():
        rate, retry = spec.get("rate_limits") or {}, spec.get("retry_config") or {}
        queues[name] = QueueSettings(
            int(retry.get("maxAttempts", -1)),
            _seconds(retry.get("minBackoff", "5s")),
            _seconds(retry.get("maxBackoff", "60s")),
            min(int(rate.get("maxConcurrentDispatches", concurrency_cap)), concurrency_cap),
            float(rate.get("maxDispatchesPerSecond", 10)),
        )
    return queues


def production_queue_settings(
    repo_root: Path, concurrency_cap: int, live: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, QueueSettings]:
    """Every production queue with its ops-owned retry contract.

    Concurrency is production's value capped for one machine; attempts, backoff
    and rate are production's. With a production snapshot the running queues
    are the source and the deploy files are not read.
    """
    if live:
        return live_queue_settings(live, concurrency_cap)
    import yaml

    ops = yaml.safe_load((repo_root / "backend" / "deploy" / "ops" / "prod.yaml").read_text())["cloud_tasks"]
    queues: dict[str, QueueSettings] = {}
    for name, spec in ops.items():
        queues[name] = QueueSettings(
            int(spec.get("max_attempts", -1)),
            _seconds(spec.get("min_backoff", "5s")),
            _seconds(spec.get("max_backoff", "60s")),
            min(int(spec.get("max_concurrent_dispatches", concurrency_cap)), concurrency_cap),
            float(spec.get("max_dispatches_per_second", 10)),
        )
    for name, (concurrent, rate, attempts, low, high) in _QUEUES_OUTSIDE_OPS.items():
        queues.setdefault(name, QueueSettings(attempts, low, high, min(concurrent, concurrency_cap), rate))
    return queues


def encode_settings(queues: Mapping[str, QueueSettings]) -> str:
    return json.dumps(
        {
            name: [q.max_attempts, q.min_backoff, q.max_backoff, q.max_concurrent, q.max_per_second]
            for name, q in queues.items()
        }
    )


def _shared_queue(env: Mapping[str, str], *, owns_dispatch: bool) -> LocalTaskQueue:
    db_path, secret, raw = (env.get(name, "").strip() for name in (DB_ENV, SECRET_ENV, SETTINGS_ENV))
    if not (db_path and secret and raw):
        raise RuntimeError(f"a shared task queue needs {DB_ENV}, {SECRET_ENV} and {SETTINGS_ENV}")
    queues = {
        name: QueueSettings(int(v[0]), float(v[1]), float(v[2]), int(v[3]), float(v[4]))
        for name, v in json.loads(raw).items()
    }
    return LocalTaskQueue(Path(db_path), queues, secret=secret, owns_dispatch=owns_dispatch)


def install_client(env: Mapping[str, str] | None = None) -> LocalTaskQueue:
    """Give one service process the shared queue: it creates tasks and checks tokens, it never delivers."""
    source = os.environ if env is None else env
    import utils.cloud_tasks as production

    queue = _shared_queue(source, owns_dispatch=False)
    production._tasks_client = queue
    production.id_token = _LocalFirstIdToken(production.id_token, queue)
    _accept_backfill_deliveries(source)
    print("harness_task_queue event=client_installed", flush=True)
    return queue


def dispatcher_main() -> int:
    """The shared queue's only dispatcher (``python -m dev_harness.local_task_queue``)."""
    import signal

    queue = _shared_queue(os.environ, owns_dispatch=True)
    queue.start()
    print(f"harness_task_queue event=dispatcher_started queues={len(queue._queues)}", flush=True)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_args: stop.set())
    stop.wait()
    queue.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(dispatcher_main())
