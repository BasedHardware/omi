"""Durable, trailing-edge enrichment outbox (moved from ``utils/sync/reprocess.py``, plan C2).

Only IDs and scheduling metadata live here. A deterministic task name survives a
lost enqueue acknowledgement. The existing sequencer sweep repairs missing or
exhausted tasks in bounded batches, including a crash between mark and enqueue.
"""

from __future__ import annotations

import hashlib
import math
import logging
import os
import random
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from collections.abc import Iterator
from typing import Any, Callable, Literal, TypeVar, TypeAlias, TypeGuard
from urllib.parse import urlsplit
from time import monotonic

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from prometheus_client import Counter

from utils.conversations import summary_delivery
from config.summary_guarantee import (
    ADMITTED_OWNER,
    deadline_seconds,
    enabled as summary_enabled,
    first_summary_pending,
    preserves_admitted,
)
from config.policy import FirstSummaryPolicy, resolve_stage_policy
from config.sync_reprocess import settle_seconds
from config.repeat_work import revision_reuse
from database._client import get_firestore_client
from database.summary_processing import record_empty_failure, EMPTY_BLOCKED_REASON

Row: TypeAlias = dict[str, Any]
ResultT = TypeVar('ResultT')

logger = logging.getLogger(__name__)

COLLECTION = 'sync_reprocess_outbox'
LEASE_SECONDS = 1800  # Greater than the Cloud Tasks dispatch deadline.
FIRST_SUMMARY_LEASE_SECONDS = 120
FIRST_SUMMARY_HEARTBEAT_SECONDS = 30
REPAIR_SECONDS = 1800
WAKE_CHECK_SECONDS = 300
LIVE_DEFER_SECONDS = 120
# Both bindings stay valid so rows created before the C3 switch drain on their stored handler.
HANDLER_PATHS = ('/v2/sync-jobs/run', '/v2/enrichment/run')
COALESCED = Counter('sync_reprocess_coalesced_total', 'Sync updates folded into an existing enrichment obligation')
UNBOUND = Counter('sync_reprocess_unbound_total', 'Sync obligations awaiting a complete worker binding', ['action'])
# A conversation row at Firestore's 1 MiB ceiling refuses every enrichment write (#23341).
HELD_DOCUMENT_SIZE_LIMIT = 'document_size_limit'


def _is_document_size_limit(error: BaseException) -> bool:
    # Imported at the call: unit suites stub database._client without this predicate.
    from database._client import is_document_size_limit_error

    return is_document_size_limit_error(error)


class FirstSummaryCallbackPending(RuntimeError):
    """No processing output exists yet; retain the lease/debt without empty-result spend."""


def key(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()


def owns_runtime() -> bool:
    from utils.sync.stage import production_stage

    return bool(os.getenv('FIRESTORE_EMULATOR_HOST')) or production_stage()


def _mutate(document_id: str, operation: Callable[[Row | None], tuple[Row | None, ResultT]]) -> ResultT:
    if not owns_runtime():
        raise RuntimeError('sync reprocess outbox requires production or a Firestore emulator')
    return _cas(get_firestore_client(), document_id, operation)


def _cas(client: Any, document_id: str, operation: Callable[[Row | None], tuple[Row | None, ResultT]]) -> ResultT:
    ref = client.collection(COLLECTION).document(document_id)

    # All state for one obligation is in one document. Optimistic conditional
    # writes avoid read-lock upgrade deadlocks under simultaneous appends while
    # fencing claims, extension and completion against the exact read revision.
    for attempt in range(10):
        snapshot = ref.get()
        old = snapshot.to_dict() if snapshot.exists else None
        new, result = operation(old)
        if new == old:
            return result
        try:
            if old is None:
                ref.create(new)
            else:
                fence = firestore.LastUpdateOption(snapshot.update_time)
                if new is None:
                    ref.delete(option=fence)
                else:
                    ref.update(new, option=fence)
            return result
        except (AlreadyExists, FailedPrecondition, NotFound):
            if attempt == 9:
                raise
            time.sleep(random.uniform(0.005, min(0.2, 0.01 * 2**attempt)))
    raise AssertionError('outbox CAS loop must return or raise within its retry budget')


def mutate_row(
    document_id: str, operation: Callable[[Row | None], tuple[Row | None, ResultT]], *, client: Any = None
) -> ResultT:
    """Public CAS entry for ``database.outbox_firestore``; resolves ``_mutate`` per call unless bound to a client."""
    if client is not None:
        return _cas(client, document_id, operation)
    return _mutate(document_id, operation)


def wake_row(row: Row) -> None:
    """Public wake entry for ``database.outbox_firestore``; resolves ``_enqueue`` per call."""
    _enqueue(row)


def valid_dispatch_binding(dispatch: object) -> TypeGuard[dict[str, str]]:
    """A binding belongs to the receiving sync handler, including its audience."""
    if not isinstance(dispatch, dict):
        return False
    for field in ('queue', 'handler', 'audience', 'invoker_sa'):
        value = dispatch.get(field)
        if not isinstance(value, str) or not value or value != value.strip():
            return False
    try:
        url = urlsplit(dispatch['handler'])
    except ValueError:
        return False
    return (
        url.scheme == 'https'
        and bool(url.netloc)
        and url.path.endswith(HANDLER_PATHS)
        and not url.query
        and not url.fragment
        and dispatch['audience'] == dispatch['handler']
    )


def valid_effects_binding(row: dict[str, Any]) -> bool:
    dispatch = row.get('dispatch')
    if valid_dispatch_binding(dispatch):
        return True
    if not row.get('effects_only') or not isinstance(dispatch, dict):
        return False
    if not all(
        isinstance(dispatch.get(field), str) and dispatch[field].strip() == dispatch[field] and dispatch[field]
        for field in ('queue', 'handler', 'audience', 'invoker_sa')
    ):
        return False
    try:
        handler, audience = urlsplit(dispatch['handler']), urlsplit(dispatch['audience'])
        return (
            handler.scheme == audience.scheme == 'https'
            and bool(handler.netloc)
            and handler.netloc == audience.netloc
            and not handler.query
            and not handler.fragment
            and handler.path.endswith('/v1/conversation-finalization-jobs/run')
            and audience.path in ('', '/', handler.path)
            and not audience.query
            and not audience.fragment
        )
    except ValueError:
        return False


def _dispatch_binding() -> dict[str, str] | None:
    from config import enrichment as enrichment_config

    if enrichment_config.route() == 'enrichment_queue':
        binding = enrichment_config.dispatch_binding()
        if valid_dispatch_binding(binding):
            return binding
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='sync_dispatch',
            from_mode='enrichment_queue',
            to_mode='sync_handler',
            reason='config_incomplete',
            outcome='degraded',
            log=logger,
        )
    handler = os.getenv('SYNC_TASKS_HANDLER_URL', '')
    binding = {
        'queue': os.getenv('SYNC_TASKS_QUEUE', ''),
        'handler': handler,
        'audience': os.getenv('SYNC_TASKS_OIDC_AUDIENCE') or handler,
        'invoker_sa': os.getenv('SYNC_TASKS_INVOKER_SA', ''),
    }
    return binding if valid_dispatch_binding(binding) else None


def _task_name(row: Row) -> str:
    document_id = row.get('document_id') or key(row['uid'], row['conversation_id'])
    name = f"sr-{document_id}-{row['task_token']}"
    if row.get('wake_generation'):
        name += f"-repair-{row['wake_generation']}"
    return name


def _wake_exists(row: Row) -> bool:
    from utils.cloud_tasks import named_task_exists

    return named_task_exists(row['dispatch']['queue'], _task_name(row))


def _enqueue(row: dict[str, Any]) -> None:
    from utils.cloud_tasks import enqueue_named_task

    # A backfill obligation is repaired by the fresh service's sweep. Retain
    # the originating queue/worker/identity rather than borrowing that sweep's
    # fresh capacity or audience. These bindings contain no credentials.
    dispatch = row.get('dispatch')
    if not valid_effects_binding(row):
        raise RuntimeError('sync reprocessing requires a complete worker binding')
    assert isinstance(dispatch, dict)
    handler = dispatch['handler']
    if not (
        handler.endswith(HANDLER_PATHS)
        or row.get('effects_only')
        and handler.endswith('/v1/conversation-finalization-jobs/run')
    ):
        raise RuntimeError('sync reprocessing requires the sync worker handler binding')
    from utils.conversations.demand_processing import schedule

    document_id = row.get('document_id') or key(row['uid'], row['conversation_id'])
    payload = {'kind': 'sync_reprocess', 'key': document_id, 'task_token': row['task_token']}
    name = _task_name(row)

    first_summary = first_summary_pending(row)
    if not first_summary and schedule(
        row['uid'],
        document_id,
        payload,
        dispatch,
        name,
        not_before=row['due_at'],
        effects_only=bool(row.get('effects_only')),
        immediate=bool(row.get('immediate')),
    ):
        return
    from config.demand_processing import enabled

    eager_recovery = bool(row.get('effects_only')) and enabled(row['uid'])
    enqueue_named_task(
        dispatch['queue'],
        handler,
        name,
        payload,
        audience=dispatch['audience'],
        invoker_sa=dispatch['invoker_sa'],
        schedule_at=math.ceil(time.time() if eager_recovery else row['due_at']),
    )


def mark(
    uid: str,
    conversation_id: str,
    language: str,
    *,
    now: float | None = None,
    mutate: Callable | None = None,
    effects_only: bool = False,
    snapshot_summary: bool = False,
) -> None:
    """Record one enrichment obligation.

    Projection may inject a transactional mutation to commit its replay receipt
    and privacy fences with this obligation. The default retains the normal
    CAS path; both paths enqueue only after durable persistence.
    """
    if mutate is not None and not owns_runtime():
        raise RuntimeError('sync reprocess projection requires production or a Firestore emulator')
    current = time.time() if now is None else now
    stamps: list[tuple[str, str]] = []
    update = mark_update(
        uid,
        conversation_id,
        language,
        current=current,
        settle_at=current + settle_seconds(),
        coalesce='max',
        effects_only=effects_only,
        batch=mutate is not None,
        snapshot_summary=snapshot_summary,
        stamps=stamps,
    )
    document_id = key(uid, conversation_id + ('\0effects' if effects_only else ''))
    row, coalesced = (mutate or _mutate)(document_id, update)
    record_summary_stamps(stamps)
    if coalesced:
        COALESCED.inc()
    if row.get('_wake', not coalesced) and valid_dispatch_binding(row.get('dispatch')):
        _enqueue(row)  # Failure leaves the obligation durable for the sweep.
    elif not valid_dispatch_binding(row.get('dispatch')):
        UNBOUND.labels(action='mark').inc()


def mark_update(
    uid: str,
    conversation_id: str,
    language: str,
    *,
    current: float,
    settle_at: float,
    coalesce: Literal['min', 'max'],
    effects_only: bool,
    batch: bool,
    policy_id: str | None = None,
    new_dispatch: Callable[[], dict[str, str] | None] | None = None,
    snapshot_summary: bool = False,
    stamps: list[tuple[str, str]] | None = None,
) -> Callable[[Row | None], tuple[Row, tuple[Row, bool]]]:
    """The CAS operation behind ``mark`` and ``Outbox.enqueue``: one obligation per key, coalesced.

    ``settle_at`` is the requested wake; an open row keeps the later (``max``, settle) or the earlier
    (``min``, deadline) of the two. ``new_dispatch`` may supply a new row's binding (backfill); it is
    called only when no row exists, so a coalesced append never re-resolves it.

    ``snapshot_summary`` (E1) records the first-summary policy on a new or reopened obligation, or on an
    open one that predates snapshots; ``stamps`` collects ``(source, policy_id)`` for telemetry after commit.
    """
    candidate: FirstSummaryPolicy | None = None

    def update(old: Row | None) -> tuple[Row, tuple[Row, bool]]:
        nonlocal candidate
        if stamps is not None:
            stamps.clear()  # A CAS or transaction retry re-runs this operation.
        if old and old.get('summary_blocked_reason') == EMPTY_BLOCKED_REASON:
            return old, ({**old, '_wake': False}, True)
        row = dict(old or {})
        row.pop('_wake', None)  # Dispatch intent belongs to this CAS result, not its persisted replay.
        row.update(
            document_id=key(uid, conversation_id + ('\0effects' if effects_only else '')),
            uid=uid,
            conversation_id=conversation_id,
            language=language,
            version=row.get('version', 0) + 1,
            due_at=(
                max(row.get('due_at') or 0, settle_at)
                if coalesce == 'max'
                else min(row.get('due_at') or float('inf'), settle_at)
            ),
        )
        if policy_id is not None:
            row['policy_id'] = policy_id
        # Timestamp every durable obligation, even before rollout. Neither an
        # append nor a retry owns the original acceptance time.
        row['first_pending_at'] = current if old and old.get('dormant') else row.get('first_pending_at', current)
        if snapshot_summary and (not old or old.get('dormant') or row.get('first_summary_policy') is None):
            if candidate is None:
                candidate = resolve_stage_policy(
                    uid, 'first_summary', obligation=old if old and not old.get('dormant') else None
                )
            row['first_summary_policy'] = candidate.to_dict()
            row['first_summary_policy_source'] = 'creation' if not old or old.get('dormant') else 'fallback'
            if stamps is not None:
                stamps.append((row['first_summary_policy_source'], candidate.policy_id))
        row['dormant'] = False
        row['summary_repair'] = False
        row['effects_only'] = effects_only

        if first_summary_pending(row):
            row['summary_deadline_at'] = min(
                row.get('summary_deadline_at', float('inf')),
                row['first_pending_at'] + _deadline_seconds(row),
            )
            row['due_at'] = min(row['due_at'], row['summary_deadline_at'])
        from config.demand_processing import enabled

        demand_enabled = enabled(uid)
        if demand_enabled or revision_reuse():
            # Keep demand's processing headroom when both policies are enabled;
            # revision reuse alone retains its upstream one-hour ceiling.
            row['first_pending_at'] = row.get('first_pending_at', current)
            ceiling = 3540 if demand_enabled else 3600
            row['due_at'] = min(row['due_at'], row['first_pending_at'] + ceiling)

        row.setdefault('summary_lane', 'batch' if batch else summary_delivery.lane({}))
        if old is None:
            row.update(
                task_token=uuid.uuid4().hex,
                task_due_at=row['due_at'],
                lease_until=0,
                dispatch=(new_dispatch() if new_dispatch else None) or _dispatch_binding(),
            )
        elif old.get('dormant'):
            row['dispatch'] = _dispatch_binding()
        elif not valid_dispatch_binding(row.get('dispatch')):
            row['dispatch'] = None
        wake = old is None
        if old is not None and (old.get('dormant') or (row.get('task_due_at') or 0) > row['due_at']):
            row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
            wake = True
        return row, ({**row, '_wake': wake}, old is not None)

    return update


def _deadline_seconds(row: Row) -> int:
    snapshot = row.get('first_summary_policy')
    if snapshot is not None:
        return FirstSummaryPolicy.from_dict(snapshot).first_summary_deadline_seconds
    return deadline_seconds()


def summary_policy_for(row: Row) -> bool:
    """E1: a snapshotted obligation decides first summary once; older rows read the live flags."""
    snapshot = row.get('first_summary_policy')
    if snapshot is not None:
        return FirstSummaryPolicy.from_dict(snapshot).first_summary_enabled
    return summary_enabled(row['uid'], include_admitted_context=False) or preserves_admitted(row)


def stamp_claim_policy(row: Row, cache: dict[str, FirstSummaryPolicy], stamps: list[tuple[str, str]]) -> None:
    """E1: a batch obligation claimed without a snapshot gets a deterministic fallback one."""
    if row.get('summary_lane') != 'batch' or row.get('first_summary_policy') is not None:
        return
    if 'candidate' not in cache:
        cache['candidate'] = resolve_stage_policy(row['uid'], 'first_summary', obligation=row)
    candidate = cache['candidate']
    row['first_summary_policy'] = candidate.to_dict()
    row['first_summary_policy_source'] = 'fallback'
    stamps.append(('fallback', candidate.policy_id))


def record_summary_stamps(stamps: list[tuple[str, str]]) -> None:
    from config.policy.telemetry import record_policy_source

    for source, policy_id in stamps:
        record_policy_source('fallback' if source == 'fallback' else 'stage', policy_id)


@contextmanager
def _heartbeat(document_id: str, task_token: str, owner: str, context: Row) -> Iterator[None]:
    """Renew only this request's owner/token, stopping when the request exits.

    This scoped daemon does only a bounded CAS heartbeat, never model work.
    A lost owner cannot resurrect its lease; an in-flight RPC on shutdown also
    checks the stop event inside its CAS before writing.
    """
    stopped = threading.Event()

    def renew() -> None:
        while not stopped.wait(FIRST_SUMMARY_HEARTBEAT_SECONDS):

            def update(old: Row | None) -> tuple[Row | None, bool]:
                if (
                    stopped.is_set()
                    or old is None
                    or old.get('dormant')
                    or old.get('owner') != owner
                    or old.get('task_token') != task_token
                ):
                    return old, False
                expiry = time.time() + FIRST_SUMMARY_LEASE_SECONDS
                context['lease_until'] = expiry
                return {**old, 'lease_until': expiry}, True

            try:
                if not _mutate(document_id, update):
                    return
            except Exception as error:
                logger.warning('event=summary_heartbeat outcome=error exception_type=%s', type(error).__name__)

    worker = threading.Thread(target=renew, name='first-summary-heartbeat', daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join(timeout=2)


def run(document_id: str, task_token: str, process: Callable[[str, str, str], Any], *, now: float | None = None) -> str:
    current = time.time() if now is None else now
    from utils.conversations.demand_processing import admit
    from config.demand_processing import enabled

    if not admit(document_id, now=current, token=task_token):
        return 'priority_wait'
    owner = uuid.uuid4().hex
    cache: dict[str, FirstSummaryPolicy] = {}
    stamps: list[tuple[str, str]] = []

    def claim(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
        stamps.clear()
        if old is None or old.get('dormant') or old['task_token'] != task_token:
            return old, ('stale', None)
        if old.get('lease_until', 0) > current:
            return old, ('busy', None)
        row = dict(old)
        stamp_claim_policy(row, cache, stamps)
        if row['due_at'] > current and (not row.get('effects_only') or not enabled(row['uid'])):
            row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
            return row, ('deferred', row)

        first_summary = first_summary_pending(row)
        lease_seconds = FIRST_SUMMARY_LEASE_SECONDS if first_summary else LEASE_SECONDS
        row.update(lease_until=current + lease_seconds, owner=owner)
        return row, ('claimed', row)

    status, row = _mutate(document_id, claim)
    record_summary_stamps(stamps)
    if status == 'deferred':
        assert row is not None
        _enqueue(row)
        return status
    if status != 'claimed':
        return status
    assert row is not None
    # Exceptions leave a leased, dirty row. Retry/sweep recovers after expiry.
    summary_policy = summary_policy_for(row)
    summary_seen = False
    superseded = False
    retry_revision = None
    empty_blocked = False
    held_reason: str | None = None
    process_context = None
    if row.get('effects_only'):
        from utils.conversations.lazy_enrichment import enrich_settled

        try:
            enrich_settled(row['uid'], row['conversation_id'], row['language'])
        except InvalidArgument as error:
            if not _is_document_size_limit(error):
                raise
            held_reason = HELD_DOCUMENT_SIZE_LIMIT
    else:

        lane_token = summary_delivery.LANE_CONTEXT.set(
            row.get('summary_lane')
            or (
                'backfill' if (row.get('dispatch') or {}).get('queue') == 'sync-backfill' else summary_delivery.lane({})
            )
        )
        process_context = (
            {'owner': owner, 'lease_until': row['lease_until']}
            if summary_policy and not row.get('summary_seen')
            else None
        )
        process_token = summary_delivery.PROCESS_CONTEXT.set(process_context)
        accept_token = summary_delivery.ACCEPT_CONTEXT.set(row.get('first_pending_at'))
        context_token = summary_delivery.REPAIR_CONTEXT.set(row if row.get('summary_repair') else None)
        admitted_token = ADMITTED_OWNER.set(row['uid'] if preserves_admitted(row) else None)
        try:
            with _heartbeat(document_id, task_token, owner, process_context) if process_context else nullcontext():
                output = process(row['uid'], row['conversation_id'], row['language'])
                if summary_policy:
                    summary_seen = output is not None and summary_delivery.present(
                        summary_delivery.field(output, 'structured')
                    )
                    discarded = (output is not None and summary_delivery.field(output, 'discarded', False)) or (
                        preserves_admitted(row) and bool(process_context and process_context.get('discarded'))
                    )
                    blocked = bool(process_context and process_context.get('blocked_reason'))
                    custody = bool(
                        process_context and (process_context.get('redirect_to') or process_context.get('defer_reason'))
                    )
                    if output is None and preserves_admitted(row) and not discarded and not blocked and not custody:
                        raise FirstSummaryCallbackPending('first-summary callback has no output yet')
                    if output is not None and not summary_seen and not discarded and not blocked:
                        raise summary_delivery.SummaryOutputUnavailable('first-summary output is empty')
        except summary_delivery.SummaryRepairSuperseded as error:
            output = None
            superseded = True
            retry_revision = error.retry_revision
        except InvalidArgument as error:
            if not _is_document_size_limit(error):
                raise
            held_reason = HELD_DOCUMENT_SIZE_LIMIT
        except summary_delivery.SummaryOutputUnavailable:
            if not process_context or not record_empty_failure(
                get_firestore_client(), COLLECTION, document_id, owner, task_token
            ):
                raise
            empty_blocked = True
        finally:
            ADMITTED_OWNER.reset(admitted_token)
            summary_delivery.REPAIR_CONTEXT.reset(context_token)
            summary_delivery.LANE_CONTEXT.reset(lane_token)
            summary_delivery.ACCEPT_CONTEXT.reset(accept_token)
            summary_delivery.PROCESS_CONTEXT.reset(process_token)

    if empty_blocked:
        return 'blocked'

    if held_reason is not None:
        # No retry of the same write can ever land, so the obligation is held
        # dormant with its reason instead of re-woken on every sweep. The
        # conversation is not touched: the content stays, only the enrichment
        # debt is parked until something shrinks the row.

        def hold(old: Row | None) -> tuple[Row | None, None]:
            if old is None or old.get('owner') != owner or old.get('task_token') != task_token:
                return old, None
            parked = dict(old)
            parked.update(
                dormant=True, due_at=None, lease_until=0, owner=None, held_reason=held_reason, held_at=current
            )
            return parked, None

        _mutate(document_id, hold)
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='sync_dispatch',
            from_mode='enrichment_outbox',
            to_mode='held',
            reason=held_reason,
            outcome='exhausted',
            log=logger,
        )
        logger.warning('event=sync_reprocess outcome=held reason=%s', held_reason)
        return 'held'

    if process_context and process_context.get('redirect_to'):
        from utils.enrichment.custody import transfer_redirect

        pending = transfer_redirect(document_id, task_token, owner, process_context['redirect_to'], now=current)
        if pending is not None:
            _enqueue(pending)  # Transactional custody survives a lost enqueue acknowledgement.
        return 'redirected'

    if process_context and process_context.get('defer_reason'):

        def defer(old: Row | None) -> tuple[Row | None, Row | None]:
            if old is None or old.get('owner') != owner or old.get('task_token') != task_token:
                return old, None
            pending = dict(old)
            pending.update(
                deferred_reason=process_context['defer_reason'],
                due_at=current + LIVE_DEFER_SECONDS,
                task_due_at=current + LIVE_DEFER_SECONDS,
                task_token=uuid.uuid4().hex,
                lease_until=0,
                owner=None,
                wake_check_after=current + LIVE_DEFER_SECONDS,
            )
            # Scheduling is deferred; the original admitted deadline is not.
            return pending, pending

        pending = _mutate(document_id, defer)
        if pending is not None:
            _enqueue(pending)
        return 'deferred'

    def finish(old: Row | None) -> tuple[Row | None, Row | None]:
        if old is None or old.get('owner') != owner:
            return old, None

        if superseded and retry_revision is not None:
            # An append may precede the repair claim without another outbox
            # mark/version bump. Keep that obligation and refresh its fence.
            pending = dict(old)
            pending.update(
                summary_repair=True,
                summary_expected_revision=retry_revision,
                lease_until=0,
                task_token=uuid.uuid4().hex,
                task_due_at=min(current, pending['due_at']),
                due_at=min(current, pending['due_at']),
            )
            return pending, pending

        if old['version'] == row['version']:
            if summary_policy and summary_seen:
                # Retain only scheduling metadata as the first-summary receipt.
                # Future revisions keep their trailing-edge coalescing policy.
                settled = dict(old)
                settled.update(
                    summary_seen=True,
                    dormant=True,
                    due_at=None,
                    lease_until=0,
                    uid=None,
                    conversation_id=None,
                    language=None,
                    dispatch=None,
                    summary_repair=False,
                    summary_expected_revision=None,
                )
                return settled, None
            return None, None
        pending = dict(old)
        if summary_seen and summary_policy:
            pending['summary_seen'] = True
            pending['first_pending_at'] = current
            pending['summary_repair'] = False
            pending['summary_expected_revision'] = None
            pending['due_at'] = max(current, pending['first_pending_at']) + settle_seconds()
        pending.update(
            lease_until=0,
            task_token=uuid.uuid4().hex,
            task_due_at=pending['due_at'],
        )
        return pending, pending

    pending = _mutate(document_id, finish)
    if pending is not None:
        _enqueue(pending)
    return 'superseded' if superseded else 'processed'


def sweep(
    *,
    now: float | None = None,
    limit: int = 100,
    discard: Callable[[str], bool] | None = None,
    client: Any = None,
    wake: Callable[[Row], None] | None = None,
    cursor: bool = True,
) -> dict[str, int]:
    """Re-wake due obligations; ``discard`` retires privacy-fenced rows instead (contract (b) invariant 6).

    ``client``/``wake`` bind the pass to an injected store and task creator (the outbox conformance suite);
    an injected creator stands in for the queue binding and the named-task probe. ``cursor=False`` (the
    contract (b) outbox, invariant 8) scans from the oldest due row instead of resuming the shared
    ``sync_reprocess_scan`` checkpoint. An expired lease is fenced and re-woken under a new token, and
    ``wake_check_after`` throttles a row only once its wake was created.
    """
    from utils.enrichment import scan as enrichment_scan

    current = time.time() if now is None else now
    counts = {'repaired': 0, 'error': 0}
    if discard is not None:
        counts['discarded'] = 0
        counts['expired'] = 0
    if not owns_runtime():
        return counts

    binding = _dispatch_binding()
    limit = max(1, min(100, limit))
    bound = client
    client = bound or get_firestore_client()

    def mutate(document_id: str, operation):
        return _cas(bound, document_id, operation) if bound is not None else _mutate(document_id, operation)

    enqueue = wake or _enqueue
    injected = wake is not None
    # One range/order field uses the automatic single-field index.
    previous, start = enrichment_scan.begin(client, COLLECTION) if cursor else (None, None)
    query = (
        client.collection(COLLECTION)
        .where('due_at', '<=', current)
        .order_by('due_at')
        .order_by('__name__')
        .limit(limit)
    )
    exhausted = False

    def due_snapshots():
        nonlocal exhausted
        page_query = query.start_after(start) if start else query
        # Pending valid wakes at the front must not hide missing wakes behind
        # them. Bound both scanning and external task probes independently.
        for _ in range(10):
            page = list(page_query.stream())
            yield from page
            if len(page) < limit:
                exhausted = True
                return
            page_query = query.start_after(page[-1])

    checked = 0
    check_started = monotonic()
    last = None
    for snapshot in due_snapshots():
        if monotonic() - check_started >= 10:
            break
        last = snapshot

        def repair(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
            if old is None or old.get('dormant') or old.get('lease_until', 0) > current:
                return old, ('skipped', None)
            row = dict(old)
            # A lease that ran out is new information, so the wake-check throttle does not apply to it.
            expired = bool(row.get('owner')) and row.get('lease_until', 0) > 0
            if not expired and row.get('wake_check_after', 0) > current:
                return old, ('skipped', None)
            if not injected and not valid_effects_binding(row):
                if binding is None:
                    return old, ('unbound', None)
                # Claim and fence the repaired binding in the same CAS. Any old
                # task delivery becomes stale; valid backfill bindings stay put.
                row.update(dispatch=binding, task_token=uuid.uuid4().hex, task_due_at=current)
            if expired:
                # Fence the old holder (invariant 1) and retire its delivery: its task already ran.
                row.update(owner=None, lease_until=0, task_token=uuid.uuid4().hex, task_due_at=current)
                row.pop('summary_seen_by', None)

            row['wake_check_after'] = current + WAKE_CHECK_SECONDS
            if not expired and not injected and first_summary_pending(row):
                # Probe outside CAS, then recheck the exact name under CAS below.
                return row, ('check', row)
            if row['task_due_at'] + REPAIR_SECONDS <= current:
                row.update(task_token=uuid.uuid4().hex, task_due_at=current)
            return row, ('expired' if expired else 'ready', row)

        def unthrottle(token: str, checked_after: float) -> Callable[[Row | None], tuple[Row | None, None]]:
            def update(old: Row | None) -> tuple[Row | None, None]:
                if old is None or old.get('task_token') != token or old.get('wake_check_after') != checked_after:
                    return old, None
                return {**old, 'wake_check_after': 0}, None

            return update

        try:
            status, row = mutate(snapshot.id, repair)
            if status == 'expired' and 'expired' in counts:
                counts['expired'] += 1
            if status == 'check' and row is not None:
                checked += 1
                if _wake_exists(row):
                    if checked >= limit:
                        break
                    continue
                checked_name = _task_name(row)

                def replace(old: Row | None) -> tuple[Row | None, Row | None]:
                    if (
                        old is None
                        or old.get('dormant')
                        or old.get('lease_until', 0) > current
                        or _task_name(old) != checked_name
                    ):
                        return old, None
                    replacement = dict(old)
                    # Absence includes an exhausted/deleted task's name tombstone.
                    replacement.update(task_token=uuid.uuid4().hex, task_due_at=current)
                    replacement.pop('wake_generation', None)
                    return replacement, replacement

                row = mutate(snapshot.id, replace)
            if status == 'unbound':
                UNBOUND.labels(action='repair').inc()
            if row is not None and discard is not None and discard(snapshot.id):
                counts['discarded'] += 1
                row = None
            if row is not None:
                try:
                    enqueue(row)
                except Exception:
                    # The wake was not created: let the next pass retry instead of hiding the row for
                    # WAKE_CHECK_SECONDS. Best effort; a lost reset only delays the retry to that bound.
                    try:
                        mutate(snapshot.id, unthrottle(row['task_token'], row['wake_check_after']))
                    except Exception:
                        pass
                    raise
                counts['repaired'] += 1
        except Exception as error:
            counts['error'] += 1
            logger.error('event=sync_reprocess action=repair outcome=error exception_type=%s', type(error).__name__)
        if checked >= limit:
            break
    if cursor:
        enrichment_scan.finish(previous, last, exhausted)
    return counts


def due_rows(*, now: float, limit: int, client: Any = None) -> list[tuple[str, Row]]:
    """Pull mode: up to ``limit`` due, unleased, awake rows as ``(document_id, row)`` (single-field index)."""
    query = (
        (client or get_firestore_client())
        .collection(COLLECTION)
        .where('due_at', '<=', now)
        .order_by('due_at')
        .limit(max(1, min(100, limit)))
    )
    rows = []
    for snapshot in query.stream():
        row = snapshot.to_dict() or {}
        if not row.get('dormant') and row.get('lease_until', 0) <= now and row.get('task_token'):
            rows.append((snapshot.id, row))
    return rows


def mark_effects(uid: str, conversation_id: str, language: str, *, immediate: bool = False) -> None:
    """Blind-write lazy debt: no extra Firestore read on visible completion.

    Increment preserves concurrent dirtying; merge preserves an active worker's
    lease. The existing CAS completion sees that increment and retains the debt.
    Token changes fence older deliveries; all effects read the settled row.
    """
    if not owns_runtime():
        raise RuntimeError('lazy enrichment requires production or a Firestore emulator')
    current = time.time()
    # Preserve the daytime merge window as far as the hard completion ceiling
    # permits; open/explicit demand still bypasses this closed-surface wait.
    quiet_seconds = 3540
    document_id = key(uid, conversation_id + '\0effects')
    row = dict(
        document_id=document_id,
        uid=uid,
        conversation_id=conversation_id,
        language=language,
        effects_only=True,
        immediate=immediate,
        task_token=uuid.uuid4().hex,
        due_at=current + quiet_seconds,
        task_due_at=current + quiet_seconds,
        dispatch=_effects_binding(),
    )
    get_firestore_client().collection(COLLECTION).document(document_id).set(
        {**row, 'version': firestore.Increment(1)}, merge=True
    )
    if valid_effects_binding(row):
        _enqueue(row)
    else:
        # Match the sync outbox's unbound-host contract: visible work survives,
        # and the configured sweep CAS-rebinds the durable obligation later.
        UNBOUND.labels(action='mark').inc()


def _effects_binding() -> dict[str, str]:
    binding = _dispatch_binding()
    if binding is not None:
        return binding
    # Listen/pusher already have the durable finalization queue, identity and
    # worker. Reuse that protected handler for the same sync outbox protocol.
    from utils.cloud_tasks import listen_finalization_binding

    return listen_finalization_binding()
