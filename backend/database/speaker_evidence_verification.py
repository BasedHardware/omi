"""Short-lived coordination for one separately authorized speaker evidence exercise."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
import time
from typing import Any

from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError
from google.cloud.firestore_v1 import DELETE_FIELD, Client, DocumentReference, DocumentSnapshot

from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from utils.observability import speaker_evidence_erasure as metrics

TASK_FIELD = 'speaker_evidence_verification'
COLLECTION = 'speaker_evidence_verification_runs'
MAX_LIFETIME = timedelta(minutes=10)
WRITER_WAIT_SECONDS = 15
RPC_TIMEOUT = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Run:
    uid: str
    token: str
    ref: DocumentReference

    def read(self) -> tuple[DocumentSnapshot, dict[str, Any]]:
        snapshot = self.ref.get(retry=None, timeout=RPC_TIMEOUT)
        data = snapshot.to_dict() or {}
        expiry = data.get('expires_at')
        now = _now()
        if (
            snapshot.create_time is None
            or not isinstance(expiry, datetime)
            or expiry.tzinfo is None
            or not now < expiry <= snapshot.create_time + MAX_LIFETIME
            or data.get('account_hash') != _digest(self.uid)
        ):
            return snapshot, {}
        return snapshot, data

    def change(self, allowed: Callable[[dict[str, Any]], bool], **fields: Any) -> datetime | None:
        for _ in range(3):
            snapshot, data = self.read()
            if not data or not allowed(data):
                return None
            try:
                return self.update(snapshot, **fields).update_time
            except FailedPrecondition:
                # The writer and dispatcher both update this document.
                continue
        return None

    def update(self, snapshot: DocumentSnapshot, **fields: Any) -> Any:
        # An expired, deleted or superseded snapshot cannot be used to claim a
        # second writer, attach a new task, or publish a duplicate completion.
        assert snapshot.update_time is not None
        return self.ref.update(
            fields,
            option=Client.write_option(last_update_time=snapshot.update_time),
            retry=None,
            timeout=RPC_TIMEOUT,
        )


def enabled_for(uid: str) -> bool:
    authorized = os.getenv('SPEAKER_EVIDENCE_VERIFY_UID_SHA256')
    return bool(
        uid
        and authorized
        and _digest(uid) == authorized
        and re.fullmatch(r'[0-9a-f]{64}', os.getenv('SPEAKER_EVIDENCE_VERIFY_TOKEN', ''))
        and metrics.has_executor_revision()
    )


def _run(uid: str, client: Client | None = None) -> Run | None:
    if not enabled_for(uid):
        return None
    token = os.environ['SPEAKER_EVIDENCE_VERIFY_TOKEN']
    plane = account_deletion_firestore_client(firestore_client=client)
    return Run(uid, token, plane.collection(COLLECTION).document(_digest(token)))


def wait_for_deletion_marker(uid: str, client: Client) -> Run | None:
    """Claim once immediately before the evidence transaction and wait for a committed marker."""
    run = _run(uid, client)
    if run is None:
        return None
    try:
        _, data = run.read()
        if not data or 'writer' in data:
            return None
        marker = account_deletion_document(uid, firestore_client=client)
        if marker.get(retry=None, timeout=RPC_TIMEOUT).exists:
            return None
        deadline = time.monotonic() + WRITER_WAIT_SECONDS
        end = min(data['expires_at'], _now() + timedelta(seconds=WRITER_WAIT_SECONDS))

        def remaining() -> float:
            return min(deadline - time.monotonic(), (end - _now()).total_seconds())

        waiting = run.change(lambda state: 'writer' not in state and remaining() > 0, writer='waiting', wait_until=end)
        if waiting is None:
            return None
    except GoogleAPICallError:
        # No confirmed claim. Keep the ordinary writer and its marker fence.
        return None
    metrics.verification('writer_waiting')

    while (budget := remaining()) > 0:
        try:
            observed = marker.get(retry=None, timeout=min(RPC_TIMEOUT, budget))
            job_id = (observed.to_dict() or {}).get('wipe_job_id')
            if observed.create_time and observed.create_time > waiting and isinstance(job_id, str) and job_id:
                if run.change(
                    lambda state: state.get('writer') == 'waiting' and remaining() > 0,
                    writer='released',
                    marker_job=_digest(job_id),
                ):
                    metrics.verification('writer_released')
                    return run
        except GoogleAPICallError:
            pass
        time.sleep(max(0, min(0.1, remaining())))

    record_writer_result(run, 'timed_out')
    raise TimeoutError('speaker evidence verification writer timed out')


def record_writer_result(run: Run | None, outcome: str) -> None:
    if run is None:
        return
    metrics.verification(f'writer_{outcome}')
    try:
        expected = 'waiting' if outcome == 'timed_out' else 'released'
        run.change(lambda state: state.get('writer') == expected, writer=outcome)
    except GoogleAPICallError:
        # Missing coordination evidence is inconclusive; preserve the original writer result.
        pass


@dataclass(frozen=True)
class Task:
    run: Run
    job: str
    name: str


def reserve_task(uid: str, job_id: str, queue_path: str, task_id: str) -> Task | None:
    if not queue_path:
        return None
    try:
        run = _run(uid)
        if run is None:
            return None
        task = Task(run, _digest(job_id), f'{queue_path}/tasks/{task_id}')
        if run.change(
            lambda state: 'task' not in state,
            task=task.name,
            job=task.job,
            dispatch='pending',
            confirm_until=_now() + timedelta(seconds=10),
        ):
            return task
        return None
    except GoogleAPICallError:
        return None


def confirm_enqueue(task: Task) -> None:
    """Called only when the Cloud Tasks create operation acknowledged a new task."""
    try:
        if task.run.change(
            lambda state: state.get('task') == task.name and state.get('dispatch') == 'pending', dispatch='enqueued'
        ):
            metrics.verification('task_enqueued')
    except GoogleAPICallError:
        pass


@dataclass
class SweepReceipt:
    task: Task
    writer_refused_before_sweep: bool
    checked: bool = False


def admit_task(
    uid: str,
    job_id: str,
    token: object,
    queue_path: str,
    queue_header: str,
    task_header: str,
    retry_count: int,
) -> tuple[bool, SweepReceipt | None]:
    """Called after OIDC and job resolution. Return whether this delivery should retry."""
    if (
        not token
        or token != os.getenv('SPEAKER_EVIDENCE_VERIFY_TOKEN')
        or not queue_path
        or queue_header != queue_path.rsplit('/', 1)[-1]
        or not task_header
        or '/' in task_header
        or os.getenv('K_SERVICE') != os.getenv('SPEAKER_EVIDENCE_VERIFY_SYNC_SERVICE', 'backend-sync')
    ):
        return False, None

    try:
        run = _run(uid)
        if run is None:
            return False, None
        _, data = run.read()
    except GoogleAPICallError:
        return False, None
    task = Task(run, _digest(job_id), f'{queue_path}/tasks/{task_header}')
    if data.get('task') != task.name or data.get('job') != task.job:
        return False, None
    deadline = data.get('wait_until')
    writer_pending = (
        data.get('writer') in ('waiting', 'released') and isinstance(deadline, datetime) and _now() < deadline
    )
    # A dispatch may race the CreateTask acknowledgement. Retry while the
    # receipt is pending, or while the one admitted writer is still in flight.
    dispatch = data.get('dispatch')
    confirm_until = data.get('confirm_until')
    awaiting_ack = dispatch == 'pending' and isinstance(confirm_until, datetime) and _now() < confirm_until
    if awaiting_ack or (dispatch == 'enqueued' and writer_pending):
        metrics.verification('task_deferred')
        return True, None
    if dispatch != 'enqueued':
        return False, None
    metrics.verification('task_admitted')
    if retry_count > 0:
        metrics.verification('task_admitted_retry')
    sequenced = data.get('writer') == 'refused_marker_present' and data.get('marker_job') == task.job
    return False, SweepReceipt(task, sequenced)


_sweep: ContextVar[SweepReceipt | None] = ContextVar('speaker_evidence_verification_sweep', default=None)


@contextmanager
def observe_sweep(receipt: SweepReceipt | None) -> Iterator[None]:
    context = _sweep.set(receipt)
    try:
        yield
    finally:
        _sweep.reset(context)


def record_checked_sweep(uid: str) -> None:
    receipt = _sweep.get()
    if receipt is not None and receipt.task.run.uid == uid:
        receipt.checked = True


def complete_task(receipt: SweepReceipt) -> None:
    """Credit the same admitted execution only after its checked sweep and full wipe succeeded."""
    if not receipt.checked:
        return
    task = receipt.task
    try:
        completed = task.run.change(
            lambda state: state.get('task') == task.name
            and state.get('job') == task.job
            and state.get('dispatch') == 'enqueued',
            dispatch='completed',
            executor_revision=metrics.revision(),
            task=DELETE_FIELD,
            job=DELETE_FIELD,
            marker_job=DELETE_FIELD,
            confirm_until=DELETE_FIELD,
            wait_until=DELETE_FIELD,
        )
        if completed is None:
            return
        metrics.verification('task_completed_checked_zero_remaining')
        if receipt.writer_refused_before_sweep:
            metrics.verification('task_completed_after_writer_refusal')
    except GoogleAPICallError:
        pass
