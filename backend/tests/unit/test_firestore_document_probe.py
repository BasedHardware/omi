"""The document-read probe must count every lookup and query read, and never break one."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from database.firestore_document_probe import (  # noqa: E402
    FIRESTORE_DOCUMENT_READS,
    FIRESTORE_QUERY_OPERATIONS,
    collection_pattern,
    install_document_read_probe,
)


from database import firestore_tier_context as tier_context


@pytest.fixture(autouse=True, params=['unattributed', 'basic', 'plus'])
def request_tier(request):
    owner = tier_context._RequestOwner(tier=request.param, expires_at=time.monotonic() + 60)
    token = tier_context._request_owner.set(owner)
    yield
    tier_context._request_owner.reset(token)


def _count(collection: str, outcome: str) -> float:
    value = FIRESTORE_DOCUMENT_READS.labels(
        collection=collection, outcome=outcome, tier=tier_context.current_tier()
    )._value.get()
    return float(value or 0)


def _count_operations(collection: str) -> float:
    value = FIRESTORE_QUERY_OPERATIONS.labels(collection=collection, tier=tier_context.current_tier())._value.get()
    return float(value or 0)


class _Snapshot:
    def __init__(self, exists, reference=None):
        self.exists = exists
        self.reference = reference


class _Ref:
    def __init__(self, path):
        self._path = path


def test_collection_pattern_strips_document_ids():
    assert collection_pattern(('users', 'uid-abc', 'conversations', 'conv-def')) == 'users/conversations'
    assert collection_pattern(('account_deletions', 'uid-abc')) == 'account_deletions'
    assert collection_pattern(('users', 'uid-abc')) == 'users'


def test_collection_pattern_bounds_cardinality():
    # An unreviewed collection must not mint a new label value.
    assert collection_pattern(('some_new_collection', 'id')) == 'other'
    # A user-derived value can never survive into a label.
    assert 'uid-abc' not in collection_pattern(('users', 'uid-abc', 'unreviewed', 'x'))
    assert collection_pattern(()) == 'unknown'
    assert collection_pattern(None) == 'unknown'


def test_collection_pattern_names_the_live_other_hot_paths():
    # These currently dominate collection="other" on the billed read line.
    # Nested conversation photos must not collapse to users/conversations or other.
    assert collection_pattern(('users', 'uid-abc', 'hourly_usage', '2026-09-01-00')) == 'users/hourly_usage'
    assert collection_pattern(('users', 'uid-abc', 'messages', 'msg-1')) == 'users/messages'
    assert (
        collection_pattern(('users', 'uid-abc', 'conversations', 'conv-1', 'photos', 'photo-1'))
        == 'users/conversations/photos'
    )
    assert collection_pattern(('users', 'uid-abc', 'memories', 'mem-1')) == 'users/memories'
    assert collection_pattern(('users', 'uid-abc', 'candidates', 'cand-1')) == 'users/candidates'
    assert collection_pattern(('users', 'uid-abc', 'knowledge_nodes', 'node-1')) == 'users/knowledge_nodes'
    assert collection_pattern(('users', 'uid-abc', 'knowledge_edges', 'edge-1')) == 'users/knowledge_edges'


def test_probe_counts_hit_and_miss_and_returns_snapshot_unchanged():
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    DocumentReference = firestore_document.DocumentReference

    calls = []

    def fake_get(self, *args, **kwargs):
        calls.append(self._path)
        return _Snapshot(exists=self._path[-1] == 'present')

    original = DocumentReference.get
    setattr(DocumentReference, 'get', fake_get)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        hit_before = _count('users/conversations', 'hit')
        miss_before = _count('users/conversations', 'miss')

        present = DocumentReference.__new__(DocumentReference)
        present._path = ('users', 'u1', 'conversations', 'present')
        absent = DocumentReference.__new__(DocumentReference)
        absent._path = ('users', 'u1', 'conversations', 'absent')

        assert DocumentReference.get(present).exists is True
        assert DocumentReference.get(absent).exists is False

        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count('users/conversations', 'miss') == miss_before + 1
        # The underlying read still ran exactly twice: the probe observes, never skips.
        assert len(calls) == 2
    finally:
        setattr(DocumentReference, 'get', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_recording_failure_never_propagates(monkeypatch):
    import database.firestore_document_probe as probe

    class _Exploding:
        def labels(self, **kwargs):
            raise RuntimeError('registry unavailable')

    monkeypatch.setattr(probe, 'FIRESTORE_DOCUMENT_READS', _Exploding())
    # Must not raise: a telemetry fault may never break a Firestore read.
    probe._record(('users', 'u1', 'conversations', 'c1'), True)


def test_operation_recording_failure_never_propagates(monkeypatch):
    import database.firestore_document_probe as probe

    class _Exploding:
        def labels(self, **kwargs):
            raise RuntimeError('registry unavailable')

    monkeypatch.setattr(probe, 'FIRESTORE_QUERY_OPERATIONS', _Exploding())
    # Must not raise: a telemetry fault may never break a Firestore query.
    probe._record_operation(('users', 'u1', 'conversations'))


def test_probe_counts_each_document_in_a_batch_read():
    firestore_client_mod = pytest.importorskip('google.cloud.firestore_v1.client')
    Client = firestore_client_mod.Client

    def fake_get_all(self, references, *args, **kwargs):
        for ref in references:
            yield _Snapshot(exists=ref._path[-1] == 'present', reference=ref)

    original = Client.get_all
    setattr(Client, 'get_all', fake_get_all)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        hit_before = _count('users/conversations', 'hit')
        miss_before = _count('users/conversations', 'miss')

        refs = [
            _Ref(('users', 'u1', 'conversations', 'present')),
            _Ref(('users', 'u1', 'conversations', 'absent')),
            _Ref(('users', 'u1', 'conversations', 'absent')),
        ]
        client = Client.__new__(Client)
        snapshots = list(Client.get_all(client, refs))

        # Every snapshot is still handed back, in order, unmodified.
        assert [s.exists for s in snapshots] == [True, False, False]
        # A batch read bills per document, so each one is counted.
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count('users/conversations', 'miss') == miss_before + 2
    finally:
        setattr(Client, 'get_all', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_counts_each_document_lazily():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    consumed = []
    snapshots = [
        _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1'))),
        _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c2'))),
        _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c3'))),
    ]

    def fake_stream(self, *args, **kwargs):
        def gen():
            for snapshot in snapshots:
                consumed.append(snapshot.reference._path[-1])
                yield snapshot

        return gen()

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        hit_before = _count('users/conversations', 'hit')
        ops_before = _count_operations('users/conversations')
        query = Query.__new__(Query)
        # A real Query always carries its parent collection; the ops counter
        # reduces through it.
        query._parent = _Ref(('users', 'u1', 'conversations'))
        iterator = Query.stream(query)

        # The underlying generator must not be consumed until the caller pulls.
        assert consumed == []
        assert _count('users/conversations', 'hit') == hit_before
        assert _count_operations('users/conversations') == ops_before

        first = next(iterator)
        assert first.reference._path[-1] == 'c1'
        assert consumed == ['c1']
        assert _count('users/conversations', 'hit') == hit_before + 1

        rest = list(iterator)
        assert [s.reference._path[-1] for s in rest] == ['c2', 'c3']
        assert consumed == ['c1', 'c2', 'c3']
        assert _count('users/conversations', 'hit') == hit_before + 3
        # One RunQuery operation was billed for the whole stream.
        assert _count_operations('users/conversations') == ops_before + 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_counts_an_empty_result_as_one_operation():
    # Firestore bills a minimum of one read for an empty query result. The
    # document counter records that minimum as outcome="floor", and the
    # operations counter records the RunQuery. Both must fire even though no
    # snapshot passed through.
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        return iter(())

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        ops_before = _count_operations('users/conversations')
        floor_before = _count('users/conversations', 'floor')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        assert list(Query.stream(query)) == []
        assert _count_operations('users/conversations') == ops_before + 1
        assert _count('users/conversations', 'floor') == floor_before + 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_operation_counted_when_consumer_abandons_stream():
    # A caller that stops iterating early (GeneratorExit) still ran the RPC;
    # the operation must be recorded by the finally block, and cleanup must
    # not raise even when the generator is being torn down.
    import database.firestore_document_probe as probe

    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        def gen():
            yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))
            yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c2')))

        return gen()

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        probe.install_document_read_probe.__globals__['_installed'] = False
        probe.install_document_read_probe()

        ops_before = _count_operations('users/conversations')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        iterator = Query.stream(query)
        next(iterator)
        iterator.close()

        assert _count_operations('users/conversations') == ops_before + 1
    finally:
        setattr(Query, 'stream', original)
        probe.install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_unknown_collection_reduces_to_other():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('brand_new_collection', 'id1')))

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        other_before = _count('other', 'hit')
        query = Query.__new__(Query)
        snapshots = list(Query.stream(query))

        assert len(snapshots) == 1
        assert _count('other', 'hit') == other_before + 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_recording_failure_never_propagates(monkeypatch):
    import database.firestore_document_probe as probe

    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    class _Exploding:
        def labels(self, **kwargs):
            raise RuntimeError('registry unavailable')

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c2')))

    monkeypatch.setattr(probe, 'FIRESTORE_DOCUMENT_READS', _Exploding())
    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        probe.install_document_read_probe.__globals__['_installed'] = False
        probe.install_document_read_probe()

        query = Query.__new__(Query)
        snapshots = list(Query.stream(query))
        assert [s.reference._path[-1] for s in snapshots] == ['c1', 'c2']
    finally:
        setattr(Query, 'stream', original)
        probe.install_document_read_probe.__globals__['_installed'] = False


def test_collection_reference_get_funnels_through_query_stream_without_double_counting():
    # google-cloud-firestore 2.20.0: CollectionReference.get delegates to
    # Query.get, which materialises Query.stream. Wrapping the collection layer
    # too would count each document twice; this pins the funnel shape the probe
    # relies on.
    firestore_collection = pytest.importorskip('google.cloud.firestore_v1.collection')
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    CollectionReference = firestore_collection.CollectionReference
    Query = firestore_query.Query

    snapshots = [
        _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1'))),
        _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c2'))),
    ]

    def fake_stream(self, *args, **kwargs):
        def gen():
            for snapshot in snapshots:
                yield snapshot

        return gen()

    original_stream = Query.stream
    original_get = CollectionReference.get
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        hit_before = _count('users/conversations', 'hit')
        ops_before = _count_operations('users/conversations')

        # The real CollectionReference.get body calls self._query().get() --
        # only the RPC-bound Query.stream needs faking for this funnel check.
        collection = CollectionReference.__new__(CollectionReference)
        collection._path = ('users', 'u1', 'conversations')
        docs = CollectionReference.get(collection)

        assert [d.reference._path[-1] for d in docs] == ['c1', 'c2']
        # Two documents and exactly one operation: no double count.
        assert _count('users/conversations', 'hit') == hit_before + 2
        assert _count_operations('users/conversations') == ops_before + 1
    finally:
        setattr(Query, 'stream', original_stream)
        setattr(CollectionReference, 'get', original_get)
        install_document_read_probe.__globals__['_installed'] = False


class _AggRow:
    def __init__(self, value):
        self.value = value


class _AggCollection:
    def __init__(self, path):
        self._path = path


def _stream_aggregation(matched):
    """Run one aggregation through the probe and return the counted delta."""
    firestore_agg = pytest.importorskip('google.cloud.firestore_v1.aggregation')
    AggregationQuery = firestore_agg.AggregationQuery

    def fake_stream(self, *args, **kwargs):
        yield [_AggRow(matched)]

    original = AggregationQuery.stream
    setattr(AggregationQuery, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        outcome = 'hit' if matched > 0 else 'miss'
        before = _count('users/conversations', outcome)
        query = AggregationQuery.__new__(AggregationQuery)
        query._collection_ref = _AggCollection(('users', 'u1', 'conversations'))
        results = list(AggregationQuery.stream(query))

        assert results[0][0].value == matched
        return _count('users/conversations', outcome) - before
    finally:
        setattr(AggregationQuery, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_aggregation_stream_bills_one_read_per_index_entry_batch():
    # Firestore charges an aggregation one read per batch of up to 1000 index
    # entries, NOT one read per matched document. Counting matched documents
    # would overstate a large count() by up to 1000x and swamp this counter.
    assert _stream_aggregation(4) == 1
    assert _stream_aggregation(1000) == 1
    assert _stream_aggregation(1001) == 2
    assert _stream_aggregation(2_500_000) == 2500


def test_aggregation_stream_matching_nothing_still_bills_one_read():
    assert _stream_aggregation(0) == 1


def test_install_is_idempotent():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    firestore_client = pytest.importorskip('google.cloud.firestore_v1.client')
    firestore_agg = pytest.importorskip('google.cloud.firestore_v1.aggregation')
    Query = firestore_query.Query
    DocumentReference = firestore_document.DocumentReference
    Client = firestore_client.Client
    AggregationQuery = firestore_agg.AggregationQuery
    originals = (
        DocumentReference.get,
        Client.get_all,
        Query.stream,
        AggregationQuery.stream,
    )
    already_wrapped = getattr(Query.stream, '_omi_read_probe', False)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        wrapped = Query.stream
        install_document_read_probe()
        assert Query.stream is wrapped
        assert getattr(Query.stream, '_omi_read_probe', False)
        if not already_wrapped:
            assert Query.stream is not originals[2]
    finally:
        setattr(DocumentReference, 'get', originals[0])
        setattr(Client, 'get_all', originals[1])
        setattr(Query, 'stream', originals[2])
        setattr(AggregationQuery, 'stream', originals[3])
        install_document_read_probe.__globals__['_installed'] = False


def test_tier_series_reconcile_to_collection_totals(monkeypatch):
    from prometheus_client import CollectorRegistry, Counter
    from database import firestore_document_probe as probe

    registry = CollectorRegistry()
    reads = Counter('test_reads', 'reads', ['collection', 'outcome', 'tier'], registry=registry)
    operations = Counter('test_operations', 'operations', ['collection', 'tier'], registry=registry)
    monkeypatch.setattr(probe, 'FIRESTORE_DOCUMENT_READS', reads)
    monkeypatch.setattr(probe, 'FIRESTORE_QUERY_OPERATIONS', operations)
    path = ('users', 'private-uid', 'conversations', 'private-document')
    for label in tier_context.TIER_VALUES:
        tier_context._request_owner.set(tier_context._RequestOwner(tier=label, expires_at=time.monotonic() + 60))
        probe._record(path, True, amount=3)
        probe._record(path, False)
        probe._record_operation(path[:-1])
    samples = [s for m in reads.collect() for s in m.samples if s.name == 'test_reads_total']
    assert sum(s.value for s in samples) == 4 * len(tier_context.TIER_VALUES)
    assert {s.labels['collection'] for s in samples} == {'users/conversations'}
    assert {s.labels['tier'] for s in samples} == tier_context.TIER_VALUES
    assert sum(s.value for m in operations.collect() for s in m.samples if s.name == 'test_operations_total') == len(
        tier_context.TIER_VALUES
    )


def _billed(collection, kind):
    import database.firestore_document_probe as probe

    value = probe.FIRESTORE_BILLED_READS.labels(
        collection=collection, kind=kind, tier=tier_context.current_tier()
    )._value.get()
    return float(value or 0)


def test_collection_pattern_resolves_a_unique_collection_group_parent():
    assert collection_pattern(('memory_items',)) == 'users/memory_items'
    assert collection_pattern(('photos',)) == 'other'
    assert collection_pattern(('memory_items', 'id')) == 'other'


def test_lookup_miss_is_a_not_found_billed_read():
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    DocumentReference = firestore_document.DocumentReference

    def fake_get(self, *args, **kwargs):
        return _Snapshot(exists=False)

    original = DocumentReference.get
    setattr(DocumentReference, 'get', fake_get)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        before_not_found = _billed('users/conversations', 'not_found')
        before_lookup = _billed('users/conversations', 'lookup')
        ref = DocumentReference.__new__(DocumentReference)
        ref._path = ('users', 'u1', 'conversations', 'c1')
        DocumentReference.get(ref)
        assert _billed('users/conversations', 'not_found') == before_not_found + 1
        assert _billed('users/conversations', 'lookup') == before_lookup
    finally:
        setattr(DocumentReference, 'get', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_abandoned_stream_counts_only_documents_already_yielded():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c2')))

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        hit_before = _count('users/conversations', 'hit')
        floor_before = _count('users/conversations', 'floor')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        stream = Query.stream(query)
        next(stream)
        stream.close()
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count('users/conversations', 'floor') == floor_before

        closed = Query.stream(query)
        closed.close()
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count('users/conversations', 'floor') == floor_before + 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_stream_exception_keeps_documents_already_yielded():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))
        raise RuntimeError('read failed')

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        hit_before = _count('users/conversations', 'hit')
        ops_before = _count_operations('users/conversations')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        with pytest.raises(RuntimeError):
            list(Query.stream(query))
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count_operations('users/conversations') == ops_before + 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_offset_bills_skipped_documents():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        hit_before = _count('users/conversations', 'hit')
        floor_before = _count('users/conversations', 'floor')
        billed_before = _billed('users/conversations', 'query')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        query._offset = 10
        assert len(list(Query.stream(query))) == 1
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count('users/conversations', 'floor') == floor_before + 10
        assert _billed('users/conversations', 'query') == billed_before + 11
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_query_stream_names_the_calling_function():
    import database.firestore_document_probe as probe

    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'memory_items', 'm1')))

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'memory_items'))

        def read_memory_items():
            return list(Query.stream(query))

        read_memory_items()
        callers = []
        for metric in probe.FIRESTORE_BILLED_READS_BY_CALLER.collect():
            for sample in metric.samples:
                if not sample.name.endswith('_total'):
                    continue
                if sample.labels.get('collection') != 'users/memory_items':
                    continue
                if sample.labels.get('caller', '').endswith(':read_memory_items') and sample.value > 0:
                    callers.append(sample.labels['caller'])
        assert callers
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def _overflow():
    import database.firestore_document_probe as probe

    return float(probe.FIRESTORE_CALLER_LABEL_OVERFLOW._value.get() or 0)


def test_caller_cardinality_collapses_past_the_cap(monkeypatch):
    import database.firestore_document_probe as probe

    saved = set(probe._known_callers)
    monkeypatch.setattr(probe, 'MAX_CALLERS', 1)
    probe._known_callers.clear()
    before = _overflow()
    try:
        first = probe.bound_caller('database.memories:get_memories')
        second = probe.bound_caller('database.chat:get_messages')
        assert first == 'database.memories:get_memories'
        assert second == 'other'
        assert _overflow() == before + 1
        assert probe.bound_caller('database.memories:get_memories') == 'database.memories:get_memories'
        assert _overflow() == before + 1
        assert probe.bound_caller('not a caller') == 'other'
        assert probe.bound_caller('x' * 97 + ':ok') == 'other'
        assert _overflow() == before + 1
        assert len(probe._known_callers) == 1
    finally:
        probe._known_callers.clear()
        probe._known_callers.update(saved)


def test_call_site_skips_plumbing_frames(monkeypatch):
    import database.firestore_document_probe as probe

    class _Frame:
        def __init__(self, module, name, back):
            self.f_globals = {'__name__': module}
            self.f_code = type('Code', (), {'co_name': name})()
            self.f_back = back

    product = _Frame('database.memories', 'get_memories', None)
    budget = _Frame('utils.other.list_budget', 'materialize_query', product)
    executor = _Frame('utils.executors', 'run_blocking', budget)
    helper = _Frame('database.helpers', 'prepare_for_read', executor)
    boundary = _Frame('database.read_boundary', 'parse_snapshot', helper)
    client = _Frame('database._client', 'delete_collection_recursive', boundary)
    runtime = _Frame('contextlib', '__enter__', client)
    pooled = _Frame('concurrent.futures.thread', '_worker', runtime)
    threaded = _Frame('threading', 'run', pooled)
    loop = _Frame('asyncio.events', '_run', threaded)
    google = _Frame('google.cloud.firestore_v1.query', 'get', loop)
    anonymous = _Frame('database.memories', '<lambda>', google)
    probe_frame = _Frame(probe.__name__, 'stream', anonymous)
    caller = _Frame(probe.__name__, 'call_site', probe_frame)
    monkeypatch.setattr(probe.inspect, 'currentframe', lambda: caller)
    saved = set(probe._known_callers)
    try:
        assert probe.call_site() == 'database.memories:get_memories'
    finally:
        probe._known_callers.clear()
        probe._known_callers.update(saved)


def test_caller_cap_covers_the_measured_read_functions():
    import database.firestore_document_probe as probe

    # 921 functions in backend/database and backend/utils call a Firestore read
    # (scan on 2026-09-23). The cap must sit above that count and stay bounded.
    assert probe.MAX_CALLERS >= 921
    assert probe.MAX_CALLERS <= 4096


def test_caller_cap_holds_under_concurrency(monkeypatch):
    import threading

    import database.firestore_document_probe as probe

    cap = 32
    attempts = 200
    monkeypatch.setattr(probe, 'MAX_CALLERS', cap)
    saved = set(probe._known_callers)
    probe._known_callers.clear()
    before = _overflow()
    barrier = threading.Barrier(attempts)

    def worker(index):
        barrier.wait()
        probe.bound_caller('database.memories:fn_%s' % index)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(attempts)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(probe._known_callers) == cap
        assert _overflow() == before + (attempts - cap)
    finally:
        probe._known_callers.clear()
        probe._known_callers.update(saved)


def test_sum_aggregation_bills_one_read_not_the_value():
    firestore_agg = pytest.importorskip('google.cloud.firestore_v1.aggregation')
    AggregationQuery = firestore_agg.AggregationQuery

    class _SumRow:
        def __init__(self):
            self.value = 5000

    def fake_stream(self, *args, **kwargs):
        yield [_SumRow()]

    original = AggregationQuery.stream
    setattr(AggregationQuery, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        before = _billed('users/conversations', 'query')
        query = AggregationQuery.__new__(AggregationQuery)
        query._collection_ref = _AggCollection(('users', 'u1', 'conversations'))
        query._aggregations = [type('SumAggregation', (), {})()]
        assert len(list(AggregationQuery.stream(query))) == 1
        assert _billed('users/conversations', 'query') == before + 1
    finally:
        setattr(AggregationQuery, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_empty_aggregation_stream_bills_the_minimum():
    firestore_agg = pytest.importorskip('google.cloud.firestore_v1.aggregation')
    AggregationQuery = firestore_agg.AggregationQuery

    def fake_stream(self, *args, **kwargs):
        return iter(())

    original = AggregationQuery.stream
    setattr(AggregationQuery, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        before = _count('users/conversations', 'floor')
        query = AggregationQuery.__new__(AggregationQuery)
        query._collection_ref = _AggCollection(('users', 'u1', 'conversations'))
        assert list(AggregationQuery.stream(query)) == []
        assert _count('users/conversations', 'floor') == before + 1
    finally:
        setattr(AggregationQuery, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_stream_wrapper_delegates_explain_metrics():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    Query = firestore_query.Query

    class _ExplainStream:
        def __init__(self):
            self._items = [_Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))]

        def __iter__(self):
            return self

        def __next__(self):
            if not self._items:
                raise StopIteration
            return self._items.pop(0)

        def get_explain_metrics(self):
            return {'plan': True}

    def fake_stream(self, *args, **kwargs):
        return _ExplainStream()

    original = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        stream = Query.stream(query)
        assert stream.get_explain_metrics() == {'plan': True}
        assert len(list(stream)) == 1
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_list_documents_counts_each_name_and_an_empty_floor():
    firestore_collection = pytest.importorskip('google.cloud.firestore_v1.collection')
    CollectionReference = firestore_collection.CollectionReference

    def fake_list(self, *args, **kwargs):
        yield _Ref(('users', 'u1', 'conversations', 'c1'))
        yield _Ref(('users', 'u1', 'conversations', 'c2'))

    original = CollectionReference.list_documents
    setattr(CollectionReference, 'list_documents', fake_list)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        parent = CollectionReference.__new__(CollectionReference)
        parent._path = ('users', 'u1', 'conversations')
        before = _count('users/conversations', 'hit')
        assert len(list(CollectionReference.list_documents(parent))) == 2
        assert _count('users/conversations', 'hit') == before + 2

        def empty(self, *args, **kwargs):
            return iter(())

        setattr(CollectionReference, 'list_documents', empty)
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        floor_before = _count('users/conversations', 'floor')
        assert list(CollectionReference.list_documents(parent)) == []
        assert _count('users/conversations', 'floor') == floor_before + 1
    finally:
        setattr(CollectionReference, 'list_documents', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_collections_bills_one_read_per_rpc():
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    DocumentReference = firestore_document.DocumentReference

    def fake_collections(self, *args, **kwargs):
        yield type('Col', (), {'id': 'conversations'})()
        yield type('Col', (), {'id': 'memories'})()
        yield type('Col', (), {'id': 'memory_items'})()

    original = DocumentReference.collections
    setattr(DocumentReference, 'collections', fake_collections)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        parent = DocumentReference.__new__(DocumentReference)
        parent._path = ('users', 'u1')
        before = _count('users', 'floor')
        assert len(list(DocumentReference.collections(parent))) == 3
        assert _count('users', 'floor') == before + 1
    finally:
        setattr(DocumentReference, 'collections', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_get_partitions_counts_each_partition():
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    CollectionGroup = firestore_query.CollectionGroup

    def fake_partitions(self, *args, **kwargs):
        yield object()
        yield object()

    original = CollectionGroup.get_partitions
    setattr(CollectionGroup, 'get_partitions', fake_partitions)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        query = CollectionGroup.__new__(CollectionGroup)
        query._parent = _Ref(('memory_items',))
        before = _count('users/memory_items', 'hit')
        assert len(list(CollectionGroup.get_partitions(query))) == 2
        assert _count('users/memory_items', 'hit') == before + 2
    finally:
        setattr(CollectionGroup, 'get_partitions', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_on_snapshot_counts_documents_in_the_callback():
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    DocumentReference = firestore_document.DocumentReference
    seen = []

    def fake_watch(self, callback, *args, **kwargs):
        callback([_Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))], [], None)
        return callback

    original = DocumentReference.on_snapshot
    setattr(DocumentReference, 'on_snapshot', fake_watch)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        ref = DocumentReference.__new__(DocumentReference)
        ref._path = ('users', 'u1', 'conversations', 'c1')
        before = _billed('users/conversations', 'query')

        def user_callback(payload, changes, read_time):
            seen.append(payload)

        DocumentReference.on_snapshot(ref, user_callback)
        assert len(seen) == 1
        assert _billed('users/conversations', 'query') == before + 1
    finally:
        setattr(DocumentReference, 'on_snapshot', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_transaction_get_and_query_get_do_not_double_count():
    firestore_client = pytest.importorskip('google.cloud.firestore_v1.client')
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.query')
    firestore_txn = pytest.importorskip('google.cloud.firestore_v1.transaction')
    Client = firestore_client.Client
    DocumentReference = firestore_document.DocumentReference
    Query = firestore_query.Query
    Transaction = firestore_txn.Transaction

    def fake_get_all(self, references, *args, **kwargs):
        for reference in references:
            yield _Snapshot(exists=False, reference=reference)

    original_get_all = Client.get_all
    setattr(Client, 'get_all', fake_get_all)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        before = _billed('users/conversations', 'not_found')
        txn = Transaction.__new__(Transaction)
        txn._client = Client.__new__(Client)
        ref = DocumentReference.__new__(DocumentReference)
        ref._path = ('users', 'u1', 'conversations', 'c1')
        assert len(list(Transaction.get(txn, ref))) == 1
        assert _billed('users/conversations', 'not_found') == before + 1
    finally:
        setattr(Client, 'get_all', original_get_all)
        install_document_read_probe.__globals__['_installed'] = False

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'conversations', 'c1')))

    original_stream = Query.stream
    setattr(Query, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        hit_before = _count('users/conversations', 'hit')
        ops_before = _count_operations('users/conversations')
        query = Query.__new__(Query)
        query._parent = _Ref(('users', 'u1', 'conversations'))
        query._limit_to_last = False
        docs = Query.get(query)
        assert len(docs) == 1
        assert _count('users/conversations', 'hit') == hit_before + 1
        assert _count_operations('users/conversations') == ops_before + 1
    finally:
        setattr(Query, 'stream', original_stream)
        install_document_read_probe.__globals__['_installed'] = False


def test_vector_query_stream_is_counted_once():
    firestore_vector = pytest.importorskip('google.cloud.firestore_v1.vector_query')
    VectorQuery = firestore_vector.VectorQuery

    def fake_stream(self, *args, **kwargs):
        yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'memory_items', 'm1')))

    original = VectorQuery.stream
    setattr(VectorQuery, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        query = VectorQuery.__new__(VectorQuery)
        query._nested_query = type('Nested', (), {'_parent': _Ref(('users', 'u1', 'memory_items'))})()
        before = _count('users/memory_items', 'hit')
        assert len(list(VectorQuery.stream(query))) == 1
        assert _count('users/memory_items', 'hit') == before + 1
    finally:
        setattr(VectorQuery, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_async_lookup_query_and_aggregation():
    import asyncio

    firestore_document = pytest.importorskip('google.cloud.firestore_v1.async_document')
    firestore_client = pytest.importorskip('google.cloud.firestore_v1.async_client')
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.async_query')
    firestore_agg = pytest.importorskip('google.cloud.firestore_v1.async_aggregation')
    AsyncDocumentReference = firestore_document.AsyncDocumentReference
    AsyncClient = firestore_client.AsyncClient
    AsyncQuery = firestore_query.AsyncQuery
    AsyncAggregationQuery = firestore_agg.AsyncAggregationQuery

    async def fake_get(self, *args, **kwargs):
        return _Snapshot(exists=False)

    def fake_get_all(self, references, *args, **kwargs):
        async def gen():
            for reference in references:
                yield _Snapshot(exists=True, reference=reference)

        return gen()

    def fake_stream(self, *args, **kwargs):
        async def gen():
            if False:
                yield None

        return gen()

    def fake_agg(self, *args, **kwargs):
        async def gen():
            yield [_AggRow(4)]

        return gen()

    originals = (
        AsyncDocumentReference.get,
        AsyncClient.get_all,
        AsyncQuery.stream,
        AsyncAggregationQuery.stream,
    )
    setattr(AsyncDocumentReference, 'get', fake_get)
    setattr(AsyncClient, 'get_all', fake_get_all)
    setattr(AsyncQuery, 'stream', fake_stream)
    setattr(AsyncAggregationQuery, 'stream', fake_agg)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()

        async def exercise():
            ref = AsyncDocumentReference.__new__(AsyncDocumentReference)
            ref._path = ('users', 'u1', 'conversations', 'c1')
            await AsyncDocumentReference.get(ref)
            client = AsyncClient.__new__(AsyncClient)
            docs = [item async for item in AsyncClient.get_all(client, [ref])]
            assert len(docs) == 1
            query = AsyncQuery.__new__(AsyncQuery)
            query._parent = _Ref(('users', 'u1', 'conversations'))
            rows = [item async for item in AsyncQuery.stream(query)]
            assert rows == []
            agg = AsyncAggregationQuery.__new__(AsyncAggregationQuery)
            agg._collection_ref = _AggCollection(('users', 'u1', 'conversations'))
            aggregated = [item async for item in AsyncAggregationQuery.stream(agg)]
            assert len(aggregated) == 1

        miss_before = _billed('users/conversations', 'not_found')
        hit_before = _count('users/conversations', 'hit')
        floor_before = _count('users/conversations', 'floor')
        asyncio.run(exercise())
        assert _billed('users/conversations', 'not_found') == miss_before + 1
        assert _count('users/conversations', 'hit') == hit_before + 2
        assert _count('users/conversations', 'floor') == floor_before + 1
    finally:
        setattr(AsyncDocumentReference, 'get', originals[0])
        setattr(AsyncClient, 'get_all', originals[1])
        setattr(AsyncQuery, 'stream', originals[2])
        setattr(AsyncAggregationQuery, 'stream', originals[3])
        install_document_read_probe.__globals__['_installed'] = False


def test_async_list_documents_collections_and_partitions():
    import asyncio

    firestore_collection = pytest.importorskip('google.cloud.firestore_v1.async_collection')
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.async_document')
    firestore_query = pytest.importorskip('google.cloud.firestore_v1.async_query')
    AsyncCollectionReference = firestore_collection.AsyncCollectionReference
    AsyncDocumentReference = firestore_document.AsyncDocumentReference
    AsyncCollectionGroup = firestore_query.AsyncCollectionGroup

    originals = (
        AsyncCollectionReference.list_documents,
        AsyncDocumentReference.collections,
        AsyncCollectionGroup.get_partitions,
    )

    def fake_list(self, *args, **kwargs):
        async def gen():
            yield _Ref(('users', 'u1', 'conversations', 'c1'))

        return gen()

    def fake_collections(self, *args, **kwargs):
        async def gen():
            yield type('Col', (), {'id': 'memories'})()
            yield type('Col', (), {'id': 'memory_items'})()

        return gen()

    def fake_parts(self, *args, **kwargs):
        async def gen():
            yield object()

        return gen()

    setattr(AsyncCollectionReference, 'list_documents', fake_list)
    setattr(AsyncDocumentReference, 'collections', fake_collections)
    setattr(AsyncCollectionGroup, 'get_partitions', fake_parts)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        names_before = _count('users/conversations', 'hit')
        floor_before = _count('users', 'floor')
        parts_before = _count('users/memory_items', 'hit')

        async def exercise():
            parent = AsyncCollectionReference.__new__(AsyncCollectionReference)
            parent._path = ('users', 'u1', 'conversations')
            names = [item async for item in AsyncCollectionReference.list_documents(parent)]
            assert len(names) == 1
            document = AsyncDocumentReference.__new__(AsyncDocumentReference)
            document._path = ('users', 'u1')
            ids = [item async for item in AsyncDocumentReference.collections(document)]
            assert len(ids) == 2
            group = AsyncCollectionGroup.__new__(AsyncCollectionGroup)
            group._parent = _Ref(('memory_items',))
            parts = [item async for item in AsyncCollectionGroup.get_partitions(group)]
            assert len(parts) == 1

        asyncio.run(exercise())
        assert _count('users/conversations', 'hit') == names_before + 1
        assert _count('users', 'floor') == floor_before + 1
        assert _count('users/memory_items', 'hit') == parts_before + 1
    finally:
        setattr(AsyncCollectionReference, 'list_documents', originals[0])
        setattr(AsyncDocumentReference, 'collections', originals[1])
        setattr(AsyncCollectionGroup, 'get_partitions', originals[2])
        install_document_read_probe.__globals__['_installed'] = False


def test_async_vector_stream_is_counted():
    import asyncio

    firestore_vector = pytest.importorskip('google.cloud.firestore_v1.async_vector_query')
    AsyncVectorQuery = firestore_vector.AsyncVectorQuery

    def fake_stream(self, *args, **kwargs):
        async def gen():
            yield _Snapshot(exists=True, reference=_Ref(('users', 'u1', 'memory_items', 'm1')))

        return gen()

    original = AsyncVectorQuery.stream
    setattr(AsyncVectorQuery, 'stream', fake_stream)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        query = AsyncVectorQuery.__new__(AsyncVectorQuery)
        query._nested_query = type('Nested', (), {'_parent': _Ref(('users', 'u1', 'memory_items'))})()
        before = _count('users/memory_items', 'hit')

        async def pull():
            return [item async for item in AsyncVectorQuery.stream(query)]

        assert len(asyncio.run(pull())) == 1
        assert _count('users/memory_items', 'hit') == before + 1
    finally:
        setattr(AsyncVectorQuery, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_billed_reads_keep_the_request_tier():
    firestore_document = pytest.importorskip('google.cloud.firestore_v1.document')
    DocumentReference = firestore_document.DocumentReference

    def fake_get(self, *args, **kwargs):
        return _Snapshot(exists=True)

    original = DocumentReference.get
    setattr(DocumentReference, 'get', fake_get)
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        before = _billed('users/conversations', 'lookup')
        ref = DocumentReference.__new__(DocumentReference)
        ref._path = ('users', 'u1', 'conversations', 'c1')
        DocumentReference.get(ref)
        assert _billed('users/conversations', 'lookup') == before + 1
        assert tier_context.current_tier() in {'unattributed', 'basic', 'plus'}
    finally:
        setattr(DocumentReference, 'get', original)
        install_document_read_probe.__globals__['_installed'] = False


def test_sdk_read_surface_matches_the_installed_package():
    import importlib
    import inspect

    import database.firestore_document_probe as probe

    install_document_read_probe.__globals__['_installed'] = False
    install_document_read_probe()
    seen = set()
    for qualified, method, sync, coverage in probe.SDK_READ_SURFACE:
        seen.add((qualified, method, sync))
        module_name, _, class_name = qualified.rpartition('.')
        cls = getattr(importlib.import_module(module_name), class_name)
        if coverage == 'absent':
            assert not hasattr(cls, method), qualified
            continue
        fn = getattr(cls, method)
        marked = bool(getattr(fn, '_omi_read_probe', False))
        if coverage == 'wrapped':
            assert marked, '%s.%s is not wrapped' % (qualified, method)
        elif coverage == 'funnel':
            assert not marked, '%s.%s is wrapped and would double-count' % (qualified, method)
            source = inspect.getsource(fn)
            assert 'stream(' in source or 'get_all(' in source or '.get(' in source
        elif coverage == 'unimplemented':
            assert not marked
            assert 'NotImplementedError' in inspect.getsource(fn)
        elif coverage == 'builder':
            assert not marked
        else:
            raise AssertionError(coverage)
        assert sync in ('sync', 'async')
    required = {
        'DocumentReference.get',
        'Client.get_all',
        'Transaction.get',
        'Transaction.get_all',
        'Query.get',
        'Query.stream',
        'CollectionReference.get',
        'CollectionReference.stream',
        'CollectionReference.list_documents',
        'CollectionGroup.get_partitions',
        'AggregationQuery.get',
        'AggregationQuery.stream',
        'VectorQuery.stream',
        'AsyncDocumentReference.get',
        'AsyncClient.get_all',
        'AsyncQuery.stream',
        'AsyncAggregationQuery.stream',
    }
    names = set()
    for qualified, method, _, _ in probe.SDK_READ_SURFACE:
        names.add(qualified.rsplit('.', 1)[-1] + '.' + method)
    assert required <= names
    assert len(seen) == len(probe.SDK_READ_SURFACE)


def test_product_code_does_not_call_on_snapshot():
    import subprocess

    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            'git',
            'grep',
            '-l',
            '-E',
            r'\.on_snapshot\(|\.onSnapshot\(',
            '--',
            'backend',
            'web',
            'app',
            'desktop',
            'plugins',
            'omi',
            ':(exclude)**/tests/**',
            ':(exclude)**/testing/**',
            ':(exclude)**/node_modules/**',
            ':(exclude)**/*.md',
            ':(exclude)backend/database/firestore_document_probe.py',
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    # git grep exits 1 when nothing matches.
    assert result.returncode in (0, 1), result.stderr
    assert result.stdout.strip() == ''
