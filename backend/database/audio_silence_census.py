"""Indexed 24-hour user census with a hard, content-free read budget."""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from google.api_core.exceptions import DeadlineExceeded
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from utils.lifecycle_metrics import COHORT_SECONDS, SILENCE_CENSUS_SOURCES, SILENCE_CENSUS_STATES, seconds

WINDOW_SECONDS = COHORT_SECONDS
PAGE_LIMIT = 300
INDEX_ENTRY_BATCH_SIZE = 1000
READ_BUDGET = 4000
SAMPLE_DEADLINE_SECONDS = 5
RPC_TIMEOUT_SECONDS = 10


class _BudgetExhausted(Exception):
    pass


class _SampleDeadlineExceeded(Exception):
    pass


class _Reads:
    def __init__(self, limit):
        self.limit = limit
        self.used = 0
        self.modeled = 0
        self.partial = False

    def documents(self, count):
        self.used += count
        self.modeled += count

    def source_query(self):
        # Reserve one read for the query's index-entry batch, or its minimum
        # charge when the page is empty. The page cap is at most one batch.
        self.used += 1

    def aggregate(self):
        # COUNT(1) is capped at one matching index entry and therefore costs at
        # most one billed read. Charge it before the RPC to fail closed.
        if self.used >= self.limit:
            self.partial = True
            raise _BudgetExhausted
        self.used += 1
        self.modeled += 1


@dataclass
class _Evidence:
    activity: bool = False
    audio: bool = False
    job: bool = False
    received: bool = False
    outbox: bool = False
    sessions: bool = False
    latest: float = float('-inf')
    source: str = 'other'


def _uid(path):
    parts = path.split('/')
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations' or not parts[1]:
        raise ValueError('invalid conversation reference')
    return parts[1]


def _source(value):
    value = getattr(value, 'value', value)
    return value if value in {'omi', 'desktop'} else 'other'


def _observe_source(evidence, value, clock):
    if value is None:
        return
    try:
        stamp = seconds(clock)
    except (KeyError, TypeError, ValueError):
        return
    if stamp >= evidence.latest:
        evidence.latest = stamp
        evidence.source = _source(value)


def _census_state(item):
    if not item.activity:
        return 'audio_no_app_activity'
    return 'app_active_with_audio' if item.audio else 'app_active_no_audio'


def sample(client, namespace, now, *, read_budget=READ_BUDGET, page_limit=PAGE_LIMIT):
    """Return unique classifiable users, completeness and conservative read counts.

    A full source page conservatively means unseen evidence exists. Candidate
    existence aggregates restore exact app/audio classification where possible;
    an empty-audio candidate remains unclassified when unseen upload-session
    maps could still exist. Users without enough evidence never become zeros.
    ``reads`` reports returned documents plus existence aggregates;
    ``budget_reads`` also includes one billed source-query unit per page.
    """
    current = seconds(now)
    after = current - WINDOW_SECONDS
    after_datetime = datetime.fromtimestamp(after, tz=timezone.utc)
    current_datetime = datetime.fromtimestamp(current, tz=timezone.utc)
    reads = _Reads(read_budget)
    deadline = time.monotonic() + SAMPLE_DEADLINE_SECONDS
    evidence = {}
    truncated = {'conversations': False, 'jobs': False, 'outbox': False}

    def rpc_timeout():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reads.partial = True
            raise _SampleDeadlineExceeded
        return min(RPC_TIMEOUT_SECONDS, remaining)

    def stream(kind, query):
        timeout = rpc_timeout()
        # Keep room for the minimum/index-entry read charged for this query.
        cap = min(page_limit, INDEX_ENTRY_BATCH_SIZE, reads.limit - reads.used - 1)
        if cap <= 0:
            reads.partial = truncated[kind] = True
            return []
        reads.source_query()
        rows = []
        try:
            for row in query.limit(cap).stream(timeout=timeout, retry=None):
                rows.append(row)
                reads.documents(1)
        except DeadlineExceeded:
            # Preserve rows already received, publish them only as lower bounds,
            # and let the shared deadline stop any follow-up query work.
            reads.partial = truncated[kind] = True
            return rows
        truncated[kind] = len(rows) == cap
        reads.partial |= truncated[kind]
        return rows

    def exists(query):
        timeout = rpc_timeout()
        reads.aggregate()
        try:
            aggregation = query.limit(1).count().get(timeout=timeout, retry=None)
        except DeadlineExceeded as error:
            reads.partial = True
            raise _SampleDeadlineExceeded from error
        return int(aggregation[0][0].value) > 0

    def activity_query(uid):
        return (
            client.collection('users')
            .document(uid)
            .collection('conversations')
            .where(filter=FieldFilter('created_at', '>=', after_datetime))
            .where(filter=FieldFilter('created_at', '<=', current_datetime))
        )

    def job_query(uid):
        return (
            client.collection(f'{namespace}_jobs')
            .where(filter=FieldFilter('owner_id', '==', uid))
            .where(filter=FieldFilter('enqueued_at', '>=', after))
            .where(filter=FieldFilter('enqueued_at', '<=', current))
        )

    def outbox_query(uid):
        return (
            client.collection('sync_reprocess_outbox')
            .where(filter=FieldFilter('uid', '==', uid))
            .where(filter=FieldFilter('first_pending_at', '>=', after))
            .where(filter=FieldFilter('first_pending_at', '<=', current))
        )

    def remember(uid):
        if not isinstance(uid, str) or not uid:
            reads.partial = True
            return None
        return evidence.setdefault(uid, _Evidence())

    conversations = jobs = outbox = []
    try:
        conversations = stream(
            'conversations',
            client.collection_group('conversations')
            .where(filter=FieldFilter('created_at', '>=', after_datetime))
            .where(filter=FieldFilter('created_at', '<=', current_datetime))
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .order_by('__name__')
            .select(('created_at', 'source', 'server_batch_audio_received', 'record_upload_sessions')),
        )
        jobs = stream(
            'jobs',
            client.collection(f'{namespace}_jobs')
            .where(filter=FieldFilter('enqueued_at', '>=', after))
            .where(filter=FieldFilter('enqueued_at', '<=', current))
            .order_by('enqueued_at')
            .order_by('__name__')
            .select(('owner_id', 'enqueued_at', 'source', 'record_snapshot.source')),
        )
        outbox = stream(
            'outbox',
            client.collection('sync_reprocess_outbox')
            .where(filter=FieldFilter('dormant', '==', False))
            .where(filter=FieldFilter('first_pending_at', '>=', after))
            .where(filter=FieldFilter('first_pending_at', '<=', current))
            .order_by('first_pending_at')
            .order_by('__name__')
            .select(('uid', 'first_pending_at')),
        )
    except _BudgetExhausted:
        pass
    except _SampleDeadlineExceeded:
        # A page that was not read cannot support negative classification.
        # Candidate checks below also stop at the same deadline.
        for kind in truncated:
            truncated[kind] = True

    for doc in conversations:
        row = doc.to_dict() or {}
        try:
            item = remember(_uid(doc.reference.path))
        except ValueError:
            reads.partial = True
            continue
        if item is None:
            continue
        item.activity = True
        item.received |= row.get('server_batch_audio_received') is True
        item.sessions |= bool(row.get('record_upload_sessions'))
        item.audio |= item.received or item.sessions
        _observe_source(item, row.get('source'), row.get('created_at'))

    for doc in jobs:
        row = doc.to_dict() or {}
        item = remember(row.get('owner_id'))
        if item is None:
            continue
        item.activity = item.audio = item.job = True
        snapshot = row.get('record_snapshot')
        _observe_source(item, row.get('source') or (snapshot or {}).get('source'), row.get('enqueued_at'))

    for doc in outbox:
        row = doc.to_dict() or {}
        item = remember(row.get('uid'))
        if item is None:
            continue
        item.audio = item.outbox = True

    counts = {(state, source): 0 for state in SILENCE_CENSUS_STATES for source in SILENCE_CENSUS_SOURCES}
    try:
        for uid in sorted(evidence):
            item = evidence[uid]
            if truncated['jobs'] and not item.job and exists(job_query(uid)):
                item.activity = item.audio = item.job = True
            if truncated['conversations']:
                if not item.received and exists(
                    activity_query(uid).where(filter=FieldFilter('server_batch_audio_received', '==', True))
                ):
                    item.audio = item.received = True
                if not item.activity and exists(activity_query(uid)):
                    item.activity = True
            if truncated['outbox'] and not item.outbox and exists(outbox_query(uid)):
                item.audio = item.outbox = True
            if not item.audio and truncated['conversations']:
                # An unseen non-empty record_upload_sessions map cannot be
                # disproved by COUNT. Do not mislabel this user as silent.
                continue
            counts[_census_state(item), item.source] += 1
    except (_BudgetExhausted, _SampleDeadlineExceeded):
        pass
    return {
        'counts': counts,
        'partial': reads.partial,
        'reads': reads.modeled,
        'budget_reads': reads.used,
    }
