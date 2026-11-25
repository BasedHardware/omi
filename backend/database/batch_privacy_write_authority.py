"""Select eligible scheduler write evidence and keep shadow observational."""

from math import isfinite
import time
from typing import Any

from config.batch_pipeline import Priority
from config.firestore_read_levers import lever_enabled, lever_percent
from database import batch_privacy_write_cache as cache, privacy_check_metrics as metrics
from database.batch_pipeline_privacy import (
    BatchPrivacyBlocked,
    PRIVACY_COLLECTION,
    read_live_batch_write_authority,
    privacy_owner_key,
)
from database.batch_privacy_attempt import token_version
from database.batch_pipeline_transaction_labels import current_operation
from database.privacy_ttl_cache import disabled as ttl_disabled

# The cache may update scheduling metadata on existing leases only.
LEASE_FIELDS = frozenset(
    {
        'state',
        'token',
        'attempt',
        'lease_until',
        'shared_gpu_key',
        'record_first_leased_at',
        'unit_kind',
    }
)
QUEUE_FIELDS = frozenset({'head', 'tail', 'deficit', 'continuing'})
_ABSENT = object()
PRIORITIES = frozenset(str(int(priority)) for priority in Priority)


@metrics.with_batch_plan
def check_cached_write(
    client, transaction, uid, *, conversation_ids, expected_generation, read_budget, site=None, on_hit=None
):
    """Return a generation when handled here, otherwise leave certification to the caller."""
    if site not in cache.SITES:
        return None
    shadow = lever_enabled('bpp_tokenless_write_shadow', uid)
    enforce = lever_enabled('bpp_tokenless_write_cache', uid) and lever_percent('bpp_tokenless_write_shadow') == 0
    if not (
        (shadow or enforce)
        and transaction is not None
        and lever_percent('privacy_checks_shadow') == 0
        and lever_percent('bpp_shared_owner_shadow') == 0
        and cache.available(client)
        and not ttl_disabled()
    ):
        return None
    ids = frozenset(conversation_ids)
    if any(not isinstance(cid, str) or not cid or '/' in cid or len(cid.encode()) > 256 for cid in ids):
        return None
    started = time.time()
    lookup = cache.read_tokenless(client, privacy_owner_key(uid), ids, expected_generation)
    if lookup is None:
        return None
    metrics.called('batch')
    if enforce and lookup.decision is not None and lookup.decision.fresh():
        if on_hit is not None:
            on_hit(uid, ids, site, lookup.decision)
        cache.TOKENLESS.labels(f'{site}_hit').inc()
        metrics.decision('batch')
        return lookup.decision.generation
    return _read_and_cache_tokenless(
        client,
        transaction,
        uid,
        lookup,
        ids,
        started,
        shadow=shadow,
        site=site,
        expected_generation=expected_generation,
        read_budget=read_budget,
    )


def _read_and_cache_tokenless(
    client, transaction, uid, lookup, ids, started, *, shadow, site, expected_generation, read_budget
):
    walk: dict[str, Any] = {}
    snapshot, version = None, None

    def compare(generation):
        if shadow and lookup.decision is not None:
            try:
                cache.compare_tokenless(site, lookup.decision, snapshot, version, generation)
            except Exception:
                cache.TOKENLESS_SHADOW.labels(site, 'unavailable').inc()

    try:
        reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))
        snapshot = metrics.read_snapshot('batch', reference, transaction=transaction, read_budget=read_budget)
        version = token_version(snapshot)
        generation = read_live_batch_write_authority(
            client,
            transaction,
            uid,
            conversation_ids=ids,
            expected_generation=expected_generation,
            privacy_snapshot=snapshot,
            read_budget=read_budget,
            walk_out=walk,
        )
    except BatchPrivacyBlocked as error:
        metrics.decision('batch', error.reason.value)
        compare(None)
        raise
    except Exception:
        metrics.decision('batch', 'authority_unavailable')
        if shadow and lookup.decision is not None:
            cache.TOKENLESS_SHADOW.labels(site, 'unavailable').inc()
        raise
    metrics.decision('batch')
    compare(generation)
    if version is not None:
        try:
            cache.store_tokenless(lookup, ids | walk.get('verified', set()), snapshot, version, generation, started)
        except Exception:
            cache.TOKENLESS.labels('set_error').inc()
    return generation


def _same_value(before, after):
    # Python equates bools, integers and floats. Preserve Firestore types on
    # fields whose contents cannot change in a metadata-only write.
    if type(before) is not type(after):
        return False
    if isinstance(before, dict):
        return before.keys() == after.keys() and all(_same_value(value, after[key]) for key, value in before.items())
    if isinstance(before, list):
        return len(before) == len(after) and all(_same_value(left, right) for left, right in zip(before, after))
    return before == after


def _changed_fields(previous, row):
    return {
        field
        for field in previous.keys() | row.keys()
        if not _same_value(previous.get(field, _ABSENT), row.get(field, _ABSENT))
    }


def _nonnegative_number(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def _job_lease(key, previous, row):
    attempt = previous.get('attempt', 0)
    generation = previous.get('privacy_generation')
    changed = _changed_fields(previous, row)
    return (
        previous.get('state') == 'ready'
        and row.get('state') == 'leased'
        and previous.get('segment_id') == key
        and previous.get('requires_compute_admission') is True
        and row.get('requires_compute_admission') is True
        and type(generation) is int
        and generation >= 0
        and type(row.get('privacy_generation')) is int
        and _nonnegative_number(attempt)
        and type(row.get('attempt')) is int
        and row['attempt'] == attempt + 1
        and isinstance(row.get('token'), str)
        and bool(row['token'])
        and row['token'] != previous.get('token')
        and _nonnegative_number(row.get('lease_until'))
        and row['lease_until'] > 0
        and ('unit_kind' not in changed or ('unit_kind' not in previous and row.get('unit_kind') == 'conversation'))
        and (
            'record_first_leased_at' not in changed
            or (
                'record_first_leased_at' not in previous
                and bool((previous.get('projection_binding') or {}).get('native_record'))
                and attempt == 0
                and not previous.get('admission_refusals')
                and _nonnegative_number(row.get('record_first_leased_at'))
            )
        )
        and changed <= LEASE_FIELDS
    )


def _queue_lease(key, previous, row, jobs):
    if not (
        _changed_fields(previous, row) <= QUEUE_FIELDS
        and type(row.get('continuing')) is bool
        and _nonnegative_number(row.get('deficit'))
    ):
        return False
    head = previous.get('head')
    members = {segment: job for segment, job in jobs.items() if key == f"{job.get('priority')}_{job.get('owner_key')}"}
    if not members:
        return False
    while isinstance(head, str) and head in members:
        head = members.pop(head).get('next')
    if members or not isinstance(head, str) or row.get('head') != head:
        return False
    if head:
        return row.get('tail') == previous.get('tail') and row['continuing'] is True
    return row.get('tail') == '' and row['deficit'] == 0 and row['continuing'] is False


def _control_lease(previous, row, drained_queues, jobs):
    priorities = {str(job.get('priority')) for job in jobs.values()}
    if not priorities <= PRIORITIES:
        return False
    before_rings, after_rings = previous.get('rings'), row.get('rings')
    if (
        not isinstance(before_rings, dict)
        or not isinstance(after_rings, dict)
        or before_rings.keys() != after_rings.keys()
    ):
        return False
    allowed = {'rings'}
    for priority, after in after_rings.items():
        before = before_rings[priority]
        if priority not in priorities:
            if after != before:
                return False
            continue
        active, service, hint = (f'p{priority}_{name}' for name in ('active', 'service', 'frontier_hint'))
        allowed.update((active, service, hint))
        if not (
            isinstance(before, list)
            and isinstance(after, list)
            and all(isinstance(queue, str) for queue in before + after)
            and len(after) == len(set(after))
            and set(after) == set(before) - drained_queues
            and row.get(active) is bool(after)
            and _nonnegative_number(previous.get(service))
            and _nonnegative_number(row.get(service))
            and row[service] >= previous[service]
            and hint not in row
        ):
            return False
    return priorities <= after_rings.keys() and _changed_fields(previous, row) <= allowed


def _only_existing_leases(view) -> bool:
    if view.patches or view.external:
        return False
    jobs = {}
    for address, row in view.writes.items():
        table, key = address
        # An absent or unread original never qualifies, even if it has a buffered row.
        if not view.exists.get(address):
            return False
        if table == 'jobs':
            if not _job_lease(key, view.cache[address], row):
                return False
            jobs[key] = row
    if not jobs:
        return False
    for job in jobs.values():
        gpu_key = job.get('shared_gpu_key', '')
        if not isinstance(gpu_key, str) or (gpu_key and ('gpus', gpu_key) not in view.writes):
            return False

    drained_queues = {key for (table, key), row in view.writes.items() if table == 'queues' and row.get('head') == ''}
    operation = current_operation()
    for (table, key), row in view.writes.items():
        previous = view.cache[table, key]
        if table == 'jobs':
            continue
        if table == 'queues' and _queue_lease(key, previous, row, jobs):
            continue
        if table == 'gpus':
            segment = row.get('segment_id')
            job = jobs.get(segment) if isinstance(segment, str) else None
            if (
                job is not None
                and not previous.get('token')
                and job.get('shared_gpu_key') == key
                and row == {'segment_id': segment, 'token': job['token'], 'lease_until': job['lease_until']}
                and _changed_fields(previous, row) <= {'segment_id', 'token', 'lease_until', 'released_token'}
            ):
                continue
        if operation == f'batch_pull shard={key}':
            if table == 'control' and _control_lease(previous, row, drained_queues, jobs):
                continue
            if (
                table == 'pull_claims'
                and set(previous) == {'token', 'expires_at'}
                and isinstance(previous['token'], str)
                and previous['token']
                and _nonnegative_number(previous['expires_at'])
                and previous['expires_at'] > 0
                and row == {'token': '', 'expires_at': 0.0}
            ):
                continue
        return False
    return True


def authorize_buffered_writes(view) -> None:
    lease_mode = lever_percent('bpp_tokenless_write_cache') or lever_percent('bpp_tokenless_write_shadow')
    lease_only = lease_mode > 0 and _only_existing_leases(view)
    guarded = set()
    for (table, key), value in view.writes.items():
        if table not in {'jobs', 'results', 'coalesce_groups', 'coalesce_sources', 'coalesce_heads'}:
            continue
        job = view.get('jobs', key) if table == 'results' else value
        identity = (
            job['owner_id'],
            job.get('conversation_id'),
            job.get('capture_source_conversation_id'),
            job.get('privacy_generation'),
        )
        if identity in guarded:
            continue
        guarded.add(identity)
        generation = view._check_privacy(
            job['owner_id'],
            conversation_ids=tuple(
                value for value in (job.get('conversation_id'), job.get('capture_source_conversation_id')) if value
            ),
            expected_generation=job.get('privacy_generation'),
            site='lease' if lease_only else None,
        )
        if table == 'jobs' and value.get('privacy_generation') is None:
            value['privacy_generation'] = generation
