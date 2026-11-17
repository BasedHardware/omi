"""Bounded sampled-prefix proof for the three Firestore-authoritative due hints.

The primary prefix is complete only within its existing limit. Selected rows
in that prefix must be discoverable; every PG hint must equal its current
selected primary document. Valid hints beyond the primary prefix are allowed.
This is not a claim of whole-backlog coverage or of custody authority.
"""

from __future__ import annotations

import time

from database import rpc_deadline
from database.batch_pipeline_shadow_hook import shadow_mode_enabled
import database.jobstore.codec as codec
from database.jobstore.cohort import project_document
from database.jobstore.connection import sql
from database.jobstore.dual_store import mirrored, read_current, shadow_writes_enabled
from utils.staging_fence import jobstore_mirror_factory_admits

_FIELDS = {'leased': 'lease_until', 'retry': 'available_at', 'result_ready': 'enqueued_at'}


def compare_sampled_due(primary, shadow, args: tuple, kwargs: dict, budget_s: float) -> str:
    from database.jobstore.index_store import BoundedPostgresReader, connection_deadline

    state = args[0] if args else kwargs.get('state')
    now = args[1] if len(args) > 1 else kwargs.get('now')
    limit = args[2] if len(args) > 2 else kwargs.get('limit', 100)
    if not isinstance(state, str) or state not in _FIELDS or not isinstance(now, (int, float)):
        return 'unknown'
    if (
        not jobstore_mirror_factory_admits(primary.namespace)
        or not shadow_mode_enabled()
        or not shadow_writes_enabled()
    ):
        return 'unknown'
    deadline = time.monotonic() + budget_s
    if getattr(primary, 'client', None) is not None:
        rpc_deadline.bind_firestore_client(primary.client)

    def observe():
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError('sampled due observation deadline')
        primary_keys = primary.due(state, now, limit)
        copy_keys = BoundedPostgresReader(shadow, left).due(state, now, limit)
        keys = sorted(set(primary_keys) | set(copy_keys))
        current = read_current(primary, [('jobs', key) for key in keys])
        with shadow.pool.connection(timeout=max(0, deadline - time.monotonic()), existing_only=True) as conn:
            with connection_deadline(conn, deadline), conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute(
                    sql()
                    .SQL('SET LOCAL statement_timeout = {}')
                    .format(sql().Literal(max(1, int((deadline - time.monotonic()) * 1000))))
                )
                copies = {key: shadow.read_doc(conn, 'jobs', key) for key in copy_keys}
        selected = {
            key: project_document(primary.namespace, 'jobs', key, current.get(('jobs', key), {})) for key in keys
        }
        expected = [key for key in primary_keys if selected[key]]
        # An expired/moved primary prefix is a racing observation, never a pass.
        for key in primary_keys:
            doc = current.get(('jobs', key), {})
            if not doc or doc.get('state') != state or doc.get(_FIELDS[state], float('inf')) > now:
                return (
                    'unknown',
                    primary_keys,
                    copy_keys,
                    codec.canonical([(key, current.get(('jobs', key), {})) for key in keys]),
                    codec.canonical(copies),
                )
        valid = set(expected) <= set(copy_keys)
        for key in copy_keys:
            doc = selected[key]
            if not doc:
                valid = False
                continue
            valid = valid and doc.get('state') == state and doc.get(_FIELDS[state], float('inf')) <= now
            valid = valid and codec.canonical(mirrored(doc, 'jobs')) == codec.canonical(copies[key])
        # Selected primary rows retain their order within the returned hint prefix.
        valid = valid and [key for key in copy_keys if key in set(expected)] == expected
        outcome = ('match' if valid else 'mismatch') if expected or copy_keys else 'unknown'
        return (
            outcome,
            primary_keys,
            copy_keys,
            codec.canonical([(key, current.get(('jobs', key), {})) for key in keys]),
            codec.canonical(copies),
        )

    with rpc_deadline.rpc_deadline(deadline):
        before, after = observe(), observe()
    if time.monotonic() > deadline:
        raise TimeoutError('sampled due observation deadline')
    active = jobstore_mirror_factory_admits(primary.namespace) and shadow_mode_enabled() and shadow_writes_enabled()
    return before[0] if before == after and active else 'unknown'
