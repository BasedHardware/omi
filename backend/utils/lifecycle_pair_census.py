"""Leader-fenced, cursor-based lifecycle pair observations (402 reads/pass).

No repair and no log text. Three indexed passes rotate through active jobs,
queued mirrors and processing conversations. Metrics describe a bounded page,
not the fleet's exact mismatch stock.
"""

import logging
import threading
import time
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from prometheus_client import Gauge
from utils.lifecycle_metrics import COHORT_START, seconds

KINDS = (
    'conv_queued_job_terminal',
    'conv_processing_job_terminal',
    'job_live_conv_missing',
    'finalization_job_id_set_job_absent',
)
PAGE_SIZE = 200
CADENCE_SECONDS = 300
LIVE = frozenset({'queued', 'leased', 'blocked_byok'})
TERMINAL = frozenset({'completed', 'dead_letter'})
PHASES = ('jobs', 'queued', 'processing')
JOB_FIELDS = ('status', 'kind', 'uid', 'conversation_id', 'finalization_revision', 'created_at')
CONV_FIELDS = (
    'status',
    'finalization_status',
    'finalization_job_id',
    'finalization_revision',
    'deleted',
    'is_deleted',
    'discarded',
    'sync_merged_into',
    'deferred',
)
MISMATCH = Gauge(
    'omi_finalization_pair_mismatch', 'Pair mismatches in each leg last bounded page, not fleet stock', ['leg', 'kind']
)
NEW_MISMATCH = Gauge(
    'omi_finalization_pair_new_mismatch', 'Recent-job pair mismatches in each leg last bounded page', ['leg', 'kind']
)
OBSERVED = Gauge(
    'omi_finalization_pair_observed_at_seconds', 'Last successful fenced observation of this indexed leg', ['leg']
)
TRUNCATED = Gauge(
    'omi_finalization_pair_scan_truncated', '1 when this indexed leg has another page or an uninspectable row', ['leg']
)
for _phase in PHASES:
    OBSERVED.labels(_phase).set(0)
_LOCK = threading.Lock()
_due = 0.0


def classify(job, conversation, job_id):
    if conversation and any(
        conversation.get(key) for key in ('deleted', 'is_deleted', 'discarded', 'sync_merged_into', 'deferred')
    ):
        return None
    if job is None:
        return (
            'finalization_job_id_set_job_absent' if conversation and conversation.get('finalization_job_id') else None
        )
    if conversation is None:
        return 'job_live_conv_missing' if job.get('status') in LIVE else None
    if conversation.get('finalization_job_id') != job_id or conversation.get('finalization_revision') != job.get(
        'finalization_revision'
    ):
        return None  # An older generation does not own this mirror.
    if job.get('status') in TERMINAL:
        if conversation.get('status') == 'processing':
            return 'conv_processing_job_terminal'
        if conversation.get('finalization_status') == 'queued':
            return 'conv_queued_job_terminal'
    return None


def _part(value):
    return isinstance(value, str) and bool(value) and '/' not in value


def sample(client, state, *, now=None):
    current = time.time() if now is None else now
    phase = state.get('phase', 'jobs')
    if phase not in PHASES:
        raise ValueError('invalid census leg')
    if phase == 'jobs':
        collection = client.collection('conversation_finalization_jobs')
        query = collection.where(filter=FieldFilter('status', 'in', sorted(LIVE)))
    else:
        collection = client.collection_group('conversations')
        field, value = ('finalization_status', 'queued') if phase == 'queued' else ('status', 'processing')
        query = collection.where(filter=FieldFilter(field, '==', value))
    query = query.order_by('__name__')
    cursors = state.get('cursors')
    if cursors is None:
        cursors = {phase: state.get('cursor')}  # Accept a pre-map checkpoint once.
    if not isinstance(cursors, dict) or set(cursors) - set(PHASES):
        raise ValueError('invalid census cursor map')
    cursor = cursors.get(phase)
    if cursor:
        parts = cursor.split('/') if isinstance(cursor, str) else []
        collection_name = 'conversation_finalization_jobs' if phase == 'jobs' else 'conversations'
        if (
            not parts
            or len(parts) % 2
            or not all(_part(part) for part in parts)
            or parts[-2] != collection_name
            or (phase == 'jobs' and len(parts) != 2)
        ):
            raise ValueError('invalid census cursor')
        query = query.start_after({'__name__': client.document(cursor)})
    page = list(
        query.select(JOB_FIELDS if phase == 'jobs' else CONV_FIELDS).limit(PAGE_SIZE).stream(timeout=10, retry=None)
    )
    pairs = []
    blind = len(page) == PAGE_SIZE
    for doc in page:
        row = doc.to_dict() or {}
        if phase == 'jobs':
            if row.get('kind') in {'listen_quiet_check', 'conversation_merge'}:
                continue
            uid, cid = row.get('uid'), row.get('conversation_id')
            if not _part(uid) or not _part(cid):
                blind = True
                continue
            ref = client.document(f'users/{uid}/conversations/{cid}')
        else:
            parts = doc.reference.path.split('/')
            if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations':
                blind = True
                continue
            job_id = row.get('finalization_job_id')
            if not job_id:
                continue  # Bare processing has its own existing orphan repair.
            if not _part(job_id):
                blind = True
                continue
            ref = client.collection('conversation_finalization_jobs').document(job_id)
        pairs.append((doc, row, ref))
    refs = {ref.path: ref for _, _, ref in pairs}
    snapshots = (
        list(
            client.get_all(
                list(refs.values()), field_paths=CONV_FIELDS if phase == 'jobs' else JOB_FIELDS, timeout=10, retry=None
            )
        )
        if refs
        else []
    )
    by_path = {doc.reference.path: doc for doc in snapshots}
    if set(by_path) != set(refs):
        raise ValueError('incomplete counterpart read')
    counts = dict.fromkeys(KINDS, 0)
    fresh = dict.fromkeys(KINDS, 0)
    for doc, row, ref in pairs:
        snapshot = by_path[ref.path]
        other = snapshot.to_dict() if snapshot.exists else None
        job, conv, job_id = (row, other, doc.id) if phase == 'jobs' else (other, row, ref.id)
        kind = classify(job, conv, job_id)
        if kind:
            counts[kind] += 1
            try:
                entered = seconds(job['created_at']) if job else None
            except (KeyError, ValueError, TypeError):
                entered = None
            if entered is None:
                blind = True  # No clock can prove a new regression.
            elif max(COHORT_START, current - 86400) <= entered <= current:
                fresh[kind] += 1
    next_state = {
        'phase': PHASES[(PHASES.index(phase) + 1) % len(PHASES)],
        'cursors': {**cursors, phase: page[-1].reference.path if len(page) == PAGE_SIZE else None},
        'cursor': None,
    }
    return counts, blind, next_state, fresh


def run_page(client, now, token):
    ref = client.collection('lifecycle_alarm_scan').document('pairs')

    @firestore.transactional
    def acquire(tx):
        state = ref.get(transaction=tx, timeout=10, retry=None).to_dict() or {}
        if state.get('next_due', 0) > now or state.get('lease_until', 0) > now:
            return None
        tx.set(ref, {**state, 'lease_owner': token, 'lease_until': now + 120, 'next_due': now + CADENCE_SECONDS})
        return state

    # One attempt keeps the document-read budget hard even under contention.
    state = acquire(client.transaction(max_attempts=1))
    if state is None:
        return None
    counts, blind, cursor, fresh = sample(client, state, now=now)

    @firestore.transactional
    def finish(tx):
        current = ref.get(transaction=tx, timeout=10, retry=None).to_dict() or {}
        if current.get('lease_owner') != token or current.get('lease_until', 0) <= time.time():
            return False
        tx.set(ref, {**current, **cursor, 'lease_until': 0, 'lease_owner': None, 'observed_at': now})
        return True

    return (counts, blind, fresh, state.get('phase', 'jobs')) if finish(client.transaction(max_attempts=1)) else None


def observe(*, client=None, now=None):
    global _due
    current = time.time() if now is None else now
    if not _LOCK.acquire(blocking=False):
        return
    try:
        if current < _due:
            return
        _due = current + CADENCE_SECONDS
        try:
            if client is None:
                from database._client import get_firestore_client

                client = get_firestore_client()
            result = run_page(client, current, uuid.uuid4().hex)
        except Exception as error:
            logging.getLogger(__name__).warning(
                'event=lifecycle_pair_sample outcome=unavailable exception_type=%s', type(error).__name__
            )
            return
        if result is not None:
            counts, blind, fresh, phase = result
            for kind, count in counts.items():
                MISMATCH.labels(phase, kind).set(count)
                NEW_MISMATCH.labels(phase, kind).set(fresh[kind])
            TRUNCATED.labels(phase).set(int(blind))
            OBSERVED.labels(phase).set(current)
    finally:
        _LOCK.release()
