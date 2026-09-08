"""The document-read probe must count every lookup and query read, and never break one."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from database.firestore_document_probe import (  # noqa: E402
    FIRESTORE_DOCUMENT_READS,
    collection_pattern,
    install_document_read_probe,
)


def _count(collection: str, outcome: str) -> float:
    value = FIRESTORE_DOCUMENT_READS.labels(collection=collection, outcome=outcome)._value.get()
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
    # These three currently dominate collection="other" on the billed read line.
    # Nested conversation photos must not collapse to users/conversations or other.
    assert collection_pattern(('users', 'uid-abc', 'hourly_usage', '2026-09-01-00')) == 'users/hourly_usage'
    assert collection_pattern(('users', 'uid-abc', 'messages', 'msg-1')) == 'users/messages'
    assert (
        collection_pattern(('users', 'uid-abc', 'conversations', 'conv-1', 'photos', 'photo-1'))
        == 'users/conversations/photos'
    )


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
        query = Query.__new__(Query)
        iterator = Query.stream(query)

        # The underlying generator must not be consumed until the caller pulls.
        assert consumed == []
        assert _count('users/conversations', 'hit') == hit_before

        first = next(iterator)
        assert first.reference._path[-1] == 'c1'
        assert consumed == ['c1']
        assert _count('users/conversations', 'hit') == hit_before + 1

        rest = list(iterator)
        assert [s.reference._path[-1] for s in rest] == ['c2', 'c3']
        assert consumed == ['c1', 'c2', 'c3']
        assert _count('users/conversations', 'hit') == hit_before + 3
    finally:
        setattr(Query, 'stream', original)
        install_document_read_probe.__globals__['_installed'] = False


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
    try:
        install_document_read_probe.__globals__['_installed'] = False
        install_document_read_probe()
        wrapped = Query.stream
        install_document_read_probe()
        assert Query.stream is wrapped
        assert Query.stream is not originals[2]
    finally:
        setattr(DocumentReference, 'get', originals[0])
        setattr(Client, 'get_all', originals[1])
        setattr(Query, 'stream', originals[2])
        setattr(AggregationQuery, 'stream', originals[3])
        install_document_read_probe.__globals__['_installed'] = False
