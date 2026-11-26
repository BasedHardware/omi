from unittest.mock import Mock

import pytest

from database import user_data_deletion as deletion


@pytest.mark.parametrize('case', ['empty', 'clean', 'survivors', 'later_page_failure', 'parent_failure', 'disabled'])
def test_post_root_sweep_coverage(monkeypatch, case):
    if case == 'disabled':
        monkeypatch.setenv('SPEAKER_EVIDENCE_ERASURE_CHECK_ENABLED', 'false')
    else:
        monkeypatch.delenv('SPEAKER_EVIDENCE_ERASURE_CHECK_ENABLED', raising=False)
    plane = Mock()
    owner = plane.collection.return_value.document.return_value
    parents = owner.collection.return_value
    conversations = [] if case == 'empty' else [Mock(), Mock()]
    parents.list_documents.return_value = iter(conversations)
    if case == 'parent_failure':
        parents.list_documents.side_effect = RuntimeError('parent unavailable')
    collections = [conversation.collection.return_value for conversation in conversations]
    deleted = []

    def delete(collection, *, client):
        assert client is plane
        deleted.append(collection)

    def children():
        assert deleted == collections
        if case in ('survivors', 'later_page_failure'):
            yield object()
            if case == 'later_page_failure':
                raise RuntimeError('next page unavailable')

    for collection in collections:
        collection.list_documents.side_effect = children

    metrics = deletion.metrics
    counters = (
        metrics.SWEEP_STARTED,
        metrics.SWEEP_CHECKED,
        metrics.SWEEP_FAILED,
        metrics.SWEEP_DISABLED,
        metrics.REMAINING,
    )
    before = [counter._value.get() for counter in counters]
    failures = {
        'survivors': 'survived account erasure',
        'later_page_failure': 'next page',
        'parent_failure': 'parent unavailable',
    }
    if case in failures:
        with pytest.raises(RuntimeError, match=failures[case]):
            deletion._sweep_speaker_evidence('synthetic', plane, delete)
    else:
        deletion._sweep_speaker_evidence('synthetic', plane, delete)

    expected = {
        'empty': (1, 1, 0, 0, 0),
        'clean': (1, 1, 0, 0, 0),
        'survivors': (1, 1, 0, 0, 2),
        'later_page_failure': (1, 0, 1, 0, 1),
        'parent_failure': (1, 0, 1, 0, 0),
        'disabled': (1, 0, 0, 1, 0),
    }
    assert tuple(counter._value.get() - start for counter, start in zip(counters, before)) == expected[case]
    parents.list_documents.assert_called_once_with()
    if case != 'parent_failure':
        assert deleted == collections
    if case == 'disabled':
        for collection in collections:
            collection.list_documents.assert_not_called()
