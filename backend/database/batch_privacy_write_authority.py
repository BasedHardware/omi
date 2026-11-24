"""Select eligible scheduler write evidence and keep shadow observational."""

import time
from typing import Any

from config.firestore_read_levers import lever_enabled, lever_percent
from database import batch_privacy_write_cache as cache, privacy_check_metrics as metrics
from database.batch_pipeline_privacy import (
    BatchPrivacyBlocked,
    PRIVACY_COLLECTION,
    read_live_batch_write_authority,
    privacy_owner_key,
)
from database.batch_privacy_attempt import token_version
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
        'last_policy_hold',
        'policy_parts',
        'unit_kind',
    }
)
LEASE_TABLES = frozenset({'jobs', 'queues', 'gpus', 'control', 'pull_claims'})


@metrics.with_batch_plan
def check_cached_write(client, transaction, uid, *, conversation_ids, expected_generation, read_budget, site=None):
    """Return a generation when handled here, otherwise leave certification to the caller."""
    shadow = lever_enabled('bpp_tokenless_write_shadow', uid)
    enforce = (
        site is not None
        and lever_enabled('bpp_tokenless_write_cache', uid)
        and lever_percent('bpp_tokenless_write_shadow') == 0
    )
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
    if enforce and lookup.decision is not None:
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
        expected_generation=expected_generation,
        read_budget=read_budget,
    )


def _read_and_cache_tokenless(
    client, transaction, uid, lookup, ids, started, *, shadow, expected_generation, read_budget
):
    walk: dict[str, Any] = {}
    snapshot, version = None, None

    def compare(generation):
        if shadow and lookup.decision is not None:
            try:
                cache.compare_tokenless(lookup.decision, snapshot, version, generation)
            except Exception:
                cache.TOKENLESS_SHADOW.labels('unavailable').inc()

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
            cache.TOKENLESS_SHADOW.labels('unavailable').inc()
        raise
    metrics.decision('batch')
    compare(generation)
    if version is not None:
        try:
            cache.store_tokenless(lookup, ids | walk.get('verified', set()), snapshot, version, generation, started)
        except Exception:
            cache.TOKENLESS.labels('set_error').inc()
    return generation


def _only_existing_leases(view) -> bool:
    if view.patches or view.external or not view.writes:
        return False
    for (table, key), next_row in view.writes.items():
        if table not in LEASE_TABLES:
            return False
        if table != 'jobs':
            continue
        previous = view.cache.get((table, key))
        if not previous or previous.get('state') != 'ready' or next_row.get('state') != 'leased':
            return False
        # This lease is followed by independent, live compute authorization.
        if previous.get('requires_compute_admission') is not True:
            return False
        generation = previous.get('privacy_generation')
        if type(generation) is not int or generation < 0:
            return False
        fields = previous.keys() | next_row.keys()
        if any(previous.get(field) != next_row.get(field) for field in fields - LEASE_FIELDS):
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
