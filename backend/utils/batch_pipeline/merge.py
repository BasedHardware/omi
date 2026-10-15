"""Ordered durable result log. Projection consumers must use stable segment IDs."""

from database.batch_pipeline_store import Store
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.metrics import QueueMetrics


class OrderedMerge:
    def __init__(self, store: Store, *, metrics: QueueMetrics | None = None):
        self.store = store
        self.metrics = metrics

    def commit_next(self, owner_id: str, now: float) -> dict | None:
        key = owner_key(owner_id)

        def commit(tx):
            owner = tx.get('owners', key)
            candidate = tx.first_pending(key)
            if not candidate or candidate['state'] != 'result_ready':
                return None
            job = tx.get('jobs', candidate['segment_id'])
            existing = tx.get('results', job['segment_id'])
            if existing:
                raise RuntimeError('result log exists for pending job; reconciliation required')
            watermark = owner.get('watermark')
            position = {'capture_at': job['capture_at'], 'segment_id': job['segment_id']}
            if watermark and (position['capture_at'], position['segment_id']) <= (
                watermark['capture_at'],
                watermark['segment_id'],
            ):
                raise RuntimeError('non-monotone merge candidate')
            entry = {
                **position,
                'owner_key': key,
                'result': job['result'],
                'committed_at': now,
                'projection_state': 'pending',
            }
            tx.put('results', job['segment_id'], entry)
            job.update(state='committed', merge_pending=False)
            tx.put('jobs', job['segment_id'], job)
            owner.update(watermark=position, revision=owner.get('revision', 0) + 1)
            tx.put('owners', key, owner)
            return entry

        entry = self.store.run(commit)
        if entry and self.metrics:
            self.metrics.record('committed')
        return entry

    def committed_result(self, segment_id: str) -> dict:
        """Idempotent re-read after a lost commit reply; no external side effects."""
        return self.store.run(lambda tx: tx.get('results', segment_id))
