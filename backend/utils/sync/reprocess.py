"""Durable, trailing-edge sync enrichment outbox.

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
import time
import uuid
from typing import Any, Callable, TypeVar, TypeAlias, TypeGuard
from urllib.parse import urlsplit

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
from prometheus_client import Counter

from config.sync_reprocess import settle_seconds
from config.repeat_work import revision_reuse
from database._client import get_firestore_client

Row: TypeAlias = dict[str, Any]
ResultT = TypeVar('ResultT')

logger = logging.getLogger(__name__)

COLLECTION = 'sync_reprocess_outbox'
LEASE_SECONDS = 1800  # Greater than the Cloud Tasks dispatch deadline.
FIRST_SUMMARY_LEASE_SECONDS = 120
REPAIR_SECONDS = 1800
COALESCED = Counter('sync_reprocess_coalesced_total', 'Sync updates folded into an existing enrichment obligation')
UNBOUND = Counter('sync_reprocess_unbound_total', 'Sync obligations awaiting a complete worker binding', ['action'])


def key(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()


def owns_runtime() -> bool:
    from utils.sync.stage import production_stage

    return bool(os.getenv('FIRESTORE_EMULATOR_HOST')) or production_stage()


def _mutate(document_id: str, operation: Callable[[Row | None], tuple[Row | None, ResultT]]) -> ResultT:
    if not owns_runtime():
        raise RuntimeError('sync reprocess outbox requires production or a Firestore emulator')
    client = get_firestore_client()
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
        and url.path.endswith('/v2/sync-jobs/run')
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
    handler = os.getenv('SYNC_TASKS_HANDLER_URL', '')
    binding = {
        'queue': os.getenv('SYNC_TASKS_QUEUE', ''),
        'handler': handler,
        'audience': os.getenv('SYNC_TASKS_OIDC_AUDIENCE') or handler,
        'invoker_sa': os.getenv('SYNC_TASKS_INVOKER_SA', ''),
    }
    return binding if valid_dispatch_binding(binding) else None


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
        handler.endswith('/v2/sync-jobs/run')
        or row.get('effects_only')
        and handler.endswith('/v1/conversation-finalization-jobs/run')
    ):
        raise RuntimeError('sync reprocessing requires the sync worker handler binding')
    from utils.conversations.demand_processing import schedule

    document_id = row.get('document_id') or key(row['uid'], row['conversation_id'])
    payload = {'kind': 'sync_reprocess', 'key': document_id, 'task_token': row['task_token']}
    name = f"sr-{document_id}-{row['task_token']}"
    from config.summary_guarantee import enabled as summary_enabled

    first_summary = summary_enabled(row['uid']) and not row.get('effects_only') and not row.get('summary_seen')
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
) -> None:
    """Record one enrichment obligation.

    Projection may inject a transactional mutation to commit its replay receipt
    and privacy fences with this obligation. The default retains the normal
    CAS path; both paths enqueue only after durable persistence.
    """
    if mutate is not None and not owns_runtime():
        raise RuntimeError('sync reprocess projection requires production or a Firestore emulator')
    current = time.time() if now is None else now

    def update(old: Row | None) -> tuple[Row, tuple[Row, bool]]:
        row = dict(old or {})
        row.update(
            document_id=key(uid, conversation_id + ('\0effects' if effects_only else '')),
            uid=uid,
            conversation_id=conversation_id,
            language=language,
            version=row.get('version', 0) + 1,
            due_at=max(row.get('due_at') or 0, current + settle_seconds()),
        )
        # Timestamp every durable obligation, even before rollout. Neither an
        # append nor a retry owns the original acceptance time.
        row['first_pending_at'] = current if old and old.get('dormant') else row.get('first_pending_at', current)
        row['dormant'] = False
        row['summary_repair'] = False
        from config.summary_guarantee import enabled as summary_enabled, deadline_seconds

        if summary_enabled(uid) and not effects_only and not row.get('summary_seen'):
            row['summary_deadline_at'] = min(
                row.get('summary_deadline_at', float('inf')), row['first_pending_at'] + deadline_seconds()
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
        row.update(effects_only=effects_only)
        from utils.conversations.summary_delivery import lane

        row.setdefault('summary_lane', 'batch' if mutate is not None else lane({}))
        if old is None:
            row.update(
                task_token=uuid.uuid4().hex, task_due_at=row['due_at'], lease_until=0, dispatch=_dispatch_binding()
            )
        elif old.get('dormant'):
            row['dispatch'] = _dispatch_binding()
        elif not valid_dispatch_binding(row.get('dispatch')):
            row['dispatch'] = None
        wake = old is None
        if old is not None and (old.get('dormant') or (row.get('task_due_at') or 0) > row['due_at']):
            row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
            wake = True
        row['_wake'] = wake
        return row, (row, old is not None)

    document_id = key(uid, conversation_id + ('\0effects' if effects_only else ''))
    row, coalesced = (mutate or _mutate)(document_id, update)
    if coalesced:
        COALESCED.inc()
    if row.get('_wake', not coalesced) and valid_dispatch_binding(row.get('dispatch')):
        _enqueue(row)  # Failure leaves the obligation durable for the sweep.
    elif not valid_dispatch_binding(row.get('dispatch')):
        UNBOUND.labels(action='mark').inc()


def run(document_id: str, task_token: str, process: Callable[[str, str, str], Any], *, now: float | None = None) -> str:
    current = time.time() if now is None else now
    from utils.conversations.demand_processing import admit
    from config.demand_processing import enabled

    if not admit(document_id, now=current, token=task_token):
        return 'priority_wait'
    owner = uuid.uuid4().hex

    def claim(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
        if old is None or old.get('dormant') or old['task_token'] != task_token:
            return old, ('stale', None)
        if old.get('lease_until', 0) > current:
            return old, ('busy', None)
        row = dict(old)
        if row['due_at'] > current and (not row.get('effects_only') or not enabled(row['uid'])):
            row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
            return row, ('deferred', row)
        from config.summary_guarantee import enabled as summary_enabled

        first_summary = summary_enabled(row['uid']) and not row.get('summary_seen') and not row.get('effects_only')
        lease_seconds = FIRST_SUMMARY_LEASE_SECONDS if first_summary else LEASE_SECONDS
        row.update(lease_until=current + lease_seconds, owner=owner)
        return row, ('claimed', row)

    status, row = _mutate(document_id, claim)
    if status == 'deferred':
        assert row is not None
        _enqueue(row)
        return status
    if status != 'claimed':
        return status
    assert row is not None
    # Exceptions leave a leased, dirty row. Retry/sweep recovers after expiry.
    summary_seen = False
    if row.get('effects_only'):
        from utils.conversations.lazy_enrichment import enrich_settled

        enrich_settled(row['uid'], row['conversation_id'], row['language'])
    else:
        from config.summary_guarantee import enabled as summary_enabled
        from utils.conversations.summary_delivery import (
            REPAIR_CONTEXT,
            LANE_CONTEXT,
            ACCEPT_CONTEXT,
            PROCESS_CONTEXT,
            lane,
        )

        lane_token = LANE_CONTEXT.set(
            row.get('summary_lane')
            or ('backfill' if (row.get('dispatch') or {}).get('queue') == 'sync-backfill' else lane({}))
        )
        process_context = (
            {'owner': owner, 'lease_until': row['lease_until']}
            if summary_enabled(row['uid']) and not row.get('summary_seen')
            else None
        )
        process_token = PROCESS_CONTEXT.set(process_context)
        accept_token = ACCEPT_CONTEXT.set(row.get('first_pending_at'))
        context_token = REPAIR_CONTEXT.set(row if row.get('summary_repair') else None)
        try:
            output = process(row['uid'], row['conversation_id'], row['language'])
        finally:
            REPAIR_CONTEXT.reset(context_token)
            LANE_CONTEXT.reset(lane_token)
            ACCEPT_CONTEXT.reset(accept_token)
            PROCESS_CONTEXT.reset(process_token)
        from config.summary_guarantee import enabled as summary_enabled
        from utils.conversations.summary_delivery import field, present, SummaryOutputUnavailable

        summary_seen = output is not None and (
            field(output, 'discarded', False) or present(field(output, 'structured'))
        )
        blocked = bool(process_context and process_context.get('blocked_reason'))
        if summary_enabled(row['uid']) and output is not None and not summary_seen and not blocked:
            raise SummaryOutputUnavailable('first-summary output is empty')

    def finish(old: Row | None) -> tuple[Row | None, Row | None]:
        if old is None or old.get('owner') != owner:
            return old, None
        from config.summary_guarantee import enabled as summary_enabled

        if old['version'] == row['version']:
            if summary_enabled(row['uid']) and summary_seen:
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
        if summary_seen and summary_enabled(row['uid']):
            pending['summary_seen'] = True
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
    return 'processed'


def sweep(*, now: float | None = None, limit: int = 100) -> dict[str, int]:
    current = time.time() if now is None else now
    counts = {'repaired': 0, 'error': 0}
    if not owns_runtime():
        return counts
    from config.summary_guarantee import repair_enabled

    if repair_enabled():
        from services.summary_debt_repair import tick

        tick(now=current)
    binding = _dispatch_binding()
    limit = max(1, min(100, limit))
    client = get_firestore_client()
    # One range/order field uses the automatic single-field index.
    snapshots = client.collection(COLLECTION).where('due_at', '<=', current).order_by('due_at').limit(limit).stream()
    for snapshot in snapshots:

        def repair(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
            if old is None or old.get('dormant') or old.get('lease_until', 0) > current:
                return old, ('skipped', None)
            row = dict(old)
            if not valid_effects_binding(row):
                if binding is None:
                    return old, ('unbound', None)
                # Claim and fence the repaired binding in the same CAS. Any old
                # task delivery becomes stale; valid backfill bindings stay put.
                row.update(dispatch=binding, task_token=uuid.uuid4().hex, task_due_at=current)
            from config.summary_guarantee import enabled as summary_enabled

            repair_seconds = (
                FIRST_SUMMARY_LEASE_SECONDS
                if summary_enabled(row['uid']) and not row.get('summary_seen') and not row.get('effects_only')
                else REPAIR_SECONDS
            )
            if row['task_due_at'] + repair_seconds <= current:
                row.update(task_token=uuid.uuid4().hex, task_due_at=current)
            return row, ('ready', row)

        try:
            status, row = _mutate(snapshot.id, repair)
            if status == 'unbound':
                UNBOUND.labels(action='repair').inc()
            if row is not None:
                _enqueue(row)
                counts['repaired'] += 1
        except Exception as error:
            counts['error'] += 1
            logger.error('event=sync_reprocess action=repair outcome=error exception_type=%s', type(error).__name__)
    return counts


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
