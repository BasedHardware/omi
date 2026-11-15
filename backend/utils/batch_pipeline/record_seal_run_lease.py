"""One proof coordinator per partition, including duplicate Indexed Job pods.

This maintenance-only lease outlives the Job's hard 1680s ceiling. It never
changes a recording or supplies producer/privacy authority. Children are reaped
before release; a dead coordinator leaves a bounded 1800s recovery wait.
"""

import uuid

from google.cloud import firestore


class RepairRunLease:
    def __init__(self, client, shard, shards):
        self.client = client
        self.ref = client.collection('batch_pipeline_prod_maintenance').document(f'record_seal_run_{shards}_{shard}')
        self.token = uuid.uuid4().hex

    def acquire(self, now):
        @firestore.transactional
        def claim(tx):
            current = self.ref.get(transaction=tx, timeout=3, retry=None).to_dict() or {}
            if current.get('until', 0) > now:
                return False
            tx.set(self.ref, {'until': now + 1800, 'token': self.token})
            return True

        return claim(self.client.transaction(max_attempts=3))

    def release(self):
        @firestore.transactional
        def clear(tx):
            current = self.ref.get(transaction=tx, timeout=3, retry=None).to_dict() or {}
            if current.get('token') == self.token:
                tx.set(self.ref, {'until': 0, 'token': ''})

        clear(self.client.transaction(max_attempts=3))
