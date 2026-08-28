"""The document-read probe must count every single-document read, and never break one."""

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
