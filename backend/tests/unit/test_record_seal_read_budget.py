"""Planning model for repair Firestore reads; real privacy walk, synthetic audio IO."""

from functools import partial
from collections import Counter

from database import batch_pipeline_privacy
from utils.batch_pipeline import record_seal_cluster_repair as cluster
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.record_seal_budget import SweepBudget
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_record_seal_nojob import source, SCOPE, SERVER, PATH, JOB_PATH
from tests.unit.test_record_seal_cluster_repair import proof


def test_uncontended_canonical_seal_read_budget_with_live_privacy_walk(source, proof, monkeypatch):
    store, client, artifacts = source
    content, segment = cluster.record_identity('synthetic', 'capture')
    client.rows[JOB_PATH] = {
        'segment_id': segment,
        'owner_id': 'synthetic',
        'conversation_id': 'capture',
        'state': 'record_pending',
        'record_content_id': content,
        'privacy_generation': 0,
        'record_snapshot': {'finished_at': client.rows[PATH]['finished_at']},
    }
    monkeypatch.setattr(batch_pipeline_privacy, 'lever_enabled', lambda *a: False)
    artifacts.authorize = partial(batch_artifact_authorize, store)
    counts = Counter()
    original = StrictFirestoreDocument.get

    def read(reference, *args, **kwargs):
        counts['total'] += 1
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', read)
    assert (
        cluster.repair_one(store, object(), artifacts, SCOPE[0], flags=SERVER, inventory=proof, budget=SweepBudget(10))
        == 'sealed'
    )
    # Discovery, transaction retries, SDK-installed write fences and optional
    # policy/cache probes are outside this uncontended leaf-read measurement.
    assert counts['total'] == 20  # Committed revision + three ledger fence reads.
