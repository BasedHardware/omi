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
            # Terminal quarantine atomically removes merge_pending; it never
            # enters this success log or the projection predecessor chain.
            candidate = tx.first_pending(key)
            if not candidate or candidate['state'] != 'result_ready':
                return None
            job = tx.get('jobs', candidate['segment_id'])
            existing = tx.get('results', job['segment_id'])
            if existing:
                raise RuntimeError('result log exists for pending job; reconciliation required')
            watermark = owner.get('watermark')
            position = {'capture_at': job['capture_at'], 'segment_id': job['segment_id']}
            late = bool(
                watermark
                and (position['capture_at'], position['segment_id'])
                <= (watermark['capture_at'], watermark['segment_id'])
            )
            tail = owner.get('log_tail', watermark['segment_id'] if watermark else None)
            entry = {
                **position,
                'protocol_version': job['protocol_version'],
                'owner_key': key,
                'owner_id': job['owner_id'],
                'conversation_id': job.get('conversation_id'),
                'privacy_generation': job.get('privacy_generation'),
                'previous_segment_id': tail,
                'late_capture': late,
                'log_sequence': owner.get('log_sequence', 0) + 1,
                'result': job['result'],
                'committed_at': now,
                'projection_state': 'pending',
            }
            if job.get('recovery_state') == 'recovered':
                entry['recovery_version'] = 1
            tx.put('results', job['segment_id'], entry)
            job.update(state='committed', merge_pending=False)
            tx.put('jobs', job['segment_id'], job)
            owner.update(
                watermark=watermark if late else position,
                log_tail=job['segment_id'],
                log_sequence=entry['log_sequence'],
                revision=owner.get('revision', 0) + 1,
            )
            tx.put('owners', key, owner)
            return entry

        entry = self.store.run(commit)
        if entry and self.metrics:
            self.metrics.record('committed')
        return entry

    def committed_result(self, segment_id: str) -> dict:
        """Idempotent re-read after a lost commit reply; no external side effects."""
        return self.store.run(lambda tx: tx.get('results', segment_id))
