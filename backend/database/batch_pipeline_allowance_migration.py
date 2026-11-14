"""Resumable CAS migration of current allowance decisions; no content reads."""

from google.cloud import firestore

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_allowance_hold import STATE, enabled, park

KEY = 'allowance_parking_v1'


def candidates(store):
    return (
        store.client.collection(f'{store.namespace}_jobs')
        .where('state', '==', 'retry')
        .where('compute_decision.outcome', '==', 'held')
        .where('compute_decision.reason', '==', 'allowance_exhausted')
    )


def counts(store) -> dict:
    """COUNT aggregations only: a dry run never reads or prints a user row."""
    jobs = store.client.collection(f'{store.namespace}_jobs')
    return {
        'retry': int(jobs.where('state', '==', 'retry').count().get()[0][0].value),
        'allowance_retry': int(candidates(store).count().get()[0][0].value),
        'policy_held': int(jobs.where('state', '==', STATE).count().get()[0][0].value),
    }


def apply_page(store, now: float, *, size: int = 100) -> dict:
    if not enabled():
        raise ValueError('parking switch is off')
    size = max(1, min(size, 100))
    progress = store.client.collection(f'{store.namespace}_migrations').document(KEY)
    checkpoint = progress.get().to_dict() or {}
    query = candidates(store).order_by('__name__')
    if checkpoint.get('after'):
        ref = store.client.collection(f'{store.namespace}_jobs').document(checkpoint['after'])
        query = query.start_after({'__name__': ref})
    rows = list(query.limit(size).select([]).stream())
    parked, fenced = 0, 0
    for snapshot in rows:

        def migrate(tx):
            job = tx.get('jobs', snapshot.id)
            return park(tx, job, now)

        try:
            parked += store.run(migrate)
        except BatchPrivacyBlocked:
            fenced += 1  # Erasure owns the row; never bypass its authority.
    # A crash before this write replays only this bounded page. park's state
    # predicate makes that replay idempotent. A failure never advances it.
    complete = len(rows) < size

    @firestore.transactional
    def checkpoint_page(transaction):
        current = progress.get(transaction=transaction).to_dict() or {}
        if current != checkpoint:
            raise RuntimeError('migration checkpoint changed; resume durable progress')
        transaction.set(progress, {'after': None if complete else rows[-1].id, 'complete': complete, 'updated_at': now})

    checkpoint_page(store.client.transaction())
    return {'examined': len(rows), 'parked': parked, 'fenced': fenced, 'complete': complete}
