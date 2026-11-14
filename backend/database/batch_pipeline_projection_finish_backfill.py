"""One resumable stamping pass, shared by all projection-serving processes.

Deploy unconditional clock writers everywhere before running this pass. Its
cursor and versioned completion marker live in the same namespace as the rows.
Each page commits its stamps and checkpoint atomically; concurrent invocations
cannot advance a stale checkpoint or declare an incomplete pass complete.
"""

from google.cloud import firestore

from database.batch_pipeline_projection_finish import (
    PROJECTION_FINISH_DUE_FIELD,
    PROJECTION_FINISH_STATES,
    projection_finish_state_fields,
)

BACKFILL_VERSION = 1
BACKFILL_KEY = f'projection_finish_clock_v{BACKFILL_VERSION}'


def backfill_ref(client, namespace):
    return client.collection(f'{namespace}_control').document(BACKFILL_KEY)


def backfill_complete(client, namespace) -> bool:
    marker = backfill_ref(client, namespace).get().to_dict() or {}
    return backfill_marker_complete(marker)


def backfill_marker_complete(marker: dict) -> bool:
    """Trust only this version's completion in the selected store/namespace."""
    return marker.get('version') == BACKFILL_VERSION and marker.get('complete') is True


def stamp_page(store, now: float, *, size: int = 200, apply: bool = False) -> dict:
    """Inspect at most 200 rows; apply resumes from the last committed page.

    No projection receipt, state, payload, or existing backoff clock is changed.
    Transactional re-reads fence rows that transitioned since discovery. Failure
    leaves the checkpoint unchanged; a retry visits that page again.
    """
    marker_ref = backfill_ref(store.client, store.namespace)
    before = marker_ref.get().to_dict() or {}
    if before.get('version') == BACKFILL_VERSION and before.get('complete') is True:
        return {'complete': True, 'scanned': 0, 'missing': 0, 'stamped': 0}
    after = tuple(before['after']) if before.get('after') else None
    ids, cursor = store.projection_page(size, after=after, states=PROJECTION_FINISH_STATES)
    refs = [store.client.collection(f'{store.namespace}_results').document(sid) for sid in ids]

    def missing(row):
        return row.get('projection_state') in PROJECTION_FINISH_STATES and PROJECTION_FINISH_DUE_FIELD not in row

    if not apply:
        count = sum(missing(ref.get().to_dict() or {}) for ref in refs)
        return {'complete': False, 'scanned': len(ids), 'missing': count, 'stamped': 0}

    @firestore.transactional
    def commit(transaction):
        current = marker_ref.get(transaction=transaction).to_dict() or {}
        if current != before:
            raise RuntimeError('backfill checkpoint changed; retry from durable progress')
        # One BatchGet per page, not one RPC per row: 200 serial transactional reads from an
        # operator host cost about 17 s a page, which made the pass a 12-hour job. The read set
        # and the transaction's conflict fence are the same documents either way.
        fetched = store.client.get_all(refs, transaction=transaction) if refs else ()
        snapshots = {snapshot.reference.path: snapshot for snapshot in fetched}
        rows = [snapshots[ref.path].to_dict() or {} for ref in refs]
        count = 0
        for ref, row in zip(refs, rows):
            if missing(row):
                transaction.update(ref, projection_finish_state_fields(row['projection_state'], now))
                count += 1
        transaction.set(
            marker_ref,
            {
                'version': BACKFILL_VERSION,
                'after': list(cursor) if cursor else None,
                'complete': cursor is None,
                'updated_at': now,
            },
        )
        return {'complete': cursor is None, 'scanned': len(ids), 'missing': count, 'stamped': count}

    return commit(store.client.transaction())
