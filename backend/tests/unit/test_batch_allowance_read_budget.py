"""Count actual transaction reads, including both job privacy fences and queue tail."""

from collections import Counter

import pytest

from database.batch_pipeline_allowance_hold import OWNERS, park
from database.batch_pipeline_store import FirestoreTransaction
from testing.store_fixtures import make_sim
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key


@pytest.mark.parametrize('transition', ['release', 'migration'])
@pytest.mark.parametrize('redirects,expected', [(-1, (9, 6)), (0, (16, 8)), (2, (24, 12))])
def test_actual_read_envelope_with_existing_tail_and_conversation_fences(monkeypatch, transition, redirects, expected):
    monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', 'off')
    # Measure the full uncached privacy walks rather than process-local cache hits.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":0,"privacy_negative_lookup_cache":0}')
    h = make_sim()
    try:
        uid = h.seed_user('synthetic')
        for prefix in ('held', 'tail'):
            if redirects >= 0:
                h.customer.add_conversation(uid, f'{prefix}-0')
                for index in range(redirects):
                    h.customer.merge_conversation(uid, f'{prefix}-{index}', f'{prefix}-{index + 1}')
        queue = Scheduler(h.store)
        for segment in ('held', 'tail'):
            work = WorkItem(
                segment,
                uid,
                1 if segment == 'held' else 2,
                f'gs://synthetic/{segment}',
                30,
                Priority.DEEP,
                conversation_id=f'{segment}-0' if redirects >= 0 else None,
            )
            queue.enqueue(work, 0)
            if segment == 'held':
                lease = queue.pull(1)[0]
                assert queue.defer('held', lease.token, 2, held_reason='allowance_exhausted')
        if transition == 'release':
            assert h.store.run(lambda tx: park(tx, tx.get('jobs', 'held'), 3))
        client = h.customer.client
        for (table, key), value in h.store.rows.items():
            client.rows[(f'{h.namespace}_{table}', key)] = value
        reads = Counter()
        original = StrictFirestoreDocument.get

        def counted(self, *args, **kwargs):
            reads[self.path[0]] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
        tx = FirestoreTransaction(client, h.namespace, client.transaction())
        if transition == 'release':
            key = owner_key(uid)
            owner = tx.get(OWNERS, key)
            job = tx.get('jobs', 'held')
            Scheduler.release_allowance_in_transaction(tx, job, 10)
            owner['held_count'] -= 1
            tx.put(OWNERS, key, owner)
        else:
            assert park(tx, tx.get('jobs', 'held'), 10)
        tx.flush()
        # Discovery is one additional read, not part of the point transaction.
        assert sum(reads.values()) + 1 == expected[0 if transition == 'release' else 1], reads
    finally:
        h.close()
