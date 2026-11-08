"""The five timed jobs readers emit constant, scoped billed-read origins."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database import batch_pipeline_quarantine_recovery as recovery
from database import batch_pipeline_store as store
from database import firestore_document_probe as probe
from database import firestore_read_origin as origin
from database import record_seal_worker as seal_worker
from tests.unit.test_batch_pipeline_timeliness import _Client, _Query, EPOCH, NOW, SLA
from utils.batch_pipeline import record_seal_cluster_repair as repair


@pytest.mark.parametrize(
    'reader', ['held_candidates', 'recovery_candidates', 'discover_jobs', 'pending_page', 'timeliness_sample']
)
def test_each_reader_emits_a_closed_origin_and_restores_parent(monkeypatch, reader):
    module = {
        'held_candidates': recovery,
        'recovery_candidates': recovery,
        'discover_jobs': repair,
        'pending_page': seal_worker,
        'timeliness_sample': store,
    }[reader]
    expected = f'job:{module.__name__.split(".")[-1]}:{reader}'
    counter = probe.FIRESTORE_BILLED_READS_BY_ORIGIN.labels(
        origin=expected, collection='batch_pipeline_prod_jobs', kind='query'
    )
    before = counter._value.get()
    seen = []

    def stream(*args, **kwargs):
        seen.append(origin.current_read_origin())
        # Exercise the existing billed-read recorder inside the real reader's
        # query scope; no exporter or Firestore client is created by this test.
        probe._record(('batch_pipeline_prod_jobs', 'unit'), True, kind='query')
        return []

    client = MagicMock()
    query = client.collection.return_value
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    query.stream.side_effect = stream
    with origin.read_origin('job:parent'):
        if reader == 'held_candidates':
            recovery.held_candidates(client, 'ns')
        elif reader == 'recovery_candidates':
            recovery.recovery_candidates(client, 'ns', None)
        elif reader == 'discover_jobs':
            repair.discover_jobs(client, budget=MagicMock())
        elif reader == 'pending_page':
            seal_worker.pending_page(client, 'ns', horizon=datetime.now(timezone.utc))
        else:
            monkeypatch.setattr(_Query, 'stream', stream)
            store.timeliness_sample(_Client(), 'ns', EPOCH, NOW, SLA)
        assert origin.current_read_origin() == 'job:parent'
    assert seen and set(seen) == {expected}
    assert counter._value.get() == before + len(seen)
