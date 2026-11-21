"""Indexed, capped reads for lifecycle alarms. No identity leaves these functions."""

import os

from google.cloud.firestore_v1 import FieldFilter

from config.firestore_read_levers import lever_enabled

from utils.lifecycle_metrics import PAGE_LIMIT, COHORT_SECONDS, COHORT_START, cohort_age


def _where(query, field, op, value):
    return query.where(filter=FieldFilter(field, op, value))


def _replica_key(namespace):
    # Cohort per serving replica so a percentage is a real canary; one namespace
    # key would put the whole fleet in or out together (Luna r1 on #24639).
    # Same identity as fsr_read_cache.serving_config_key, inlined so this module's
    # import closure (batch images) does not grow.
    host = os.getenv('HOSTNAME')
    if host:
        return host
    revision, instance = os.getenv('K_REVISION'), os.getenv('INSTANCE_ID') or os.getenv('GAE_INSTANCE')
    return f'{revision}:{instance}' if revision and instance else namespace


def record_pending(client, namespace, now):
    stock = _where(client.collection(f'{namespace}_jobs'), 'state', '==', 'record_pending')
    cohort = _where(stock, 'enqueued_at', '>=', max(COHORT_START, now - COHORT_SECONDS)).order_by('enqueued_at')
    if lever_enabled('lifecycle_record_pending_head', _replica_key(namespace)):
        # The page is ordered oldest first from the cohort's lower bound, so its
        # first row alone determines cohort_age. A capped count reproduces the
        # full-page flag. ~1,000 document reads per tick become 1 plus the
        # aggregation's index-entry charge (1 read per 1,000 entries).
        rows = [doc.to_dict() for doc in cohort.limit(1).stream(timeout=10, retry=None)]
        full = int(cohort.limit(PAGE_LIMIT).count().get(timeout=10, retry=None)[0][0].value) >= PAGE_LIMIT
    else:
        rows = [doc.to_dict() for doc in cohort.limit(PAGE_LIMIT).stream(timeout=10, retry=None)]
        full = len(rows) == PAGE_LIMIT
    # The capped aggregate crosses the stock alert threshold without loading
    # thousands of job documents or scanning terminal history in the client.
    count = int(stock.limit(5001).count().get(timeout=10, retry=None)[0][0].value)
    return {'record_pending': (cohort_age(rows, 'enqueued_at', now), count, full or count == 5001)}


def nojob(client, namespace):
    from config.record_audio import record_identity

    # Same indexed collection-group owner/name page as no-job repair. This
    # observation never seals or registers rows and does not advance a cursor.
    query = _where(client.collection_group('conversations'), 'record_lane_owner', '==', 'batch_live_v1')
    page = list(
        query.order_by('__name__')
        .select(('status', 'deleted', 'record_audio_closed', 'record_upload_sessions'))
        .limit(128)
        .stream(timeout=10, retry=None)
    )
    counts = {'sealed_no_job': 0, 'open_no_tokens': 0, 'open_with_tokens': 0}
    candidates = []
    for doc in page:
        row = doc.to_dict()
        if row.get('deleted') or row.get('status') != 'completed':
            continue
        parts = doc.reference.path.split('/')
        if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations':
            raise ValueError('invalid conversation reference')
        _, job_id = record_identity(parts[1], parts[3])
        ref = client.collection(f'{namespace}_jobs').document(job_id)
        kind = (
            'sealed_no_job'
            if row.get('record_audio_closed')
            else 'open_with_tokens' if row.get('record_upload_sessions') else 'open_no_tokens'
        )
        candidates.append((ref, kind))
    present = (
        {
            doc.reference.path
            for doc in client.get_all([ref for ref, _ in candidates], field_paths=[], timeout=10, retry=None)
            if doc.exists
        }
        if candidates
        else set()
    )
    for ref, kind in candidates:
        if ref.path not in present:
            counts[kind] += 1
    return {kind: (0, count, len(page) == 128) for kind, count in counts.items()}


def enrichment(client, now):
    collection = client.collection('sync_reprocess_outbox')
    query = (
        _where(
            _where(collection, 'dormant', '==', False),
            'first_pending_at',
            '>=',
            max(COHORT_START, now - COHORT_SECONDS),
        )
        .order_by('first_pending_at')
        .limit(PAGE_LIMIT)
    )
    page = [doc.to_dict() for doc in query.stream(timeout=10, retry=None)]
    lanes = {'fresh': [], 'backfill': []}
    for row in page:
        if row.get('dormant') or row.get('due_at') is None:
            continue
        # Use durable admission metadata only. Calling the routing helper here
        # could read a rollout flag per legacy row, outside this read budget.
        policy = row.get('first_summary_policy') or {}
        first_summary = (
            not row.get('effects_only')
            and not row.get('summary_seen')
            and (
                policy.get('first_summary_enabled') is True or isinstance(row.get('summary_deadline_at'), (int, float))
            )
        )
        lane = 'backfill' if row.get('summary_lane') == 'backfill' and not first_summary else 'fresh'
        lanes[lane].append(row)
    stock = _where(_where(collection, 'summary_lane', '==', 'backfill'), 'due_at', '>=', 0)
    count = int(stock.limit(20001).count().get(timeout=10, retry=None)[0][0].value)
    return {
        lane: (
            cohort_age(rows, 'first_pending_at', now),
            count if lane == 'backfill' else len(rows),
            len(page) == PAGE_LIMIT or (lane == 'backfill' and count == 20001),
        )
        for lane, rows in lanes.items()
    }


def blocked_byok(client, now):
    from datetime import datetime, timezone

    after = datetime.fromtimestamp(now - 7 * COHORT_SECONDS, tz=timezone.utc)
    query = _where(client.collection('conversation_finalization_jobs'), 'status', '==', 'blocked_byok')
    page = [
        doc.to_dict()
        for doc in _where(query, 'blocked_byok_at', '>=', after)
        .order_by('blocked_byok_at')
        .limit(PAGE_LIMIT)
        .stream(timeout=10, retry=None)
    ]
    # Older rows have no entry stamp: their stock remains covered by the
    # existing informational age and stock metrics, never this page cohort.
    return {
        'blocked_byok': (
            cohort_age(page, 'blocked_byok_at', now, 7 * COHORT_SECONDS),
            len(page),
            len(page) == PAGE_LIMIT,
        )
    }


def enrichment_summary_repair(client):
    query = _where(_where(client.collection('sync_reprocess_outbox'), 'summary_repair', '==', True), 'due_at', '>=', 0)
    count = int(query.limit(101).count().get(timeout=10, retry=None)[0][0].value)
    return {'all': (0, count, count == 101)}


VENDOR_HELD_COUNT_LIMIT = 100_000


def vendor_held(client, namespace, now):
    """Capped vendor_held counts by hold reason and the oldest held row's age, for the held gauges.

    Counts are equality-only aggregations (index merging; one read per 1,000 index entries), and the
    oldest row comes from the (state, enqueued_at) index, so a tick reads one document. A row with no
    recognised ``vendor_hold.reason`` counts as ``unknown``. No identity leaves this function.
    """
    from utils.observability.reasons import VendorHoldReason

    def count(query):
        return int(query.limit(VENDOR_HELD_COUNT_LIMIT).count().get(timeout=10, retry=None)[0][0].value)

    held = _where(client.collection(f'{namespace}_jobs'), 'state', '==', 'vendor_held')
    total = count(held)
    counts = {reason: 0 for reason in VendorHoldReason}
    if total:
        for reason in VendorHoldReason:
            if reason is not VendorHoldReason.UNKNOWN:
                counts[reason] = count(_where(held, 'vendor_hold.reason', '==', reason.value))
        counts[VendorHoldReason.UNKNOWN] = max(0, total - sum(counts.values()))
    oldest = [
        doc.to_dict().get('enqueued_at')
        for doc in held.order_by('enqueued_at').select(['enqueued_at']).limit(1).stream(timeout=10, retry=None)
    ]
    started = oldest[0] if oldest else None
    age = max(0.0, now - started) if isinstance(started, (int, float)) and not isinstance(started, bool) else 0.0
    return counts, age, total >= VENDOR_HELD_COUNT_LIMIT


PROVIDER_STAGE_STATES = ('provider_pending', 'provider_running')
# An aggregation bills one read per 1,000 index entries, so a 1e6 cap costs at most ~1,000 reads.
PROVIDER_STAGE_COUNT_LIMIT = 1_000_000


def provider_stage(client, namespace, now):
    """Capped stock and oldest age of each provider-STT stage state, from the (state, enqueued_at) index.

    The timeliness alarm leaves ``provider_pending`` out by design (allowance holds park units there
    for a day), so this is the stage's only stock signal. One count and one head read per state.
    """
    jobs = client.collection(f'{namespace}_jobs')
    rows = {}
    for state in PROVIDER_STAGE_STATES:
        stock = _where(jobs, 'state', '==', state)
        count = int(stock.limit(PROVIDER_STAGE_COUNT_LIMIT).count().get(timeout=10, retry=None)[0][0].value)
        head = [
            doc.to_dict().get('enqueued_at')
            for doc in stock.order_by('enqueued_at').select(['enqueued_at']).limit(1).stream(timeout=10, retry=None)
        ]
        started = head[0] if head else None
        valid = isinstance(started, (int, float)) and not isinstance(started, bool)
        rows[state] = (count, max(0.0, now - started) if valid else 0.0)
    return rows
